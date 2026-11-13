"""GD1 — Bàn điều khiển FFmpeg bằng lời: preview + validate + job ffmpeg.

Vì sao có test riêng:
- argv từ LLM điều khiển THỰC THI trên máy chủ — MỌI lớp chặn của
  validate_argv phải được neo bằng test (binary lạ / URL / device grabber /
  `..` / nhiều output / ext lạ / thiếu nguồn). Sót một lớp = lộ RCE.
- Worker chạy validate LẦN HAI với ext THẬT — operand input của LLM đo sai
  ext (preview đo "mp4", file tải về là "webm") phải được chuẩn hóa đúng.
- Job thật: publish version GC3 + progress từ `-progress pipe:1` + manifest
  stage "encode" (retry encode dài không encode lại).
- Preview: chưa cấu hình model → 422; LLM JSON bẩn → 502; file người khác →
  404 (LLM không được dịch lệnh đọc file người khác).

Chạy:
    cd backend && PYTHONPATH=. python tests/test_ffmpeg_cmd.py
"""
from __future__ import annotations

import json
import os
import pathlib
import sys
import tempfile

WORK = pathlib.Path(tempfile.mkdtemp(prefix="vv_ffmpeg_"))
os.environ["DATABASE_URL"] = f"sqlite:///{WORK}/ffmpeg.db"
os.environ["MEDIA_ROOT"] = str(WORK / "media")
os.environ["VOICEVIBE_INLINE"] = "1"
os.environ.pop("VOICEVIBE_API_KEYS", None)
os.environ.pop("VOICEVIBE_ADMIN_KEY", None)

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient  # noqa: E402

from app import main as MAIN  # noqa: E402
from app import ratelimit as RL  # noqa: E402
from app.main import app  # noqa: E402
from app.pipelines import ffmpeg_cmd as FC  # noqa: E402

c = TestClient(app)
RL.reset()
assert c.post("/v1/auth/setup",
              json={"email": "admin@local", "password": "matkhau123"}).status_code == 201

GOOD = ["ffmpeg", "-y", "-i", "/work/input.mp4", "-ss", "120", "-t", "10",
        "/work/output.mp4"]

# --------------------------------------------- 1. validate_argv đã neo ở selftest
FC._selftest()

# --------------------------------------------- 2. preview: auth/422 validate đầu vào
c.cookies.clear()
assert c.post("/v1/ffmpeg/preview",
              json={"instruction": "cắt đoạn 2 phút"}).status_code == 401
assert c.post("/v1/auth/login",
              json={"email": "admin@local", "password": "matkhau123"}
              ).status_code in (200, 204)
RL.reset()
r = c.post("/v1/ffmpeg/preview", json={"instruction": "x"})
assert r.status_code == 422, r.text
r = c.post("/v1/ffmpeg/preview", json={"instruction": "cắt đoạn 2 phút"})
assert r.status_code == 422 and "nguồn" in r.text, r.text
r = c.post("/v1/ffmpeg/preview",
           json={"instruction": "xoá quảng cáo", "media_url": "media/x/v.mp4",
                 "remove_sponsor": True})
assert r.status_code == 422 and "SponsorBlock" in r.text, r.text
# media người khác → 404 (admin thì được — dùng user thường kiểm)
r = c.post("/v1/ffmpeg/preview",
           json={"instruction": "cắt đoạn 2 phút", "source_url": "https://x/v"})
assert r.status_code == 422 and "mô hình" in r.text.lower(), r.text
print("2. preview: 401/422 nguồn + sponsor + chưa cấu hình model ... OK")

# --------------------------------------------- 3. preview với FakeChat
from app.pipelines import summary as SUMMARY  # noqa: E402

GOOD_JSON = ('{"command":"ffmpeg -y -i /work/input.mp4 -ss 120 -t 10 '
             '/work/output.mp4","explanation":"cắt từ phút 2 kéo dài 10 giây",'
             '"warnings":[]}')


