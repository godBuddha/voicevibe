r"""B3+B4 — job `render`: burn phụ đề song ngữ 2 style + cắt dọc 9:16 + banner.

Port từ OpenCreator `internal/service/srt_embed.go` + `render_stage.go`
(Apache-2.0) — ghi nguồn từng phần:

  B3 — Burn phụ đề ASS 2 style (`srt_embed.go:767-778`):
    Cả 2 dòng nằm trong MỘT Dialogue event style "Major"; dòng 2 đổi style
    inline bằng tag `{\rMinor}` + `\N` → 2 dòng song ngữ KHÔNG CHỒNG nhau
    (khác cách 2 event riêng — 2 event riêng chỗ đệm thiếu là đè nhau).
  - Style port `subtitle_style/style.go`: Major fontsize 14 / Minor 10 trong
    không gian 384×288; PrimaryColor #FFBF00 (vàng hổ phách); outline 2.5/1.5;
    Alignment 2 (bottom-center); KHÔNG ghi PlayResX/Y — libass tự xử lý scale,
    một code path cho mọi độ phân giải (720p ngang, 720×1280 dọc).
  - Wrap theo CHIỀU RỘNG HIỂN THỊ (`srt_embed.go:467-501`): hệ số rune-width
    space .33 / CJK 1.0 / Thai .92 / wide .95 / CHỮ HOA .66 / thường+số .56 /
    dấu .38 / default .62; `maxLineWidth = (scaledWidth − margins) × 0.92` với
    width chuẩn hoá về không gian 384.
    MỞ RỘNG so với OpenCreator: họ BỎ wrap latin (trả 1 dòng — tệ với tiếng
    Việt dài); VoiceVibe wrap THEO TỪ, greedy fill tới trần thì xuống dòng.

  B4 — Render dọc 9:16 (`srt_embed.go:1027-1035`):
    scale=720:1280:force_original_aspect_ratio=decrease (giữ aspect),
    pad=720:1280:(ow-iw)/2:250 (video đẩy xuống y=250, đầu dành cho banner),
    banner dải đen 250px + 2 dòng chữ vàng (major y=120 fs44, minor y=178
    fs30). KHÁC OpenCreator: banner vẽ bằng Pillow → PNG → `overlay` (họ dùng
    drawtext — escape chuỗi tiếng Việt có dấu là nguồn bug kinh điển); encode
    dùng `-crf 20` thay `-b:v 7587k` (chất lượng ổn định hơn theo chiều dài).

  Burn ffmpeg (`render_stage.go:69-75`): `-vf ass=filename='…' -c:v libx264
  -preset fast` + escape path `\\ ' : , [ ]`.

Thứ tự stage (kế hoạch D3): vertical TRƯỚC burn — phụ đề đo bề rộng theo frame
DỌC 720×1280 khi cả hai bật (khớp OpenCreator: video dọc mới được burn).
"""
from __future__ import annotations

import json
import hashlib
import math
import os
import subprocess

from .manifest import JobCancelled, Manifest, atomic_write_json

RENDER_STAGES = ("prepare", "subtitles", "vertical", "burn")


def render_fingerprint(material: dict) -> str:
    """Vân tay RIÊNG của render — dùng TOÀN BỘ material truyền vào.

    Vì sao không dùng `params_fingerprint`: nó đọc danh sách key tường minh của
    dub (ngôn ngữ/giọng/prompt…) — các key render (banner, vertical, cues) sẽ
    bị BỎ QUÊ âm thầm → đổi banner giữa hai lần chạy tái dùng sổ tay cũ (bẫy
    fingerprint số 3 của kế hoạch, đúng dạng bẫy). render soi mọi key nó đưa.
    """
    return hashlib.sha256(
        json.dumps(material, ensure_ascii=False, sort_keys=True, default=str)
        .encode("utf-8")).hexdigest()


VERT_W, VERT_H = 720, 1280
BANNER_H = 250
BANNER_MAJOR_Y, BANNER_MINOR_Y = 120, 178
BANNER_MAJOR_FS, BANNER_MINOR_FS = 44, 30
BANNER_COLOR = (255, 255, 0)  # vàng — khớp fontcolor=yellow của OpenCreator

ASS_PLAYRES_W, ASS_PLAYRES_H = 384, 288
ASS_SAFETY = 0.92
ASS_MARGINS = 10  # MarginL/R của style gốc

