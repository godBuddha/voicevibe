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

# GD2 — phụ đề dễ đọc: mỗi dòng có hạn ký tự và mỗi cue có hạn "tốc độ đọc"
# (cps = ký tự/giây). Chỉ bật khi caller CẤU HÌNH (render(..., max_line_chars=…)
# — None nghĩa là giữ nguyên hành vi cũ cho mọi caller hiện có + selftest
# (không phá SRT đang ổn).
DEFAULT_MAX_LINE_CHARS = 42
DEFAULT_MAX_CPS = 21.0


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


def _wrap_line(line: str, max_chars: int, warnings: list[str]) -> list[str]:
    """Chia một dòng dài thành nhiều dòng ≤ max_chars theo ranh giới TỪ (greedy).
    Một từ đơn lẻ dài hơn hạn → giữ nguyên + cảnh báo (cắt giữa từ tệ hơn)."""
    if len(line) <= max_chars:
        return [line]
    out: list[str] = []
    cur = ""
    for word in line.split(" "):
        cand = f"{cur} {word}" if cur else word
        if len(cand) <= max_chars or not cur:
            cur = cand
        else:
            out.append(cur)
            cur = word
    if cur:
        out.append(cur)
    for chunk in out:
        if len(chunk) > max_chars:
            warnings.append(
                f"dòng có một từ dài hơn {max_chars} ký tự — giữ nguyên: "
                f"«{chunk[:24]}…»")
    return out


def _split_index(text: str, ratio: float) -> int:
    """Vị trí ký tự tách gần `ratio`·len(text) tại ranh giới TỪ. Trả -1 khi
    không tách được (ít hơn 2 từ)."""
    words = text.split(" ")
    if len(words) < 2:
        return -1
    target = max(1, min(len(text) - 1, round(ratio * len(text))))
    best, best_diff, pos = -1, 1 << 30, 0
    for k, word in enumerate(words[:-1]):
        pos += len(word) + (1 if k else 0)
        diff = abs(pos - target)
        if diff < best_diff:
            best, best_diff = pos, diff
    return best


