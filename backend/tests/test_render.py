"""B3+B4 — Guard job `render`: burn phụ đề ASS 2 style + dọc 9:16 + banner.

Vì sao có test riêng (selftest đã kiểm thuật toán thuần):
- ĐƯỜNG HTTP THẬT: validate create_job (≥1 toggle; burn cần nguồn; key XOR
  job id), worker _run_render thật (monkeypatch run_render), ownership job
  phụ đề (job của người khác → lỗi rõ), đuôi file phụ đề sai → lỗi.
- GUARD NGƯỢC (nguyên tắc verification): đổi banner/vertical/burn PHẢI đổi
  vân tay render (render_fingerprint soi TOÀN BỘ material — bẫy fingerprint
  số 3; params_fingerprint của dub bỏ qua key lạ là bẫy thật).

Bootstrap khớp pattern repo. Chạy:
    cd backend && PYTHONPATH=. python tests/test_render.py
"""
from __future__ import annotations

import os
import pathlib
import sys
import tempfile

WORK = pathlib.Path(tempfile.mkdtemp(prefix="vv_render_"))
os.environ["DATABASE_URL"] = f"sqlite:///{WORK}/render.db"
os.environ["MEDIA_ROOT"] = str(WORK / "media")
os.environ["VOICEVIBE_INLINE"] = "1"
os.environ.pop("VOICEVIBE_API_KEYS", None)
os.environ.pop("VOICEVIBE_ADMIN_KEY", None)

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient  # noqa: E402

from app import ratelimit as RL  # noqa: E402
from app.main import app  # noqa: E402
from app.pipelines import render as RND  # noqa: E402
from app.pipelines.manifest import params_fingerprint  # noqa: E402

c = TestClient(app)
RL.reset()
assert c.post("/v1/auth/setup",
              json={"email": "admin@local", "password": "matkhau123"}).status_code == 201

# --------------------------------------------- 1. validate create_job 422
FAKE_MEDIA = str(WORK / "src.mp4")
with open(FAKE_MEDIA, "wb") as f:
    f.write(b"MP4")
for bad, why in [
    ({"type": "render", "media_url": FAKE_MEDIA}, "không toggle nào"),
    ({"type": "render", "media_url": FAKE_MEDIA, "burn_subtitles": True},
     "burn nhưng không nguồn phụ đề"),
    ({"type": "render", "media_url": FAKE_MEDIA, "burn_subtitles": True,
      "subtitle_key": "jobs/x.srt", "subtitle_job_id": "abc"},
     "cả hai nguồn phụ đề"),
    ({"type": "render", "media_url": FAKE_MEDIA, "subtitle_key": "jobs/x.srt"},
     "chỉ có nguồn phụ đề mà không bật burn"),
]:
    r = c.post("/v1/jobs", json=bad)
    assert r.status_code == 422, f"{why}: {r.text}"
# banner-only là hợp lệ (có toggle)
r = c.post("/v1/jobs", json={"type": "render", "media_url": FAKE_MEDIA,
                             "vertical": True, "banner": {"major": "T", "minor": "P"}})
assert r.status_code in (200, 202), r.text
RL.reset()
print("1. validate render 422 + banner-only hợp lệ ..... OK")

# --------------------------------------------- 2. render_fingerprint soi đủ
m1 = {"media_url": "x", "burn_subtitles": True, "vertical": False,
      "banner": {"major": "A", "minor": "B"}, "cues_fingerprint": "h"}
m2 = {**m1, "banner": {"major": "A", "minor": "X"}}
m3 = {**m1, "vertical": True}
m4 = {**m1, "cues_fingerprint": "g"}
assert RND.render_fingerprint(m1) != RND.render_fingerprint(m2), "đổi banner phải đổi vân tay"
assert RND.render_fingerprint(m1) != RND.render_fingerprint(m3), "đổi vertical phải đổi vân tay"
assert RND.render_fingerprint(m1) != RND.render_fingerprint(m4), "đổi phụ đề phải đổi vân tay"
# guard NGƯỢC: params_fingerprint của dub là bộ khác — không dùng nhầm
assert params_fingerprint({"media_url": "x"}, "render") != RND.render_fingerprint(m1)
print("2. render_fingerprint soi toàn bộ material ........ OK")

# --------------------------------------------- 3. worker _run_render thật
_calls: list[dict] = []
KEY = "jobs/ZZ/render.mp4"


def fake_run_render(src, *, burn_subtitles=False, vertical=False, banner=None,
                    cues_text=None, cues_ext="", workdir="", job_id="",
                    key_prefix="", storage=None, abort_check=None,
                    progress_cb=None):
    _calls.append({"src": src, "burn": burn_subtitles, "vert": vertical,
                   "banner": banner, "cues_ext": cues_ext,
                   "cues_len": len(cues_text or "")})
    if progress_cb:
        progress_cb(70, "in phụ đề")
    return f"{key_prefix}render.mp4"


