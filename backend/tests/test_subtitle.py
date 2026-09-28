"""Guard cho pipeline phụ đề: SRT / VTT / ASS + song ngữ.

Vì sao có test riêng thay vì tin vào `stt.to_srt`: job `subtitle` từng trả 501
(luôn luôn), nên không có gì kiểm chứng đường xuất phụ đề cả. Ba định dạng có ba
quy ước thời gian KHÁC NHAU và rất dễ viết sai nếu tự nối chuỗi:

    SRT  00:00:01,500   dấu PHẨY thập phân
    VTT  00:00:01.500   dấu CHẤM + header WEBVTT
    ASS  0:00:01.50     phần TRĂM giây, không phải milli

Đây là lý do dùng pysubs2 (MIT) thay vì tự viết: sai một dấu là phụ đề lệch giờ
trên trình phát, mà mắt thường nhìn file không thấy.

Đồng thời ghim chế độ song ngữ: mỗi cue phải có đúng 2 dòng (bản gốc, bản dịch),
và ASS phải dùng `\\N` chứ không phải ký tự xuống dòng thật — ASS coi `\n` là
khoảng trắng nên phụ đề sẽ dồn thành một dòng.

Chỉ cần `pysubs2`; không cần fastapi/GPU.
Chạy:  cd backend && PYTHONPATH=. python tests/test_subtitle.py
"""
from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from app.pipelines.subtitle import (  # noqa: E402
    FORMATS, build_cues, extension, render, speaker_prefix,
)
from app.providers.base import TranscriptSegment  # noqa: E402

SEGS = [
    TranscriptSegment(0.0, 2.5, "Xin chào các bạn", "SPEAKER_00"),
    TranscriptSegment(2.5, 5.0, "Hôm nay thử phụ đề", "SPEAKER_01"),
    TranscriptSegment(5.0, 8.25, "Kết thúc", None),
]
TRANS = ["Hello everyone", "Testing subtitles today", "The end"]

# ------------------------------------------------------- 1. nhãn người nói
assert speaker_prefix("SPEAKER_00") == "Người 1: ", speaker_prefix("SPEAKER_00")
assert speaker_prefix("SPEAKER_01") == "Người 2: "
assert speaker_prefix(None) == ""
assert speaker_prefix("") == ""
# nhãn lạ (không theo mẫu pyannote) phải giữ nguyên chứ không nuốt
assert speaker_prefix("Alice") == "Alice: "
print("nhãn người nói ....................... OK")

# ---------------------------------------------------------- 2. SRT
srt = render(SEGS, "srt")
lines = srt.splitlines()
assert lines[0] == "1" and lines[1] == "00:00:00,000 --> 00:00:02,500", lines[:2]
assert "Người 1: Xin chào các bạn" in srt, srt
assert "Người 2: Hôm nay thử phụ đề" in srt, srt
# segment không có người nói -> không có tiền tố rỗng "None:"
assert "Người 3" not in srt and "None" not in srt, srt
# dấu phẩy thập phân, KHÔNG phải dấu chấm
assert "00:00:05,000 --> 00:00:08,250" in srt, srt
assert "," in srt.splitlines()[1], srt
print("SRT (dấu phẩy, có số thứ tự) ......... OK")

# ---------------------------------------------------------- 3. VTT
vtt = render(SEGS, "vtt")
assert vtt.lstrip().startswith("WEBVTT"), vtt[:60]
assert "00:00:00.000 --> 00:00:02.500" in vtt, vtt
assert "00:00:05.000 --> 00:00:08.250" in vtt, vtt
print("VTT (header + dấu chấm) .............. OK")

# ---------------------------------------------------------- 4. ASS
ass = render(SEGS, "ass")
assert "[Script Info]" in ass, ass[:200]
assert "[V4+ Styles]" in ass, ass[:400]
assert "[Events]" in ass, ass[:600]
assert "Default" in ass, ass[:400]
# thời gian ASS là phần trăm giây: 2.5s -> 0:00:02.50 (KHÔNG phải .500)
assert "0:00:02.50" in ass, [l for l in ass.splitlines() if "0:00:02" in l]
assert ",500" not in ass, "ASS không dùng milli-giây"
print("ASS (style + phần trăm giây) ......... OK")

