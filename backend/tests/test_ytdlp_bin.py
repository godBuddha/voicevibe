"""GC4 — tự cập nhật yt-dlp (pipelines/ytdlp_bin.py) + cắm vào download.py.

Vì sao có test riêng:
- YT-DLP GÃY THEO YOUTUBE (mỗi lần YouTube đổi giao diện) — cơ chế cập nhật
  phải tải binary chính thức, kiểm SHA-256, và QUAN TRỌNG NHẤT: binary hỏng
  KHÔNG ĐƯỢC thay binary tốt (checksum sai → giữ nguyên bản cũ).
- resolve_prefix phải FALLBACK về pip khi binary thiếu/hỏng — job tải video
  không được chết vì binary gãy.
- Kênh "off" (mặc định) không được đụng mạng.
- fetch_release nightly phải chọn đúng entry PRERELEASE (không nhầm stable).

Mọi case OFFLINE — http_get + runner fake, MEDIA_ROOT tạm.

Chạy:
    cd backend && PYTHONPATH=. python tests/test_ytdlp_bin.py
"""
from __future__ import annotations

import json
import os
import pathlib
import sys
import tempfile

WORK = pathlib.Path(tempfile.mkdtemp(prefix="vv_ytbin_"))
os.environ["DATABASE_URL"] = f"sqlite:///{WORK}/yt.db"
os.environ["MEDIA_ROOT"] = str(WORK / "media")
os.environ["VOICEVIBE_INLINE"] = "1"
os.environ.pop("VOICEVIBE_API_KEYS", None)
os.environ.pop("VOICEVIBE_ADMIN_KEY", None)

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

import hashlib  # noqa: E402
import time  # noqa: E402

from app.pipelines import download as DLM  # noqa: E402
from app.pipelines import ytdlp_bin as YB  # noqa: E402

BIN_DIR = YB.bin_dir(str(WORK / "media"))  # root mặc định (env MEDIA_ROOT)


# --------------------------------- 1. fetch_release: stable + nightly + thiếu asset
def fake_http_factory(releases_json, asset_bytes=b"\x7fELF-ytdlp", sha_for=None):
    calls = {"n": 0}

    def http_get(url: str) -> bytes:
        calls["n"] += 1
        if "/releases" in url:
            return json.dumps(releases_json).encode()
        if url.endswith("/sha") or url.endswith("/ns"):
            digest = sha_for or hashlib.sha256(asset_bytes).hexdigest()
            return f"{digest}  {YB.ASSET}\n0000  other-file\n".encode()
        return asset_bytes

    http_get.calls = calls
    return http_get


ASSET_BYTES = b"\x7fELF-ytdlp-fake-binary"
stable_rel = {
    "tag_name": "2026.10.05",
    "prerelease": False,
    "assets": [
        {"name": YB.ASSET, "browser_download_url": "https://gh/dl/asset"},
        {"name": YB.SHA_FILE, "browser_download_url": "https://gh/dl/sha"},
    ],
}
meta = YB.fetch_release("stable", http_get=fake_http_factory(stable_rel))
assert meta == {"tag": "2026.10.05", "asset_url": "https://gh/dl/asset",
                "sha_url": "https://gh/dl/sha"}, meta
# nightly: list có stable trước, prerelease sau → chọn đúng PRERELEASE
nightly_list = [
    {"tag_name": "2026.10.05", "prerelease": False, "assets": []},
    {"tag_name": "2026.10.06-nightly", "prerelease": True,
     "assets": [{"name": YB.ASSET, "browser_download_url": "https://gh/dl/n"},
                {"name": YB.SHA_FILE, "browser_download_url": "https://gh/dl/ns"}]},
]
meta = YB.fetch_release("nightly", http_get=fake_http_factory(nightly_list))
assert meta["tag"] == "2026.10.06-nightly", meta
# release không có asset → None (không tải mù quáng)
bad = {"tag_name": "x", "assets": [{"name": "other", "browser_download_url": "u"}]}
assert YB.fetch_release("stable", http_get=fake_http_factory(bad)) is None
# nightly không có prerelease → None
none_list = [{"tag_name": "x", "prerelease": False, "assets": []}]
assert YB.fetch_release("nightly", http_get=fake_http_factory(none_list)) is None
print("1. fetch_release: stable/nightly/thiếu asset ........... OK")

