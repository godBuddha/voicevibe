"""A1 — Sổ tay công đoạn (stage manifest) cho job lồng tiếng.

Vấn đề: `dub_audio` trước đây chạy một mạch trong thư mục tạm /tmp — job hỏng
giữa đường (mạng LLM đứt, hủy giữa chừng, worker bị kill) là làm lại TỪ ĐẦU:
nghe lại cả giờ audio, dịch lại tất cả, đọc lại tất cả. Với video dài đó là cả
giờ GPU + tiền LLM bỏ đi.

Giải pháp (port từ KrillinAI `internal/pipeline/manifest.go`, Apache-2.0): mỗi
job có một THƯ MỤC LÀM VIỆC BỀN `MEDIA_ROOT/jobs/{job_id}/work/` và một file
`manifest.json` ghi trạng thái từng công đoạn (chuẩn bị → nghe → dịch → đọc →
căn → trộn → đóng gói). Công đoạn nào xong rồi, chạy lại thì bỏ qua — giống nấu
bữa tiệc nhiều món: món nào chín rồi thì không nấu lại.

Hai quy tắc làm cho sổ tay ĐÁNG TIN (KrillinAI học được từ thực chiến):
  1. **Ghi nguyên tử** (temp → fsync → đổi tên → fsync thư mục): mất điện giữa
     chừng không bao giờ để lại file sổ tay nửa vời — hoặc cũ hoàn chỉnh, hoặc
     không có gì.
  2. **Cờ ok phải có file thật đi kèm**: worker bị `revoke(terminate=True)` kill
     cứng thì `finally` không chạy, cờ có thể ghi trước khi file kịp ghi xong.
     Nên "công đoạn xong" = cờ ok VÀ mọi file output của nó tồn tại, kích thước
     > 0. Không bao giờ tin cờ một mình.

Vân tay tham số (params fingerprint): đổi ngôn ngữ / giọng đọc / tốc độ / mode
nhạc nền giữa hai lần chạy → kết quả cũ trộn lẫn cấu hình mới ra video "không
thuộc ai". Nên lệch vân tay = bỏ sổ cũ (đổi tên `.stale`), chạy lại sạch, và
ghi chú `resume=drift-full-rerun` vào job để người dùng thấy lý do.

Tệp này KHÔNG import DB — cả tasks.py lẫn dub_pipeline.py đều import nó,
import qua lại sẽ thành vòng.
"""
from __future__ import annotations

import hashlib
import json
import os
import tempfile
import time
from typing import Any

MANIFEST_NAME = "manifest.json"

# Thứ tự công đoạn job dub — mỗi tên khớp một khối trong dub_audio.
STAGES = ("prepare", "stt", "translate", "tts", "fit", "mix", "mux")

SCHEMA_VERSION = 1


def read_outputs(workdir: str) -> dict:
    """Đọc `outputs` từ sổ tay của workdir — accessor nhẹ cho caller.

    B4b: tasks._run_dub cần biết key phụ đề song ngữ (`subs_key`) sau khi
    dub_audio trả về — đọc file sổ tay trực tiếp thay vì bắt dub_audio trả
    thêm giá trị (signature của nó là contract của smoke scripts).
    Sổ không đọc được / không có → {} (thông tin phụ không được giết job).
    """
    path = os.path.join(workdir, MANIFEST_NAME)
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return data.get("outputs") or {}
    except (OSError, ValueError):
        return {}


class JobCancelled(Exception):
    """Job bị hủy giữa đường.

    Nâng riêng (không trộn vào Exception chung) để tasks.py bắt đúng trường hợp
    này: giữ status=cancelled (đã đặt ở chỗ hủy), ghi lời nhắc "chạy lại để tiếp
    tục" — KHÔNG đánh dấu failed. _set_failed vốn đã từ chối ghi đè cancelled,
    đây là lớp giữ an toàn thứ hai cho thông điệp.
    """


