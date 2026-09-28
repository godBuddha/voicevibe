"""Guard chống hallucination của Whisper.

Whisper LUÔN phải sinh ra ký tự, kể cả khi đoạn audio chỉ có nhạc hoặc tiếng ồn —
nên nó bịa. Với pipeline lồng tiếng, câu bịa không chỉ hiện sai trong phụ đề: nó
được DỊCH rồi ĐỌC LÊN thành tiếng, tức là thêm hẳn nội dung không có trong bản gốc.

Test thuần logic, không cần model hay GPU: `segment_is_hallucination` chỉ đọc ba
chỉ số mà model đưa ra (`no_speech_prob`, `avg_logprob`, `compression_ratio`), nên
dựng được đối tượng giả cho mọi ca — kể cả ca khó tạo bằng model thật.

Điều quan trọng nhất được ghim ở đây là **không lọc quá tay**: bỏ nhầm câu nói thật
tệ hơn nhiều so với để lọt một câu bịa. Vì vậy mỗi ngưỡng đều có ca "sát ngưỡng
nhưng vẫn phải GIỮ".

Run:  cd backend && PYTHONPATH=. python tests/test_hallucination.py
"""
from __future__ import annotations

import pathlib
import sys
from dataclasses import dataclass

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from app.pipelines.stt import (  # noqa: E402
    COMPRESSION_MAX,
    LOGPROB_MIN,
    LOGPROB_MIN_HARD,
    NO_SPEECH_MAX,
    drop_hallucinations,
    segment_is_hallucination,
)


@dataclass
class FakeSeg:
    """Đúng hình dạng faster-whisper trả về (các trường ta dùng)."""

    text: str
    start: float = 0.0
    end: float = 1.0
    no_speech_prob: float = 0.0
    avg_logprob: float = -0.3
    compression_ratio: float = 1.0


def bad(seg) -> str:
    r = segment_is_hallucination(seg)
    assert r, f"đáng lẽ phải bị loại: {seg}"
    return r


def ok(seg) -> None:
    r = segment_is_hallucination(seg)
    assert r is None, f"KHÔNG được loại: {seg} (lý do đưa ra: {r})"


# ------------------------------------------- 1. câu nói bình thường -> GIỮ
ok(FakeSeg("Xin chào các bạn, mình là Long."))
ok(FakeSeg("Hello everyone"))
print("câu bình thường -> giữ ................. OK")

# ------------------------------- 2. im lặng: no_speech cao + logprob thấp
r = bad(FakeSeg("Hãy subscribe cho kênh của tôi nhé", no_speech_prob=0.92,
                avg_logprob=-1.2))
assert "no_speech" in r, r
print("im lặng -> loại (nêu rõ lý do) ........ OK")

# --------------------- 3. SÁT NGƯỠNG: no_speech cao NHƯNG logprob vẫn tốt -> GIỮ
# Đây là ca quan trọng nhất. Đoạn nói ngắn/ngắt quãng làm model phân vân
# (no_speech cao) trong khi vẫn giải mã đúng (logprob tốt). Lọc theo mỗi
# no_speech_prob sẽ ăn mất những câu nói thật ngắn — đúng loại lỗi tệ nhất.
ok(FakeSeg("Vâng.", no_speech_prob=0.95, avg_logprob=-0.25))
ok(FakeSeg("Đúng rồi.", no_speech_prob=0.88, avg_logprob=-0.5))
print("no_speech cao nhưng logprob tốt -> giữ . OK")

# --------------------------- 4. giải mã đoán bừa: logprob rất thấp -> loại
r = bad(FakeSeg("một hai ba bốn năm sáu", avg_logprob=-1.8))
assert "avg_logprob" in r, r
print("logprob rất thấp -> loại ............... OK")

# ------------------------------- 5. lặp lại: compression_ratio cao -> loại
r = bad(FakeSeg("Cảm ơn các bạn đã theo dõi " * 3, compression_ratio=3.1))
assert "compression_ratio" in r, r
print("văn bản lặp lại -> loại ................ OK")

