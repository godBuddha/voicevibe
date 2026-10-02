"""B1 — Tải video/âm thanh từ URL bằng yt-dlp (nhập từ youwee, MIT).

Vì sao dùng CLI subprocess thay vì thư viện `yt_dlp.YoutubeDL`:
- Hủy giữa đường phải GIẾT ĐƯỢC cả nhóm tiến trình: yt-dlp có thể spawn
  aria2c/ffmpeg con. `Popen(start_new_session=True)` + `os.killpg` kill sạch
  cả nhóm — revoke Celery `terminate=True` chỉ giết tiến trình worker, để
  yt-dlp mồ côi là rác `.part` nằm luôn trên đĩa (đã gặp kiểu mồ côi ở docker
  deploy khác). Thư viện nhúng vào tiến trình worker không tách được nhóm.
- Progress phải đi qua `_record_progress` (DB) — đọc dòng stdout của CLI cho
  phép map % từng stream (video → audio → merge) một cách chủ động, không phụ
  thuộc hook callback của thư viện.
- Selftest chạy OFFLINE: `runner` injectable — CI không đụng mạng (guard rủi
  ro số 10 của kế hoạch).

Nguyên tắc vàng của youwee được giữ lại: KHÔNG tự làm danh mục site — để
yt-dlp quyết định, chỉ vá site khi gặp lỗi thật.

Giới hạn an toàn (youwee KHÔNG có — VoiceVibe làm tốt hơn):
- `MAX_DURATION_S` kiểm bằng Python SAU probe — KHÔNG dùng `--match-filter`,
  vì match_filter chỉ "bỏ qua" và exit 0: job tưởng thành công mà không có file.
- `--no-playlist` luôn bật (tải playlist cả trăm video là không kiểm soát).
- URL validate: chỉ http(s), từ chối URL bắt đầu bằng `-` (option injection).

Ladder format port nguyên văn `src-tauri/src/utils/format.rs` (mp4 ≤ chiều cao,
không chọn codec; bạnwee chọn codec h264 riêng nhưng VoiceVibe chỉ cần mp4 —
dub/mux đằng sau re-encode anyway).

Error map port `src-tauri/src/services/ytdlp.rs parse_ytdlp_error` — match
substring lowercase trên stderr, message tiếng Việt có gợi ý hành động.
"""
from __future__ import annotations

import json
import os
import signal
import subprocess
import sys

from .manifest import JobCancelled, atomic_write_json

# ------------------------------------------------------------------- ladder
# quality -> format string. Thứ tự fallback (dấu /) là của yt-dlp: candidate
# đầu thỏa mãn được chọn; rớt xuống candidate sau.
FORMAT_LADDER: dict[str, str] = {
    "1080": (
        "bestvideo[height<=1080][ext=mp4]+bestaudio[ext=m4a]/"
        "bestvideo[height<=1080]+bestaudio/"
        "best[height<=1080]/best"
    ),
    "720": (
        "bestvideo[height<=720][ext=mp4]+bestaudio[ext=m4a]/"
        "bestvideo[height<=720]+bestaudio/"
        "best[height<=720]/best"
    ),
    "480": (
        "bestvideo[height<=480][ext=mp4]+bestaudio[ext=m4a]/"
        "bestvideo[height<=480]+bestaudio/"
        "best[height<=480]/best"
    ),
    "audio": "bestaudio/best",
}
QUALITIES = ("1080", "720", "480", "audio")

MAX_DURATION_S = 7200  # 2 giờ — probe báo trước, chặn bằng Python (xem docstring)
PROBE_TIMEOUT_S = 60.0
SOCKET_TIMEOUT_S = 15  # per-connection — chống treo vĩnh viễn trên mạng hỏng

