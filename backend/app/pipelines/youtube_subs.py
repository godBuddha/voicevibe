"""B2 — phụ đề YouTube SẴN CÓ (port OpenCreator youtube_subtitle.go:283-403, Apache-2.0).

Vì sao đáng làm: video YouTube có phụ đề sẵn thì LẤY LUÔN — đỡ nghe lại bằng
Whisper (tiết kiệm cả giờ GPU cho video dài). Thứ tự ưu tiên chọn track port
nguyên vẹn từ OpenCreator:

  1. auto-caption NGUYÊN BẢN (`{lang}-orig` — bản YouTube tự sinh đúng thứ tiếng
     được nói trong video, KHÔNG phải bản tự dịch);
  2. manual caption của ngôn ngữ gốc (người upload tự viết — chất lượng cao nhất);
  3. auto caption thường.
  - LOẠI track đã bị YouTube DỊCH SẴN sang thứ tiếng khác: URL caption có tham
    số `tlang=` — dùng nhầm là phụ đề không khớp tiếng người nói trong video.
  - Chuẩn hoá mã ngôn ngữ: `iw`→`he` (mã Hebrew cũ của YouTube), `zh-hans`→`zh`.

Làm TỐT HƠN OpenCreator (họ fail ngay khi YouTube không có caption): caller
(bucket `_youtube_transcript` của tasks.py) rơi về Whisper tự động — job không
chết vì video nghèo caption.

Định dạng VTT auto-caption YouTube là word-level: mốc giờ inline
`<00:00:01.399>` trước từng từ (rolling captions — từ bị lặp giữa các cue).
Parser ghép word → câu tại dấu câu, mốc giờ mỗi từ giữ nguyên cho A4 cue-split.

Selftest offline: select_track + parse VTT đều chạy không mạng.
"""
from __future__ import annotations

import re

from ..providers.base import TranscriptSegment, Word

# ---------------------------------------------------------------- chọn track

def canonical_lang(lang: str | None) -> str:
    """Chuẩn hoá mã ngôn ngữ YouTube → code nội bộ (port canonicalYouTubeLanguage)."""
    if not lang:
        return ""
    l = (lang or "").replace("_", "-").strip().lower()
    if l == "iw":
        return "he"  # YouTube dùng iw cho Hebrew (legacy ISO-639-1)
    if l.startswith("zh"):
        return "zh"  # zh-hans / zh-CN / zh-Hant → gộp về zh (không phân biệt chữ giản/phồn)
    return l


def _is_translated_track(entry: dict) -> bool:
    """Track bị YouTube tự dịch sẵn (URL caption có `tlang=`) — LOẠI."""
    return "tlang=" in (entry.get("url") or "")


def _prefer_vtt(entries: list[dict]) -> list[dict]:
    # vtt trước (dễ parse + có word ts), srv3/json3 sau nếu chỉ có
    return sorted(entries or [], key=lambda e: (e.get("ext", "") not in ("vtt", "vtt3")))


def _pick_from(mapping: dict | None, code: str) -> dict | None:
    for k, entries in (mapping or {}).items():
        if canonical_lang(k) == canonical_lang(code):
            for e in _prefer_vtt(entries):
                if e.get("url") and not _is_translated_track(e):
                    return e
    return None


