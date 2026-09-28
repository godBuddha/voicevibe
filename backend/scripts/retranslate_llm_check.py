"""Kiểm chứng vòng lặp re-translate với LLM THẬT (OpenRouter).

Vì sao cần: test đơn vị dùng translator giả nên chỉ chứng minh *logic* của vòng
lặp. Trên box GPU, bản dịch chạy bằng Marian local — mà Marian KHÔNG có
`retranslate_shorter`, nên vòng lặp đúng đắn bỏ qua và không có gì được kiểm
chứng thật. Script này gọi một LLM thật để trả lời câu hỏi: model có thực sự trả
về câu ngắn hơn, và `_retranslate_pass` có nhận nó không?

Chỉ gọi 1-2 lần API, nội dung là câu mẫu tổng hợp (không phải dữ liệu người dùng).

Chạy:
  OPENROUTER_KEY=sk-or-... python backend/scripts/retranslate_llm_check.py
"""
from __future__ import annotations

import os
import pathlib
import struct
import sys
import tempfile
import wave

sys.path.insert(0, str(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from app.pipelines.dub_pipeline import _retranslate_pass, build_plan  # noqa: E402
from app.pipelines.translate import CloudChatTranslator  # noqa: E402
from app.providers.base import TranscriptSegment  # noqa: E402

KEY = os.environ.get("OPENROUTER_KEY")
if not KEY:
    print("thiếu OPENROUTER_KEY — bỏ qua")
    sys.exit(0)

BASE = os.environ.get("OPENROUTER_BASE", "https://openrouter.ai/api/v1")
MODEL = os.environ.get("OPENROUTER_MODEL", "openai/gpt-4o-mini")

# Câu tiếng Việt dài, dịch sang tiếng Anh chắc chắn vượt slot 1.6 giây.
SRC = "Hôm nay chúng ta sẽ thử nghiệm toàn bộ hệ thống dịch và lồng tiếng tự động"
SLOT = 1.6
TMP = tempfile.mkdtemp(prefix="yv_rtllm_")


def wav_bytes(seconds: float, sr: int = 16000) -> bytes:
    import io

    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(struct.pack("<h", 0) * int(sr * seconds))
    return buf.getvalue()


class FakeTTS:
    """Giả lập TTS: độ dài tỉ lệ số ký tự (14 ký tự/giây, sát giọng đọc thật)."""

    cps = 14.0
    calls: list[str] = []

    def synthesize(self, text: str, voice=None) -> bytes:
        self.calls.append(text)
        return wav_bytes(max(0.3, len(text) / self.cps))


print(f"model: {MODEL}")
tr = CloudChatTranslator(BASE, KEY, MODEL, "vi", "en")

full = tr.translate(SRC).strip()
print(f"\n1. dịch đầy đủ : {full!r} ({len(full)} ký tự)")

tts = FakeTTS()
dur = len(full) / tts.cps
att = [TranscriptSegment(0.0, SLOT, SRC, "SPEAKER_00")]
texts = [full]
durs = [dur]
plan = build_plan(att, texts, durs)
assert plan[0].needs_shorter_text, (
    f"câu dịch phải vượt slot {SLOT}s để phép kiểm có nghĩa (gen={dur:.1f}s)")
print(f"   tổng hợp giả: {dur:.1f}s > slot {SLOT}s -> cần bản ngắn hơn")

budget = max(8, int((len(full) / dur) * SLOT * 0.95))
print(f"\n2. gọi retranslate_shorter(max_chars={budget}) …")
short = tr.retranslate_shorter(full, budget).strip()
print(f"   -> {short!r} ({len(short)} ký tự)")

assert short, "model trả về rỗng"

# KHÔNG khẳng định `len(short) <= budget`. Đã chạy thật và model VƯỢT ngân sách:
# xin ≤21 ký tự, trả về 45. Đây chính là lý do `_retranslate_pass` đo trên AUDIO
# tổng hợp chứ không tin độ dài chuỗi — nếu tin, bản "ngắn hơn" này (45 ký tự so
# với 71) vẫn có thể nói ra dài hơn slot và bị đọc méo.
if len(short) > budget:
    print(f"   (!) model VƯỢT ngân sách: {len(short)} > {budget} — "
          "đúng như dự phòng, nên phải đo trên audio")

# Qua đúng vòng lặp của pipeline, không chỉ gọi hàm.
n = _retranslate_pass(tr, plan, texts, durs, ["/tmp/x.wav"], [""], tts, TMP, 1)
print(f"\n3. _retranslate_pass nhận: {n} đoạn")
assert n == 1, f"vòng lặp phải nhận bản ngắn hơn, nhận {n}"
# KHÔNG khẳng định `texts[0] == short`. `_retranslate_pass` gọi model LẦN NỮA, và
# LLM không tất định (temperature 0.2) — lần trước đã hỏng đúng vì so bằng nhau.
# Khẳng định BẤT BIẾN mới đúng: bản mới khác, ngắn hơn về ký tự, và audio ngắn hơn.
print(f"   -> {texts[0]!r} ({len(texts[0])} ký tự) [khác lời gọi ở bước 2 "
      "— model không tất định]")
assert texts[0].strip(), "không được để rỗng"
assert texts[0] != full, "phải là bản dịch mới"
assert len(texts[0]) < len(full), (len(texts[0]), len(full))
assert durs[0] < dur, (durs[0], dur)

plan2 = build_plan(att, texts, durs)
print(f"   sau khi thay: {durs[0]:.1f}s, cờ needs_shorter_text = "
      f"{plan2[0].needs_shorter_text}, speed = {plan2[0].speed:.2f}")
print(f"   (trước: {dur:.1f}s, speed bị ép = {plan[0].speed:.2f})")

print("\nLLM RE-TRANSLATE CHECK PASSED")