# --------------------------------- 2. refresh happy path: binary 755 + state + tmp sạch
http_get = fake_http_factory(stable_rel, ASSET_BYTES)
res = YB.refresh("stable", http_get=http_get, media_root=str(WORK / "media"))
assert res["version"] == "2026.10.05", res
path = YB.binary_path("stable", str(WORK / "media"))
assert os.path.isfile(path) and os.access(path, os.X_OK)
assert not os.path.exists(path + ".tmp"), "tmp phải được dọn (os.replace)"
state = YB.read_state("stable", str(WORK / "media"))
assert state["sha256"] == hashlib.sha256(ASSET_BYTES).hexdigest()
assert state["version"] == "2026.10.05"
print("2. refresh: binary chạy được + state + tmp sạch ...... OK")

# --------------------------------- 3. checksum SAI → giữ nguyên binary cũ
old_binary = YB.binary_path("stable", str(WORK / "media"))
with open(old_binary, "rb") as f:
    old_bytes = f.read()
http_get = fake_http_factory(stable_rel, b"corrupted-download", sha_for="0" * 64)
try:
    YB.refresh("stable", http_get=http_get, media_root=str(WORK / "media"),
               force=True)
    raise AssertionError("sha sai phải raise")
except ValueError as e:
    assert "checksum" in str(e) or "giữ nguyên" in str(e), e
with open(old_binary, "rb") as f:
    assert f.read() == old_bytes, "binary tốt bị phá!"
assert not os.path.exists(old_binary + ".tmp"), "tmp phải dọn khi sha sai"
print("3. checksum sai: binary cũ byte-không-đổi ............ OK")

# --------------------------------- 4. fresh → skip, không gọi mạng
http_get = fake_http_factory(stable_rel)
YB.refresh("stable", http_get=http_get, media_root=str(WORK / "media"))
before = http_get.calls["n"]
res = YB.refresh("stable", http_get=http_get, media_root=str(WORK / "media"))
assert res.get("skipped") == "fresh", res
assert http_get.calls["n"] == before, "fresh không được gọi mạng"
print("4. fresh ≤24h: skip, không mạng ...................... OK")

# --------------------------------- 5. resolve_prefix: off / binary OK / binary hỏng
YB.reset_cache()
assert YB.resolve_prefix("off", runner=lambda a: (0, "x", "")) == \
    [sys.executable, "-m", "yt_dlp"], "off phải là pip library"
# binary chạy được → binary prefix + TTL cache (runner chỉ chạy 1 lần)
calls = {"n": 0}

def ok_runner(argv):
    calls["n"] += 1
    return 0, "2026.10.05", ""

YB.reset_cache()
pfx = YB.resolve_prefix("stable", str(WORK / "media"), runner=ok_runner)
assert pfx == [old_binary], pfx
first_n = calls["n"]
YB.resolve_prefix("stable", str(WORK / "media"), runner=ok_runner)
assert calls["n"] == first_n, "TTL cache phải chặn probe lặp"
# binary hỏng (runner exit 1) → fallback pip + kick refresh nền
YB.reset_cache()

def bad_runner(argv):
    return 1, "", "Permission denied"

assert YB.resolve_prefix("stable", str(WORK / "media"), runner=bad_runner) == \
    [sys.executable, "-m", "yt_dlp"]
YB.reset_cache()
print("5. resolve_prefix: off/binary OK TTL/hỏng fallback ... OK")

# --------------------------------- 6. build_argv/probe_argv với prefix
import sys as _sys  # noqa: E402

PIPPFX = [_sys.executable, "-m", "yt_dlp"]
argv = DLM.build_argv("https://x.test/v", "/tmp/out", "720", prefix=PIPPFX)
assert argv[:3] == PIPPFX, argv[:4]
assert "-f" in argv and "--no-playlist" in argv, "flag cũ không mất"
assert "best" in " ".join(argv), "format ladder phải còn"
pargv = DLM.probe_argv("https://x.test/v", prefix=PIPPFX)
assert pargv[:3] == PIPPFX and "--dump-single-json" in pargv
print("6. build_argv/probe_argv: prefix + flag giữ nguyên ... OK")

# --------------------------------- 7. autorefresh: stale → gọi; lỗi mạng không chết process
import threading  # noqa: E402

YB.reset_cache()
http_get = fake_http_factory(stable_rel, ASSET_BYTES)
refreshed = {"n": 0}
real_refresh = YB.refresh


def counting_refresh(channel, **kw):
    refreshed["n"] += 1
    return real_refresh(channel, http_get=http_get, media_root=str(WORK / "media"),
                        force=True)


# stale: state cũ 25 giờ → maybe_autorefresh phải kick thread nền
old_state = YB.read_state("stable", str(WORK / "media"))
old_state["checked_at"] = old_state["checked_at"] - 25 * 3600
with open(os.path.join(BIN_DIR, f"{YB.STATE_NAME}.stable"), "w") as f:
    json.dump(old_state, f)