def select_track(manual: dict | None, auto: dict | None,
                 lang: str | None) -> dict | None:
    """Chọn track caption tốt nhất. Trả format dict (có "url") hoặc None.

    Thứ tự port `youtube_subtitle.go:283-329`:
    - lang chỉ định: auto `-orig` → manual lang → auto lang;
    - lang rỗng ("auto"): metadata.language (caller truyền lang) → nếu vẫn rỗng:
      1 track `-orig` duy nhất → 1 manual duy nhất → 1 auto duy nhất → track đầu.
    """
    if lang:
        t = (_pick_from(auto, f"{lang}-orig") or _pick_from(manual, lang)
             or _pick_from(auto, lang))
        return t
    # lang rỗng: dò "nguyên bản"
    orig_codes = [k for k in (auto or {}) if k.endswith("-orig") or "original" in k.lower()]
    if len(orig_codes) == 1:
        t = _pick_from(auto, orig_codes[0])
        if t:
            return t
    manual_codes = [k for k in (manual or {}) if k != "live_chat"]
    if len(manual_codes) == 1:
        t = _pick_from(manual, manual_codes[0])
        if t:
            return t
    auto_codes = [k for k in (auto or {}) if k not in orig_codes]
    if len(auto_codes) == 1:
        t = _pick_from(auto, auto_codes[0])
        if t:
            return t
    # nhiều track mà không biết ngôn ngữ — lấy track tốt nhất có thể (manual > auto,
    # vtt trước) theo thứ tự bảng chữ để chạy lặp lại được (không lệ dict order).
    for mapping in (manual, auto):
        for code in sorted(mapping or {}):
            t = _pick_from(mapping, code)
            if t:
                return t
    return None


# ------------------------------------------------------------------ lấy track

def fetch_captions(url: str, lang: str | None = None, *,
                   info_fn=None, fetch_fn=None) -> list[TranscriptSegment] | None:
    """Lấy phụ đề YouTube → list[TranscriptSegment]. None = không có track phù hợp.

    Trả None (KHÔNG raise) khi video nghèo caption — caller quyết định rơi về
    Whisper (`sub_source=auto`) hay fail thân thiện (`sub_source=youtube`).
    `yt_dlp` import local: thiếu package → coi như không có caption (auto path).
    """
    if info_fn is None:
        try:
            import yt_dlp
        except ImportError:
            return None

        def info_fn(u: str, opts: dict):
            with yt_dlp.YoutubeDL(opts) as ydl:
                return ydl.extract_info(u, download=False)

        def fetch_fn(track_url: str) -> str:
            import httpx

            return httpx.get(track_url, timeout=30.0).text

    info = info_fn(url, {"skip_download": True, "noplaylist": True,
                         "quiet": True, "no_warnings": True})
    entry = select_track(info.get("subtitles") or {},
                         info.get("automatic_captions") or {}, lang)
    if not entry:
        return None
    return parse_vtt(fetch_fn(entry["url"]))


# ------------------------------------------------------------------ parse VTT

_WORD_TS = re.compile(r"<(\d{2}:\d{2}:\d{2}\.\d{3})>")
_CUE_TIME = re.compile(r"^(\d{2}:\d{2}:\d{2}\.\d{3})\s*-->\s*(\d{2}:\d{2}:\d{2}\.\d{3})")
_TAG = re.compile(r"<[^>]+>")
_SENTENCE_END = ".!?。！？"


def _ts(s: str) -> float:
    h, m, sec = s.split(":")
    return int(h) * 3600 + int(m) * 60 + float(sec)


def _clean(text: str) -> str:
    return _TAG.sub("", text or "").replace("&nbsp;", " ").strip()


def _iter_cues(vtt_text: str):
    """Duyệt cue VTT THẬT SỰ bằng tay.

    Vì sao không dùng pysubs2: parser VTT của nó rối với inline word-timestamp
    (đã gặp thật — cue bắt đầu bằng `<00:00:02.400>` bị coi là "missed subtitle
    start", text bị rỗng, event bị chia sai). VTT YouTube là định dạng rất đơn
    giản: dòng thời gian `-->` + các dòng nội dung, các cue ngăn bởi dòng trống
    — tự quét là chắc chắn hơn.
    """
    lines = (vtt_text or "").splitlines()
    i = 0
    while i < len(lines):
        m = _CUE_TIME.match(lines[i].strip())
        if m is None:
            i += 1  # header (WEBVTT/NOTE) hoặc dòng id cue — bỏ qua
            continue
        start, end = _ts(m.group(1)), _ts(m.group(2))
        i += 1
        body: list[str] = []
        while i < len(lines) and lines[i].strip() != "":
            body.append(lines[i])
            i += 1
        yield start, end, "\n".join(body)


