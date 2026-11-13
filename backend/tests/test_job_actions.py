"""GD4 (C5) — POST /v1/jobs/{id}/actions + Job.revision (optimistic concurrency).

Vì sao có test riêng:
- `expected_revision` lệch → 409 KÈM revision mới là hợp đồng của agent:
  "có ai đó đổi job trước — đọc lại rồi thử". Sai shape (404/500, thiếu
  revision trong body) là agent không biết phải làm gì.
- `set_params` chỉ cho job TERMINAL (failed/cancelled/interrupted): dispatch
  gửi params SNAPSHOT trong tham số task — sửa params job đang chạy là vô
  nghĩa, chặn 409 phải bám đúng thông điệp hướng dẫn (hủy trước / dùng Nhân
  bản) thay vì chỉ báo lỗi chung chung.
- Sửa params đi QUA ĐÚNG đường validate tạo job (`_validate_job_in`) — hai
  đường validate là nguồn bug kinh điển (nguyên tắc GC3).
- revision tăng ở CẢ 3 chỗ đổi job: transition() thành công, claim_job thắng
  lease, set_params. Guard False KHÔNG tăng (race cancel-vs-done).

Chạy:
    cd backend && PYTHONPATH=. python tests/test_job_actions.py
"""
from __future__ import annotations

import os
import pathlib
import sys
import tempfile

WORK = pathlib.Path(tempfile.mkdtemp(prefix="vv_actions_"))
os.environ["DATABASE_URL"] = f"sqlite:///{WORK}/actions.db"
os.environ["MEDIA_ROOT"] = str(WORK / "media")
os.environ["VOICEVIBE_INLINE"] = "1"
os.environ.pop("VOICEVIBE_API_KEYS", None)
os.environ.pop("VOICEVIBE_ADMIN_KEY", None)

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import select  # noqa: E402

from app import main as MAIN  # noqa: E402
from app import ratelimit as RL  # noqa: E402
from app.main import app  # noqa: E402
from app.db import SessionLocal  # noqa: E402
from app.models import Job, JobStatus, User  # noqa: E402

c = TestClient(app)
RL.reset()
assert c.post("/v1/auth/setup",
              json={"email": "admin@local", "password": "matkhau123"}).status_code == 201

real_dispatch = MAIN.dispatch
MAIN.dispatch = lambda *a, **k: ("inline", None)


def mk_job(status: JobStatus, *, params: dict | None = None) -> str:
    with SessionLocal() as db:
        # GHIM admin — select limit(1) không ORDER BY là không xác định trên
        # DB có nhiều user (đã dính thật: job về tay u2 → admin GET 404).
        UID = db.scalars(select(User.id).where(
            User.role == "admin").limit(1)).first()
        j = Job(user_id=UID, type="translate", status=status, params=params or {})
        db.add(j)
        db.commit()
        db.refresh(j)
        return j.id


# --------------------------------------------- 1. GET trả revision; transition tăng
QJ = c.post("/v1/jobs", json={"type": "translate", "text": "x",
                              "source_lang": "vi", "target_lang": "en"}).json()["job_id"]
d = c.get(f"/v1/jobs/{QJ}").json()
assert d["revision"] == 0, d
assert c.post(f"/v1/jobs/{QJ}/cancel").status_code == 200
assert c.get(f"/v1/jobs/{QJ}").json()["revision"] == 1, "cancel là 1 transition"
assert c.post(f"/v1/jobs/{QJ}/retry").status_code in (200, 202)
assert c.get(f"/v1/jobs/{QJ}").json()["revision"] == 2, "retry là transition thứ 2"
# guard False không tăng: cancel job đã kết thúc (done) → 409, revision đứng yên
DONED = mk_job(JobStatus.done)
assert c.post(f"/v1/jobs/{DONED}/cancel").status_code == 409
assert c.get(f"/v1/jobs/{DONED}").json()["revision"] == 0
print("1. GET revision + transition tăng, guard False đứng yên . OK")

