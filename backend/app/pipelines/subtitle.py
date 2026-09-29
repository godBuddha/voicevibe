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


def build_cues(segments: list[TranscriptSegment],
               translations: list[str] | None = None, *,
               bilingual: bool = False, show_speaker: bool = True) -> list[Cue]:
    """Ghép segment (+ bản dịch) thành cue.

    `translations` phải khớp chỉ số với `segments`; lệch độ dài là lỗi lập trình
    (bản dịch sinh ra từ chính danh sách segment), nên ném lỗi thay vì im lặng
    bỏ qua — bỏ qua sẽ ra phụ đề thiếu dòng mà không ai biết.
    """
    if translations is not None and len(translations) != len(segments):
        raise ValueError(
            f"số bản dịch ({len(translations)}) khác số segment ({len(segments)})")
    if bilingual and translations is None:
        raise ValueError("bilingual cần bản dịch (translations=None)")

    cues: list[Cue] = []
    for i, seg in enumerate(segments):
        who = speaker_prefix(seg.speaker) if show_speaker else ""
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
    cues = build_cues(segments, translations, bilingual=bilingual,
                      show_speaker=show_speaker)

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

    print("SRT ....................... OK")
    print("VTT ....................... OK")
    print("ASS ....................... OK")
    print("song ngữ .................. OK")
    print("SUBTITLE SELFTEST PASSED")


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        _selftest()