def parse_vtt(vtt_text: str) -> list[TranscriptSegment]:
    """VTT → segments. Tự phát hiện 2 dạng:

    - word-level (auto-caption YouTube có mốc `<00:00:01.399>` inline):
      ghép từ thành câu tại dấu câu — mốc từng từ giữ nguyên (A4 dùng để
      tách cue đúng ranh giới từ); từ lặp giữa các cue ROLLING được khử trùng
      lặp theo (text, mốc giờ);
    - block-level (manual caption thường): mỗi cue là 1 segment, strip tag.
    """
    cues = list(_iter_cues(vtt_text))
    head = "\n".join(body for _, _, body in cues[:10])
    if _WORD_TS.search(head):
        return _parse_word_level(cues)
    out: list[TranscriptSegment] = []
    for start, end, body in cues:
        txt = _clean(body)
        if not txt or (out and txt == out[-1].text and start == out[-1].start):
            continue
        out.append(TranscriptSegment(start, end, txt))
    return out


def _parse_word_level(cues) -> list[TranscriptSegment]:
    """Word-level: tách từng `<ts> từ`, end = start của từ kế (YouTube rolling
    captions báo thời lượng bằng mốc từ sau), ghép câu tại dấu câu. Từ lặp do
    cue ROLLING (cùng chữ + cùng mốc giờ xuất hiện ở cue kế) bị bỏ."""
    words: list[Word] = []
    seen: set[tuple[str, float]] = set()
    for _start, _end, body in cues:
        cur_ts = _start
        parts = re.split(r"(<\d{2}:\d{2}:\d{2}\.\d{3}>)", body or "")
        for p in parts:
            p = p.strip()
            if not p:
                continue
            m = re.fullmatch(r"<(\d{2}:\d{2}:\d{2}\.\d{3})>", p)
            if m:
                cur_ts = _ts(m.group(1))
                continue
            for tok in _clean(p).split():
                key = (tok, round(cur_ts, 3))
                if key in seen:
                    continue  # cue rolling lặp lại từ đã đọc
                seen.add(key)
                words.append(Word(cur_ts, cur_ts, tok))
    for i, w in enumerate(words):
        w.end = words[i + 1].start if i + 1 < len(words) else w.start + 0.5

    segs: list[TranscriptSegment] = []
    cur: list[Word] = []

    def flush() -> None:
        if not cur:
            return
        text = " ".join(w.text for w in cur).strip()
        if text:
            segs.append(TranscriptSegment(cur[0].start, cur[-1].end, text,
                                          None, list(cur)))
        cur.clear()

    for w in words:
        cur.append(w)
        span = w.end - cur[0].start
        if w.text[-1:] in _SENTENCE_END or len(cur) >= 30 or span >= 20.0:
            flush()
    flush()
    return segs