# --------------------------------------------- 2. claim_job thắng lease cũng tăng
from app.jobstate import claim_job  # noqa: E402

CJ = mk_job(JobStatus.queued)
with SessionLocal() as db:
    j = db.get(Job, CJ)
    before = j.revision or 0
    assert claim_job(db, CJ, "task-x")
with SessionLocal() as db:
    assert db.get(Job, CJ).revision == before + 1, "lease cũng là một lần đổi"
print("2. claim_job tăng revision ....................... OK")

# --------------------------------------------- 3. actions: auth/404/action lạ
c.cookies.clear()
r = c.post(f"/v1/jobs/{QJ}/actions", json={"action": "cancel"})
assert r.status_code == 401, r.status_code
r = c.post("/v1/auth/login",
           json={"email": "admin@local", "password": "matkhau123"})
assert r.status_code in (200, 204)
U2 = mk_job(JobStatus.queued)
with SessionLocal() as db:  # job của user khác — IDOR phải 404 (giấu sự tồn tại)
    u2 = User(email="u2@local", password_hash="x", role="user")
    db.add(u2)
    db.commit()
    db.refresh(u2)
    j = db.get(Job, U2)
    j.user_id = u2.id
    db.commit()
# IDOR: user THƯỜNG không được hành động trên job người khác (admin được —
# _own_job chủ-or-admin; 404 giấu sự tồn tại, không 403 lộ)
from app.security import hash_password  # noqa: E402

with SessionLocal() as db:
    u2 = db.scalars(select(User).where(User.email == "u2@local")).first()
    u2.password_hash = hash_password("matkhau456")
    db.commit()
c2 = TestClient(app)
RL.reset()
assert c2.post("/v1/auth/login",
               json={"email": "u2@local", "password": "matkhau456"}
               ).status_code in (200, 204)
assert c2.post(f"/v1/jobs/{QJ}/actions",
               json={"action": "cancel"}).status_code == 404
r = c.post(f"/v1/jobs/{QJ}/actions", json={"action": "nổ máy"})
assert r.status_code == 422 and "cancel" in r.text, r.text
print("3. 401/404 IDOR/action lạ 422 .................... OK")

# --------------------------------------------- 4. set_params: 422/409 theo trạng thái
FJ = mk_job(JobStatus.failed, params={"source_lang": "vi", "target_lang": "ja"})
assert c.post(f"/v1/jobs/{FJ}/actions", json={"action": "set_params"}).status_code == 422
RJ = mk_job(JobStatus.running)
r = c.post(f"/v1/jobs/{RJ}/actions", json={"action": "set_params",
                                           "patch": {"target_lang": "en"}})
assert r.status_code == 409 and "hủy trước" in r.text, r.text
DJ = mk_job(JobStatus.done)
r = c.post(f"/v1/jobs/{DJ}/actions", json={"action": "set_params",
                                           "patch": {"target_lang": "en"}})
assert r.status_code == 409 and "duplicate" in r.text, r.text
# sai tham số → 422 từ validate (glossary sai định dạng)
r = c.post(f"/v1/jobs/{FJ}/actions", json={"action": "set_params",
                                           "patch": {"glossary": "thiếu dấu bằng"}})
assert r.status_code == 422 and "dòng 1" in r.text, r.text
print("4. set_params: 422 rỗng/validate, 409 running/done OK")

# --------------------------------------------- 5. set_params hợp lệ + revision
RL.reset()
_g = c.get(f"/v1/jobs/{FJ}")
assert _g.status_code == 200, (_g.status_code, _g.text)
rev0 = _g.json()["revision"]
r = c.post(f"/v1/jobs/{FJ}/actions", json={"action": "set_params",
                                           "patch": {"target_lang": "en"}})