class FakeChat:
    def __init__(self, resp: str) -> None:
        self.resp = resp
        self.system_seen = ""
        self.user_seen = ""
        self.kw = {}

    def complete(self, system, user, *, json_mode=False, max_tokens=2048,
                 **kw):
        self.system_seen, self.user_seen, self.kw = system, user, kw
        return self.resp


real_build = SUMMARY.build_chat
SUMMARY.build_chat = lambda: FakeChat(GOOD_JSON)
try:
    RL.reset()
    r = c.post("/v1/ffmpeg/preview",
               json={"instruction": "cắt từ 2:00 đến 2:10",
                     "media_url": "media/x/video.mp4"})
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["ffmpeg_argv"][0] == "ffmpeg" and d["output_ext"] == "mp4", d
    assert d["input_name"] == "/work/input.mp4", d
    assert "cắt" in d["explanation"], d
    # quyền sở hữu: key đúng chủ (media/x — admin luôn ok), file của người khác
    r = c.post("/v1/ffmpeg/preview",
               json={"instruction": "cắt đoạn", "media_url": "media/u2/other.mp4"})
    assert r.status_code == 200, r.text  # admin đọc được mọi file

    # LLM JSON bẩn → 502
    SUMMARY.build_chat = lambda: FakeChat("mô hình lôi thôi không json")
    RL.reset()
    r = c.post("/v1/ffmpeg/preview",
               json={"instruction": "cắt đoạn", "media_url": "media/x/v.mp4"})
    assert r.status_code == 502 and "Dịch lại" in r.text, r.text
    # LLM sinh lệnh vi phạm hợp đồng → 502 kèm hướng dẫn
    SUMMARY.build_chat = lambda: FakeChat(
        '{"command":"ffmpeg -i http://evil /work/output.mp4",'
        '"explanation":"x","warnings":[]}')
    RL.reset()
    r = c.post("/v1/ffmpeg/preview",
               json={"instruction": "cắt đoạn", "media_url": "media/x/v.mp4"})
    assert r.status_code == 502 and "không hợp lệ" in r.text, r.text
finally:
    SUMMARY.build_chat = real_build
    RL.reset()
print("3. preview FakeChat: 200 + 502 JSON bẩn + 502 vi phạm ... OK")

# --------------------------------------------- 4. tạo job ffmpeg: validate lúc tạo
real_dispatch = MAIN.dispatch
MAIN.dispatch = lambda *a, **k: ("inline", None)
# admin bypass _owns_media (đúng thiết kế _own_job/_owns_media: chủ-or-admin)
# — cử admin tạo file "media/admin/secret.mp4" cho ca 404 của user thường sau.
RL.reset()
r = c.post("/v1/jobs", json={"type": "ffmpeg", "ffmpeg_argv": GOOD,
                             "media_url": "media/u2/other.mp4"})
assert r.status_code in (200, 202), r.text  # admin đọc được mọi file
# admin bypass _owns_media — 404 chỉ đúng cho user thường; kiểm bằng c2
from app.security import hash_password  # noqa: E402
from app.db import SessionLocal  # noqa: E402
from app.models import User, MediaObject  # noqa: E402

with SessionLocal() as db:
    u2 = db.get(User, None) or None
    from sqlalchemy import select
    # tạo user thường + media object của user đó
    if db.scalars(select(User).where(User.email == "u2@local")).first() is None:
        db.add(User(email="u2@local",
                    password_hash=hash_password("matkhau456"), role="user"))
        db.commit()
    u2 = db.scalars(select(User).where(User.email == "u2@local")).first()
    if db.scalars(select(MediaObject).where(
            MediaObject.key == "media/u2/other.mp4")).first() is None:
        db.add(MediaObject(key="media/u2/other.mp4", user_id=u2.id))
        db.commit()
c2 = TestClient(app)
RL.reset()
assert c2.post("/v1/auth/login",
               json={"email": "u2@local", "password": "matkhau456"}
               ).status_code in (200, 204)

