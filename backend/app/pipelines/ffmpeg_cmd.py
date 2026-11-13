"""GD1 — Bàn điều khiển FFmpeg bằng lời: LLM dịch yêu cầu → lệnh ffmpeg.

Mô hình 2 chặng (tách riêng = an toàn riêng):
  1. DỊCH LỆNH (preview): user gõ tiếng Việt tự nhiên ("cắt từ 2:00 đến 2:10")
     → LLM trả JSON {command, explanation, warnings}. Chưa chạy gì cả — user
     XEM trước lệnh rồi mới bấm "Chạy lệnh này".
  2. CHẠY LỆNH (job type "ffmpeg"): argv đã validate ở preview đi cùng job;
     worker CHẠY LẠI validate (không tin gì đã qua tay mạng) rồi Popen ffmpeg.

AN TOÀN argv — 5 lớp chặn trong `validate_argv`, quyết định KHÔNG shell=True
bao giờ (shlex.split chỉ để tách chuỗi, quotes không sinh ra thực thi):
  1. chỉ binary `ffmpeg`, mỗi arg là chuỗi ≤ 300 ký tự, tối đa 32 arg;
  2. CẤM mọi URL (`://`) — ffmpeg có thể đọc http/ftp/file URL (SSRF +
     đọc file ngoài);
  3. CẤM `..` trong path `/work/…` — mọi I/O ép vào thư mục làm việc;
  4. CẤM `-f <device>` (avdevice/x11grab/dshow/pulse/alsa… — đọc camera/mic
     màn hình máy chủ) và `-` trần (đọc/ghi stdin/stdout);
  5. đúng 1 file NHẬP (`/work/input.<ext>` — tên do SERVER ghi, ext của file
     thật) + 1 file XUẤT (`/work/output.<ext>`, arg CUỐI, ext trong allowlist
     — chọn ext = chọn tính nén thật, giữ ai đó nhét `.sh`/`.so`).

TƯƠNG THÍCH: LLM hay quên `-y` / tự thêm `-progress` — hệ tự chuẩn hóa và
GHI WARNING (người dùng thấy hệ đã can thiệp vào lệnh của họ, không im lặng).

PROGRESS: `ffmpeg -progress pipe:1` in `key=value` mỗi dòng. BẪY đã biết:
`out_time_ms` là MICRO-GIÂY (không phải milli dù tên), quirk của ffmpeg từ
xưa tới nay — test neo bằng fixture để ai đổi cũng thấy đỏ.
"""
from __future__ import annotations

import json
import os
import re
import shlex
import subprocess
from collections.abc import Callable

from .manifest import JobCancelled

# Path "hợp đồng" với LLM — worker thay /work/ → workdir thật khi chạy
# (rewrite ở tasks._run_ffmpeg). Hằng này cũng là CHỮ DẤU để validate phân
# biệt operand input/output với các tham số khác.
INPUT_PREFIX = "/work/input"
OUTPUT_PREFIX = "/work/output"

ALLOWED_OUT_EXTS = ("mp4", "mkv", "webm", "mov", "mp3", "wav", "m4a", "aac",
                    "flac", "ogg", "gif", "png", "jpg")
# `-f` grabber thiết bị: đọc camera/mic/màn hình máy chủ — điều tuyệt đối cấm.
DENY_FORMATS = ("avdevice", "avfoundation", "x11grab", "gdigrab", "fbdev",
                "kmsgrab", "v4l2", "dshow", "pulse", "alsa", "jack", "oss",
                "sndio", "lavfi", "concat")
MAX_ARGV = 32
MAX_ARGS_LEN = 300
FFMPEG_TIMEOUT_S = 7200  # 2h — encode 4K dài cũng đủ; treo phải chết, không ôm mãi

_FFMPEG_BIN = "ffmpeg"


