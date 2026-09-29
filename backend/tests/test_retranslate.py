"""Guard cho vòng lặp re-translate khi đoạn dịch không vừa thời lượng.

Bối cảnh: `plan_timing` chỉ GẮN CỜ `needs_shorter_text`; trước đây cách duy nhất
để khớp là ép `atempo` tới `max_speed` (1.35) — ở tốc độ đó giọng méo rõ. Bản dịch
ngắn hơn cho kết quả tự nhiên hơn hẳn.

Test chạy hoàn toàn offline: translator giả và TTS giả, không cần GPU/LLM. Nhờ vậy
kiểm được cả những ca khó tạo ra bằng model thật (model trả về dài hơn, model lỗi,
TTS lỗi).

Điểm mấu chốt được ghim ở đây:
  1. Đoạn vừa thời lượng thì KHÔNG gọi re-translate (không tốn lượt LLM vô ích)
  2. Bản ngắn hơn và **nói ra ngắn hơn** -> được nhận, cờ được xoá
  3. Chuỗi ngắn hơn nhưng **nói ra DÀI hơn** -> KHÔNG nhận (đo trên audio, không
     tin độ dài chuỗi)
  4. Model trả về dài hơn -> không nhận, và vòng lặp DỪNG (không gọi mãi)
  5. Translator không có `retranslate_shorter` (Marian local) -> bỏ qua êm, không lỗi
  6. Lỗi mạng/LLM -> không giết job
  7. Ngân sách ký tự tính từ tốc độ nói THẬT của bản dịch hiện tại

Run:  cd backend && PYTHONPATH=. python tests/test_retranslate.py
"""
from __future__ import annotations

import os
import pathlib
import struct
import sys
import tempfile
import wave

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from app.pipelines.dub_pipeline import build_plan  # noqa: E402
from app.pipelines.dub_pipeline import _retranslate_pass  # noqa: E402
from app.providers.base import TranscriptSegment  # noqa: E402

TMP = tempfile.mkdtemp(prefix="vv_rt_")


def wav_bytes(seconds: float, sr: int = 16000) -> bytes:
    """WAV im lặng đúng độ dài — để TTS giả điều khiển `gen_duration` chính xác."""
    import io

    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(struct.pack("<h", 0) * int(sr * seconds))
    return buf.getvalue()


class FakeTTS:
    """TTS giả: độ dài audio tỉ lệ với số ký tự (theo `chars_per_sec` cho trước).

    `override` cho phép ép một chuỗi cụ thể ra độ dài bất kỳ — cần cho ca "chuỗi
    ngắn hơn nhưng nói ra dài hơn".
    """

    def __init__(self, chars_per_sec: float = 12.0, override: dict | None = None):
        self.cps = chars_per_sec
        self.override = override or {}
        self.calls: list[str] = []

    def synthesize(self, text: str, voice=None) -> bytes:
        self.calls.append(text)
        dur = self.override.get(text)
        if dur is None:
            dur = max(0.2, len(text) / self.cps)
        return wav_bytes(dur)


class FakeTranslator:
    """Translator giả có `retranslate_shorter`, ghi lại các lời gọi."""

    def __init__(self, mapping: dict[str, str] | None = None, boom: bool = False):
        self.mapping = mapping or {}
        self.boom = boom
        self.asked: list[tuple[str, int]] = []

    def retranslate_shorter(self, text: str, max_chars: int) -> str:
        self.asked.append((text, max_chars))
        if self.boom:
            raise RuntimeError("LLM không truy cập được")
        return self.mapping.get(text, text[:max_chars])


class NoRetranslateTranslator:
    """Như LocalMarianTranslator: chỉ có `translate`, không có bản ngắn hơn."""

    def translate(self, text: str) -> str:
        return text


LONG = "This is a very long translated sentence that will never fit the slot"
FITS = "Short line"


def make_plan(texts, durations, segs):
    att = [TranscriptSegment(s, e, t, "SPEAKER_00") for (s, e), t in zip(segs, texts)]
    return att, build_plan(att, texts, durations)


# --------------------------------------------- 1. đoạn vừa slot -> không gọi
segs = [(0.0, 5.0)]
texts = [FITS]
att, plan = make_plan(texts, [2.0], segs)
tr, tts = FakeTranslator(), FakeTTS()
assert not any(s.needs_shorter_text for s in plan)
n = _retranslate_pass(tr, plan, texts, [2.0], ["/tmp/a.wav"], [""], tts, TMP, 1)
assert n == 0 and tr.asked == [], "đoạn vừa slot không được gọi re-translate"
print("đoạn vừa slot -> không gọi LLM ......... OK")