def selftest() -> None:
    """Selftest OFFLINE — fake metadata + VTT chuỗi, không đụng mạng."""
    # 1. canonical lang
    assert canonical_lang("iw") == "he"
    assert canonical_lang("zh-Hans") == "zh"
    assert canonical_lang("zh_CN") == "zh"
    assert canonical_lang("vi-VN") == "vi-vn"
    assert canonical_lang(None) == ""
    print("1. canonical_lang ................................. OK")

    # 2. select_track — thứ tự ưu tiên port OpenCreator
    manual = {"vi": [{"ext": "vtt", "url": "https://c/manual?v=1"},
                     {"ext": "srv3", "url": "https://c/manual2"}]}
    auto = {"vi": [{"ext": "vtt", "url": "https://c/auto?tlang=en"},   # ĐÃ DỊCH — loại
                   {"ext": "vtt", "url": "https://c/auto"},
                   {"ext": "srv3", "url": "https://c/auto2"}],
            "vi-orig": [{"ext": "vtt", "url": "https://c/orig"}]}
    t = select_track(manual, auto, "vi")
    assert t["url"] == "https://c/orig", t            # auto -orig thắng
    t = select_track({}, {}, "vi")
    assert t is None, "không có track nào → None (rơi về Whisper)"
    t = select_track(manual, {}, "vi")
    assert t["url"] == "https://c/manual?v=1", t     # manual ưu tiên khi không có auto
    # auto có bản tlang (dịch sẵn) — loại, rơi xuống auto thường
    t = select_track({}, {"vi": [{"ext": "vtt", "url": "https://c/x?tlang=en"},
                                 {"ext": "vtt", "url": "https://c/x"}]}, "vi")
    assert t["url"] == "https://c/x", t
    # lang rỗng: 1 track manual duy nhất được chọn
    t = select_track({"en": [{"ext": "vtt", "url": "https://c/m-en"}]}, {}, None)
    assert t["url"] == "https://c/m-en", t
    print("2. select_track ưu tiên orig > manual > auto ...... OK")

    # 3. parse block-level (manual caption)
    block = """WEBVTT

00:00:00.000 --> 00:00:02.500
Xin chào <c>đại</c> gia

00:00:02.500 --> 00:00:05.000
Video thử nghiệm
"""
    segs = parse_vtt(block)
    assert len(segs) == 2 and segs[0].text == "Xin chào đại gia", segs
    assert (segs[0].start, segs[0].end) == (0.0, 2.5), segs[0]
    assert segs[0].words is None
    print("3. parse block-level strip tag .................... OK")

    # 4. parse word-level (auto-caption có mốc inline) — ghép câu
    word = """WEBVTT

00:00:00.000 --> 00:00:02.400
<00:00:00.000><c> Hôm</c><00:00:00.500><c> nay</c><00:00:01.000><c> trời</c><00:00:01.500><c> đẹp.</c>

00:00:02.400 --> 00:00:04.000
<00:00:02.400><c> Đi</c><00:00:02.900><c> chơi!</c>
"""
    segs = parse_vtt(word)
    assert len(segs) == 2, segs
    assert segs[0].text == "Hôm nay trời đẹp.", segs[0].text
    assert segs[0].words and len(segs[0].words) == 4, segs[0].words
    assert segs[0].words[0].start == 0.0 and abs(segs[0].words[0].end - 0.5) < 1e-6
    assert segs[0].words[-1].text == "đẹp."
    assert abs(segs[1].start - 2.4) < 1e-6, segs[1].start

    # 4b. cue ROLLING — cue sau lặp lại từ của cue trước (cùng chữ + mốc giờ):
    # khử trùng lặp, không có "trời đẹp. trời đẹp."
    rolling = """WEBVTT

00:00:00.000 --> 00:00:02.000
<00:00:00.000><c> Hôm</c><00:00:00.500><c> nay</c><00:00:01.000><c> trời</c>

00:00:01.000 --> 00:00:03.000
<00:00:01.000><c> trời</c><00:00:01.500><c> đẹp.</c>
"""
    segs = parse_vtt(rolling)
    assert len(segs) == 1 and segs[0].text == "Hôm nay trời đẹp.", segs
    assert [w.text for w in segs[0].words] == ["Hôm", "nay", "trời", "đẹp."]
    print("4. parse word-level ghép câu + khử rolling ..... OK")

    # 5. fetch_captions fake — end-to-end không mạng
    info_fn = lambda u, o: {"subtitles": manual, "automatic_captions": auto}  # noqa: E731
    fetch_fn = lambda tu: block  # noqa: E731
    segs = fetch_captions("https://x.test/v", "vi", info_fn=info_fn, fetch_fn=fetch_fn)
    assert segs and segs[0].text == "Xin chào đại gia"
    assert fetch_captions("https://x.test/v", "xx", info_fn=info_fn, fetch_fn=fetch_fn) \
        is None, "lang không có track → None"
    print("5. fetch_captions end-to-end fake ................. OK")

    print("YOUTUBE SUBS SELFTEST PASSED")


if __name__ == "__main__":
    selftest()