# ------------------------------------------------------- error map thân thiện
# Thứ tự = thứ tự ưu tiên match (đặc thù trước, chung sau). Port bảng của
# youwee `ytdlp.rs:472-621` — message gốc tiếng Anh, dịch tiếng Việt kèm gợi ý.
ERROR_MAP: list[tuple[str, str]] = [
    ("this version of yt-dlp has been deprecated",
     "yt-dlp đã quá cũ. Cập nhật trong container: pip install -U yt-dlp"),
    ("sign in to confirm your age",
     "Video giới hạn độ tuổi — cần cookies đăng nhập (Cài đặt → Tải video từ link)."),
    ("sign in to confirm",
     "YouTube yêu cầu xác thực (chống bot) — cần cookies đăng nhập "
     "(Cài đặt → Tải video từ link)."),
    ("private video",
     "Video riêng tư — cần cookies đăng nhập (Cài đặt → Tải video từ link)."),
    ("members-only", "Video chỉ dành cho thành viên trả phí của kênh."),
    ("join this channel", "Video chỉ dành cho thành viên của kênh."),
    ("video unavailable", "Video không tồn tại hoặc đã bị gỡ."),
    ("is not a valid url", "Đường link không hợp lệ."),
    ("unsupported url", "yt-dlp chưa hỗ trợ trang web này."),
    ("not available in your country",
     "Video chặn khu vực của bạn — thử cấu hình proxy (Cài đặt → Tải video từ link)."),
    ("geo", "Video chặn khu vực của bạn — thử cấu hình proxy."),
    ("429", "Bị giới hạn tốc độ — đợi vài phút rồi thử lại."),
    ("too many requests", "Bị giới hạn tốc độ — đợi vài phút rồi thử lại."),
    ("no subtitles", "Video không có phụ đề."),
    ("subtitles are disabled", "Video đã tắt phụ đề."),
    ("requested format is not available",
     "Không có bản ghi phù hợp mức chất lượng đã chọn — thử mức thấp hơn."),
    ("unable to download", "Lỗi mạng khi tải — kiểm tra kết nối rồi thử lại."),
    ("timed out", "Hết giờ kết nối — mạng chậm hoặc máy chủ chặn."),
    ("http error 403", "Máy chủ từ chối truy cập — có thể cần cookies."),
    ("http error 429", "Bị giới hạn tốc độ — đợi vài phút rồi thử lại."),
    ("connection", "Lỗi mạng — kiểm tra kết nối rồi thử lại."),
]


def human_error(stderr_text: str) -> str | None:
    """Match substring lowercase trên stderr → message người dùng hiểu được.

    Match THỨ TỰ trong ERROR_MAP (đặc thù trước). Trả None = lỗi lạ, caller
    nhét stderr gốc (cắt) vào message.
    """
    low = (stderr_text or "").lower()
    for pattern, msg in ERROR_MAP:
        if pattern in low:
            return msg
    return None


def validate_url(url: str) -> str:
    """Chặn URL xấu TRƯỚC khi đưa vào argv — pattern `utils/security.rs`."""
    u = (url or "").strip()
    if not u.lower().startswith(("http://", "https://")):
        raise ValueError("link phải là URL http/https")
    if u.startswith("-"):
        raise ValueError("link không được bắt đầu bằng dấu gạch")
    return u


def cookies_ok(path: str | None) -> bool:
    """File cookie chỉ nhận khi dòng đầu ĐÚNG header Netscape — port
    `youtube_cookies.go:15-24`: format khác (đơn giản là dán JSON cookie) sẽ
    khiến yt-dlp chết kiểu khó hiểu, fail sớm tại đây là kịp."""
    if not path:
        return False
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            return f.readline().startswith("# Netscape HTTP Cookie File")
    except OSError:
        return False


def _yt_extractor_args(url: str) -> list[str]:
    """Trick youwee (extractor-args) — YouTube chặn IP datacenter không cookie
    với client web mặc định ("Sign in to confirm you're not a bot"). Client
    `android` vẫn tải được ẩn danh (đã kiểm thật 03/10 với "Me at the zoo" —
    tv/ios/web_embedded đều chết). Chỉ áp cho youtube/youtu.be; site khác
    không đụng (nguyên tắc: yt-dlp quyết định)."""
    from urllib.parse import urlparse

    host = (urlparse(url).hostname or "").lower()
    if host in ("youtube.com", "www.youtube.com", "youtu.be", "m.youtube.com"):
        return ["--extractor-args", "youtube:player_client=android"]
    return []


def build_argv(url: str, dest_dir: str, quality: str, *,
               cookies_file: str | None = None, proxy: str | None = None) -> list[str]:
    """Lệnh yt-dlp đầy đủ. `--newline` để mỗi progress là MỘT dòng (parse %)."""
    if quality not in FORMAT_LADDER:
        raise ValueError(f"quality phải là một trong {list(QUALITIES)}")
    argv = [
        sys.executable, "-m", "yt_dlp",
        "--newline", "--no-warnings", "--no-playlist",
        "--socket-timeout", str(SOCKET_TIMEOUT_S),
        "--retries", "3", "--fragment-retries", "3",
        "--extractor-retries", "2", "--file-access-retries", "2",
        "--no-keep-video", "--no-keep-fragments", "--force-overwrites",
        "-f", FORMAT_LADDER[quality],
        "-o", os.path.join(dest_dir, "source.%(ext)s"),
    ]
    if quality == "audio":
        argv += ["-x", "--audio-format", "mp3", "--audio-quality", "192K"]
    if cookies_file:
        argv += ["--cookies", cookies_file]
    if proxy:
        argv += ["--proxy", proxy]
    argv += _yt_extractor_args(url)
    argv.append(url)
    return argv