def validate_argv(argv: list[str], input_ext: str) -> tuple[list[str], list[str]]:
    """Kiểm argv từ LLM → (argv sạch, warnings). Lỗi ném ValueError tiếng Việt.

    `input_ext` là phần mở rộng THẬT của file nguồn (server biết qua storage),
    không tin ext LLM chọn — operand input phải là `/work/input.<input_ext>`.
    """
    warnings: list[str] = []
    if not isinstance(argv, list) or not argv:
        raise ValueError("lệnh trống hoặc không phải danh sách tham số")
    if any(not isinstance(a, str) for a in argv):
        raise ValueError("lệnh chứa tham số không phải chuỗi")
    if argv[0] != _FFMPEG_BIN:
        raise ValueError(
            f"chỉ chạy được lệnh «ffmpeg» — nhận được «{argv[0]}»")
    if len(argv) > MAX_ARGV:
        raise ValueError(f"quá nhiều tham số ({len(argv)} > {MAX_ARGV})")
    if any(len(a) > MAX_ARGS_LEN for a in argv):
        raise ValueError(f"có tham số dài hơn {MAX_ARGS_LEN} ký tự — lệnh LLM "
                         "khuyết lạ, dịch lại")

    # chuẩn hoá: bỏ -progress của LLM (server tự thêm), tự chèn -y
    clean = [argv[0]]
    i = 1
    while i < len(argv):
        a = argv[i]
        if a == "-progress":
            warnings.append("bỏ «-progress» do LLM thêm — hệ tự quản tiến độ")
            i += 2
            continue
        if a == "-y":
            clean.append(a)  # giữ nguyên -y có sẵn (không cảnh báo)
            i += 1
            continue
        clean.append(a)
        i += 1
    if "-y" not in clean:
        clean.insert(1, "-y")
        warnings.append("tự thêm «-y» (ghi đè file xuất cũ không hỏi lại)")

    # ---- LỚP AN TOÀN QUÉT TOÀN BỘ lệnh TRƯỚC khi xét hình dạng operand —
    # lỗi "thiếu file nguồn" không được che khuất lỗi nguy hiểm hơn.
    if "://" in " ".join(clean[1:]):
        raise ValueError("lệnh chứa URL — bàn điều khiển chỉ xử lý file hệ "
                         "có, không tải/đọc qua mạng (làm trên link hãy dùng "
                         "mục «Tải video từ link» trước)")
    for a in clean[1:]:
        if a.startswith("/work/") and ".." in a:
            raise ValueError("lệnh chứa «..» — mọi file phải nằm thẳng trong "
                             "thư mục làm việc")
        if a == "-":
            raise ValueError("lệnh dùng «-» (stdin/stdout) — không hỗ trợ")

    input_name = f"{INPUT_PREFIX}.{input_ext}"
    inputs = [a for a in clean if a.startswith(f"{INPUT_PREFIX}.")]
    if inputs != [input_name]:
        if not inputs:
            raise ValueError(
                f"lệnh thiếu file nguồn — phải có «{input_name}»")
        raise ValueError(
            f"file nguồn phải đúng một «{input_name}» (file bạn đã chọn) — "
            f"nhận được: {inputs}")

    # output: CHỈ 1 operand /work/output.*, và nó phải là arg CUỐI
    if len(clean) < 2:
        raise ValueError("lệnh thiếu file xuất")
    outs = [a for a in clean[1:] if a.startswith(f"{OUTPUT_PREFIX}.")]
    if len(outs) > 1:
        raise ValueError("chỉ cho MỘT file xuất (ghép nhiều bước hãy chạy "
                         "nhiều lần với kết quả job trước)")
    out = clean[-1]
    if not out.startswith(f"{OUTPUT_PREFIX}."):
        raise ValueError(
            f"file xuất phải là arg CUỐI dạng «{OUTPUT_PREFIX}.<đuôi>» — "
            f"nhận được «{out}»")
    out_ext = out[len(OUTPUT_PREFIX) + 1:].lower()
    if out_ext not in ALLOWED_OUT_EXTS:
        raise ValueError(
            f"đuôi xuất «.{out_ext}» không hỗ trợ — chọn trong {list(ALLOWED_OUT_EXTS)}")
    # đối chiếu cặp -f: cấm grabber thiết bị
    for k, a in enumerate(clean[1:-1]):
        if a == "-f":
            fmt = clean[k + 2] if k + 2 < len(clean) else ""
            if fmt in DENY_FORMATS:
                raise ValueError(
                    f"định dạng «{fmt}» đọc thiết bị/màn hình máy chủ — bị cấm")
    return clean, warnings