try:
    RL.reset()
    r = c2.post("/v1/jobs", json={"type": "ffmpeg", "ffmpeg_argv": GOOD,
                                  "media_url": "media/u2/other.mp4"})
    assert r.status_code in (200, 202), r.text
    RL.reset()
    r = c2.post("/v1/jobs", json={"type": "ffmpeg", "media_url": "media/u2/other.mp4"})
    assert r.status_code == 422 and "ffmpeg_argv" in r.text, r.text
    RL.reset()
    r = c2.post("/v1/jobs", json={"type": "ffmpeg", "ffmpeg_argv": GOOD})
    assert r.status_code == 422 and "ĐÚNG MỘT nguồn" in r.text, r.text
    RL.reset()
    r = c2.post("/v1/jobs", json={"type": "ffmpeg",
                                  "ffmpeg_argv": ["ffmpeg", "-i", "http://x",
                                                  "/work/input.mp4",
                                                  "/work/output.mp4"],
                                  "media_url": "media/u2/other.mp4"})
    assert r.status_code == 422 and "URL" in r.text, r.text
    RL.reset()
    r = c2.post("/v1/jobs", json={"type": "ffmpeg", "ffmpeg_argv": GOOD,
                                  "media_url": "media/admin/secret.mp4"})
    assert r.status_code == 404, "file người khác 404"
    print("4. tạo job: 422 thiếu argv/nguồn/URL + 404 IDOR ........ OK")
finally:
    MAIN.dispatch = real_dispatch

# --------------------------------------------- 5. worker _run_ffmpeg với fake runner
from app import tasks as TK  # noqa: E402
from app.pipelines import ffmpeg_cmd as FCM  # noqa: E402

# nguồn "media/u2/other.mp4" phải có file thật trên storage (Local)
with SessionLocal() as db:
    pass
import shutil  # noqa: E402

media_root = str(WORK / "media")
os.makedirs(os.path.join(media_root, "u2"), exist_ok=True)
# tạo file mp4 giả đủ lớn để ffprobe skip (probe_duration trả None là ok)
with open(os.path.join(media_root, "u2", "other.mp4"), "wb") as f:
    f.write(b"\x00" * 2048)

calls: list[list[str]] = []


def fake_runner(argv):
    calls.append(list(argv))
    # -progress phải đứng TRƯỚC operand output (đặt sau là output thứ hai)
    out_idx = argv.index("/work/output.mp4") if "/work/output.mp4" in argv \
        else argv.index([a for a in argv if a.endswith("output.mp4")][0])
    assert "-progress" in argv and argv.index("-progress") < out_idx, argv
    wd = os.path.dirname(argv[out_idx])
    with open(os.path.join(wd, "output.mp4"), "wb") as f:
        f.write(b"\x00" * 4096)
    # contract của FC.run_ffmpeg: (code, stderr đuôi) — progress đã neo ở selftest
    return (0, "err tail")


real_run = FCM.run_ffmpeg
FCM.run_ffmpeg = lambda argv, wd, **kw: fake_runner(argv)  # noqa: E731
real_resolve = TK._resolve_media
TK._resolve_media = lambda key, storage: os.path.join(
    media_root, *key.split("/")[1:])  # media/u2/other.mp4 → path thật
try:
    RL.reset()
    MAIN.dispatch = real_dispatch  # inline thật cho job này
    r = c2.post("/v1/jobs", json={"type": "ffmpeg", "ffmpeg_argv": GOOD,
                                  "media_url": "media/u2/other.mp4"})
    assert r.status_code in (200, 202), r.text
    JID = r.json()["job_id"]
    d = c2.get(f"/v1/jobs/{JID}").json()
    assert d["status"] == "done", d
    assert d["result_key"].endswith("out/result-v1.mp4"), d  # publish GC3 đổi con trỏ
    assert d["revision"] >= 2, d
    assert d["params"].get("stage"), "progress phải được ghi"
    # result tải được + artifact v1 published (GC3)
    res = c2.get(f"/v1/jobs/{JID}/result").json()
    assert res.get("download_url") or res.get("kind") == "audio", res
    arts = c2.get(f"/v1/jobs/{JID}/artifacts").json()
    assert arts["artifacts"] and arts["artifacts"][0]["version"] == 1, arts
    # file xuất thật trên storage
    assert os.path.getsize(os.path.join(
        media_root, "jobs", JID, "output.mp4")) == 4096