def probe_argv(url: str, *, cookies_file: str | None = None,
               proxy: str | None = None) -> list[str]:
    argv = [sys.executable, "-m", "yt_dlp",
            "--dump-single-json", "--skip-download", "--no-playlist",
            "--no-warnings", "--socket-timeout", str(SOCKET_TIMEOUT_S)]
    if cookies_file:
        argv += ["--cookies", cookies_file]
    if proxy:
        argv += ["--proxy", proxy]
    argv += _yt_extractor_args(url)
    argv.append(url)
    return argv


def _probe_json(argv: list[str], *, timeout: float = PROBE_TIMEOUT_S,
                runner=None) -> dict:
    """Chạy probe → parse JSON. runner injectable cho selftest offline.

    Contract của runner: (code, stdout, stderr) — như subprocess.run.
    """
    if runner is None:
        res = subprocess.run(argv, capture_output=True, text=True, timeout=timeout)
        code, out, err = res.returncode, res.stdout, res.stderr
    else:
        code, out, err = runner(argv)
    if code != 0:
        msg = human_error(err) or (err or "probe thất bại").strip().splitlines()[-1]
        raise ValueError(msg[:300])
    try:
        return json.loads(out)
    except json.JSONDecodeError as exc:
        raise ValueError(f"không đọc được metadata từ link: {exc}") from exc


def probe(url: str, *, cookies_file: str | None = None, proxy: str | None = None,
          runner=None) -> dict:
    """Metadata TRƯỚC khi tải — dùng cho preview + giới hạn duration."""
    url = validate_url(url)
    info = _probe_json(probe_argv(url, cookies_file=cookies_file, proxy=proxy),
                       runner=runner)
    return {
        "title": info.get("title") or "",
        "duration": info.get("duration"),
        "thumbnail": info.get("thumbnail"),
        "uploader": info.get("uploader") or "",
        "webpage_url": info.get("webpage_url") or url,
        "ext": info.get("ext"),
    }


def _find_output(dest_dir: str) -> str | None:
    """File `source.{ext}` sinh ra sau tải — bỏ .part (chưa xong)."""
    for name in sorted(os.listdir(dest_dir)):
        if name.startswith("source.") and not name.endswith(".part"):
            path = os.path.join(dest_dir, name)
            if os.path.getsize(path) > 0:
                return path
    return None


def _kill_group(proc: subprocess.Popen) -> None:
    try:
        os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
    except (ProcessLookupError, PermissionError):
        pass


def _progress_map(line: str, stream_idx: int, streams_seen: int) -> int | None:
    """`[download]  23.4% of ~10.00MiB` → % TỔNG theo luồng.

    luồng 1 → 10–50, luồng 2 → 50–85 (luồng thứ N dồn về cuối); merge → 90.
    """
    if "Merging formats into" in line:
        return 90
    if "[download]" not in line or "%" not in line:
        return None
    try:
        pct = float(line.split("%")[0].split("[download]")[-1].strip())
    except ValueError:
        return None
    lo = 10 + min(stream_idx, streams_seen - 1) * (75 / max(streams_seen, 1))
    hi = 10 + (min(stream_idx, streams_seen - 1) + 1) * (75 / max(streams_seen, 1))
    return int(lo + (hi - lo) * pct / 100)


