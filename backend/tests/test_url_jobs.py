"""B1/B2 — Guard đường "dán link" vào job dub/stt/subtitle + phụ đề YouTube.

Vì sao có test riêng:
- Đường nguồn ĐỔI: trước đây mọi job media phải upload; giờ `source_url` tải về
  workdir bền. Sai lầm nguy hiểm nhất: file tải về luôn có TÊN CỐ ĐỊNH
  (source.mp4) → nếu source_url/quality KHÔNG vào vân tay manifest thì đổi link
  giữa hai lần chạy tái dùng sổ tay của video khác (bản dịch/TTS lẫn lộn).
- Phụ đề YouTube phải bỏ được WHISPER (đúng là tiết kiệm GPU), nhưng vẫn phải
  diarize + merge để gán người nói; video không có caption phải rơi về Whisper
  khi `auto` và FAIL RÕ khi user chọn cứng `youtube`.
- Validate tạo job phải chặn TRƯỚC (dub/stt/subtitle cần media_url hoặc
  source_url; sub_source sai giá trị → 422).

Bootstrap khớp pattern repo. Chạy:
    cd backend && PYTHONPATH=. python tests/test_url_jobs.py
"""
from __future__ import annotations

import os
import pathlib
import sys
import tempfile

WORK = pathlib.Path(tempfile.mkdtemp(prefix="vv_url_"))
os.environ["DATABASE_URL"] = f"sqlite:///{WORK}/url.db"
os.environ["MEDIA_ROOT"] = str(WORK / "media")
os.environ["VOICEVIBE_INLINE"] = "1"
os.environ.pop("VOICEVIBE_API_KEYS", None)
os.environ.pop("VOICEVIBE_ADMIN_KEY", None)

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

import httpx  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app import ratelimit as RL  # noqa: E402
from app.main import app  # noqa: E402
from app.pipelines import download as DLM  # noqa: E402
from app.pipelines import dub_pipeline as DUBMOD  # noqa: E402
from app.pipelines import stt as STTMOD  # noqa: E402
from app.pipelines import youtube_subs as YT  # noqa: E402
from app.pipelines.manifest import params_fingerprint  # noqa: E402
from app.pipelines.stt import diarize as real_diarize  # noqa: E402
from app.pipelines.stt import merge as real_merge  # noqa: E402

c = TestClient(app)
RL.reset()
assert c.post("/v1/auth/setup",
              json={"email": "admin@local", "password": "matkhau123"}).status_code == 201

# --------------------------------------------- 1. validate tạo job (chặn trước)
for bad in [
    {"type": "dub", "source_lang": "vi", "target_lang": "en"},        # không nguồn
    {"type": "stt", "sub_source": "cả hai"},                          # sub_source lạ
    {"type": "subtitle", "source_url": "https://x.test/v", "format": "mp3"},
    {"type": "dub", "source_url": "not-a-url"},
]:
    r = c.post("/v1/jobs", json=bad)
    assert r.status_code == 422, f"{bad} -> {r.status_code}: {r.text}"
# subtitle chỉ dán link không upload vẫn được NHẬN (không 422 thiếu nguồn)
r = c.post("/v1/jobs", json={"type": "subtitle", "source_url": "https://x.test/v",
                             "format": "srt"})
assert r.status_code in (200, 202), r.text
RL.reset()
print("1. validate chặn thiếu nguồn + giá trị lạ ......... OK")

# --------------------------------------------- 2. vân tay theo link
base = {"source_lang": "vi", "target_lang": "en", "speaker_voices": {},
        "background_mode": "silence", "max_speed": 1.35, "media_url": "/tmp/x.mp4"}
fp1 = params_fingerprint({**base, "source_url": "https://x.test/v1", "quality": "1080"}, "tag")
fp2 = params_fingerprint({**base, "source_url": "https://x.test/v2", "quality": "1080"}, "tag")
fp3 = params_fingerprint({**base, "source_url": "https://x.test/v1", "quality": "720"}, "tag")
fp4 = params_fingerprint({**base, "source_url": "https://x.test/v1", "quality": "1080",
                          "sub_source": "whisper"}, "tag")
assert fp1 != fp2, "đổi LINK phải đổi vân tay (file tải về cùng tên source.mp4!)"
assert fp1 != fp3, "đổi QUALITY phải đổi vân tay"
assert fp1 != fp4, "đổi sub_source (caption khác bản whisper) phải đổi vân tay"
fp1b = params_fingerprint({**base, "source_url": "https://x.test/v1", "quality": "1080"}, "tag")
assert fp1 == fp1b, "cùng tham số phải cùng vân tay"
print("2. vân tay gồm source_url/quality/sub_source ...... OK")