MAJOR_FS, MINOR_FS = 14, 10  # không gian 384×288 (port style.go)

# ------------------------------------------------------------------ wrap

def _rune_width(r: str, fontsize: float) -> float:
    """Chiều rộng hiển thị của một rune theo % fontSize — port
    `srt_embed.go:480-501` (bảng hệ số port nguyên vẹn)."""
    if r.isspace():
        return fontsize * 0.33
    o = ord(r)
    if (0x4E00 <= o <= 0x9FFF or 0x3400 <= o <= 0x4DBF     # CJK Ideograph
            or 0x3040 <= o <= 0x30FF or 0xAC00 <= o <= 0xD7AF):  # Kana/Hangul
        return fontsize * 1.0
    if 0x0E00 <= o <= 0x0E7F:                               # Thai
        return fontsize * 0.92
    if 0xFF01 <= o <= 0xFF60 or 0x3000 <= o <= 0x303F:      # Fullwidth
        return fontsize * 0.95
    if "A" <= r <= "Z":
        return fontsize * 0.66
    if "a" <= r <= "z" or "0" <= r <= "9":
        return fontsize * 0.56
    if not r.isalnum():
        return fontsize * 0.38
    return fontsize * 0.62


def _is_cjk(r: str) -> bool:
    o = ord(r)
    return (0x4E00 <= o <= 0x9FFF or 0x3400 <= o <= 0x4DBF
            or 0x3040 <= o <= 0x30FF or 0xAC00 <= o <= 0xD7AF)


def text_width(text: str, fontsize: float) -> float:
    return sum(_rune_width(c, fontsize) for c in text)


def max_units(frame_w: int, frame_h: int, fontsize: float) -> float:
    """Độ dài tối đa (đơn vị width) một dòng được phép có — port
    `newSubtitleWrapConfig` srt_embed.go:248-272: chuẩn hoá frame về không gian
    384×288, trừ lề, nhân hệ số an toàn 0.92, sàn = fontSize."""
    scale = min(ASS_PLAYRES_W / frame_w, ASS_PLAYRES_H / frame_h)
    width = math.floor(frame_w * scale)
    usable = (width - ASS_MARGINS * 2) * ASS_SAFETY
    return max(usable, fontsize)


def wrap_line(text: str, *, fontsize: float, max_u: float) -> list[str]:
    """Chia 1 dòng thành nhiều dòng theo CHIỀU RỘNG HIỂN THỊ.

    Latin/tiếng Việt: greedy THEO TỪ (ngắt tại khoảng trắng — mở rộng so với
    OpenCreator bỏ wrap latin). CJK: greedy theo ký tự, không xuống dòng ngay
    trước dấu câu. Đã vừa 1 dòng → trả nguyên (như OpenCreator)."""
    if text_width(text, fontsize) <= max_u:
        return [text]
    if _is_cjk(text[:1]) or any(_is_cjk(c) for c in text):
        return _wrap_cjk(text, fontsize, max_u)
    return _wrap_latin(text, fontsize, max_u)


def _wrap_latin(text: str, fontsize: float, max_u: float) -> list[str]:
    words = text.split()
    lines: list[str] = []
    cur = ""
    for w in words:
        cand = f"{cur} {w}" if cur else w
        if text_width(cand, fontsize) <= max_u or not cur:
            cur = cand
        else:
            lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


_PUNCT = ".,;:!?。！？、）)」』"

def _wrap_cjk(text: str, fontsize: float, max_u: float) -> list[str]:
    lines: list[str] = []
    cur = ""
    cur_w = 0.0
    for ch in text:
        w = _rune_width(ch, fontsize)
        if cur and cur_w + w > max_u:
            # không để dấu câu bơ đơn ở đầu dòng kế
            if cur[-1] not in _PUNCT and ch in _PUNCT:
                lines.append(cur + ch)
                cur, cur_w = "", 0.0
                continue
            lines.append(cur)
            cur, cur_w = ch, w
        else:
            cur += ch
            cur_w += w
    if cur:
        lines.append(cur)
    return lines


# ------------------------------------------------------------------ ASS 2 style