def parse_llm_response(resp: str) -> dict:
    """Trích {command, explanation, warnings} từ chữ LLM (fence/prose chịu được
    — cùng phong cách `_extract_json_object` của translate_batch, nhưng object
    3 key chứ không phải mảng 1 key)."""
    text = (resp or "").strip()
    if text.startswith("```"):
        first_nl = text.find("\n")
        if first_nl != -1:
            body = text[first_nl + 1:]
            end = body.rfind("```")
            text = (body[:end] if end != -1 else body).strip()
    start = text.find("{")
    if start == -1:
        raise ValueError("mô hình không trả về JSON")
    depth, in_str, esc = 0, False, False
    raw = ""
    for i in range(start, len(text)):
        ch = text[i]
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                raw = text[start:i + 1]
                break
    if not raw:
        raise ValueError("JSON của mô hình chưa đóng ngoặc")
    try:
        data = json.loads(raw)
    except ValueError:
        import re as _re
        data = json.loads(_re.sub(r",\s*([}\]])", r"\1", raw))
    if not isinstance(data, dict) or not data.get("command"):
        raise ValueError("JSON thiếu trường «command» (lệnh ffmpeg)")
    return {
        "command": str(data["command"]),
        "explanation": str(data.get("explanation") or "").strip(),
        "warnings": [str(w) for w in (data.get("warnings") or [])][:5],
    }


def command_to_argv(command: str, input_ext: str) -> tuple[list[str], list[str]]:
    """Chuỗi `command` LLM → argv + validate. shlex.split CHỈ tách chuỗi
    (quotes), KHÔNG thực thi — chạy thật là Popen argv-list, không shell."""
    argv = shlex.split(command)
    return validate_argv(argv, input_ext)


def build_prompt() -> tuple[str, str]:
    """(system, hướng dẫn dùng chung) — system từ Prompt hệ thống
    `ffmpeg_cmd` (sửa được trong /admin), hướng dẫn user message dựng cứng
    vì nó là PHẦN GIAO THỨC (path hợp đồng) — không cho sửa làm vỡ hợp đồng."""
    from .. import prompts as P

    system = P.render("ffmpeg_cmd")
    rules = (
        "QUY ƯẮC BẮT BUỘC:\n"
        "- File nguồn: /work/input.<phần_mở_rộng> — chỉ có MỘT file, tên"
        " được hệ thống cung cấp ở dưới, dùng nguyên văn.\n"
        "- File xuất: /work/output.<đuôi> là THAM SỐ CUỐI CÙNG của lệnh.\n"
        "- KHÔNG dùng URL, KHÔNG dùng stdin/stdout (dấu -), KHÔNG dùng -f"
        " kiểu grabber (x11grab/dshow/pulse...).\n"
        "- KHÔNG thêm -progress (hệ tự quản). KHÔNG cần -y (hệ tự thêm).\n"
        "- CHỈ trả JSON, không markdown, không lời dẫn: "
        '{"command":"ffmpeg ...","explanation":"giải thích ngắn gọn tiếng Việt",'
        '"warnings":["cảnh báo nếu có, nếu không thì mảng rỗng"]}'
    )
    return system, rules


def _parse_progress_line(line: str, duration_s: float) -> int | None:
    """Đọc 1 dòng output `-progress pipe:1` → % (0..99) hoặc None.

    BẪY: `out_time_ms` là MICRO-giây (ffmpeg đặt tên sai từ đời trước) —
    out_time=15s in `out_time_ms=15000000`. Hỗ trợ cả `out_time_us` nếu
    ffmpeg tương lai đổi tên cho đúng. `progress=end` → 99 (100留给 done)."""
    line = line.strip()
    if line == "progress=end":
        return 99
    if not line.startswith("out_time_us") and not line.startswith("out_time_ms"):
        return None
    try:
        micros = float(line.split("=", 1)[1])
    except (IndexError, ValueError):
        return None
    out_s = micros / 1_000_000.0
    if duration_s <= 0:
        return None
    return max(0, min(99, round(100.0 * out_s / duration_s)))