# ---------------------------------------------------------- 5. song ngữ
bi = render(SEGS, "srt", translations=TRANS, bilingual=True)
assert "Người 1: Xin chào các bạn\nHello everyone" in bi, bi
assert "Người 2: Hôm nay thử phụ đề\nTesting subtitles today" in bi, bi
# mỗi cue đúng 2 dòng chữ (bỏ dòng trống ngăn cách và dòng thời gian)
blocks = [b for b in bi.split("\n\n") if b.strip()]
for b in blocks:
    body = b.splitlines()[2:]
    assert len(body) == 2, f"cue phải có 2 dòng, nhận {body!r}"
print("song ngữ: đúng 2 dòng mỗi cue ....... OK")

# ASS song ngữ phải dùng \N (xuống dòng cứng), không phải newline thật
bi_ass = render(SEGS, "ass", translations=TRANS, bilingual=True)
events = [l for l in bi_ass.splitlines() if l.startswith("Dialogue:")]
assert events, bi_ass
assert all(r"\N" in e for e in events), events
print("ASS song ngữ dùng \\N ............... OK")

# --------------------------------------------- 6. dịch rỗng -> giữ dòng gốc
# Một cue trống trơn tệ hơn cue chỉ có tiếng gốc (ví dụ đoạn nhạc không lời).
mixed = render([SEGS[0]], "srt", translations=[""], bilingual=True)
assert "Xin chào các bạn" in mixed, mixed
_body = [b for b in mixed.split("\n\n") if b.strip()][0].splitlines()[2:]
assert _body == ["Người 1: Xin chào các bạn"], (
    f"bản dịch rỗng KHÔNG được tạo thêm dòng trống, nhận {_body!r}")
print("bản dịch rỗng -> giữ dòng gốc ....... OK")

# ------------------------------------------- 7. segment end == start
# Whisper thỉnh thoảng trả segment dài 0 giây. Phải xuất được file hợp lệ, không
# làm lệch mốc của các cue sau.
zero = render([TranscriptSegment(1.0, 1.0, "chớp"), SEGS[1]], "srt")
assert "00:00:01,000 --> 00:00:01,001" in zero, zero
assert "00:00:02,500 --> 00:00:05,000" in zero, zero
print("segment 0 giây không làm hỏng file ... OK")

# --------------------------------------------------- 8. đầu vào sai
for bad in ("ass2", "txt", "SRT", ""):
    try:
        render(SEGS, bad)
    except ValueError:
        pass
    else:
        raise AssertionError(f"định dạng {bad!r} phải bị từ chối")
print("định dạng lạ bị từ chối ............. OK")

try:
    render(SEGS, "srt", translations=["chỉ một"], bilingual=True)
except ValueError as e:
    assert "khác số segment" in str(e), e
else:
    raise AssertionError("lệch số bản dịch phải báo lỗi")

try:
    render(SEGS, "srt", bilingual=True)          # song ngữ mà không có bản dịch
except ValueError:
    pass
else:
    raise AssertionError("bilingual thiếu translations phải báo lỗi")
print("đầu vào sai bị chặn ................. OK")

# ----------------------------------------------------- 9. tắt nhãn người nói
plain = render(SEGS, "srt", show_speaker=False)
assert "Người 1:" not in plain and "Xin chào các bạn" in plain, plain
print("tắt nhãn người nói .................. OK")

# ------------------------------------------------------ 10. tên file
assert extension("srt") == "srt" and extension("ass") == "ass"
assert set(FORMATS) == {"srt", "vtt", "ass"}
print("phần mở rộng file ................... OK")

# --------------------------------------------- 11. cue dựng đúng cấu trúc
cues = build_cues(SEGS, TRANS, bilingual=True)
assert len(cues) == 3, cues
assert cues[0].lines == ["Người 1: Xin chào các bạn", "Hello everyone"], cues[0]
assert (cues[0].start, cues[0].end) == (0.0, 2.5), cues[0]
print("build_cues giữ mốc thời gian ........ OK")

print("SUBTITLE GUARD PASSED")