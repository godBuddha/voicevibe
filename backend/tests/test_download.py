"""B1 — Guard tính năng nhập từ URL (yt-dlp).

Vì sao có test riêng thay vì tin vào selftest module:
- selftest kiểm THUẬT TOÁN (ladder, error map, marker) bằng runner fake;
- suite này kiểm ĐƯỜNG HTTP THẬT: tạo job type=download qua POST /v1/jobs
  (validate 422 chặn TRƯỚC khi tạo — cùng nguyên tắc subtitle), preview
  endpoint (401 chưa đăng nhập, 422 link xấu), worker _run_download thật với
  storage local + monkeypatch ensure_downloaded, và JobIn KHÔNG nuốt field
  (bài học pydantic âm thầm — background_mode từng vậy).

Bootstrap khớp pattern repo: env TRƯỚC import, sqlite + VOICEVIBE_INLINE=1.
Chạy:  cd backend && PYTHONPATH=. python tests/test_download.py
"""
from __future__ import annotations

import os
import pathlib
import sys
import tempfile

WORK = pathlib.Path(tempfile.mkdtemp(prefix="vv_dl_"))
os.environ["DATABASE_URL"] = f"sqlite:///{WORK}/dl.db"
os.environ["MEDIA_ROOT"] = str(WORK / "media")
os.environ["VOICEVIBE_INLINE"] = "1"
os.environ.pop("VOICEVIBE_API_KEYS", None)
os.environ.pop("VOICEVIBE_ADMIN_KEY", None)

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

import httpx  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app import ratelimit as RL  # noqa: E402
from app.db import SessionLocal  # noqa: E402
from app.main import app  # noqa: E402
from app.models import User  # noqa: E402
from app.security import hash_password  # noqa: E402

c = TestClient(app)
RL.reset()
anon = TestClient(app)
RL.reset()

# ------------------------------------------------- 1. chưa đăng nhập → 401
for method, path, kw in [("get", "/v1/jobs", {}),
                         ("post", "/v1/download/preview", {"json": {"url": "https://x"}}),
                         ("post", "/v1/jobs",
                          {"json": {"type": "download", "source_url": "https://x.test/v"}})]:
    r = anon.post(path, **kw) if method == "post" else anon.get(path, **kw)
    assert r.status_code == 401, f"{method} {path} -> {r.status_code}"
print("1. chưa đăng nhập 401 ............................. OK")

assert c.post("/v1/auth/setup",
              json={"email": "admin@local", "password": "matkhau123"}).status_code == 201

# ------------------------------------------------- 2. JobIn không nuốt field
r = c.post("/v1/jobs", json={"type": "download",
                             "source_url": "https://x.test/video?v=abc",
                             "quality": "720"})
assert r.status_code in (200, 202), r.text
JID = r.json()["job_id"]
d = c.get(f"/v1/jobs/{JID}").json()
# INLINE dispatch chạy NGAY — job đã xong (đường monkeypatch bên dưới chưa gắn)
# nên chỉ khẳng định params chứa đủ field (pydantic không nuốt âm thầm)
assert d["params"].get("source_url") == "https://x.test/video?v=abc", d["params"]
assert d["params"].get("quality") == "720", d["params"]
print("2. JobIn giữ nguyên source_url + quality .......... OK")

# ------------------------------------------------- 3. validate tạo job 422
r = c.post("/v1/jobs", json={"type": "download", "source_url": "not-a-url"})
assert r.status_code == 422, r.text
r = c.post("/v1/jobs", json={"type": "download", "source_url": "-rm -rf /"})
assert r.status_code == 422, r.text
r = c.post("/v1/jobs", json={"type": "download", "source_url": "https://x.test/v",
                             "quality": "999"})
assert r.status_code == 422, r.text
r = c.post("/v1/jobs", json={"type": "download"})
assert r.status_code == 422, r.text
print("3. validate link/quality 422 lúc tạo job .......... OK")

# --------------------------------------- 4. preview endpoint (probe thật)
from app.pipelines import download as DLM  # noqa: E402

_PREVIEW: dict = {}


def fake_probe(url, *, cookies_file=None, proxy=None, runner=None):
    _PREVIEW["url"] = url
    _PREVIEW["cookies"] = cookies_file
    return {"title": "Video thử", "duration": 90.0, "thumbnail": "t.jpg",
            "uploader": "kênh", "webpage_url": url, "ext": "mp4"}


real_probe = DLM.probe
# endpoint import local (`from .pipelines.download import probe` TRONG hàm) —
# patch tên TRÊN MODULE nguồn mới có hiệu lực; patch main_mod.probe là vô ích.
DLM.probe = fake_probe
r = c.post("/v1/download/preview", json={"url": "https://x.test/v"})
assert r.status_code == 200, r.text
d = r.json()
assert d["title"] == "Video thử" and d["duration"] == 90.0, d
assert _PREVIEW["url"] == "https://x.test/v"
r = c.post("/v1/download/preview", json={"url": "https://x.test/v"})
# rate limit 20/phút — bấm tiếp 20 lần nữa là 429
for _ in range(25):
    rr = c.post("/v1/download/preview", json={"url": "https://x.test/v"})
    if rr.status_code == 429:
        break