# patch refresh trong module để đếm (thread daemon gọi tên module)
YB.refresh = counting_refresh
try:
    YB.maybe_autorefresh("stable", media_root=str(WORK / "media"))
    import time as _t

    deadline = _t.time() + 5
    while refreshed["n"] == 0 and _t.time() < deadline:
        _t.sleep(0.05)
    assert refreshed["n"] >= 1, "stale phải kick refresh nền"
finally:
    YB.refresh = real_refresh
# lỗi mạng trong thread nền không giết process: neo http_get ném ngay →
# thread nuốt, KHÔNG đụng mạng thật (CI chạy được mạng nhưng gọi dồn dập là
# bài học GB8 — rate-limit GitHub vô ích).
def net_fail(url):
    raise ConnectionError("network down")


real_http = YB._default_http_get
YB._default_http_get = net_fail
try:
    YB.maybe_autorefresh("stable", media_root=str(WORK / "media"), now=0)
finally:
    YB._default_http_get = real_http
# channel off → KHÔNG kick gì (không mạng, không thread)
YB.maybe_autorefresh("off")
print("7. autorefresh: stale kick nền / lỗi mạng nuốt ...... OK")

# --------------------------------- 8. ERROR_MAP[0] mới + human_error vẫn match
msg = DLM.human_error("ERROR: this version of yt-dlp has been deprecated")
assert msg and "Cập nhật yt-dlp" in msg and "Cài đặt" in msg, msg
print("8. ERROR_MAP deprecated: hướng dẫn bật kênh stable ... OK")

# --------------------------------- 9. E2E download job dùng binary prefix
from fastapi.testclient import TestClient  # noqa: E402
from app import ratelimit as RL  # noqa: E402
from app.main import app  # noqa: E402

c = TestClient(app)
RL.reset()
assert c.post("/v1/auth/setup",
              json={"email": "admin@local", "password": "matkhau123"}).status_code == 201


def fake_ensure(url, workdir, quality="1080", *, progress_cb=None, **_kw):
    os.makedirs(workdir, exist_ok=True)
    with open(os.path.join(workdir, "source.mp4"), "wb") as f:
        f.write(b"FAKE")
    return {"url": url, "quality": quality, "ext": "mp4", "size": 4,
            "title": "Video thử", "duration": 2.5}


seen_argv = {}


def runner_capture(argv, **_kw):
    seen_argv["head"] = argv[:1]
    return 0, json.dumps({"title": "t", "duration": 10, "webpage_url": "u"}), ""


real_probe_run = DLM._probe_json
DLM.ensure_downloaded = fake_ensure  # không tải thật
try:
    # channel=stable + binary CHẠY ĐƯỢC → resolve_prefix chọn binary. "Chạy được"
    # nghĩa là exec thật thành công — cài binary giả dạng shell script qua
    # refresh (ELF giả không exec được là fallback đúng, nhưng ca này cần OK).
    runnable = b"#!/bin/sh\necho 2026.10.05\n"
    YB.refresh("stable", http_get=fake_http_factory(stable_rel, runnable),
               media_root=str(WORK / "media"), force=True)
    from app.settings_service import set_setting  # noqa: E402

    set_setting("download.ytdlp_channel", "stable")
    YB.reset_cache()
    head = DLM.resolve_prefix()
    assert head == [old_binary], f"channel stable phải dùng binary — got {head}"
    # channel off → pip
    set_setting("download.ytdlp_channel", "off")
    YB.reset_cache()
    assert DLM.resolve_prefix() == PIPPFX
    from app.settings_service import delete_setting  # noqa: E402

    delete_setting("download.ytdlp_channel")
finally:
    DLM.ensure_downloaded = None  # thật (không đụng trong test này)
    DLM._probe_json = real_probe_run
YB.reset_cache()
print("9. E2E prefix theo setting: stable→binary, off→pip . OK")

# --------------------------------- 10. REGRESSION: refresh KHÔNG truyền http_get
# (bug thật trên stack 11/10: fetch_release tự chèn mặc định nhưng bước tải
# binary dưới dùng thẳng tham số None → 'NoneType' object is not callable).
YB.reset_cache()
http_get = fake_http_factory(stable_rel, ASSET_BYTES)
real_default = YB._default_http_get
YB._default_http_get = http_get
try:
    res = YB.refresh("stable", force=True, media_root=str(WORK / "media"),
                     now=time.time() + 10 ** 6)
    assert res["version"] == "2026.10.05", res
finally:
    YB._default_http_get = real_default
YB.reset_cache()
print("10. regression: refresh không truyền http_get ........ OK")

print("YTDLP BIN SUITE PASSED")