# ------------------------------- 3. _youtube_transcript: 3 đường sub_source
from app import tasks as TK  # noqa: E402

_YT_SEGS = YT.parse_vtt("""WEBVTT

00:00:00.000 --> 00:00:02.500
Xin chào <c>đại</c> gia
""")


def fake_fetch(url, lang=None, *, info_fn=None, fetch_fn=None):
    return _YT_SEGS


def none_fetch(url, lang=None, *, info_fn=None, fetch_fn=None):
    return None


real_fetch = YT.fetch_captions
YT.fetch_captions = fake_fetch
try:
    segs, note = TK._youtube_transcript("j1", {"source_url": "https://x/v",
                                               "sub_source": "auto"})
    assert segs and note == "youtube-captions"
    segs, _ = TK._youtube_transcript("j1", {"source_url": "https://x/v",
                                            "sub_source": "whisper"})
    assert segs is None, "sub_source=whisper luôn nghe lại"
    YT.fetch_captions = none_fetch
    try:
        TK._youtube_transcript("j1", {"source_url": "https://x/v",
                                      "sub_source": "youtube"})
    except ValueError as e:
        assert "Phụ đề YouTube" in str(e), e
    else:
        raise AssertionError("youtube-only không có caption phải fail rõ")
    segs, _ = TK._youtube_transcript("j1", {"source_url": "https://x/v",
                                            "sub_source": "auto"})
    assert segs is None, "auto không caption → rơi về Whisper (không fail)"
finally:
    YT.fetch_captions = real_fetch
print("3. _youtube_transcript auto/youtube/whisper ....... OK")

# ------------------------- 4. job dub với source_url + captions (đường thật)
_dub_calls: list[dict] = []


def fake_dub(src_path, source_lang, target_lang, speaker_voices, storage, *,
             workdir=None, job_id=None, source_url=None, quality=None,
             sub_source=None, captions=None, **_kw):
    _dub_calls.append({"src": src_path, "source_url": source_url,
                       "quality": quality, "sub_source": sub_source,
                       "captions": captions})
    return f"jobs/{job_id}/dub.mp4", []


def fake_ensure(url, workdir, quality="1080", *, progress_cb=None, **_kw):
    os.makedirs(workdir, exist_ok=True)
    with open(os.path.join(workdir, "source.mp4"), "wb") as f:
        f.write(b"FAKE")
    return {"url": url, "quality": quality, "ext": "mp4", "size": 4,
            "title": "Video thử", "duration": 2.5}


real_dub = DUBMOD.dub_audio
DUBMOD.dub_audio = fake_dub
DLM.ensure_downloaded = fake_ensure
YT.fetch_captions = fake_fetch
try:
    r = c.post("/v1/jobs", json={"type": "dub", "source_url": "https://x.test/v",
                                 "source_lang": "vi", "target_lang": "en",
                                 "sub_source": "auto"})
    assert r.status_code in (200, 202), r.text
    JD = r.json()["job_id"]
    d = c.get(f"/v1/jobs/{JD}").json()
    assert d["status"] == "done", d
    call = _dub_calls[-1]
    assert call["src"].endswith(os.path.join("work", "source.mp4")), call["src"]
    assert call["source_url"] == "https://x.test/v"
    assert call["quality"] == "1080" and call["sub_source"] == "auto"
    assert call["captions"] and call["captions"][0].text == "Xin chào đại gia"
finally:
    DUBMOD.dub_audio = real_dub
print("4. dub dán link: tải về workdir + captions vào sổ .. OK")

# ----------------- 5. job subtitle với source_url: captions BỎ WHISPER thật
real_transcribe = STTMOD.transcribe
_transcribe_called: list[str] = []


def must_not_transcribe(*a, **kw):
    _transcribe_called.append("called")
    raise AssertionError("phụ đề YouTube có sẵn thì KHÔNG được gọi Whisper")


def fake_diarize_no_speakers(path):
    return []  # pyannote nặng — fake; merge thuần Python tự gán speaker None


STTMOD.transcribe = must_not_transcribe
STTMOD.diarize = fake_diarize_no_speakers
YT.fetch_captions = fake_fetch
try:
    r = c.post("/v1/jobs", json={"type": "subtitle", "source_url": "https://x.test/v",
                                 "format": "srt", "sub_source": "auto"})
    assert r.status_code in (200, 202), r.text
    JS = r.json()["job_id"]
    d = c.get(f"/v1/jobs/{JS}").json()
    assert d["status"] == "done", d
    assert not _transcribe_called, "Whisper phải được BỎ QUA"
    res = c.get(f"/v1/jobs/{JS}/result").json()
    assert res["kind"] == "text" and res["filename"].endswith(".srt"), res
    assert "Xin chào đại gia" in res.get("content", ""), res.get("content", "")
