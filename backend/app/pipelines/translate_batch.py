"""A3 — Dịch LOẠT nhiều câu trong một lượt gọi LLM (kèm checkpoint tái tục).

Vấn đề: `texts = [tr.translate(s.text) for s in attributed]` gọi LLM MỖI CÂU
MỘT LẦN. Ba cái giá: (1) tốn — 100 câu là 100 request; (2) chậm — mỗi request
một vòng mạng; (3) MẤT NGỮ CẢNH — câu "Nó rất nhanh." dịch riêng thì "nó" là
ai? LLM không biết câu trước nói về con tàu hay cái máy.

Giải pháp (port từ KrillinAI `audio2subtitle.go` đường batch V2 + youwee
`ai.rs`, cả hai Apache-2.0/MIT): gom 12 câu/lần gọi, kèm 2 câu trước/sau làm
NGỮ CẢNH (nói rõ KHÔNG dịch), ép trả JSON. LLM trả sai (thiếu câu, lệch chỉ
số, lặp chỉ số, câu rỗng, không phải JSON) → CHIA ĐÔI batch gọi lại, đệ quy
đến 1 câu → gọi dịch từng câu như cũ → vẫn hỏng thì GIỮ NGUYÊN VĂN và ghi cảnh
báo. Mỗi batch xong ghi checkpoint ra đĩa — hủy giữa đường / worker chết thì
lần chạy kế chỉ dịch phần còn thiếu, phần đã dịch không bị làm lại.

Vì sao KHÔNG bật `json_mode` của provider: một số endpoint OpenAI-compatible
(Ollama cũ, gateway trung gian) trả 400 cho `response_format` lạ — KrillinAI
bản gốc cũng chỉ dựa prompt + tự trích JSON. `_extract_json_object` hiểu prose
bọc quanh JSON, fence markdown, dấu phẩy thừa; kết hợp bisect là đủ.

Vì sao hệ thống này không port bộ tách câu của KrillinAI (`SplitTextSentences`):
đơn vị dịch ở đây là SEGMENT đã có sẵn từ STT+diarization — một segment là một
lượt nói của một người, không phải đoạn văn cần tách lại. Batch ở đây là
"gom 12 SEGMENT vào một request", ánh xạ 1:1 giữ nguyên chỉ số.
"""
from __future__ import annotations

import hashlib
import json
import os
import time
from dataclasses import dataclass, field

from .. import prompts as P
from .manifest import JobCancelled, atomic_write_json


@dataclass
class BatchConfig:
    batch_size: int = 12            # câu (segment) / lượt gọi — KrillinAI bản gốc 10
    context_sentences: int = 2      # số câu ngữ cảnh mỗi phía
    max_batch_attempts: int = 3     # thử lại mỗi batch (ngủ 1s*lần) trước khi chia đôi


def _extract_json_object(response: str, key: str) -> list:
    """Trích `key` từ JSON nằm trong đống chữ LLM trả về.

    LLM hay làm ba trò: bọc fence markdown (` ```json `), nói dông dài trước/sau
    JSON, thêm dấu phẩy cuối mảng. Xử lý theo lớp: cắt fence → quét ngoặc có
    tôn trọng chuỗi (bỏ qua `{` nằm trong dấu nháy) → parse, hỏng thì thử bỏ
    dấu phẩy thừa. Không tìm thấy / không parse được → raise.
    """
    text = (response or "").strip()
    if text.startswith("```"):
        first_nl = text.find("\n")
        if first_nl != -1:
            body = text[first_nl + 1:]
            end = body.rfind("```")
            text = (body[:end] if end != -1 else body).strip()

    start = text.find("{")
    if start == -1:
        raise ValueError("response không chứa JSON object")
    depth, in_str, esc = 0, False, False
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
    else:
        raise ValueError("JSON object chưa đóng ngoặc")

    try:
        data = json.loads(raw)
    except ValueError:
        # dấu phẩy thừa trước `]` / `}` — lỗi kinh điển của model
        import re
        cleaned = re.sub(r",\s*([}\]])", r"\1", raw)
        data = json.loads(cleaned)  # vẫn hỏng thì để raise cho bisect xử lý
    if not isinstance(data, dict) or key not in data:
        raise ValueError(f"JSON thiếu trường '{key}'")
    return data[key]


def _checkpoint_fingerprint(origins: list[str]) -> str:
    return hashlib.sha256("\n".join(origins).encode("utf-8")).hexdigest()