FFMPEG_ERROR_MAP: list[tuple[str, str]] = [
    ("permission denied",
     "Không có quyền đọc/ghi file trong thư mục làm việc."),
    ("no such file or directory",
     "File nguồn không tìm thấy — job đã có file chưa? Thử nộp lại file."),
    ("invalid data found when processing input",
     "File hỏng hoặc không phải định dạng bình thường — thử file khác."),
    ("unknown encoder",
     "Bộ mã hóa không có trong bản ffmpeg cài sẵn — chọn đuôi xuất khác "
     "(mp4/mp3/wav là an toàn nhất)."),
    ("output file already exists",
     "File xuất đã có — hệ tự thêm «-y» để ghi đè, lệnh từ mô hình có vẻ sai."),
    ("does not contain any stream",
     "File không có luồng video/âm thanh nào — file trống hoặc hỏng."),
    ("invalid argument",
     "Tham số lệnh không hợp lệ với bản ffmpeg này — dịch lại với mô tả "
     "chi tiết hơn."),
    ("disk i/o error",
     "Ổ đĩa đầy hoặc lỗi đọc ghi — dọn chỗ rồi thử lại."),
    ("conversion failed",
     "ffmpeg không chuyển được giữa các định dạng đã chọn — thử đuôi xuất khác."),
    ("timed out", "Hết giờ — mạng chậm hoặc máy chủ chặn."),
]


def human_error(stderr_text: str) -> str | None:
    """Match substring lowercase trên stderr → message tiếng Việt (style
    download.ERROR_MAP). Trả None = lỗi lạ, caller nhét stderr gốc cắt ngắn."""
    text = (stderr_text or "").lower()
    for pattern, msg in FFMPEG_ERROR_MAP:
        if pattern in text:
            return msg
    return None


def probe_duration(path: str) -> float | None:
    """ffprobe đọc thời lượng (giây) — None khi không đọc được (progress
    coi như không cập nhật, không chết job)."""
    try:
        out = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", path],
            capture_output=True, text=True, timeout=30)
        return float(out.stdout.strip())
    except (OSError, ValueError, subprocess.SubprocessError):
        return None


