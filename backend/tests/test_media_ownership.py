"""B4b — Guard quyền đọc media theo HỌ KHOÁ `jobs/{job_id}/…`.

Vì sao có test riêng: `_owns_media` mở rộng từ "khớp chính xác result_s3_key"
sang "họ khoá jobs/{id}/…" là THAY ĐỔI BẢO MẬT (rủi ro số 5 của kế hoạch):
- đúng chủ job phải đọc được output PHỤ (bilingual.srt — không là result_key
  của job nào, trước đây 404 ngay với chính chủ);
- user khác PHẢI 404 (không 403 — không xác nhận tồn tại) dù cùng tiền tố;
- khoá "jobs/" rác / id job không tồn tại → 404.

Bootstrap khớp pattern repo. Chạy:
    cd backend && PYTHONPATH=. python tests/test_media_ownership.py
"""
from __future__ import annotations

import os
import pathlib
import sys
import tempfile

WORK = pathlib.Path(tempfile.mkdtemp(prefix="vv_own_"))
os.environ["DATABASE_URL"] = f"sqlite:///{WORK}/own.db"
os.environ["MEDIA_ROOT"] = str(WORK / "media")
os.environ["VOICEVIBE_INLINE"] = "1"
os.environ.pop("VOICEVIBE_API_KEYS", None)
os.environ.pop("VOICEVIBE_ADMIN_KEY", None)

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient  # noqa: E402

from app import ratelimit as RL  # noqa: E402
from app.db import SessionLocal  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Job as JobRow  # noqa: E402
from app.models import User  # noqa: E402
from app.security import hash_password  # noqa: E402
from app.storage import get_storage  # noqa: E402

c = TestClient(app)
RL.reset()
assert c.post("/v1/auth/setup",
              json={"email": "admin@local", "password": "matkhau123"}).status_code == 201
assert c.post("/v1/auth/login",
              json={"email": "x", "password": "x"}).status_code in (401, 429)
me = c.post("/v1/auth/login",
            json={"email": "admin@local", "password": "matkhau123"})
assert me.status_code == 200

# seed 2 user thường
for email in ("owner@local", "other@local"):
    with SessionLocal() as db:
        db.add(User(email=email, role="user",
                    password_hash=hash_password("matkhau456")))
        db.commit()
owner = TestClient(app)
other = TestClient(app)
RL.reset()
assert owner.post("/v1/auth/login",
                  json={"email": "owner@local", "password": "matkhau456"}).status_code == 200
RL.reset()
assert other.post("/v1/auth/login",
                  json={"email": "other@local", "password": "matkhau456"}).status_code == 200
RL.reset()

with SessionLocal() as db:
    owner_row = db.query(User).filter_by(email="owner@local").one()
    other_row = db.query(User).filter_by(email="other@local").one()
    j_owner = JobRow(user_id=owner_row.id, type="dub", status="done",
                     params={}, result_s3_key="jobs/JO1/dub.mp4")
    j_other = JobRow(user_id=other_row.id, type="dub", status="done",
                     params={}, result_s3_key="jobs/JO2/dub.mp4")
    db.add_all([j_owner, j_other])
    db.commit()
    O1, O2 = j_owner.id, j_other.id

# đặt file thật: output chính + output PHỤ (bilingual.srt)
storage = get_storage()
storage.put(f"jobs/{O1}/dub.mp4", b"MP4")
storage.put(f"jobs/{O1}/bilingual.srt", b"SRT")
storage.put(f"jobs/{O2}/dub.mp4", b"MP4")

# ------------------------------------------------ 1. chủ job đọc đủ mọi file
for key in (f"jobs/{O1}/dub.mp4", f"jobs/{O1}/bilingual.srt"):
    r = owner.get(f"/media/{key}")
    assert r.status_code == 200, f"{key}: chủ job phải đọc được → {r.status_code}"
# 2. output phụ KHÔNG là result_key — chính là case 404 trước đây
assert not any(j.result_s3_key == f"jobs/{O1}/bilingual.srt"
               for j in [j_owner]), "tiền điều kiện: srt phụ không phải result_key"
print("1. chủ job đọc result + output phụ bilingual.srt  OK")

# --------------------------------------------- 2. user khác → 404 (không 403)
for key in (f"jobs/{O1}/dub.mp4", f"jobs/{O1}/bilingual.srt"):
    r = other.get(f"/media/{key}")
    assert r.status_code == 404, f"{key}: user khác phải 404 → {r.status_code}"
# 3. admin đọc được mọi thứ (admin override)
assert c.get(f"/media/jobs/{O1}/bilingual.srt").status_code == 200
print("2. user khác 404; admin đọc được ................. OK")

# --------------------------------------------- 3. khoá rác / id lạ / không id
assert other.get("/media/jobs/ABCDEF/dub.mp4").status_code == 404, "id không tồn tại"
assert other.get("/media/jobs/dub.mp4").status_code == 404, "khoá 2 đoạn không id"
anon = TestClient(app)
RL.reset()
assert anon.get(f"/media/jobs/{O1}/dub.mp4").status_code == 401
print("3. id lạ + 2 đoạn + chưa đăng nhập 401 ........... OK")

# ------------------------------- 4. guard NGƯỢC: gỡ chủ job → file đó chết
with SessionLocal() as db:
    row = db.get(JobRow, O1)
    db.delete(row)
    db.commit()
assert owner.get(f"/media/jobs/{O1}/bilingual.srt").status_code == 404, \
    "xoá chủ job thì output phụ KHÔNG còn ai đọc được (guard ngược)"
print("4. guard ngược: xoá chủ job → 404 ................ OK")

print("MEDIA OWNERSHIP SUITE PASSED")