def work_dir(job_id: str, media_root: str | None = None) -> str:
    """Thư mục làm việc bền của một job: MEDIA_ROOT/jobs/{job_id}/work.

    Vì sao nằm dưới MEDIA_ROOT mà không phải /tmp: container compose chạy
    read_only, chỗ ghi bền duy nhất là volume media (chia sẻ giữa api và
    worker); tmpfs /tmp chết cùng container — cache resume ở đó vô nghĩa sau
    `docker compose restart`. Cùng tiền tố `jobs/{job_id}/` với kết quả job nên
    dọn dẹp một phát là sạch, và gate quyền `_owns_media` mặc khẳng không ai đọc
    được file làm việc này (khớp không key nào).

    Nếu MEDIA_ROOT không tạo được (đĩa đầy, quyền sai) → rơi về thư mục tạm:
    job vẫn chạy như cũ, chỉ là không có resume — giảm dần mà không chết.
    """
    root = media_root or os.getenv("MEDIA_ROOT") or "./media"
    path = os.path.join(root, "jobs", job_id, "work")
    try:
        os.makedirs(path, exist_ok=True)
        return path
    except OSError:
        return tempfile.mkdtemp(prefix=f"vv_work_{job_id}_")


def atomic_write_json(path: str, payload: Any) -> None:
    """Ghi JSON nguyên tử: temp cùng thư mục → fsync → đổi tên → fsync thư mục.

    os.replace là nguyên tử trên cùng một filesystem — người đọc (lần chạy kế
    tiếp) hoặc thấy file cũ hoàn chỉnh, hoặc thấy file mới hoàn chỉnh, không
    bao giờ nửa vời. fsync thư mục bảo đảm kết quả đổi tên sống qua mất điện.
    """
    directory = os.path.dirname(os.path.abspath(path)) or "."
    os.makedirs(directory, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=os.path.basename(path) + ".",
                               suffix=".tmp", dir=directory)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
            f.write("\n")
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
        dir_fd = os.open(directory, os.O_RDONLY)
        try:
            os.fsync(dir_fd)
        finally:
            os.close(dir_fd)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def _canonical(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, default=str)


def params_fingerprint(params: dict, backend_tag: str) -> str:
    """sha256 của các tham số ẢNH HƯỞNG KẾT QUẢ job dub.

    Chỉ lấy những key làm đổi chất lượng output (ngôn ngữ, giọng, nhạc nền, tốc
    độ, prompt...). Thêm key vô hại (webhook_url, limit...) vào đây sẽ khiến job
    bị làm lại oan khi user chỉ sửa webhook — nên giữ danh sách tối thiểu.
    `backend_tag` nhận diện bộ dịch (tên class + model): đổi provider/model giữa
    hai lần chạy thì bản dịch cũ là của model khác — tái dùng lẫn lộn hai văn
    phong trong một video là lỗi chất lượng, không phải tiết kiệm.
    """
    voices = params.get("speaker_voices") or {}
    material = {
        "source_lang": params.get("source_lang"),
        "target_lang": params.get("target_lang"),
        "speaker_voices": sorted((k, v) for k, v in voices.items()),
        "background_mode": params.get("background_mode") or "silence",
        "max_speed": params.get("max_speed"),
        "retranslate_rounds": params.get("retranslate_rounds"),
        "mux_video": params.get("mux_video"),
        "batch_size": params.get("batch_size"),
        "context_sentences": params.get("context_sentences"),
        "prompt_id": params.get("prompt_id"),
        "media_url": params.get("media_url"),
        # B1/B2 — dán link: file tải về luôn có TÊN CỐ ĐỊNH (source.{ext}), nên
        # media_url không phân biệt được hai lần chạy khác link. Ba key này là
        # vân tay THẬT của nguồn đầu vào — thiếu là tái dùng nhầm sổ tay.
        "source_url": params.get("source_url"),
        "quality": params.get("quality"),
        "sub_source": params.get("sub_source"),
        # B5 — backend giọng đọc (local/edge/cloud): đổi backend là đổi CHẤT
        # LƯỢNG GIỌNG — tái dùng audio của backend khác là lẫn hai giọng.
        "tts_backend": params.get("tts_backend"),
        "backend_tag": backend_tag,
    }
    return hashlib.sha256(_canonical(material).encode("utf-8")).hexdigest()