finally:
    STTMOD.transcribe = real_transcribe
print("5. subtitle dán link: caption thay Whisper ........ OK")

# --------------- 6. job subtitle auto không caption → rơi Whisper (đường thật)
STTMOD.diarize = fake_diarize_no_speakers


def transcribe_ok(path, language=None, stats=None, want_words=False):
    from app.providers.base import TranscriptSegment
    return [TranscriptSegment(0.0, 2.5, "Nghe lại bằng Whisper")], {}


STTMOD.transcribe = transcribe_ok
YT.fetch_captions = none_fetch
try:
    r = c.post("/v1/jobs", json={"type": "subtitle", "source_url": "https://x.test/v",
                                 "format": "srt", "sub_source": "auto"})
    assert r.status_code in (200, 202), r.text
    JF = r.json()["job_id"]
    d = c.get(f"/v1/jobs/{JF}").json()
    assert d["status"] == "done", d
    res = c.get(f"/v1/jobs/{JF}/result").json()
    assert "Nghe lại bằng Whisper" in res.get("content", ""), res.get("content", "")
finally:
    YT.fetch_captions = real_fetch
print("6. auto không caption → rơi Whisper, job không chết OK")

# -------- 7. sub_source=youtube không caption → job failed với message rõ ràng
YT.fetch_captions = none_fetch
try:
    r = c.post("/v1/jobs", json={"type": "subtitle", "source_url": "https://x.test/v",
                                 "format": "srt", "sub_source": "youtube"})
    assert r.status_code in (200, 202), r.text
    JY = r.json()["job_id"]
    d = c.get(f"/v1/jobs/{JY}").json()
    assert d["status"] == "failed", d
    assert "Phụ đề YouTube" in (d.get("error") or ""), d
finally:
    YT.fetch_captions = real_fetch
print("7. youtube-only không caption → failed rõ ràng .... OK")

# ------- 8. GB8 — công tắc use_cookies: 2 lựa chọn ngay trong giao diện
from app.settings_service import delete_setting, set_setting  # noqa: E402

# 8a. bật cookies mà admin chưa cấu hình → 422 LÚC TẠO JOB (không để job
# chạy nửa chừng mới chết) + preview cũng 422 cùng thông điệp.
delete_setting("download.cookies_file")
r = c.post("/v1/jobs", json={"type": "download",
                             "source_url": "https://x.test/v",
                             "quality": "720", "use_cookies": True})
assert r.status_code == 422, r.text
assert "cookies" in r.json()["detail"].lower(), r.text
r = c.post("/v1/download/preview",
           json={"url": "https://x.test/v", "use_cookies": True})
assert r.status_code == 422, r.text

# 8b. cookies đã cấu hình: use_cookies=True → ensure_downloaded NHẬN file;
#     mặc định (tắt) → cookies_file=None DÙ cookies đã cấu hình (ẩn danh là
#     an toàn hơn cho tài khoản Google — không dùng cookies vô tình).
ck_path = os.path.join(str(WORK), "ck.txt")
with open(ck_path, "w") as f:
    f.write("# Netscape HTTP Cookie File\n.x.test\tTRUE\t/\tFALSE\t0\tSID\tx\n")
set_setting("download.cookies_file", ck_path)
_ck_seen: list = []


def ensure_cookies_capture(url, workdir, quality="1080", *, progress_cb=None,
                           cookies_file=None, **_kw):
    _ck_seen.append(cookies_file)
    return fake_ensure(url, workdir, quality, progress_cb=progress_cb)


real_ensure = DLM.ensure_downloaded
DLM.ensure_downloaded = ensure_cookies_capture
try:
    r = c.post("/v1/jobs", json={"type": "download",
                                 "source_url": "https://x.test/v",
                                 "quality": "720", "use_cookies": True})
    assert r.status_code in (200, 202), r.text
    JC = r.json()["job_id"]
    d = c.get(f"/v1/jobs/{JC}").json()
    assert d["status"] == "done", d
    assert _ck_seen[-1] == ck_path, _ck_seen

    r = c.post("/v1/jobs", json={"type": "download",
                                 "source_url": "https://x.test/v",
                                 "quality": "480"})  # mặc định KHÔNG cookies
    assert r.status_code in (200, 202), r.text
    JA = r.json()["job_id"]
    d = c.get(f"/v1/jobs/{JA}").json()
    assert d["status"] == "done", d
    assert _ck_seen[-1] is None, "tắt công tắc phải tải ẩn danh"
finally:
    DLM.ensure_downloaded = real_ensure
    delete_setting("download.cookies_file")
print("8. công tắc cookies: 422 thiếu cấu hình + ẩn danh mặc định OK")

print("URL JOBS SUITE PASSED")