# --------------------------------------- 6. chỉ có ký hiệu -> loại
for t in ("...", "♪♪♪", "—", ". . ."):
    r = bad(FakeSeg(t))
    assert "ký hiệu" in r, (t, r)
print("chỉ có ký hiệu -> loại ................. OK")

# ---------------- 6b. nhãn phi-lời-nói -> loại (dịch rồi đọc lên là thêm câu)
for t in ("[Music]", "[nhạc]", "(tiếng cười)", "[Applause]", "【音楽】"):
    r = bad(FakeSeg(t))
    assert "phi-lời-nói" in r, (t, r)
print("nhãn [Music]/[nhạc] -> loại ........... OK")

# chữ có dấu tiếng Việt và chữ số KHÔNG được coi là ký hiệu
ok(FakeSeg("ừ"))
ok(FakeSeg("3"))
ok(FakeSeg("ổn"))
# câu nói thật có ngoặc bên trong thì KHÔNG phải nhãn — không được lọc
ok(FakeSeg("Anh ấy nói [rất to] rồi bỏ đi"))
ok(FakeSeg("(cười) rồi tôi đi về"))
print("chữ tiếng Việt/số, ngoặc giữa câu -> giữ . OK")

# --------------------------------------------- 7. text rỗng -> loại
r = bad(FakeSeg(""))
assert r == "empty", r
bad(FakeSeg("   "))
print("text rỗng -> loại ...................... OK")

# ------------------------- 8. thiếu chỉ số (adapter khác) -> GIỮ, không vỡ
# Provider khác (OpenAI-compatible) không trả các chỉ số này. Thiếu dữ liệu không
# được biến thành "loại bừa".
class Bare:
    def __init__(self, text):
        self.text = text


ok(Bare("câu không có chỉ số nào"))
print("thiếu chỉ số -> giữ (không loại bừa) ... OK")

# ------------------------------------- 9. ngưỡng biên: đúng bằng ngưỡng -> GIỮ
# Dùng `>` và `<` (không phải >= / <=) nên giá trị đúng bằng ngưỡng vẫn qua.
ok(FakeSeg("biên trên", no_speech_prob=NO_SPEECH_MAX, avg_logprob=LOGPROB_MIN - 0.5))
ok(FakeSeg("biên logprob", avg_logprob=LOGPROB_MIN_HARD))
ok(FakeSeg("biên nén", compression_ratio=COMPRESSION_MAX))
print("đúng ngưỡng -> giữ (không lọc oan) ..... OK")

# ----------------------------------------------- 10. lọc cả danh sách
raw = [
    FakeSeg("Câu nói thật thứ nhất"),
    FakeSeg("Hãy subscribe cho kênh nhé", no_speech_prob=0.95, avg_logprob=-1.3),
    FakeSeg("Câu nói thật thứ hai"),
    FakeSeg("...", no_speech_prob=0.99),
    FakeSeg("lặp lặp lặp", compression_ratio=2.9),
]
kept, dropped = drop_hallucinations(raw)
assert [k.text for k in kept] == ["Câu nói thật thứ nhất", "Câu nói thật thứ hai"], kept
assert len(dropped) == 3, dropped
assert all(isinstance(t, str) and isinstance(r, str) for t, r in dropped)
print("lọc danh sách + giữ nguyên thứ tự ....... OK")

# ------------------- 11. lọc sạch sẽ KHÔNG trả về rỗng (chống lọc quá tay)
only_bad = [FakeSeg("...", no_speech_prob=1.0), FakeSeg("♪♪", compression_ratio=4.0)]
kept2, dropped2 = drop_hallucinations(only_bad)
assert kept2 == only_bad and dropped2 == [], (
    "bỏ hết nội dung là hỏng nặng hơn nhiễu — phải giữ nguyên bản gốc")
print("lọc sạch -> trả nguyên bản gốc ......... OK")

# ------------------------------------------------- 12. danh sách rỗng
assert drop_hallucinations([]) == ([], [])
print("danh sách rỗng ......................... OK")

print("HALLUCINATION GUARD PASSED")