def enforce_limits(cues: list[Cue], *, max_line_chars: int, max_cps: float,
                   warnings: list[str] | None = None) -> list[Cue]:
    """GD2 — ép phụ đề vào khung dễ đọc, trả danh sách cue (đã normalize lại):

      1. **Chia dòng**: dòng vượt `max_line_chars` → wrap theo ranh giới từ.
      2. **Tốc độ đọc**: cue hiển thị nhanh hơn `max_cps` ký tự/giây → phải có
         THÊM THỜI GIAN. Tách cue làm hai là không đủ (ký tự và thời gian cùng
         chia đôi → cps nguyên vẹn) — cần MƯỢN thời gian từ khoảng trống ngay
         trước/sau cue (không đụng mốc cue lân cận: mượn xong phía sau thì
         normalize đẩy cue kế nhẹ theo). Sau đó mới tách theo ranh giới từ gần
         giữa, thời gian chia theo tỷ lệ ký tự.
      3. Không đủ chỗ trống / dòng ít hơn 2 từ → GIỮ NGUYÊN + cảnh báo
         (phụ đề hơi nhanh còn hơn job chết — pattern "thông tin phụ").

    Áp trên TỪNG dòng — cue song ngữ tách cả hai dòng theo cùng tỷ lệ ký tự;
    dòng không tách được về nửa đầu + cảnh báo.
    """
    warn = warnings if warnings is not None else []
    out: list[Cue] = []
    for i, cue in enumerate(cues):
        lines = [part for line in cue.lines
                 for part in _wrap_line(line, max_line_chars, warn)]
        dur = cue.end - cue.start
        total = sum(len(ln) for ln in lines)
        if dur <= 0 or max_cps <= 0 or total / dur <= max_cps:
            cue.lines = lines
            out.append(cue)
            continue
        # ---- mượn thời gian từ khoảng trống trước/sau (đủ cần là nghỉ)
        needed = total / max_cps
        extra = needed - dur
        next_start = cues[i + 1].start if i + 1 < len(cues) else cue.end + 10.0
        room_after = max(0.0, next_start - cue.end)
        room_before = max(0.0, cue.start - (out[-1].end if out else 0.0))
        borrow_after = min(extra, room_after)
        borrow_before = min(extra - borrow_after, room_before)
        lo, hi = cue.start - borrow_before, cue.end + borrow_after
        if hi - lo < needed - 1e-9:
            warn.append(
                f"cue {i + 1} đọc nhanh ({total / dur:.0f} ký tự/giây) nhưng "
                "không đủ chỗ trống để kéo dài — giữ nguyên mốc giờ")
            lo, hi = cue.start, cue.end
        # ---- tách theo ranh giới từ (nếu tách được)
        first = lines[0] if lines else ""
        cut = _split_index(first, 0.5)
        if cut > 0:
            ratio = cut / max(1, len(first))
            mid = lo + (hi - lo) * ratio
            a, b = [], []
            for ln in lines:
                part = _split_index(ln, ratio)
                if part > 0:
                    a.append(ln[:part].strip())
                    b.append(ln[part:].strip())
                else:
                    warn.append("một dòng phụ không tách được khi chia cue — "
                                "gộp về nửa đầu")
                    a.append(ln)
                    b.append("")
            out.append(Cue(start=lo, end=mid, lines=[x for x in a if x]))
            out.append(Cue(start=mid, end=hi, lines=[x for x in b if x]))
        else:
            warn.append(
                f"cue {i + 1} đọc nhanh nhưng ít hơn 2 từ — kéo dài thời gian")
            cue.lines = lines
            cue.start, cue.end = lo, hi
            out.append(cue)
    return normalize_cues(out)


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
           show_speaker: bool = True, max_line_chars: int | None = None,
           max_cps: float | None = None,
           warnings: list[str] | None = None) -> str:
    """Xuất phụ đề ở định dạng `fmt`. Trả về CHUỖI (chưa ghi ra storage).

    GD2 — `max_line_chars`/`max_cps` bật khung dễ đọc (chia dòng + mượn giờ
    trống để hạ tốc độ đọc); None = bỏ qua hoàn toàn (mọi caller cũ + selftest
    giữ output nguyên vẹn). Cảnh báo chia/không-tách-được trả qua `warnings`.
    """
    if fmt not in FORMATS:
        raise ValueError(f"định dạng không hỗ trợ: {fmt!r} (chọn trong {list(FORMATS)})")

    import pysubs2

    segments = _fix_windows(segments)
    cues = normalize_cues(build_cues(segments, translations, bilingual=bilingual,
                                     show_speaker=show_speaker))
    if max_line_chars is not None or max_cps is not None:
        cues = enforce_limits(
            cues,
            max_line_chars=max_line_chars
            if max_line_chars is not None else DEFAULT_MAX_LINE_CHARS,
            max_cps=max_cps if max_cps is not None else DEFAULT_MAX_CPS,
            warnings=warnings)

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

    # --- GD2: chia dòng theo ranh giới từ — mọi dòng ≤ hạn ký tự
    fits = enforce_limits([Cue(0.0, 5.0, ["Mười chín khâu " * 4])],
                          max_line_chars=20, max_cps=0)
    assert all(len(ln) <= 20 for c in fits for ln in c.lines), fits

    # --- GD2: cue đọc nhanh (100 ký tự / 2 giây = 50 cps) + chỗ trống phía sau
    #     → mượn giờ + tách 2 cue, mỗi cue ≤ 21 cps
    warns: list[str] = []
    fast = enforce_limits([Cue(0.0, 2.0, ["a " * 50]), Cue(30.0, 31.0, ["x"])],
                          max_line_chars=42, max_cps=21, warnings=warns)
    assert len(fast) == 3, fast
    for c in fast[:2]:
        chars = sum(len(ln) for ln in c.lines)
        assert chars / (c.end - c.start) <= 21 + 1e-6, (chars, c)
    assert fast[0].end <= fast[1].start + 1e-9, fast
    assert not warns, warns

    # --- GD2: không đủ chỗ trống (cue kế dính sát) → giữ mốc giờ + cảnh báo
    dense = enforce_limits([Cue(0.0, 2.0, ["a " * 50]), Cue(2.0, 3.0, ["x"])],
                           max_line_chars=42, max_cps=21, warnings=warns)
    assert dense[0].start == 0.0 and dense[0].end <= 2.0, dense
    assert any("không đủ chỗ trống" in w for w in warns), warns

    # --- GD2: render với cấu hình — dòng xuất ra ≤ hạn ký tự
    fitted = render([TranscriptSegment(0.0, 4.0, "từ " * 40)], "srt",
                    max_line_chars=42, max_cps=21)
    body = [ln for ln in fitted.splitlines()
            if ln and "-->" not in ln and not ln.strip().isdigit()]
    assert all(len(ln) <= 42 for ln in body), fitted

    print("SRT ....................... OK")
    print("VTT ....................... OK")
    print("ASS ....................... OK")
    print("song ngữ .................. OK")
    print("A6 normalize (overlap/300ms) OK")
    print("A4 tách cue theo từ ....... OK")
    print("GD2 giới hạn dòng + cps ... OK")
    print("SUBTITLE SELFTEST PASSED")


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        _selftest()