class Manifest:
    """Sổ tay trạng thái công đoạn của một job (file JSON trong workdir)."""

    def __init__(self, path: str, data: dict):
        self.path = path
        self.data = data

    # ---- hai thuộc tính tiện dụng, khớp schema JSON ----
    @property
    def stages(self) -> dict:
        return self.data.setdefault("stages", {})

    @property
    def outputs(self) -> dict:
        return self.data.setdefault("outputs", {})

    @property
    def warnings(self) -> list[str]:
        return self.data.setdefault("warnings", [])

    # ---- vòng đời ----
    @classmethod
    def create(cls, workdir: str, job_id: str, params_fp: str,
               job_type: str = "dub") -> "Manifest":
        m = cls(os.path.join(workdir, MANIFEST_NAME), {
            "v": SCHEMA_VERSION,
            "job_id": job_id,
            "job_type": job_type,
            "params_fp": params_fp,
            "updated_at": int(time.time()),
            "stages": {},
            "outputs": {},
            "warnings": [],
        })
        m.save()
        return m

    @classmethod
    def load_or_none(cls, workdir: str, params_fp: str) -> "Manifest | None":
        """Đọc sổ tay nếu CÒN DÙNG ĐƯỢC; lệch vân tay → đổi tên `.stale` rồi None.

        Mọi dạng "không tin được" (thiếu file, JSON hỏng, sai schema, lệch vân
        tay) đều trả None — caller chạy lại từ đầu. Không bao giờ raise: resume
        là nâng cấp, không phải điều kiện để job chạy.
        """
        path = os.path.join(workdir, MANIFEST_NAME)
        if not os.path.isfile(path):
            return None
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, ValueError):
            return None
        if not isinstance(data, dict) or data.get("v") != SCHEMA_VERSION:
            return None
        if data.get("params_fp") != params_fp:
            # Lệch cấu hình — sổ cũ mô tả một job khác. Cất riêng để soi lỗi
            # (không xoá: forensics), rồi chạy lại sạch.
            try:
                os.replace(path, path + ".stale")
            except OSError:
                pass
            return None
        # Khởi tạo dict thiếu (file cũ hơn schema nhỏ — tương thích tiến).
        data.setdefault("stages", {})
        data.setdefault("outputs", {})
        data.setdefault("warnings", [])
        return cls(path, data)

    def save(self) -> None:
        self.data["updated_at"] = int(time.time())
        try:
            atomic_write_json(self.path, self.data)
        except OSError:
            # Ghi sổ thất bại KHÔNG được giết job — mất resume là mất tiết kiệm,
            # không phải mất kết quả. Đĩa đầy là trường hợp thật, không hiếm.
            pass

    # ---- truy vấn / ghi trạng thái ----
    def stage_ok(self, name: str, *files: str) -> bool:
        """Công đoạn `name` xong thật chưa: cờ ok VÀ mọi file output còn nguyên.

        File tính theo đường dẫn TƯƠNG ĐỐI với thư mục chứa manifest. Kích thước
        > 0 vì ffmpeg bị kill có thể để lại file rỗng — tồn tại mà rỗng là chưa
        xong.
        """
        entry = self.stages.get(name)
        if not entry or not entry.get("ok"):
            return False
        base = os.path.dirname(os.path.abspath(self.path))
        for rel in files:
            p = os.path.join(base, rel)
            try:
                if os.path.getsize(p) <= 0:
                    return False
            except OSError:
                return False
        return True

    def mark(self, name: str, *, error: str | None = None) -> None:
        self.stages[name] = {"ok": error is None, "error": error,
                             "updated_at": int(time.time())}
        self.save()

    def note(self, warning: str) -> None:
        """Thêm cảnh báo (không trùng) — hiện ở job params cho người dùng thấy."""
        if warning and warning not in self.warnings:
            self.warnings.append(warning)
            self.save()

    def stale_names(self) -> list[str]:
        """Tên file output cũ còn sót sau khi vân tay đổi (`.stale`) — không dùng
        trong pipeline, để test soi."""
        base = os.path.dirname(os.path.abspath(self.path))
        try:
            return sorted(n for n in os.listdir(base) if n.endswith(".stale"))
        except OSError:
            return []