def ensure_downloaded(url: str, workdir: str, quality: str = "1080", *,
                      progress_cb=None, abort_check=None,
                      cookies_file: str | None = None, proxy: str | None = None,
                      max_duration: int = MAX_DURATION_S, runner=None) -> dict:
    """Tải 1 lần rồi ghi marker — lần sau khớp url+quality là SKIP.

    Marker nằm trong workdir bền (MEDIA_ROOT/jobs/{id}/work) — đúng nguyên liệu
    A1: file marker ghi nguyên tử, "xong" phải là file thực size>0. Retry job
    (nút Chạy lại) không tải lại video.
    """
    from .manifest import MANIFEST_NAME

    url = validate_url(url)
    if quality not in FORMAT_LADDER:
        raise ValueError(f"quality phải là một trong {list(QUALITIES)}")
    if cookies_file and not cookies_ok(cookies_file):
        raise ValueError(
            "file cookies phải là định dạng Netscape (dòng đầu "
            "'# Netscape HTTP Cookie File')")
    os.makedirs(workdir, exist_ok=True)
    marker_path = os.path.join(workdir, "download.json")

    marker = None
    try:
        with open(marker_path, encoding="utf-8") as f:
            marker = json.load(f)
    except Exception:  # noqa: BLE001 — thiếu/corrupt = chưa có
        marker = None
    if marker and marker.get("url") == url and marker.get("quality") == quality:
        out = os.path.join(workdir, f"source.{marker.get('ext', 'mp4')}")
        if os.path.exists(out) and os.path.getsize(out) > 0:
            return marker  # đã tải rồi — SKIP

    info = probe(url, cookies_file=cookies_file, proxy=proxy, runner=runner)
    dur = info.get("duration")
    if dur and max_duration and float(dur) > max_duration:
        raise ValueError(
            f"video dài {int(dur // 60)} phút — vượt giới hạn "
            f"{max_duration // 60} phút của hệ thống")

    if progress_cb:
        progress_cb(5, "Đang tải: đã đọc thông tin video")

    argv = build_argv(url, workdir, quality, cookies_file=cookies_file, proxy=proxy)
    streams_seen = 1 if quality == "audio" else 2
    code, err_tail = _run_stream(argv, workdir=workdir, streams_seen=streams_seen,
                                 progress_cb=progress_cb, abort_check=abort_check,
                                 runner=runner)
    if code != 0:
        msg = human_error(err_tail) or (err_tail.strip().splitlines()[-1]
                                        if err_tail.strip() else "tải thất bại")
        raise ValueError(f"Tải video thất bại: {msg[:300]}")

    out = _find_output(workdir)
    if out is None:
        raise ValueError("yt-dlp báo xong nhưng không tìm thấy file — thử lại")
    marker = {
        "url": url, "quality": quality,
        "ext": os.path.splitext(out)[1].lstrip("."),
        "size": os.path.getsize(out),
        "title": info.get("title") or "",
        "duration": info.get("duration"),
        "thumbnail": info.get("thumbnail"),
        "uploader": info.get("uploader") or "",
        "max_duration": max_duration,
        "manifest_name": MANIFEST_NAME,
    }
    atomic_write_json(marker_path, marker)
    return marker


def _run_stream(argv: list[str], *, workdir: str, streams_seen: int,
                progress_cb=None, abort_check=None, runner=None) -> tuple[int, str]:
    """Chạy yt-dlp, đọc stderr theo dòng → progress + abort giữa đường.

    runner injectable: trả (code, stdout, stderr) — cùng contract subprocess.
    Default Popen nhóm tiến trình riêng — abort thì killpg (rủi ro số 4).
    """
    if runner is not None:
        code, _out, err_tail = runner(argv)
        if abort_check and abort_check():
            raise JobCancelled("hủy trong lúc tải")
        return code, err_tail

    err_lines: list[str] = []
    proc = subprocess.Popen(argv, cwd=workdir, start_new_session=True,
                            stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
                            text=True)
    stream_idx = 0
    assert proc.stderr is not None
    for line in proc.stderr:
        line = line.rstrip()
        if line:
            err_lines.append(line)
            if "Destination:" in line and "[download]" in line:
                stream_idx = min(stream_idx + 1, streams_seen - 1)
            pct = _progress_map(line, stream_idx, streams_seen)
            if pct is not None and progress_cb:
                progress_cb(pct, "Đang tải video từ link")
        if abort_check and abort_check():
            _kill_group(proc)
            proc.wait(timeout=10)
            raise JobCancelled("hủy trong lúc tải — đã dừng yt-dlp")
    code = proc.wait()
    if abort_check and abort_check():
        raise JobCancelled("hủy trong lúc tải")
    tail = "\n".join(err_lines[-40:])
    return code, tail