def build_bilingual_ass(cues, out_path: str, *, frame_w: int, frame_h: int,
                        vertical: bool = False) -> None:
    r"""Ghi file ASS song ngữ 2 style. `cues`: list của (start, end, lines[]).

    Port kỹ thuật `srt_embed.go:767-778`: MỘT Dialogue style Major; dòng 2
    `{\rMinor}` + `\N`. 1 dòng → chỉ Major. Dọc dùng MarginV riêng của OpenCreator
    (101/92) để chừa banner.
    """
    import pysubs2

    subs = pysubs2.SSAFile()
    subs.info["Title"] = "VoiceVibe"
    # KHÔNG ghi PlayResX/Y (mặc định 384×288) — một code path mọi độ phân giải
    margin_v_major, margin_v_minor = (101, 92) if vertical else (30, 20)
    subs.styles["Major"] = pysubs2.SSAStyle(
        fontname="Noto Sans", fontsize=MAJOR_FS, bold=True,
        primarycolor=pysubs2.Color(0xFF, 0xBF, 0x00),   # #FFBF00 vàng hổ phách
        outlinecolor=pysubs2.Color(0, 0, 0), backcolor=pysubs2.Color(0, 0, 0, 100),
        borderstyle=1, outline=2.5, shadow=1.5,
        alignment=pysubs2.Alignment.BOTTOM_CENTER,
        marginl=ASS_MARGINS, marginr=ASS_MARGINS, marginv=margin_v_major)
    subs.styles["Minor"] = pysubs2.SSAStyle(
        fontname="Noto Sans", fontsize=MINOR_FS,
        primarycolor=pysubs2.Color(0xFF, 0xBF, 0x00),
        outlinecolor=pysubs2.Color(0, 0, 0), backcolor=pysubs2.Color(0, 0, 0, 100),
        borderstyle=1, outline=1.5, shadow=1.5,
        alignment=pysubs2.Alignment.BOTTOM_CENTER,
        marginl=ASS_MARGINS, marginr=ASS_MARGINS, marginv=margin_v_minor)

    for start, end, lines in cues:
        if not lines or not any(ln.strip() for ln in lines):
            continue
        max_major = max_units(frame_w, frame_h, MAJOR_FS)
        max_minor = max_units(frame_w, frame_h, MINOR_FS)
        major = wrap_line(_strip_tags(lines[0]), fontsize=MAJOR_FS, max_u=max_major)
        minor = [_strip_tags(ln) for ln in lines[1:]]
        body = r"{\rMajor}" + r"\N".join(major)
        if minor:
            body += r"\N{\rMinor}" + r"\N".join(minor)
        ev = pysubs2.SSAEvent(start=pysubs2.make_time(s=start),
                              end=pysubs2.make_time(s=end), text=body)
        ev.style = "Major"
        subs.append(ev)
    subs.save(out_path, format_="ass")


def _strip_tags(text: str) -> str:
    """Strip tag inline (VTT YouTube `<c>`/`<ts>`, ASS `{...}`, HTML)."""
    import re

    t = re.sub(r"<[^>]+>", "", text or "")
    t = re.sub(r"\{[^}]*\}", "", t)
    return t.replace("\\N", "\n").replace("\n", " ").replace("&nbsp;", " ").strip()


def load_cues_from_text(text: str, *, ext: str = "") -> list[tuple]:
    """Parse phụ đề (.srt/.vtt/.ass) → [(start, end, [dòng…])].

    pysubs2 đọc được cả 3 định dạng; mỗi event 1 cue, text `\\N`/newline tách
    dòng. Trả THỨ TỰ gốc (pysubs2 sắp theo thời gian)."""
    import pysubs2

    subs = pysubs2.SSAFile.from_string(text, format_=ext or None)
    cues: list[tuple] = []
    for ev in subs:
        if getattr(ev, "is_comment", False):
            continue
        lines = [ln.strip() for ln in (_strip_tags(ev.text)).split("\n") if ln.strip()]
        if lines:
            cues.append((ev.start / 1000.0, ev.end / 1000.0, lines))
    return cues


# ------------------------------------------------------------------ banner + cmd

def _find_font() -> str | None:
    """TTF đầu tiên tìm thấy (host/dev khác nhau — dùng fontconfig của hệ)."""
    candidates = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/noto/NotoSans-Bold.ttf",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    ]
    for p in candidates:
        if os.path.exists(p):
            return p
    try:
        out = subprocess.run(["fc-match", "-f", "%{file}", "sans:bold"],
                             capture_output=True, text=True, timeout=10)
        if out.returncode == 0 and out.stdout.strip():
            return out.stdout.strip()
    except Exception:  # noqa: BLE001 — không fc-match → fallback load_default
        pass
    return None