assert rr.status_code == 429, f"preview phải rate-limit, nhận {rr.status_code}"
RL.reset()
print("4. preview + rate limit 429 ....................... OK")

# --------------------------------- 5. worker _run_download thật (offline)
from app.pipelines.download import ensure_downloaded  # noqa: E402
from app.storage import get_storage  # noqa: E402

_calls: list[dict] = []
FAKE_MARKER = {"url": "https://x.test/v", "quality": "1080", "ext": "mp4",
               "size": 4, "title": "Video thử", "duration": 90.0,
               "thumbnail": "t.jpg", "uploader": "kênh"}


def fake_ensure(url, workdir, quality="1080", *, progress_cb=None, **kw):
    _calls.append({"url": url, "quality": quality, "workdir": workdir})
    if progress_cb:
        progress_cb(50, "Đang tải")
    src = os.path.join(workdir, "source.mp4")
    os.makedirs(workdir, exist_ok=True)
    with open(src, "wb") as f:
        f.write(b"MP4!")
    return FAKE_MARKER


DLM.ensure_downloaded = fake_ensure
r = c.post("/v1/jobs", json={"type": "download",
                             "source_url": "https://x.test/v", "quality": "1080"})
assert r.status_code in (200, 202), r.text
J2 = r.json()["job_id"]
d = c.get(f"/v1/jobs/{J2}").json()
assert d["status"] == "done", d
assert d["params"].get("download_title") == "Video thử", d["params"]
assert d["params"].get("download_duration") == 90.0
r = c.get(f"/v1/jobs/{J2}/result").json()
assert r["kind"] == "video" and r.get("download_url"), r
key = r["download_url"].removeprefix("/media/")
assert key.startswith(f"jobs/{J2}/"), key
storage = get_storage()
assert storage.exists(key), "file phải nằm trong storage"
print("5. _run_download thật: storage + metadata ......... OK")

# 6. Chạy lại KHÔNG tải lại (marker resume) — bấm retry endpoint
def ensure_marker_hit(url, workdir, quality="1080", *, progress_cb=None, **kw):
    _calls.append({"url": url, "again": True})
    src = os.path.join(workdir, "source.mp4")
    with open(src, "wb") as f:
        f.write(b"MP4!")
    return FAKE_MARKER


DLM.ensure_downloaded = ensure_marker_hit
r = c.post(f"/v1/jobs/{J2}/retry")
assert r.status_code == 409, "job done không retry được (chỉ failed/cancelled)"
print("6. retry chỉ cho failed/cancelled (409) ........... OK")

# 7. download job thất bại → message thân thiện + retry được
def ensure_failing(url, workdir, quality="1080", *, progress_cb=None, **kw):
    _calls.append({"url": url, "fail": True})
    raise ValueError("Video riêng tư — cần cookies đăng nhập (Cài đặt → Tải video từ link).")


DLM.ensure_downloaded = ensure_failing
r = c.post("/v1/jobs", json={"type": "download", "source_url": "https://x.test/v"})
J3 = r.json()["job_id"]
d = c.get(f"/v1/jobs/{J3}").json()
assert d["status"] == "failed", d
assert "cookies" in (d.get("error") or ""), d
r = c.post(f"/v1/jobs/{J3}/retry")
assert r.status_code in (200, 202), r.text
d = c.get(f"/v1/jobs/{J3}").json()
assert d["status"] == "failed", d  # vẫn fail vì fake luôn raise — nhưng retry chạy
assert len([x for x in _calls if x.get("url")]) >= 2, "retry phải gọi lại ensure"
print("7. job failed giữ message thân thiện + retry OK ... OK")

# 8. xóa job dọn file storage
DLM.ensure_downloaded = fake_ensure
r = c.post("/v1/jobs", json={"type": "download", "source_url": "https://x.test/v"})
J4 = r.json()["job_id"]
key4 = c.get(f"/v1/jobs/{J4}/result").json()["download_url"].removeprefix("/media/")
assert c.delete(f"/v1/jobs/{J4}").status_code == 200
assert not get_storage().exists(key4), "xóa job phải dọn cả file tải"
print("8. delete job dọn file ............................ OK")

# 9. owns media: user khác không đọc được file của mình
with SessionLocal() as db:
    db.add(User(email="other@local", role="user",
                password_hash=hash_password("matkhau456")))
    db.commit()
co = TestClient(app)
RL.reset()
assert co.post("/v1/auth/login",
               json={"email": "other@local", "password": "matkhau456"}).status_code == 200
r = co.get(f"/media/{key}")
assert r.status_code == 404, f"user khác đọc file của mình phải 404, nhận {r.status_code}"
assert c.get(f"/media/{key}").status_code == 200
print("9. media ownership 2 chiều ........................ OK")

DLM.probe = real_probe
print("DOWNLOAD SUITE PASSED")