real_run_render = RND.run_render
RND.run_render = fake_run_render
try:
    r = c.post("/v1/jobs", json={"type": "render", "media_url": FAKE_MEDIA,
                                 "burn_subtitles": True, "vertical": True,
                                 "banner": {"major": "T", "minor": "P"},
                                 "subtitle_key": "jobs/sub.srt"})
    assert r.status_code in (200, 202), r.text
    J = r.json()["job_id"]
    d = c.get(f"/v1/jobs/{J}").json()
    # subtitle_key "jobs/sub.srt" chưa có trong storage → job FAILED (lỗi rõ),
    # KHÔNG 500 — đây là hành vi mong đợi ở bước chưa đặt file
    if d["status"] == "failed":
        assert "media not found" in (d.get("error") or "") or "không tồn tại" in \
            (d.get("error") or ""), d
        # đặt file phụ đề rồi chạy lại
        from app.storage import get_storage
        get_storage().put("jobs/sub.srt",
                          b"1\n00:00:00,000 --> 00:00:01,000\nXin ch\xc3\xa0o\n")
        r = c.post(f"/v1/jobs/{J}/retry")
        assert r.status_code in (200, 202), r.text
        d = c.get(f"/v1/jobs/{J}").json()
    assert d["status"] == "done", d
    call = _calls[-1]
    assert call["burn"] and call["vert"] and call["cues_ext"] == "srt", call
    assert call["banner"] == {"major": "T", "minor": "P"}, call
    assert "Xin chào" in call["cues_len"] * "" or call["cues_len"] > 0
    res = c.get(f"/v1/jobs/{J}/result").json()
    assert res["kind"] == "video" and res["filename"].endswith(".mp4"), res
finally:
    RND.run_render = real_run_render
print("3. _run_render thật: key + nguồn phụ đề srt ....... OK")

# --------------------------------------------- 4. subtitle_job_id + ownership
from app.db import SessionLocal  # noqa: E402
from app.models import Job as JobRow  # noqa: E402
from app.models import User  # noqa: E402
from app.security import hash_password  # noqa: E402

with SessionLocal() as db:
    db.add(User(email="other@local", role="user",
                password_hash=hash_password("matkhau456")))
    db.commit()
co = TestClient(app)
RL.reset()
assert co.post("/v1/auth/login",
               json={"email": "other@local", "password": "matkhau456"}).status_code == 200

with SessionLocal() as db:
    me = c.get("/v1/auth/me").json()
    sub = JobRow(user_id=me["user_id"], type="subtitle", status="done",
                 params={"type": "subtitle"}, result_s3_key="jobs/s1/subtitle.srt")
    db.add(sub)
    db.commit()
    SUB_ID = sub.id
RND.run_render = fake_run_render
try:
    r = c.post("/v1/jobs", json={"type": "render", "media_url": FAKE_MEDIA,
                                 "burn_subtitles": True,
                                 "subtitle_job_id": SUB_ID})
    assert r.status_code in (200, 202), r.text
    J2 = r.json()["job_id"]
    d = c.get(f"/v1/jobs/{J2}").json()
    assert d["status"] == "done", d
    call = _calls[-1]
    assert call["cues_ext"] == "srt", call

    # job phụ đề của NGƯỜI KHÁC → job render failed với lỗi rõ (không lộ file)
    with SessionLocal() as db:
        other = db.get(User, me["user_id"])
    r = co.post("/v1/jobs", json={"type": "render", "media_url": FAKE_MEDIA,
                                  "burn_subtitles": True,
                                  "subtitle_job_id": SUB_ID})
    assert r.status_code in (200, 202), r.text
    J3 = r.json()["job_id"]
    d = co.get(f"/v1/jobs/{J3}").json()
    assert d["status"] == "failed", d
    assert "không thuộc về bạn" in (d.get("error") or ""), d
finally:
    RND.run_render = real_run_render
print("4. subtitle_job_id: của mình OK, người khác fail .. OK")

# --------------------------------------------- 5. đuôi file phụ đề sai
RND.run_render = fake_run_render
try:
    r = c.post("/v1/jobs", json={"type": "render", "media_url": FAKE_MEDIA,
                                 "burn_subtitles": True,
                                 "subtitle_key": "jobs/x.pdf"})
    assert r.status_code in (200, 202), r.text
    J5 = r.json()["job_id"]
    d = c.get(f"/v1/jobs/{J5}").json()
    assert d["status"] == "failed" and ".pdf" in (d.get("error") or ""), d
finally:
    RND.run_render = real_run_render
print("5. đuôi phụ đề sai → failed rõ ràng ............... OK")

print("RENDER SUITE PASSED")