def render_banner_png(banner: dict, out_path: str) -> None:
    """Banner 720×250: nền đen + 2 dòng chữ vàng (Pillow — né escape drawtext).

    major y=120 fs44 / minor y=178 fs30, căn giữa — khớp drawtext gốc của
    OpenCreator `buildVerticalFilter`."""
    from PIL import Image, ImageDraw, ImageFont

    img = Image.new("RGB", (VERT_W, BANNER_H), (0, 0, 0))
    draw = ImageDraw.Draw(img)
    font_path = _find_font()
    major = banner.get("major") or ""
    minor = banner.get("minor") or ""
    if font_path:
        f_major = ImageFont.truetype(font_path, BANNER_MAJOR_FS)
        f_minor = ImageFont.truetype(font_path, BANNER_MINOR_FS)
    else:  # không có TTF — bitmap default (ASCII) — banner vẫn xuất, ghi chú ở test
        f_major = f_minor = ImageFont.load_default()
    for text, y, fs, font in ((major, BANNER_MAJOR_Y, BANNER_MAJOR_FS, f_major),
                              (minor, BANNER_MINOR_Y, BANNER_MINOR_FS, f_minor)):
        if not text:
            continue
        w = draw.textlength(text, font=font)
        draw.text(((VERT_W - w) / 2, y), text[:60], font=font, fill=BANNER_COLOR)
    img.save(out_path, format="PNG")


def escape_ass_path(path: str) -> str:
    """Escape path cho filter `ass=` — port `render_stage.go:42-52`."""
    for ch, esc in (("\\", "\\\\"), ("'", "\\'"), (":", "\\:"), (",", "\\,"),
                    ("[", "\\["), ("]", "\\]")):
        path = path.replace(ch, esc)
    return path


def burn_cmd(video_in: str, ass_path: str, video_out: str) -> list[str]:
    """Port `render_stage.go:54-75`: filter `ass=` (KHÔNG subtitles=force_style —
    style nằm trong file ASS) + libx264 fast + aac 192k."""
    return ["ffmpeg", "-y", "-i", video_in,
            "-vf", f"ass=filename='{escape_ass_path(ass_path)}'",
            "-c:v", "libx264", "-preset", "fast", "-crf", "20",
            "-c:a", "aac", "-b:a", "192k", video_out]


def vertical_cmd(video_in: str, video_out: str, banner_png: str | None = None) -> list[str]:
    """Port `buildVerticalFilter` srt_embed.go:1027-1035 + `-r 30` của
    `convertToVertical` (crf thay bitrate 7587k — chất lượng ổn định theo chiều).

    BẢN DỊCH KỸ THUẬT: banner là `overlay` (filter 2 input) — KHÔNG nhét được
    vào `-vf` đơn; có banner thì dùng `-filter_complex`, không banner giữ `-vf`
    đơn (scale+pad, đích đến y=250 — phần trên 250px là đen tự nhiên vì pad)."""
    base = (f"scale={VERT_W}:{VERT_H}:force_original_aspect_ratio=decrease,"
            f"pad={VERT_W}:{VERT_H}:(ow-iw)/2:{BANNER_H}")
    if not banner_png:
        return ["ffmpeg", "-y", "-i", video_in, "-vf", base, "-r", "30",
                "-c:v", "libx264", "-preset", "fast", "-crf", "20",
                "-c:a", "aac", "-b:a", "192k", video_out]
    return ["ffmpeg", "-y", "-i", video_in, "-i", banner_png,
            "-filter_complex",
            f"[0:v]{base}[bg];[bg][1:v]overlay=0:0[v]",
            "-map", "[v]", "-map", "0:a?", "-r", "30",
            "-c:v", "libx264", "-preset", "fast", "-crf", "20",
            "-c:a", "aac", "-b:a", "192k", video_out]


def _probe_dims(path: str) -> tuple[int, int]:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0",
         "-show_entries", "stream=width,height", "-of", "csv=p=0", path],
        capture_output=True, text=True, check=True)
    w, h = out.stdout.strip().split(",")[:2]
    return int(w), int(h)