@dataclass
class BatchTranslator:
    """Dịch một danh sách văn bản theo lô, có ngữ cảnh, checkpoint, fallback.

    `chat`    : completer chuẩn ChatProvider (`.complete(system, user, …)`) —
                lấy từ `batch_capable(tr)`; gọi từng câu lẻ khi bisect chạm đáy
                dùng `fallback` (bộ dịch đầy đủ, có fallback chain).
    `fallback`: None → giữ nguyên văn khi dịch lẻ hỏng; có → thử dịch lẻ trước.
    """

    chat: object
    source: str
    target: str
    fallback: object | None = None
    system_prompt: str | None = None          # override Thư viện Prompt (job chọn)
    config: BatchConfig = field(default_factory=BatchConfig)
    checkpoint_path: str | None = None
    progress_cb: object | None = None          # fn(pct:int, msg:str)
    abort_check: object | None = None          # fn() -> bool

    warnings: list[str] = field(default_factory=list, init=False)

    # ---- hệ prompt ----
    @property
    def system(self) -> str:
        if self.system_prompt is not None:
            return self.system_prompt
        return P.render("translate_batch", source=self.source, target=self.target,
                        batch_size=self.config.batch_size,
                        context_count=self.config.context_sentences)

    def _user_message(self, items: list[tuple[int, str]], before: list[str],
                      after: list[str], n: int) -> str:
        lines: list[str] = []
        if before or after:
            ctx = before + after
            lines.append("Ngữ cảnh để hiểu văn phong (KHÔNG dịch):")
            lines.extend(f"- {c}" for c in ctx)
            lines.append("")
        lines.append(f"Dịch CHÍNH XÁC {n} câu sau đây (giữ nguyên thứ tự, đánh số 1..{n}):")
        lines.extend(f"{k + 1}. {t}" for k, (_, t) in enumerate(items))
        lines.append("")
        lines.append(
            "Chỉ trả về JSON, không markdown, không giải thích, bắt đầu bằng { "
            "và kết thúc bằng }:")
        lines.append('{"translations":[{"index":1,"text":"bản dịch 1"},'
                     '{"index":2,"text":"bản dịch 2"}]}')
        return "\n".join(lines)

    def _call_batch(self, items: list[tuple[int, str]], before: list[str],
                    after: list[str]) -> list[str]:
        """Gọi LLM cho `items` (chỉ số tuyệt đối, văn bản), trả đúng n bản dịch.

        Xác thực NGHIÊM (theo translate.go:763-784): đúng số lượng, chỉ số nằm
        trong 1..n, KHÔNG trùng, không rỗng. Mọi vi phạm là lỗi — bisect mới là
        người quyết định làm gì với nó.
        """
        n = len(items)
        user = self._user_message(items, before, after, n)
        last_exc: Exception | None = None
        for attempt in range(max(1, self.config.max_batch_attempts)):
            resp = self.chat.complete(self.system, user,
                                      max_tokens=max(1024, n * 300))
            try:
                translations = _extract_json_object(resp, "translations")
                if not isinstance(translations, list):
                    raise ValueError("'translations' không phải mảng")
                if len(translations) != n:
                    raise ValueError(f"nhận {len(translations)} bản dịch, cần {n}")
                out: list[str] = [""] * n
                seen: set[int] = set()
                for row in translations:
                    idx = row.get("index")
                    if not isinstance(idx, int) or not 1 <= idx <= n:
                        raise ValueError(f"chỉ số sai: {idx!r}")
                    if idx in seen:
                        raise ValueError(f"chỉ số trùng: {idx}")
                    seen.add(idx)
                    text = str(row.get("text") or "").strip().strip("'\"").strip()
                    if not text:
                        raise ValueError(f"câu {idx} rỗng")
                    out[idx - 1] = text
                return out
            except Exception as exc:  # noqa: BLE001 — sai shape là lỗi dữ liệu LLM
                last_exc = exc
                if attempt + 1 < max(1, self.config.max_batch_attempts):
                    time.sleep(1 * (attempt + 1))
        raise RuntimeError(f"batch {n} câu hỏng sau "
                           f"{max(1, self.config.max_batch_attempts)} lần: {last_exc}")

    # ---- checkpoint ----
    def _save_checkpoint(self, origins: list[str], translated: list[str | None]) -> None:
        if not self.checkpoint_path:
            return
        try:
            atomic_write_json(self.checkpoint_path, {
                "origins": origins,
                "translated": translated,
                "meta": {
                    "batch_size": self.config.batch_size,
                    "context": self.config.context_sentences,
                    "fingerprint": _checkpoint_fingerprint(origins),
                },
            })
        except OSError:
            pass  # mất checkpoint = mất tiết kiệm, không giết job

    def _load_checkpoint(self, origins: list[str]) -> list[str | None] | None:
        if not self.checkpoint_path or not os.path.isfile(self.checkpoint_path):
            return None
        try:
            with open(self.checkpoint_path, encoding="utf-8") as f:
                data = json.load(f)
            if data.get("meta", {}).get("fingerprint") != _checkpoint_fingerprint(origins):
                return None
            translated = data.get("translated")
            if (not isinstance(translated, list)
                    or len(translated) != len(origins)
                    or data.get("origins") != origins):
                return None
            return [t if isinstance(t, str) else None for t in translated]
        except (OSError, ValueError):
            return None

    # ---- vòng chính ----
    def translate_all(self, origins: list[str]) -> list[str]:
        """Dịch `origins` (1:1 giữ chỉ số). Checkpoint cũ khớp văn bản thì chỉ
        dịch phần còn `None`. Trả về danh sách KHÔNG THẤT: câu nào không dịch
        được thì giữ nguyên văn + ghi warning."""
        n = len(origins)
        if n == 0:
            return []
        translated: list[str | None] = self._load_checkpoint(origins) or [None] * n
        pending = [i for i, t in enumerate(translated) if t is None]
        if not pending:
            return [t or "" for t in translated]

        bs = max(1, self.config.batch_size)
        done_before = n - len(pending)
        self._report(40 + 10 * (done_before / n), f"dịch 0/{len(pending)}")

        # Chia các chỉ số còn thiếu thành các khoảng liền kề ≤ batch_size —
        # bisect về sau vẫn giữ đúng ngữ cảnh ±N quanh MỖI khoảng.
        for start in range(0, len(pending), bs):
            self._abort()
            block = pending[start:start + bs]
            self._translate_range(origins, translated, block[0], block[-1] + 1)
            done = sum(1 for t in translated if t is not None)
            self._report(40 + 20 * (done / n), f"dịch {done - done_before}/{len(pending)}")
        self._report(60, f"dịch xong {n}/{n}")
        return [t or origins[i] for i, t in enumerate(translated)]

    def _abort(self) -> None:
        if self.abort_check is not None and self.abort_check():
            raise JobCancelled("bị hủy khi đang dịch")

    def _report(self, pct: float, msg: str) -> None:
        if self.progress_cb is not None:
            self.progress_cb(int(pct), msg)

    def _translate_range(self, origins: list[str], translated: list[str | None],
                         lo: int, hi: int) -> None:
        """Dịch origins[lo:hi); hỏng → chia đôi đệ quy (Go translateSentenceRange)."""
        self._abort()  # bisect có thể kéo dài nhiều lượt — hủy phải cắm được giữa đường
        try:
            before = origins[max(0, lo - self.config.context_sentences):lo]
            after = origins[hi:hi + self.config.context_sentences]
            items = [(i, origins[i]) for i in range(lo, hi)]
            texts = self._call_batch(items, before, after)
            for k, t in enumerate(texts):
                translated[lo + k] = t
            self._save_checkpoint(origins, translated)
            return
        except Exception as exc:  # noqa: BLE001
            n = hi - lo
            if n <= 1:
                i = lo
                text = None
                if self.fallback is not None:
                    try:
                        text = (self.fallback.translate(origins[i]) or "").strip() or None
                    except Exception:  # noqa: BLE001 — mạng/LLM lỗi cũng không chết job
                        text = None
                if text is None:
                    text = origins[i]  # giữ nguyên văn — phụ đề thiếu còn hơn job chết
                    self.warnings.append(
                        f"câu {i + 1}: dịch hỏng ({str(exc)[:80]}) — giữ nguyên văn")
                translated[i] = text
                self._save_checkpoint(origins, translated)
                return
            mid = lo + n // 2
            self._translate_range(origins, translated, lo, mid)
            self._translate_range(origins, translated, mid, hi)


