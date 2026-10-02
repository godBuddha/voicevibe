"""Phụ đề: SRT / VTT / ASS, kèm chế độ song ngữ.

Trước đây job `subtitle` trả 501 vì chỉ có `stt.to_srt` (một định dạng, một ngôn
ngữ). Module này là pipeline thật: cùng dữ liệu segment + người nói, xuất ra ba
định dạng, và ghép bản dịch vào từng cue khi cần.

Vì sao tách khỏi `stt.py`: `stt.to_srt` là bước xuất của pipeline STT (một định
dạng duy nhất, có [SPEAKER] trong dòng chữ). Ở đây mô hình là "cue có nhiều dòng"
— cần cho song ngữ — và ba bộ ghi khác nhau. Trộn vào một hàm sẽ thành tham số
bật/tắt chằng chịt.

Dùng pysubs2 (MIT) làm bộ ghi: nó đã xử lý đúng các cạnh của ASS (escape khối
override `{...}`, `\\N` cho xuống dòng cứng, thời lượng dạng `h:mm:ss.cc`) — tự
viết lại thì đó chính là chỗ sinh lỗi.

Định dạng thời gian khác nhau có chủ đích:
  - SRT: `00:00:01,500` (dấu phẩy)
  - VTT: `00:00:01.500` (dấu chấm) + header `WEBVTT`
  - ASS: `0:00:01.50` (phần trăm giây, không phải milli)
pysubs2 lo cả ba; đừng tự nối chuỗi thời gian.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from ..providers.base import TranscriptSegment

FORMATS = ("srt", "vtt", "ass")
DEFAULT_FORMAT = "srt"

# A6: phụ đề ngắn hơn 300ms là "chớp mắt" — người xem không kịp đọc. Tối thiểu
# 300ms/cue (port `minimumSRTDurationMillis` từ KrillinAI srt_timeline.go).
MIN_CUE_DURATION = 0.3

# A4: tối đa 12 từ một cue (port `MaxWordOneLine` từ KrillinAI) — vượt thì tách
# cue theo ranh giới từ với mốc giờ word-level (seg.words) chính xác tới chữ.
MAX_WORDS_PER_CUE = 12


@dataclass
class Cue:
    """Một dòng phụ đề. `lines` nhiều hơn 1 khi ở chế độ song ngữ."""

    start: float
    end: float
    lines: list[str] = field(default_factory=list)


def speaker_prefix(speaker: str | None) -> str:
    """Nhãn người nói đọc được, ví dụ `SPEAKER_00: `.

    Đổi `SPEAKER_00` -> `Người 1` để phụ đề không hiện mã máy. Người vận hành
    không sửa được nhãn này trong pipeline, nhưng ít nhất nó đọc được.
    """
    if not speaker:
        return ""
    if speaker.startswith("SPEAKER_"):
        tail = speaker.split("_", 1)[1]
        if tail.isdigit():
            return f"Người {int(tail) + 1}: "
    return f"{speaker}: "


def _split_by_words(seg: TranscriptSegment, who: str) -> list[Cue]:
    """Tách một segment dài thành nhiều cue theo ranh giới TỪ (A4).

    Mốc giờ lấy từ word-level timestamps — chính xác tới từng chữ, không chia
    đều kiểu "ước lượng" (câu nói không đều nhịp: nghỉ hơi, gạch đầu dòng đều
    làm chia-đều sai). Chỉ dùng cho phụ đề MỘT ngôn ngữ: bản dịch là chuỗi rời
    của cả segment, không biết cắt tại từ nào — cue song ngữ giữ nguyên mốc câu.
    """
    words = seg.words or []
    cues: list[Cue] = []
    for i in range(0, len(words), MAX_WORDS_PER_CUE):
        group = words[i:i + MAX_WORDS_PER_CUE]
        text = " ".join(w.text for w in group).strip()
        if not text:
            continue
        cues.append(Cue(start=group[0].start, end=group[-1].end,
                        lines=[(who + text).strip()]))
    return cues or [Cue(start=seg.start, end=seg.end, lines=[(who + seg.text).strip()])]


def build_cues(segments: list[TranscriptSegment],
               translations: list[str] | None = None, *,
               bilingual: bool = False, show_speaker: bool = True) -> list[Cue]:
    """Ghép segment (+ bản dịch) thành cue.

    `translations` phải khớp chỉ số với `segments`; lệch độ dài là lỗi lập trình
    (bản dịch sinh ra từ chính danh sách segment), nên ném lỗi thay vì im lặng
    bỏ qua — bỏ qua sẽ ra phụ đề thiếu dòng mà không ai biết.

    Segment có word-level timestamps (A4, chỉ local Whisper) và dài hơn
    MAX_WORDS_PER_CUE từ → tách thành nhiều cue theo từ (chỉ đường một ngôn
    ngữ — bản dịch không biết cắt tại từ nào).
    """
    if translations is not None and len(translations) != len(segments):
        raise ValueError(
            f"số bản dịch ({len(translations)}) khác số segment ({len(segments)})")
    if bilingual and translations is None:
        raise ValueError("bilingual cần bản dịch (translations=None)")

    cues: list[Cue] = []
    for i, seg in enumerate(segments):
        who = speaker_prefix(seg.speaker) if show_speaker else ""
        if translations is None and seg.words and len(seg.words) > MAX_WORDS_PER_CUE:
            cues.extend(_split_by_words(seg, who))
            continue
        original = (who + seg.text.strip()).strip()
        lines = [original]
        if bilingual:
            tr = (translations or [""])[i].strip()
            # Bản dịch rỗng thì giữ dòng gốc: một cue trống trơn tệ hơn cue
            # chỉ có tiếng gốc.
            if tr:
                lines.append(tr)
        cues.append(Cue(start=seg.start, end=seg.end, lines=lines))
    return cues


def normalize_cues(cues: list[Cue], *, min_duration: float = MIN_CUE_DURATION,
                   allow_overlap: bool = False) -> list[Cue]:
    """Chuẩn hoá timeline (A6, port `normalizeSrtBlocks` từ KrillinAI srt_timeline.go):

      1. chống chồng lấn: cue sau bắt đầu trước khi cue trước kết thúc → đẩy
         start về đúng chỗ cue trước kết thúc;
      2. tối thiểu 300ms: cue ngắn hơn (kể cả end<=start) được kéo dài đủ mức —
         người xem kịp đọc, pysubs2 không chê.

    Sửa TẠI CHỖ trên các Cue truyền vào (chúng thuộc về pipeline, không bản sao
    để tránh lệch giữa kế hoạch và file xuất). Trả về chính danh sách đó.
    """
    prev_end = 0.0
    for cue in cues:
        if not allow_overlap and cue.start < prev_end:
            cue.start = prev_end
        if cue.end - cue.start < min_duration:
            cue.end = cue.start + min_duration
        prev_end = cue.end
    return cues


def _fix_windows(segments: list[TranscriptSegment]) -> list[TranscriptSegment]:
    """Chặn `end <= start` và thời lượng bằng 0.

    Whisper thỉnh thoảng trả segment có `end == start`, và pysubs2 sẽ cảnh báo
    hoặc ghi ra cue vô hình. Đẩy `end` lên tối thiểu 1ms — vẫn vô hình khi phát
    nhưng hợp lệ, và không làm lệch mốc của các cue sau.
    """
    out: list[TranscriptSegment] = []
    for seg in segments:
        if seg.end <= seg.start:
            seg = TranscriptSegment(start=seg.start, end=seg.start + 0.001,
                                    text=seg.text, speaker=seg.speaker)
        out.append(seg)
    return out


def render(segments: list[TranscriptSegment], fmt: str = DEFAULT_FORMAT, *,
           translations: list[str] | None = None, bilingual: bool = False,
           show_speaker: bool = True) -> str:
    """Xuất phụ đề ở định dạng `fmt`. Trả về CHUỖI (chưa ghi ra storage)."""
    if fmt not in FORMATS:
        raise ValueError(f"định dạng không hỗ trợ: {fmt!r} (chọn trong {list(FORMATS)})")

    import pysubs2

    segments = _fix_windows(segments)
    cues = normalize_cues(build_cues(segments, translations, bilingual=bilingual,
                                     show_speaker=show_speaker))

    subs = pysubs2.SSAFile()
    if fmt == "ass":
        subs.info["Title"] = "VoiceVibe"
        # Tên style KHÔNG phải một tham số của SSAStyle — nó là KHOÁ trong
        # `subs.styles` (đã gặp thật: `SSAStyle(name=...)` -> TypeError).
        subs.styles["Default"] = pysubs2.SSAStyle(
            fontname="Arial", fontsize=20,
            primarycolor=pysubs2.Color(255, 255, 255, 0),
            outlinecolor=pysubs2.Color(0, 0, 0, 0),
            backcolor=pysubs2.Color(0, 0, 0, 128),
            borderstyle=1, outline=2, shadow=0,
            alignment=pysubs2.Alignment.BOTTOM_CENTER,
        )

    for cue in cues:
        # ASS dùng `\N` cho xuống dòng cứng, KHÔNG phải "\n". pysubs2 không tự
        # chuyển, nên phải nối bằng ký tự đúng định dạng.
        text = r"\N".join(cue.lines) if fmt == "ass" else "\n".join(cue.lines)
        ev = pysubs2.SSAEvent(start=pysubs2.make_time(s=cue.start),
                               end=pysubs2.make_time(s=cue.end), text=text)
        subs.append(ev)

    return subs.to_string(fmt)


def extension(fmt: str) -> str:
    """Phần mở rộng file cho định dạng (ass giữ nguyên, không phải `.ssa`)."""
    if fmt not in FORMATS:
        raise ValueError(f"định dạng không hỗ trợ: {fmt!r}")
    return fmt


def _selftest() -> None:
    segs = [
        TranscriptSegment(0.0, 2.5, "Xin chào các bạn", "SPEAKER_00"),
        TranscriptSegment(2.5, 5.0, "Hôm nay thử phụ đề", "SPEAKER_01"),
    ]

    # --- SRT: dấu phẩy thập phân, có số thứ tự
    srt = render(segs, "srt")
    assert srt.splitlines()[0] == "1", srt
    assert "00:00:00,000 --> 00:00:02,500" in srt, srt
    assert "Người 1: Xin chào các bạn" in srt, srt
    assert "Người 2: Hôm nay thử phụ đề" in srt, srt

    # --- VTT: header + dấu chấm
    vtt = render(segs, "vtt")
    assert vtt.lstrip().startswith("WEBVTT"), vtt
    assert "00:00:00.000 --> 00:00:02.500" in vtt, vtt

    # --- ASS: phần trăm giây + style
    ass = render(segs, "ass")
    assert "[Script Info]" in ass and "[V4+ Styles]" in ass, ass
    assert "Default" in ass, ass
    assert "0:00:00.00" in ass, ass

    # --- song ngữ: hai dòng một cue
    bi = render(segs, "srt", translations=["Hello everyone", "Testing subtitles"],
                bilingual=True)
    assert "Người 1: Xin chào các bạn\nHello everyone" in bi, bi
    assert "Người 2: Hôm nay thử phụ đề\nTesting subtitles" in bi, bi

    # --- ASS song ngữ dùng \N
    bi_ass = render(segs, "ass", translations=["Hello", "Testing"], bilingual=True)
    assert r"\N" in bi_ass, bi_ass

    # --- segment end == start không được làm hỏng file
    zero = render([TranscriptSegment(1.0, 1.0, "chớp")], "srt")
    assert "--> " in zero, zero

    # --- lệch số lượng bản dịch -> lỗi rõ ràng
    try:
        render(segs, "srt", translations=["chỉ một"], bilingual=True)
    except ValueError:
        pass
    else:
        raise AssertionError("phải báo lỗi khi số bản dịch lệch")

    # --- A6: chống chồng lấn (cue sau bắt đầu 2.0 < end cue trước 2.5 -> đẩy lên 2.5)
    overlap = render([TranscriptSegment(0.0, 2.5, "câu một", "SPEAKER_00"),
                      TranscriptSegment(2.0, 5.0, "câu hai", "SPEAKER_01")], "srt")
    assert "00:00:02,500 --> 00:00:05,000" in overlap, overlap

    # --- A6: cue quá ngắn được kéo dài đủ 300ms
    tiny = render([TranscriptSegment(1.0, 1.05, "chớp")], "srt")
    assert "00:00:01,000 --> 00:00:01,300" in tiny, tiny

    # --- A4: segment 25 từ + word-level -> tách 3 cue (12/12/1) theo mốc từ
    from ..providers.base import Word

    words = [Word(0.1 * k, 0.1 * k + 0.08, f"t{k + 1}") for k in range(25)]
    long_seg = TranscriptSegment(0.0, 2.53, " ".join(w.text for w in words),
                                 "SPEAKER_00", words)
    parts = render([long_seg], "srt")
    # cue 1: từ 1..12 → [0.0, 1.18]; cue 2: 13..24 → [1.2, 2.38]; cue 3: từ 25
    # (chỉ 80ms — normalize kéo dài đủ 300ms)
    assert "00:00:00,000 --> 00:00:01,180" in parts, parts
    assert "00:00:01,200 --> 00:00:02,380" in parts, parts
    assert "t25" in parts and "Người 1: t25" in parts, parts
    # cue có bản dịch (bilingual) KHÔNG tách — bản dịch không biết cắt từ nào
    bi_long = render([long_seg], "srt", translations=["x"], bilingual=True)
    assert "00:00:00,000 --> 00:00:02,530" in bi_long, bi_long

    print("SRT ....................... OK")
    print("VTT ....................... OK")
    print("ASS ....................... OK")
    print("song ngữ .................. OK")
    print("A6 normalize (overlap/300ms) OK")
    print("A4 tách cue theo từ ....... OK")
    print("SUBTITLE SELFTEST PASSED")


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        _selftest()