def run_render(source: str, *, burn_subtitles: bool = False, vertical: bool = False,
               banner: dict | None = None, cues_text: str | None = None,
               cues_ext: str = "", workdir: str, job_id: str,
               key_prefix: str, storage,
               abort_check=None, progress_cb=None) -> str:
    """Orchestrate job render — manifest resume như dub (A1).

    Stage tắt (toggle off) thì KHÔNG mark — resume không nhảy cóc qua stage
    chưa chạy. Trả storage key kết quả (`{key_prefix}render.mp4`).
    """
    def _report(pct: int, msg: str) -> None:
        if progress_cb:
            progress_cb(pct, msg)

    def _abort() -> None:
        if abort_check is not None and abort_check():
            raise JobCancelled("job render bị hủy giữa đường")

    # Vân tay: mọi tham số ảnh hưởng hình ảnh đầu ra. backend_tag = "render"
    # (không có LLM/translate trong pipeline này).
    fp = render_fingerprint(
        {"media_url": source, "burn_subtitles": burn_subtitles,
         "vertical": vertical,
         "banner": {k: banner.get(k, "") for k in ("major", "minor")} if banner else {},
         "cues_fingerprint": _cues_sha(cues_text or "")})
    manifest = (Manifest.load_or_none(workdir, fp)
                or Manifest.create(workdir, job_id, fp, job_type="render"))
    os.makedirs(workdir, exist_ok=True)

    # ---------------------------------------------------------- 1. prepare
    if not manifest.stage_ok("prepare"):
        _abort()
        _report(5, "kiểm tra nguồn")
        w, h = _probe_dims(source)
        manifest.outputs["width"], manifest.outputs["height"] = w, h
        manifest.mark("prepare")
    w = int(manifest.outputs.get("width") or VERT_W)
    h = int(manifest.outputs.get("height") or VERT_H)

    # ---------------------------------------------------------- 2. subtitles
    ass_path = ""
    if burn_subtitles:
        if not manifest.stage_ok("subtitles"):
            _abort()
            _report(15, "dựng phụ đề 2 style")
            cues = load_cues_from_text(cues_text or "", ext=cues_ext)
            if not cues:
                manifest.mark("subtitles", error="phụ đề rỗng")
                raise ValueError("phụ đề đầu vào rỗng hoặc không đọc được")
            # Dọc trước burn: phụ đề đo bề rộng theo frame ĐÍCH (720×1280) —
            # khớp OpenCreator (video dọc mới được burn).
            vw, vh = (VERT_W, VERT_H) if vertical else (w, h)
            ass_path = os.path.join(workdir, "subs.ass")
            build_bilingual_ass(cues, ass_path, frame_w=vw, frame_h=vh,
                                vertical=vertical)
            manifest.outputs["ass"] = "subs.ass"
            manifest.mark("subtitles")
        ass_path = os.path.join(workdir, str(manifest.outputs.get("ass") or "subs.ass"))

    # ---------------------------------------------------------- 3. vertical
    cur = source
    if vertical:
        if not manifest.stage_ok("vertical"):
            _abort()
            _report(35, "cắt dọc 9:16 + banner")
            banner_png = ""
            if banner:
                banner_png = os.path.join(workdir, "banner.png")
                render_banner_png(banner, banner_png)
            out = os.path.join(workdir, "vertical.mp4")
            res = subprocess.run(vertical_cmd(source, out, banner_png or None),
                                 capture_output=True, text=True)
            if res.returncode != 0:
                manifest.mark("vertical", error=res.stderr[-300:])
                raise RuntimeError("cắt dọc 9:16 thất bại: "
                                   + res.stderr[-200:])
            manifest.outputs["vertical"] = "vertical.mp4"
            manifest.mark("vertical")
        cur = os.path.join(workdir, str(manifest.outputs.get("vertical") or "vertical.mp4"))

    # ---------------------------------------------------------- 4. burn
    out_path = os.path.join(workdir, "render.mp4")
    if not manifest.stage_ok("burn"):
        _abort()
        _report(60, "in phụ đề vào video" if burn_subtitles else "encode")
        if burn_subtitles:
            cmd = burn_cmd(cur, ass_path, out_path)
        else:  # chỉ vertical (hoặc không gì cả): encode lại cùng chất lượng
            cmd = ["ffmpeg", "-y", "-i", cur, "-c:v", "libx264", "-preset", "fast",
                   "-crf", "20", "-c:a", "aac", "-b:a", "192k", out_path]
        res = subprocess.run(cmd, capture_output=True, text=True)
        if res.returncode != 0:
            manifest.mark("burn", error=res.stderr[-300:])
            raise RuntimeError("encode thất bại: " + res.stderr[-200:])
        manifest.mark("burn")
    key = f"{key_prefix}render.mp4"
    storage.put_from_file(key, out_path)
    _report(99, "xong")
    return key