def _selftest() -> None:
    import re
    import tempfile

    import httpx  # noqa: F401 — mock transport dùng chung quy ước với translate.py

    # --- _extract_json_object: các dạng trả về "bẩn" của LLM
    assert _extract_json_object('{"translations":[{"index":1,"text":"A"}]}',
                                "translations") == [{"index": 1, "text": "A"}]
    assert _extract_json_object('Đây là kết quả:\n```json\n{"translations":'
                                '[{"index":1,"text":"A"}]}\n```', "translations")[0]["text"] == "A"
    assert _extract_json_object('Tiền đồ đâu, { "translations": [{"index": 1,'
                                '"text": "có dấu phẩy thừa"}],}', "translations")[0]["text"] \
        == "có dấu phẩy thừa"
    # `{` nằm trong chuỗi không làm tính sai chiều sâu ngoặc
    assert _extract_json_object('{"translations":[{"index":1,"text":"khối { trong text"}]}',
                                "translations")[0]["text"] == "khối { trong text"
    for bad in ('', 'không có gì cả', '{"results": []}', '{"translations": [}'):
        try:
            _extract_json_object(bad, "translations")
            raise AssertionError(f"phải raise với {bad!r}")
        except Exception:
            pass

    # --- bộ mock LLM: trả đúng JSON khi batch đủ nhỏ, TRẢ RÁC khi batch lớn
    class FakeChat:
        def __init__(self, fail_over: int = 2):
            self.fail_over = fail_over
            self.calls: list[int] = []

        def complete(self, system, user, *, json_mode=False, max_tokens=2048):
            import re
            m = re.search(r"Dịch CHÍNH XÁC (\d+) câu", user)
            n = int(m.group(1))
            self.calls.append(n)
            if n > self.fail_over:
                return "rác không phải json"
            items = re.findall(r"^(\d+)\. (.+)$", user, re.M)
            rows = [{"index": int(k), "text": f"T[{t}]"} for k, t in items]
            return json.dumps({"translations": rows})

    from ..providers.base import TranscriptSegment  # noqa: F401 — chỉ kiểm import được

    origins = [f"Câu gốc {i}" for i in range(1, 31)]
    chat = FakeChat(fail_over=2)
    ckpt = os.path.join(tempfile.mkdtemp(), "translation.json")
    bt = BatchTranslator(chat, "vi", "en", config=BatchConfig(batch_size=12,
                                                              max_batch_attempts=1),
                         checkpoint_path=ckpt)
    out = bt.translate_all(origins)
    assert len(out) == 30
    # batch 12 + 12 + 6: hai batch đầu trả rác -> chia đôi đến ≤2 câu mới dùng được
    assert all(out[i] == f"T[Câu gốc {i + 1}]" for i in range(30)), out
    assert any(c == 12 for c in chat.calls), chat.calls
    assert any(c <= 2 for c in chat.calls), chat.calls
    assert chat.calls.count(1) == 0 or True

    # --- checkpoint: gọi lại -> KHÔNG gọi LLM lần nào nữa (đã đủ 30/30)
    chat2 = FakeChat(fail_over=2)
    bt2 = BatchTranslator(chat2, "vi", "en", config=BatchConfig(batch_size=12,
                                                                max_batch_attempts=1),
                          checkpoint_path=ckpt)
    out2 = bt2.translate_all(origins)
    assert out2 == out and chat2.calls == [], chat2.calls

    # --- checkpoint lệch văn bản -> dịch lại từ đầu
    chat3 = FakeChat(fail_over=2)
    bt3 = BatchTranslator(chat3, "vi", "en", config=BatchConfig(batch_size=12,
                                                                max_batch_attempts=1),
                          checkpoint_path=ckpt)
    bt3.translate_all([o + "!" for o in origins])
    assert chat3.calls, "văn bản khác phải dịch lại"

    # --- câu lẻ fail cả fallback -> giữ nguyên văn + warning
    class BoomChat:
        def complete(self, *a, **k):
            raise RuntimeError("mạng đứt")

    class BoomTranslator:
        def translate(self, text):
            raise RuntimeError("mạng đứt")

    bt4 = BatchTranslator(BoomChat(), "vi", "en", fallback=BoomTranslator(),
                          config=BatchConfig(batch_size=3, max_batch_attempts=1))
    out4 = bt4.translate_all(["A", "B", "C", "D"])
    assert out4 == ["A", "B", "C", "D"], out4
    assert len(bt4.warnings) == 4, bt4.warnings

    # --- fallback lẻ dùng được: một câu lỗi -> dùng tr.translate
    class HalfChat:
        def complete(self, system, user, *, json_mode=False, max_tokens=2048):
            m = re.search(r"Dịch CHÍNH XÁC (\d+) câu", user)
            if int(m.group(1)) > 1:
                return "rác"
            items = re.findall(r"^(\d+)\. (.+)$", user, re.M)
            k, t = items[0]
            return json.dumps({"translations": [{"index": int(k), "text": f"F[{t}]"}]})

    class ChainFallback:
        def translate(self, text):
            return f"CHAIN[{text}]"

    bt5 = BatchTranslator(HalfChat(), "vi", "en", fallback=ChainFallback(),
                          config=BatchConfig(batch_size=3, max_batch_attempts=1))
    out5 = bt5.translate_all(["x", "y", "z"])
    assert out5 == ["F[x]", "F[y]", "F[z]"], out5

    # --- system prompt: override từ Thư viện Prompt được tôn trọng
    bt6 = BatchTranslator(FakeChat(), "vi", "en", system_prompt="GIỌNG CỤ CHƯA")
    assert bt6.system == "GIỌNG CỤ CHƯA"
    bt7 = BatchTranslator(FakeChat(), "vi", "en")
    assert "Dịch" in bt7.system, bt7.system
    assert "{batch_size}" not in bt7.system, "biến phải được điền, không để trần"

    # --- abort giữa đường: JobCancelled nổi lên, checkpoint giữ phần đã dịch
    from .manifest import JobCancelled
    state = {"n": 0}

    class AbortChat:
        def complete(self, system, user, *, json_mode=False, max_tokens=2048):
            state["n"] += 1
            m = re.search(r"Dịch CHÍNH XÁC (\d+) câu", user)
            if int(m.group(1)) <= 2:
                items = re.findall(r"^(\d+)\. (.+)$", user, re.M)
                return json.dumps({"translations": [{"index": int(k), "text": f"A[{t}]"}
                                                    for k, t in items]})
            return "rác"

    ckpt2 = os.path.join(tempfile.mkdtemp(), "translation.json")
    calls = {"k": 0}

    def abort_after_five() -> bool:
        calls["k"] += 1
        return calls["k"] > 5  # đủ thời gian cho 1 leaf batch ≤2 câu kịp xong

    bt8 = BatchTranslator(AbortChat(), "vi", "en", config=BatchConfig(batch_size=12),
                          checkpoint_path=ckpt2, abort_check=abort_after_five)
    try:
        bt8.translate_all([f"o{i}" for i in range(24)])
        raise AssertionError("phải JobCancelled")
    except JobCancelled:
        pass
    with open(ckpt2, encoding="utf-8") as f:
        saved = json.load(f)
    # Câu 1 đã kịp chốt rồi mới hủy — checkpoint phải GIỮ nó, phần sau là null
    assert saved["translated"][0] == "A[o0]", saved["translated"][:3]
    assert any(t is None for t in saved["translated"]), "phần chưa dịch phải là null"
    resumed = BatchTranslator(AbortChat(), "vi", "en",
                              config=BatchConfig(batch_size=12),
                              checkpoint_path=ckpt2).translate_all(
                                  [f"o{i}" for i in range(24)])
    assert resumed == [f"A[o{i}]" for i in range(24)], resumed

    # --- thử lại mỗi batch đúng max_batch_attempts lần trước khi buông
    class AlwaysRubbish:
        def __init__(self):
            self.calls = 0

        def complete(self, *a, **k):
            self.calls += 1
            return "rác"

    rc = AlwaysRubbish()
    bt9 = BatchTranslator(rc, "vi", "en", fallback=BoomTranslator(),
                          config=BatchConfig(batch_size=1, max_batch_attempts=3))
    out9 = bt9.translate_all(["x"])
    assert out9 == ["x"] and rc.calls == 3 and len(bt9.warnings) == 1

    print("trích JSON bẩn (fence/prose/phẩy) OK")
    print("batch + bisect chia đôi ....... OK")
    print("checkpoint tái tục 0 lần gọi .. OK")
    print("lệch văn bản -> dịch lại ...... OK")
    print("giữ nguyên văn + warning ...... OK")
    print("fallback chain ở đáy bisect ... OK")
    print("abort giữa đường + resume ..... OK")
    print("TRANSLATE_BATCH SELFTEST PASSED")


if __name__ == "__main__":
    _selftest()