# ------------------------------- 2. đoạn vượt -> xin bản ngắn hơn, ĐO audio
segs = [(0.0, 2.0)]
texts = [LONG]
SHORT = "A short line"
tts = FakeTTS()
durs = [len(LONG) / tts.cps]                    # ~5.5s -> vượt slot 2.0s
att, plan = make_plan(texts, durs, segs)
assert plan[0].needs_shorter_text is True, plan[0]
tr = FakeTranslator({LONG: SHORT})
wavs = [os.path.join(TMP, "seg0.wav")]
open(wavs[0], "wb").write(tts.synthesize(LONG))
# Chụp lại TRƯỚC khi gọi — `durs` bị hàm sửa tại chỗ, đọc sau sẽ ra giá trị mới
# và phép so sánh thành vô nghĩa (đã viết sai đúng như vậy ở lần đầu).
orig_dur = durs[0]
n = _retranslate_pass(tr, plan, texts, durs, wavs, [""], tts, TMP, 1)
assert n == 1, n
assert texts[0] == SHORT, texts[0]
assert tr.asked and tr.asked[0][0] == LONG
# ngân sách ký tự phải xuất phát từ tốc độ nói thật: cps * slot * 0.95
expect = int((len(LONG) / orig_dur) * 2.0 * 0.95)
assert tr.asked[0][1] == expect, (tr.asked[0][1], expect)
# và độ dài audio đã được cập nhật theo bản mới
assert durs[0] < orig_dur, (durs[0], orig_dur)
# plan dựng lại -> hết cờ
att2, plan2 = make_plan(texts, durs, segs)
assert not any(s.needs_shorter_text for s in plan2), plan2
print("đoạn vượt -> nhận bản ngắn hơn ......... OK")

# ---------------------- 3. chuỗi ngắn hơn nhưng NÓI RA dài hơn -> không nhận
texts = [LONG]
tts = FakeTTS(override={SHORT: 9.0})            # câu ngắn mà nói tận 9 giây
durs = [len(LONG) / tts.cps]
att, plan = make_plan(texts, durs, segs)
tr = FakeTranslator({LONG: SHORT})
n = _retranslate_pass(tr, plan, texts, durs, ["/tmp/x.wav"], [""], tts, TMP, 1)
assert n == 0, "chuỗi ngắn hơn nhưng audio dài hơn thì KHÔNG được nhận"
assert texts[0] == LONG, texts[0]
print("chuỗi ngắn nhưng audio dài -> từ chối .. OK")

# ----------------------------- 4. model trả về dài hơn -> không nhận, không lặp
texts = [LONG]
tts = FakeTTS()
durs = [len(LONG) / tts.cps]
att, plan = make_plan(texts, durs, segs)
tr = FakeTranslator({LONG: LONG + " and even longer than before"})
n = _retranslate_pass(tr, plan, texts, durs, ["/tmp/x.wav"], [""], tts, TMP, 1)
assert n == 0 and texts[0] == LONG
print("model trả dài hơn -> không nhận ....... OK")

# --------------------------------- 5. translator không hỗ trợ -> bỏ qua êm
texts = [LONG]
tts = FakeTTS()
durs = [len(LONG) / tts.cps]
att, plan = make_plan(texts, durs, segs)
n = _retranslate_pass(NoRetranslateTranslator(), plan, texts, durs,
                      ["/tmp/x.wav"], [""], tts, TMP, 1)
assert n == 0 and texts[0] == LONG, "Marian local không có đường này, phải bỏ qua"
print("translator không hỗ trợ -> bỏ qua ..... OK")

# ----------------------------------------------- 6. lỗi LLM -> không giết job
texts = [LONG]
tts = FakeTTS()
durs = [len(LONG) / tts.cps]
att, plan = make_plan(texts, durs, segs)
n = _retranslate_pass(FakeTranslator(boom=True), plan, texts, durs,
                      ["/tmp/x.wav"], [""], tts, TMP, 1)
assert n == 0 and texts[0] == LONG
print("LLM lỗi -> job không chết ............. OK")

# ------------------------ 7. TTS lỗi -> không giết job, giữ nguyên bản cũ
class BoomTTS(FakeTTS):
    def synthesize(self, text, voice=None):
        raise RuntimeError("GPU hết VRAM")


texts = [LONG]
tts = FakeTTS()
durs = [len(LONG) / tts.cps]
att, plan = make_plan(texts, durs, segs)
tr = FakeTranslator({LONG: SHORT})
n = _retranslate_pass(tr, plan, texts, durs, ["/tmp/x.wav"], [""],
                      BoomTTS(), TMP, 1)
assert n == 0 and texts[0] == LONG, "TTS lỗi thì giữ bản cũ, không sập"
print("TTS lỗi -> giữ bản cũ ................. OK")

# ------------------- 8. bản dịch đã ngắn hơn ngân sách -> không gọi vô ích
segs = [(0.0, 20.0)]                            # slot rất dài
texts = ["ok"]                                  # 2 ký tự
tts = FakeTTS()
durs = [10.0]                                   # nhưng audio 10s (nói chậm)
att, plan = make_plan(texts, durs, segs)
assert plan[0].needs_shorter_text is False      # 10s < 20s slot
print("đoạn dài thênh thang -> không gọi ..... OK")

# --------------------------------- 9. nhiều đoạn: chỉ chạm đoạn cần thiết
segs = [(0.0, 2.0), (2.0, 8.0)]
texts = [LONG, FITS]
tts = FakeTTS()
durs = [len(LONG) / tts.cps, len(FITS) / tts.cps]
att, plan = make_plan(texts, durs, segs)
tr = FakeTranslator({LONG: SHORT})
n = _retranslate_pass(tr, plan, texts, durs,
                      ["/tmp/a.wav", "/tmp/b.wav"], ["", ""], tts, TMP, 1)
assert n == 1, n
assert len(tr.asked) == 1, "chỉ đoạn vượt mới được hỏi"
assert texts[1] == FITS
print("chỉ chạm đoạn vượt thời lượng ......... OK")

print("RETRANSLATE GUARD PASSED")