"""A3 guards — dịch batch (translate_batch): tách câu/JSON/validation/bisect.

Run:  cd backend && PYTHONPATH=. python tests/test_translate_batch.py
"""
from __future__ import annotations

import json
import os
import pathlib
import sys
import tempfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from app.pipelines.manifest import JobCancelled  # noqa: E402
from app.pipelines.translate_batch import (  # noqa: E402
    BatchConfig, BatchTranslator, _extract_json_object)


def _num_user(text: str) -> int:
    import re
    m = re.search(r"Dịch CHÍNH XÁC (\d+) câu", text)
    return int(m.group(1)) if m else 0


class EchoChat:
    """LLM giả: trả đúng schema (n nhỏ), rác (n lớn). Ghi lại mọi message."""

    def __init__(self, fail_over: int = 2):
        self.fail_over = fail_over
        self.calls: list[tuple[int, str]] = []

    def complete(self, system, user, *, json_mode=False, max_tokens=2048):
        n = _num_user(user)
        self.calls.append((n, user))  # ghi USER message — ngữ cảnh nằm ở đây
        if n > self.fail_over:
            return "rác hoàn toàn"
        import re
        items = re.findall(r"^(\d+)\. (.+)$", user, re.M)
        return json.dumps({"translations": [{"index": int(k), "text": f"T[{t}]"}
                                            for k, t in items]})


ORIGINS = [f"Câu gốc {i}" for i in range(1, 13)]

# --- 1. trích JSON các dạng bẩn
assert _extract_json_object('{"translations":[{"index":1,"text":"A"}]}',
                            "translations")[0]["text"] == "A"
assert _extract_json_object('```json\n{"translations":[{"index":1,"text":"A"}]}\n```',
                            "translations")[0]["text"] == "A"
assert _extract_json_object('Kết quả: {"translations":[{"index":1,"text":"B"}],}',
                            "translations")[0]["text"] == "B"
try:
    _extract_json_object('không có json', "translations")
    raise AssertionError("phải raise")
except Exception:
    pass
print("1. trích JSON (fence/prose/phẩy thừa) ....... OK")

# --- 2. batch + bisect: 12 câu, batch fail >2 → bisect xuống ≤2
chat = EchoChat(fail_over=2)
ck = os.path.join(tempfile.mkdtemp(), "t.json")
bt = BatchTranslator(chat, "vi", "en", config=BatchConfig(batch_size=12,
                                                          max_batch_attempts=1),
                     checkpoint_path=ck)
out = bt.translate_all(ORIGINS)
assert out == [f"T[Câu gốc {i}]" for i in range(1, 13)], out
assert any(n == 12 for n, _ in chat.calls), "phải thử batch 12 trước"
# bisect 12 → 6,6 → 3,3 → 1,2: không được xuất hiện mảnh 4/5/7+ (chia đôi phải
# đúng quy tắc), và mọi lá cuối đều ≤ 2 (EchoChat chấp nhận ≤2)
sizes = {n for n, _ in chat.calls}
assert sizes == {12, 6, 3, 1, 2}, sizes
print("2. batch 12 + bisect chia đôi ................ OK")

# --- 3. ngữ cảnh: user message có 2 câu trước/sau + KHÔNG dịch chúng
chat2 = EchoChat(fail_over=99)
bt2 = BatchTranslator(chat2, "vi", "en", config=BatchConfig(batch_size=4,
                                                            context_sentences=2),
                      checkpoint_path=os.path.join(tempfile.mkdtemp(), "t2.json"))
bt2.translate_all(ORIGINS)
first_big = next(u for n, u in chat2.calls if n == 4)
assert "Ngữ cảnh để hiểu văn phong (KHÔNG dịch)" in first_big
assert "Câu gốc 1" in first_big and "Câu gốc 5" in first_big  # ±2 quanh item 3-4
assert "Câu gốc 8" not in first_big, "ngữ cảnh không được lọt quá phạm vi"
print("3. ngữ cảnh ±2 (đúng phạm vi) ................ OK")

# --- 4. checkpoint tái tục: gọi lại = 0 lượt LLM
chat3 = EchoChat(fail_over=99)
bt3 = BatchTranslator(chat3, "vi", "en", config=BatchConfig(batch_size=4),
                      checkpoint_path=ck)
assert bt3.translate_all(ORIGINS) == out
assert chat3.calls == [], "checkpoint phải ăn — không gọi LLM lại"
# lệch văn bản → dịch lại từ đầu
bt4 = BatchTranslator(EchoChat(), "vi", "en", config=BatchConfig(batch_size=4),
                      checkpoint_path=ck)
bt4.translate_all([o + "!" for o in ORIGINS])
print("4. checkpoint tái tục / lệch văn bản ......... OK")

# --- 5. đáy bisect: fallback translate; hỏng cả fallback → giữ nguyên + warning
class Boom:
    def complete(self, *a, **k):
        raise RuntimeError("mạng đứt")


class BoomTr:
    def translate(self, text):
        raise RuntimeError("mạng đứt")


bt5 = BatchTranslator(Boom(), "vi", "en", fallback=BoomTr(),
                      config=BatchConfig(batch_size=3, max_batch_attempts=1))
out5 = bt5.translate_all(["x", "y"])
assert out5 == ["x", "y"] and len(bt5.warnings) == 2, (out5, bt5.warnings)
print("5. đáy bisect: nguyên văn + warning .......... OK")

# --- 6. hệ prompt: override Thư viện Prompt; mặc định điền biến
bt6 = BatchTranslator(EchoChat(), "vi", "en", system_prompt="GIỌNG RIÊNG")
assert bt6.system == "GIỌNG RIÊNG"
assert "Dịch" in BatchTranslator(EchoChat(), "vi", "en").system
print("6. prompt override + mặc định ................ OK")

# --- 7. abort giữa đường: JobCancelled + checkpoint giữ phần đã chốt
state = {"n": 0}


class AbortChat:
    def complete(self, system, user, *, json_mode=False, max_tokens=2048):
        state["n"] += 1
        import re
        items = re.findall(r"^(\d+)\. (.+)$", user, re.M)
        return json.dumps({"translations": [{"index": int(k), "text": f"A[{t}]"}
                                            for k, t in items]})


ck2 = os.path.join(tempfile.mkdtemp(), "t3.json")
tick = {"k": 0}


def abort_after_3() -> bool:
    tick["k"] += 1
    return tick["k"] > 3


bt7 = BatchTranslator(AbortChat(), "vi", "en", config=BatchConfig(batch_size=2),
                      checkpoint_path=ck2, abort_check=abort_after_3)
try:
    bt7.translate_all([f"o{i}" for i in range(10)])
    raise AssertionError("phải JobCancelled")
except JobCancelled:
    pass
saved = json.load(open(ck2))
assert saved["translated"][0] == "A[o0]", saved["translated"][:3]
assert any(t is None for t in saved["translated"])
resumed = BatchTranslator(AbortChat(), "vi", "en",
                          config=BatchConfig(batch_size=2),
                          checkpoint_path=ck2).translate_all(
                              [f"o{i}" for i in range(10)])
assert resumed == [f"A[o{i}]" for i in range(10)]
print("7. abort giữa đường + resume ................. OK")

print("TRANSLATE BATCH GUARDS PASSED")