def run_ffmpeg(argv: list[str], workdir: str, *, duration: float = 0.0,
               progress_cb: Callable[[int, str], None] | None = None,
               abort_check: Callable[[], bool] | None = None,
               runner: Callable[[list[str]], tuple[int, str, str]] | None = None,
               timeout_s: float = FFMPEG_TIMEOUT_S) -> tuple[int, str]:
    """Chạy ffmpeg (argv-list, KHÔNG shell) — trả (code, stderr đuôi 40 dòng).

    - progress: đọc stdout dòng `key=value` (script `progress_cb` giống
      `_record_progress` của tasks).
    - abort: killpg NHÓM tiến trình (ffmpeg tự sinh process con khi dùng
      filter đa luồng — kill từng pid là sót) — import `_kill_group` từ
      download.py, MỘT nguồn duy nhất.
    - timeout: chạy quá `timeout_s` → kill nhóm + RuntimeError (treo phải
      chết có message, không ôm CPU mãi).
    """
    from .download import _kill_group

    if runner is not None:
        code, out, err_tail = runner(argv)
        if abort_check and abort_check():
            raise JobCancelled("hủy trong lúc xử lý")
        if progress_cb is not None:
            # cùng hành vi đường Popen: đọc stdout cho tiến độ (test fake
            # runner vẫn thấy pct như chạy thật)
            for line in (out or "").splitlines():
                pct = _parse_progress_line(line, duration)
                if pct is not None:
                    progress_cb(pct, "Đang xử lý video/âm thanh")
        return code, err_tail

    proc = subprocess.Popen(
        [argv[0], *argv[1:]],  # argv-list — KHÔNG shell=True bao giờ
        cwd=workdir, start_new_session=True,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    err_lines: list[str] = []
    assert proc.stdout is not None and proc.stderr is not None
    import threading

    def _drain_stderr() -> None:
        for line in proc.stderr:  # type: ignore[union-attr]
            line = line.rstrip()
            if line:
                err_lines.append(line)

    t_err = threading.Thread(target=_drain_stderr, daemon=True)
    t_err.start()
    try:
        for line in proc.stdout:
            if progress_cb is not None:
                pct = _parse_progress_line(line, duration)
                if pct is not None:
                    progress_cb(pct, "Đang xử lý video/âm thanh")
            if abort_check and abort_check():
                _kill_group(proc)
                proc.wait(timeout=10)
                raise JobCancelled("hủy trong lúc xử lý — đã dừng ffmpeg")
        code = proc.wait(timeout=timeout_s)
    except subprocess.TimeoutExpired:
        _kill_group(proc)
        proc.wait(timeout=10)
        raise RuntimeError(
            f"ffmpeg chạy quá {int(timeout_s / 60)} phút — đã dừng (video quá "
            "dài hoặc lệnh mãi chưa xong)") from None
    t_err.join(timeout=5)
    return code, "\n".join(err_lines[-40:])


def rewrite_paths(argv: list[str], workdir: str,
                  out_name: str) -> tuple[list[str], str]:
    """Thay path hợp đồng `/work/…` bằng path thật trong `workdir`.

    Trả (argv mới, path xuất tuyệt đối). Chỉ chạm operand ĐÃ qua validate —
    LLM không thể trỏ đâu khác vì validate đã chặn mọi path ngoài `/work/`.
    """
    rewritten = [argv[0]]
    out_path = ""
    for a in argv[1:]:
        if a.startswith(INPUT_PREFIX + "."):
            rewritten.append(os.path.join(workdir, os.path.basename(a)))
        elif a.startswith(OUTPUT_PREFIX + "."):
            out_path = os.path.join(workdir, out_name)
            rewritten.append(out_path)
        else:
            rewritten.append(a)
    return rewritten, out_path


def _selftest() -> None:
    # --- validate: chướng ngại từng lớp
    def bad(argv, ext="mp4", frag=None):
        try:
            validate_argv(argv, ext)
        except ValueError as exc:
            if frag:
                assert frag in str(exc), (argv, str(exc))
            return str(exc)
        raise AssertionError(f"phải chặn: {argv}")

    validate_argv(["ffmpeg", "-ss", "120", "-t", "10",
                   "/work/input.mp4", "/work/output.mp4"], "mp4")
    bad(["ffprobe", "-i", "/work/input.mp4", "/work/output.mp4"], frag="ffmpeg")
    bad(["ffmpeg", "-i", "http://evil/x", "/work/input.mp4", "/work/output.mp4"],
        frag="URL")
    bad(["ffmpeg", "-f", "x11grab", "-i", "/work/input.mp4", "/work/output.mp4"],
        frag="x11grab")
    bad(["ffmpeg", "-i", "/work/../../etc/shadow", "/work/output.mp4"],
        frag="..")
    bad(["ffmpeg", "-i", "-", "/work/output.mp4"], frag="«-»")
    bad(["ffmpeg", "-i", "/work/input.mp4", "/work/output.sh"],
        frag="không hỗ trợ")
    bad(["ffmpeg", "-i", "/work/input.mp4", "-map", "0", "/work/output.mp4",
         "/work/output.mp3"], frag="MỘT file xuất")
    bad(["ffmpeg", "-i", "/work/input.mp4", "/work/output.mp4"], ext="mkv",
        frag="/work/input.mkv")
    bad(["ffmpeg", "-i", "/work/input.mp4", "/work/input.mp4", "/work/output.mp4"],
        frag="file nguồn")
    # chuẩn hoá: -y tự thêm + -progress của LLM bị bỏ
    clean, warn = validate_argv(
        ["ffmpeg", "-progress", "pipe:1", "-i", "/work/input.mp4",
         "/work/output.mp4"], "mp4")
    assert "-y" in clean and "-progress" not in clean, clean
    assert len(warn) == 2, warn
    # có sẵn -y không cảnh báo nữa
    clean2, warn2 = validate_argv(
        ["ffmpeg", "-y", "-i", "/work/input.mp4", "/work/output.mp3"], "mp4")
    assert clean2[1] == "-y" and warn2 == [], (clean2, warn2)
    print("1. validate_argv: 5 lớp chặn + chuẩn hoá ..... OK")

    # --- parse_llm_response: sạch/fence/prose/dấu phẩy/thiếu key
    j = parse_llm_response(
        '{"command":"ffmpeg -i /work/input.mp4 /work/output.mp3",'
        '"explanation":"chuyển mp3","warnings":[]}')
    assert j["command"].startswith("ffmpeg") and j["explanation"], j
    j2 = parse_llm_response("```json\n"
                            '{"command":"ffmpeg -i /work/input.mp4 '
                            '/work/output.mp3","explanation":"x","warnings":[],}\n'
                            "```")
    assert j2["command"], j2
    j3 = parse_llm_response('Người dùng hỏi xong tôi trả: {"command":"ffmpeg -i '
                            '/work/input.mp4 /work/output.wav","explanation":"",'
                            '"warnings":["a","b"]} chúc bạn thành công')
    assert j3["warnings"] == ["a", "b"], j3
    for bad_resp in ["", "không có json", '{"explanation":"thiếu command"}',
                     '{"command":"ffmpeg …"} {"chưa đóng']:
        try:
            parse_llm_response(bad_resp)
        except ValueError:
            pass
        else:
            # dạng cuối TOLERANT (parser lấy object đầu tiên — cùng phong cách
            # translate_batch), ba dạng đầu PHẢI lỗi
            assert bad_resp in ('{"command":"ffmpeg …"} {"chưa đóng',), bad_resp
    print("2. parse_llm_response: 4 dạng bẩn .......... OK")

    # --- command_to_argv: chuỗi → argv + validate
    argv3, _w = command_to_argv(
        "ffmpeg -i '/work/input.mp4' -ss 120 -t 10 /work/output.mp4", "mp4")
    assert argv3[1] == "-y" and argv3[-1] == "/work/output.mp4", argv3
    print("3. command_to_argv (shlex, không shell) ..... OK")

    # --- progress: BẪY micro-giây
    assert _parse_progress_line("out_time_ms=15000000", 30.0) == 50, \
        "out_time_ms=15000000 với video 30s phải là 50%"
    assert _parse_progress_line("out_time_us=5000000", 10.0) == 50
    assert _parse_progress_line("progress=end", 30.0) == 99
    assert _parse_progress_line("frame=120", 30.0) is None
    assert _parse_progress_line("out_time_ms=abc", 30.0) is None
    assert _parse_progress_line("out_time_ms=0", 0.0) is None
    print("4. _parse_progress_line (out_time_ms=µs) .... OK")

    # --- run_ffmpeg với runner fake (không đụng ffmpeg thật)
    def fake_runner(_argv):
        return (0, "out_time_ms=1000000\nprogress=end", "")

    pcts: list[int] = []
    code, tail = run_ffmpeg(["ffmpeg", "-y", "/work/in"], "/tmp",
                            duration=10.0, progress_cb=lambda p, m: pcts.append(p),
                            runner=fake_runner)
    assert code == 0 and pcts and tail == "", (code, pcts, tail)

    # --- human_error
    assert human_error("ffmpeg: ERROR — Permission denied") == \
        FFMPEG_ERROR_MAP[0][1]
    assert human_error("unknown weirdness") is None
    print("5. run_ffmpeg runner fake + human_error ..... OK")

    # --- rewrite_paths
    rw, out_path = rewrite_paths(
        ["ffmpeg", "-y", "-i", "/work/input.mp4", "/work/output.mp4"],
        "/media/jobs/j1/work", "output.mp4")
    assert rw[3] == "/media/jobs/j1/work/input.mp4", rw
    assert out_path == "/media/jobs/j1/work/output.mp4", rw
    print("6. rewrite_paths vào workdir thật .......... OK")

    print("FFMPEG CMD SELFTEST PASSED")


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        _selftest()