def _selftest() -> None:
    import tempfile

    with tempfile.TemporaryDirectory() as wd:
        fp = params_fingerprint({"source_lang": "vi", "target_lang": "en",
                                 "speaker_voices": {"*": "Mai Anh"},
                                 "max_speed": 1.35}, "CloudChat:m1")
        m = Manifest.create(wd, "job123", fp)
        assert m.stages == {} and m.outputs == {} and m.warnings == []

        # vân tay ổn định: cùng tham số = cùng chuỗi
        fp2 = params_fingerprint({"speaker_voices": {"*": "Mai Anh"},
                                  "max_speed": 1.35, "source_lang": "vi",
                                  "target_lang": "en"}, "CloudChat:m1")
        assert fp2 == fp
        # khác vân tay khi đổi mọi tham số ảnh hưởng
        assert params_fingerprint({"source_lang": "vi", "target_lang": "en",
                                   "max_speed": 1.2}, "CloudChat:m1") != fp
        assert params_fingerprint({"source_lang": "vi", "target_lang": "en",
                                   "max_speed": 1.35}, "CloudChat:m2") != fp

        # mark + stage_ok (có file / thiếu file / file rỗng)
        with open(os.path.join(wd, "src16k.wav"), "wb") as f:
            f.write(b"data")
        m.mark("prepare")
        assert m.stage_ok("prepare", "src16k.wav")
        assert not m.stage_ok("prepare", "src16k.wav", "missing.wav")
        m.mark("stt", error="all 2 provider(s) failed")
        assert not m.stage_ok("stt")
        assert m.stages["stt"]["error"] == "all 2 provider(s) failed"
        with open(os.path.join(wd, "empty.wav"), "wb"):
            pass
        m.mark("tts")
        assert not m.stage_ok("tts", "empty.wav")

        # warning không trùng
        m.note("bed_mode=fallback")
        m.note("bed_mode=fallback")
        assert m.warnings == ["bed_mode=fallback"]

        # round-trip: save -> load_or_none trả đúng dữ liệu
        m2 = Manifest.load_or_none(wd, fp)
        assert m2 is not None and m2.stage_ok("prepare", "src16k.wav")
        assert m2.stages["stt"]["error"] == "all 2 provider(s) failed"

        # JSON hỏng -> None, không raise
        with open(os.path.join(wd, MANIFEST_NAME), "w") as f:
            f.write("{không phải json")
        assert Manifest.load_or_none(wd, fp) is None

        # sai schema version -> None
        atomic_write_json(os.path.join(wd, MANIFEST_NAME), {"v": 99, "params_fp": fp})
        assert Manifest.load_or_none(wd, fp) is None

        # lệch vân tay -> None + cất .stale
        atomic_write_json(os.path.join(wd, MANIFEST_NAME), {"v": 1, "params_fp": "khác"})
        assert Manifest.load_or_none(wd, fp) is None
        assert m.stale_names() == [MANIFEST_NAME + ".stale"], m.stale_names()

        # work_dir: tạo dưới root chỉ định; MEDIA_ROOT không ghi được -> tmpdir
        root = os.path.join(wd, "media")
        w = work_dir("jobabc", media_root=root)
        assert w == os.path.join(root, "jobs", "jobabc", "work") and os.path.isdir(w)
        fake_root = os.path.join(wd, "không-tồn-tại-và-không-tạo-được", "x")
        os.makedirs(fake_root)
        os.chmod(fake_root, 0o500)  # chỉ đọc
        try:
            w2 = work_dir("jobabc", media_root=fake_root)
            assert w2.startswith(tempfile.gettempdir()), w2
        finally:
            os.chmod(fake_root, 0o700)

        # atomic_write_json: dữ liệu Unicode giữ nguyên + file temp dọn sạch
        p = os.path.join(wd, "t.json")
        atomic_write_json(p, {"text": "Tiếng Việt có dấu — mọi thứ nguyên vẹn"})
        with open(p, encoding="utf-8") as f:
            assert json.load(f)["text"] == "Tiếng Việt có dấu — mọi thứ nguyên vẹn"
        leftovers = [n for n in os.listdir(wd) if n.endswith(".tmp")]
        assert leftovers == [], leftovers

    print("round-trip + vân tay ........ OK")
    print("stage_ok (cờ + file thật) .... OK")
    print("JSON hỏng / lệch schema ...... OK")
    print("lệch vân tay -> .stale ....... OK")
    print("work_dir fallback tmpdir ..... OK")
    print("ghi nguyên tử, không rác tmp . OK")
    print("MANIFEST SELFTEST PASSED")


if __name__ == "__main__":
    _selftest()