def _cues_sha(text: str) -> str:
    import hashlib

    return hashlib.sha256((text or "").encode()).hexdigest()


def selftest() -> None:
    """Selftest OFFLINE — wrap + ASS + cmd; encode thật chỉ khi có ffmpeg."""
    # 1. bảng hệ số rune-width (port srt_embed.go:480-501)
    fs = 10.0
    assert _rune_width(" ", fs) == fs * 0.33
    assert _rune_width("A", fs) == fs * 0.66
    assert _rune_width("a", fs) == fs * 0.56
    assert _rune_width("5", fs) == fs * 0.56
    assert _rune_width("中", fs) == fs * 1.0
    assert _rune_width("ก", fs) == fs * 0.92       # Thai
    assert _rune_width(",", fs) == fs * 0.38
    print("1. bảng hệ số rune-width port nguyên vẹn ..... OK")

    # 2. max_units chuẩn hoá 384-space (ngang vs dọc)
    u_land = max_units(1920, 1080, MAJOR_FS)
    assert u_land == max((384 - 20) * 0.92, MAJOR_FS), u_land
    u_vert = max_units(720, 1280, MAJOR_FS)
    scale = min(384 / 720, 288 / 1280)
    assert abs(u_vert - (math.floor(720 * scale) - 20) * 0.92) < 1e-6, u_vert
    assert u_vert < u_land, "frame dọc phải hẹp hơn (maxUnits nhỏ hơn)"
    print("2. max_units 384-space ngang > dọc ................ OK")

    # 3. wrap theo từ (latin/việt) + theo ký tự (CJK) + 1 dòng nguyên vẹn
    short = "Xin chào"
    assert wrap_line(short, fontsize=10.0, max_u=1000.0) == [short], "vừa 1 dòng trả nguyên"
    lines = wrap_line("xin chào các bạn đây là một câu dài vậy", fontsize=10.0, max_u=60.0)
    assert len(lines) >= 2, lines
    assert all(text_width(ln, 10.0) <= 60.0 + 1e-6 for ln in lines), lines
    # mỗi dòng không có từ bị CẮT ĐÔI (wrap theo từ)
    joined = " ".join(lines).split()
    assert joined == "xin chào các bạn đây là một câu dài vậy".split(), lines
    cjk = wrap_line("这是一个很长的中文句子需要换行", fontsize=10.0, max_u=45.0)
    assert len(cjk) >= 2 and all(text_width(l, 10.0) <= 45.0 + 1e-6 for l in cjk), cjk
    print("3. wrap latin theo từ + CJK theo ký tự ............ OK")

    # 4. ASS 2 style: 1 Dialogue chứa {\rMajor} + {\rMinor} + \N
    import tempfile
    tmp = tempfile.mkdtemp(prefix="vv_render_")
    cues = [(0.0, 2.0, ["Xin chào các bạn", "Hello everyone"]),
            (2.0, 4.0, ["Chỉ một dòng"])]
    ass = os.path.join(tmp, "subs.ass")
    build_bilingual_ass(cues, ass, frame_w=1920, frame_h=1080)
    txt = open(ass, encoding="utf-8").read()
    assert "[V4+ Styles]" in txt and "Major" in txt and "Minor" in txt
    dialogues = [l for l in txt.splitlines() if l.startswith("Dialogue:")]
    assert len(dialogues) == 2, dialogues
    assert r"{\rMajor}Xin chào các bạn" in dialogues[0], dialogues[0]
    assert r"\N{\rMinor}Hello everyone" in dialogues[0], dialogues[0]
    assert r"{\rMinor}" not in dialogues[1], "1 dòng → không Minor"
    assert "PlayResX" not in txt, "KHÔNG ghi PlayRes (mặc định 384×288)"
    assert "FFBF00" in txt or "&H00BF00FF" in txt.upper() or "BF00FF" in txt.upper() \
        or "00BFFF" in txt.upper(), txt.splitlines()[4:12]
    print("4. ASS 2 style 1 Dialogue + màu #FFBF00 .......... OK")

    # 5. load cues từ SRT + strip tag
    srt = ("1\n00:00:00,000 --> 00:00:02,000\nDòng <c>tag</c> một\n"
           "2\n00:00:02,000 --> 00:00:04,000\nDòng hai\n")
    cues = load_cues_from_text(srt, ext="srt")
    assert len(cues) == 2 and cues[0][2] == ["Dòng tag một"], cues
    print("5. load cues SRT + strip tag ...................... OK")

    # 6. cmd + escape
    vf = [a for a in burn_cmd("/a'b.mp4", "/x y,subs.ass", "out.mp4")
          if a.startswith("ass=")][0]
    assert "\\," in vf and "\\:" not in vf, vf
    vf_q = [a for a in burn_cmd("/a.mp4", "/x'y:s.ass", "out.mp4")
            if a.startswith("ass=")][0]
    assert "\\'" in vf_q and "\\:" in vf_q, vf_q
    v = vertical_cmd("in.mp4", "out.mp4", None)
    assert "force_original_aspect_ratio=decrease" in v[v.index("-vf") + 1]
    assert v[v.index("-vf") + 1].count("overlay=") == 0
    v2 = vertical_cmd("in.mp4", "out.mp4", "banner.png")
    fc = v2[v2.index("-filter_complex") + 1]
    assert "overlay=0:0" in fc and "force_original_aspect_ratio=decrease" in fc, fc
    assert v2[v2.index("-map") + 1] == "[v]" and "-r" in v2 and "30" in v2
    print("6. burn/vertical cmd + escape path ................ OK")

    # 7. banner Pillow (nếu có pillow + font)
    try:
        from PIL import Image  # noqa: F401
        png = os.path.join(tmp, "banner.png")
        render_banner_png({"major": "Tiêu đề chính", "minor": "Tiêu đề phụ"}, png)
        img = Image.open(png)
        assert img.size == (720, 250), img.size
    except ImportError:
        print("7. banner PNG — BỎ QUA (thiếu pillow) ............. OK")
    else:
        print("7. banner PNG 720×250 ............................ OK")

    # 8. run_render e2e với ffmpeg thật (testsrc 1s → dọc + burn) — skip khi không ffmpeg
    if HAVE_FFMPEG:
        from ..storage import LocalStorage

        src = os.path.join(tmp, "src.mp4")
        subprocess.run(["ffmpeg", "-y", "-f", "lavfi",
                        "-i", "testsrc=duration=1:size=320x180:rate=10",
                        "-f", "lavfi", "-i", "sine=frequency=440:duration=1",
                        "-c:v", "libx264", "-c:a", "aac", src],
                       check=True, capture_output=True)
        st = LocalStorage(tmp)
        key = run_render(src, burn_subtitles=True, vertical=True,
                         banner={"major": "Tiêu đề", "minor": "Phụ"},
                         cues_text=srt, cues_ext="srt",
                         workdir=os.path.join(tmp, "work"), job_id="r1",
                         key_prefix="jobs/r1/", storage=st)
        assert key == "jobs/r1/render.mp4", key
        assert st.exists(key) and len(st.get(key)) > 1000, "file render phải thật"
        # resume: chạy lại phải SKIP (mọi stage ok) — storage không đụng nữa
        key2 = run_render(src, burn_subtitles=True, vertical=True,
                          banner={"major": "Tiêu đề", "minor": "Phụ"},
                          cues_text=srt, cues_ext="srt",
                          workdir=os.path.join(tmp, "work"), job_id="r1",
                          key_prefix="jobs/r1/", storage=st)
        assert key2 == key
        # đổi banner → vân tay lệch → sổ cũ .stale, chạy lại từ đầu (đúng quy tắc A1)
        key3 = run_render(src, burn_subtitles=True, vertical=True,
                          banner={"major": "Khác", "minor": "Phụ"},
                          cues_text=srt, cues_ext="srt",
                          workdir=os.path.join(tmp, "work"), job_id="r1",
                          key_prefix="jobs/r1/", storage=st)
        assert key3 == key, "key giống nhau nhưng manifest đã được dựng lại"
        stale = [n for n in os.listdir(os.path.join(tmp, "work"))
                 if n.endswith(".stale")]
        assert stale, "sổ tay cũ phải đổi tên .stale"
        print("8. run_render e2e ffmpeg (dọc + burn + resume + drift) OK")
    else:
        print("8. run_render e2e — BỎ QUA (không ffmpeg) ......... OK")

    print("RENDER SELFTEST PASSED")


HAVE_FFMPEG = subprocess.run(["ffmpeg", "-version"], capture_output=True).returncode == 0


if __name__ == "__main__":
    selftest()