def selftest() -> None:
    """Selftest OFFLINE — runner fake, không đụng mạng."""
    import tempfile

    tmp = tempfile.mkdtemp(prefix="vv_dl_")
    calls: list[list[str]] = []

    def fake_runner(argv):
        calls.append(argv)
        # giả lập yt-dlp probe (JSON) và download (tạo file)
        if "--dump-single-json" in argv:
            return (0, json.dumps({"title": "Video thử", "duration": 90.0,
                                   "thumbnail": "t.jpg", "uploader": "kênh",
                                   "webpage_url": argv[-1], "ext": "mp4"}), "")
        with open(os.path.join(tmp, "source.mp4"), "wb") as f:
            f.write(b"x" * 100)
        return (0, "[download]  100% of 100B\nMerging formats into x\n", "")

    runner_probe = lambda argv: (  # noqa: E731
        (0, json.dumps({"title": "V", "duration": 90}), "") if "--dump-single-json" in argv
        else (0, "", ""))

    # 1. ladder + argv
    for q in QUALITIES:
        assert q in FORMAT_LADDER
    argv = build_argv("https://x.test/v", tmp, "1080")
    assert "--no-playlist" in argv and "-f" in argv
    assert argv[argv.index("-f") + 1] == FORMAT_LADDER["1080"]
    assert argv[-1] == "https://x.test/v"
    av_audio = build_argv("https://x.test/v", tmp, "audio")
    assert "-x" in av_audio and "--audio-format" in av_audio
    print("1. ladder + argv ................................. OK")

    # 2. URL validate + cookies validate
    for bad in ("ftp://x", "-abc", "not-a-url", ""):
        try:
            validate_url(bad)
        except ValueError:
            pass
        else:
            raise AssertionError(f"url {bad!r} phải bị chặn")
    try:
        build_argv("https://x/v", tmp, "999")
    except ValueError:
        pass
    else:
        raise AssertionError("quality lạ phải bị chặn")
    bad_ck = os.path.join(tmp, "ck.txt")
    with open(bad_ck, "w") as f:
        f.write("not netscape\n")
    try:
        ensure_downloaded("https://x.test/v", tmp, "1080", cookies_file=bad_ck,
                          runner=runner_probe)
    except ValueError as e:
        assert "Netscape" in str(e), e
    else:
        raise AssertionError("cookies sai format phải bị chặn")
    print("2. URL + cookies + quality validate ............... OK")

    # 3. error map
    assert human_error("ERROR: [youtube] xyz: Private video. Sign in if you have"
                       " been granted access") is not None
    assert human_error("ERROR: too many requests") is not None
    assert human_error("this version of yt-dlp has been deprecated. Use pip"
                       " install -U") == ERROR_MAP[0][1]
    assert human_error("ERROR: siêu lạ không khớp") is None
    print("3. error map thân thiện ........................... OK")

    # 4. duration gate — probe dài quá max → ValueError TRƯỚC khi tải
    def long_runner(argv):
        return (0, json.dumps({"title": "V", "duration": 999999}), "")

    try:
        probe("https://x.test/v", runner=long_runner)
        ensure_downloaded("https://x.test/v", tmp, "1080", runner=long_runner)
    except ValueError as e:
        assert "giới hạn" in str(e), e
    else:
        raise AssertionError("duration quá hạn phải bị chặn")
    print("4. giới hạn duration kiểm bằng Python ............. OK")

    # 5. tải + marker + SKIP lần 2
    marker = ensure_downloaded("https://x.test/v", tmp, "1080", runner=fake_runner)
    assert marker["ext"] == "mp4" and marker["size"] == 100, marker
    dl_calls = len([a for a in calls if "--dump-single-json" not in a])
    marker2 = ensure_downloaded("https://x.test/v", tmp, "1080", runner=fake_runner)
    assert marker2["url"] == marker["url"]
    dl_calls2 = len([a for a in calls if "--dump-single-json" not in a])
    assert dl_calls2 == dl_calls, "lần 2 phải SKIP không tải lại"
    print("5. marker download.json + resume skip ............. OK")

    # 6. abort → JobCancelled (runner ném JobCancelled ngay khi được gọi)
    tmp2 = tempfile.mkdtemp(prefix="vv_dl2_")
    try:
        ensure_downloaded("https://x.test/v2", tmp2, "1080", runner=raise_cancel)
    except JobCancelled:
        pass
    else:
        raise AssertionError("abort phải ném JobCancelled")
    print("6. abort → JobCancelled ........................... OK")

    # 7. progress map
    assert _progress_map("Merging formats into \"x.mp4\"", 0, 2) == 90
    p = _progress_map("[download]   50.0% of ~10MiB", 0, 2)
    assert p is not None and 10 <= p <= 50, p
    p2 = _progress_map("[download]  100.0% of ~10MiB", 1, 2)
    assert p2 is not None and 50 <= p2 <= 85, p2
    assert _progress_map("[ExtractAudio] x", 0, 2) is None
    print("7. progress map 2 luồng ........................... OK")

    print("DOWNLOAD SELFTEST PASSED")


def raise_cancel(argv=None):
    """Runner giả ném hủy ngay khi được gọi — khớp contract runner(argv)."""
    raise JobCancelled("hủy trong lúc tải")


if __name__ == "__main__":
    selftest()