assert r.status_code == 200, r.text
assert r.json()["revision"] == rev0 + 1
d = c.get(f"/v1/jobs/{FJ}").json()
assert d["status"] == "failed", "set_params KHÔNG đổi trạng thái (chạy lại riêng)"
assert d["params"]["target_lang"] == "en" and d["params"]["source_lang"] == "vi", d["params"]
# runtime key của pipeline không kế thừa khi set_params (cùng luật _DUP_STRIP)
FJ2 = mk_job(JobStatus.failed, params={"stage": "tts", "resume": 1})
c.post(f"/v1/jobs/{FJ2}/actions", json={"action": "set_params",
                                        "patch": {"text": "hi"}})
d2 = c.get(f"/v1/jobs/{FJ2}").json()
assert "stage" not in d2["params"] and "resume" not in d2["params"], d2["params"]
print("5. set_params hợp lệ: revision+1, merge, strip runtime . OK")

# --------------------------------------------- 6. optimistic concurrency 409/200
D = c.get(f"/v1/jobs/{FJ}").json()["revision"]
r = c.post(f"/v1/jobs/{FJ}/actions", json={"action": "set_params",
                                           "patch": {"target_lang": "ja"},
                                           "expected_revision": D - 1})
assert r.status_code == 409, r.text
assert r.json()["revision"] == D, f"409 phải trả revision mới: {r.text}"
r = c.post(f"/v1/jobs/{FJ}/actions", json={"action": "set_params",
                                           "patch": {"target_lang": "ja"},
                                           "expected_revision": D})
assert r.status_code == 200 and r.json()["revision"] == D + 1, r.text
# expected_revision không gửi = không kiểm (mặc định chấp nhận)
assert c.post(f"/v1/jobs/{FJ}/actions",
              json={"action": "set_params", "patch": {"target_lang": "fr"}}
              ).status_code == 200
print("6. expected_revision: 409 kèm revision mới / 200 . OK")

# --------------------------------------------- 7. cancel/retry/duplicate qua actions
AJ = mk_job(JobStatus.queued)
assert c.post(f"/v1/jobs/{AJ}/actions", json={"action": "cancel"}).status_code == 200
assert c.get(f"/v1/jobs/{AJ}").json()["status"] == "cancelled"
r = c.post(f"/v1/jobs/{AJ}/actions", json={"action": "retry"})
assert r.status_code == 200 and r.json()["status"] == "queued", r.text
r = c.post(f"/v1/jobs/{AJ}/actions", json={"action": "duplicate",
                                           "patch": {"text": "bản khác"}})
assert r.status_code == 200, r.text
NEW = r.json()["job_id"]
d = c.get(f"/v1/jobs/{NEW}").json()
assert d["status"] == "queued" and d["params"]["text"] == "bản khác", d
print("7. cancel/retry/duplicate qua actions ............. OK")

# --------------------------------------------- 8. X-API-Key hành động được
raw = c.post("/v1/keys", json={}).json()["key"]
c.cookies.clear()
r = c.post(f"/v1/jobs/{FJ}/actions",
           headers={"X-API-Key": raw},
           json={"action": "set_params", "patch": {"target_lang": "de"}})
assert r.status_code == 200, (r.status_code, r.text)
assert r.json()["revision"] > 0
print("8. X-API-Key: agent hành động không cần cookie .... OK")

# --------------------------------------------- 9. audit job.set_params
# Đường admin (current_admin) KHÔNG nhận X-API-Key (thiết kế cũ: chỉ cookie
# phiên hoặc X-Admin-Key) — đăng nhập lại bằng cookie cho phần này.
assert c.post("/v1/auth/login",
              json={"email": "admin@local", "password": "matkhau123"}
              ).status_code in (200, 204)
r = c.get("/v1/admin/audit?limit=50")
assert r.status_code == 200, r.status_code
rows = r.json().get("actions") or r.json().get("rows") or r.json()
blob = str(rows)
assert "job.set_params" in blob, blob[:400]
print("9. audit ghi job.set_params ....................... OK")

MAIN.dispatch = real_dispatch
print("JOB ACTIONS SUITE PASSED")