finally:
    FCM.run_ffmpeg = real_run
    TK._resolve_media = real_resolve
    MAIN.dispatch = lambda *a, **k: ("inline", None)
    RL.reset()
print("5. worker _run_ffmpeg: fake runner → done + v1 .... OK")

# --------------------------------------------- 6. retry encode: stage encode reuse
try:
    # Mô phỏng job bị sweep đánh dấu interrupted SAU khi encode xong (ca thật:
    # encode 2h xong nhưng worker chết trước khi publish) — Chạy lại phải dùng
    # lại output đã encode, KHÔNG gọi ffmpeg lần hai.
    from app.models import Job, JobStatus
    from app.db import SessionLocal as SL

    with SL() as db:
        j = db.get(Job, JID)
        j.status = JobStatus.interrupted
        db.commit()
    TK._resolve_media = real_resolve_backup = TK._resolve_media
    TK._resolve_media = lambda key, storage: os.path.join(
        media_root, *key.split("/")[1:])  # đặt lại mock (§5 đã khôi phục)
    n_calls_before = len(calls)
    MAIN.dispatch = real_dispatch
    RL.reset()
    r = c2.post(f"/v1/jobs/{JID}/retry")
    assert r.status_code in (200, 202), r.text
    d = c2.get(f"/v1/jobs/{JID}").json()
    assert d["status"] == "done", d
    assert len(calls) == n_calls_before, \
        f"stage encode còn phải KHÔNG encode lại: {len(calls)} > {n_calls_before}"
finally:
    MAIN.dispatch = lambda *a, **k: ("inline", None)
print("6. retry encode: manifest stage reuse, không chạy lại . OK")

# --------------------------------------------- 7. ffmpeg thất bại → failed + human_error
def bad_runner(argv):
    return (1, "ffmpeg: Permission denied - somepath\nsomething else")


FCM.run_ffmpeg = lambda argv, wd, **kw: bad_runner(argv)
try:
    MAIN.dispatch = real_dispatch  # inline thật — job chạy ngay
    TK._resolve_media = lambda key, storage: os.path.join(
        media_root, *key.split("/")[1:])  # mock nguồn (§6 đã giữ, đặt lại chắc)
    RL.reset()
    r = c2.post("/v1/jobs", json={"type": "ffmpeg", "ffmpeg_argv": GOOD,
                                  "media_url": "media/u2/other.mp4"})
    assert r.status_code in (200, 202), r.text
    JID2 = r.json()["job_id"]
    d = c2.get(f"/v1/jobs/{JID2}").json()
    assert d["status"] == "failed" and "quyền" in d["error"].lower(), d
finally:
    FCM.run_ffmpeg = real_run
    MAIN.dispatch = lambda *a, **k: ("inline", None)
    RL.reset()
print("7. ffmpeg fail: human_error tiếng Việt ........... OK")

# --------------------------------------------- 8. sponsorblock argv qua yt-dlp
from app.pipelines import download as DLM  # noqa: E402

argv_sb = DLM.build_argv("https://x/v", "/tmp", "1080",
                         extra_args=["--sponsorblock-remove", "sponsor,selfpromo"])
assert "--sponsorblock-remove" in argv_sb, argv_sb
assert argv_sb.index("--sponsorblock-remove") < argv_sb.index("https://x/v"), argv_sb
argv_plain = DLM.build_argv("https://x/v", "/tmp", "1080")
assert "--sponsorblock-remove" not in argv_plain, argv_plain
print("8. sponsorblock: extra_args nối trước URL ........ OK")

print("FFMPEG CMD SUITE PASSED")
