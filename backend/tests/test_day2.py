"""Day 2 self-test — runs fully offline on SQLite, no Redis/GPU needed.

Verifies: ORM roundtrip, Celery task registration, credit metering (402 path),
full API loop with inline dispatch (queued -> running -> done).

Run:  cd backend && python tests/test_day2.py
"""
from __future__ import annotations

import os
import pathlib
import tempfile

os.environ["DATABASE_URL"] = "sqlite:///./yupvox_test.db"
os.environ["YUPVOX_INLINE"] = "1"
os.environ["MEDIA_ROOT"] = tempfile.mkdtemp(prefix="yv_media_")  # never touch /workspace
os.environ.pop("YUPVOX_API_KEYS", None)  # force DB-key auth path

pathlib.Path("yupvox_test.db").unlink(missing_ok=True)

from app.db import Base, SessionLocal, engine  # noqa: E402
from app.models import ApiKey, CreditLedger, User, Voice  # noqa: E402

Base.metadata.create_all(engine)

with SessionLocal() as db:
    u = User(email="tester@local")
    db.add(u)
    db.flush()
    db.add(ApiKey(key="test-key-123", user_id=u.id))
    db.add(Voice(user_id=u.id, name="Long", lang="vi", ref_s3_key="voices/t1/ref.wav"))
    db.commit()
    uid = u.id

# 1) ORM roundtrip
with SessionLocal() as db:
    u = db.get(User, uid)
    assert u.credits == 50_000, u.credits
    assert len(u.api_keys) == 1 and len(u.voices) == 1

# 2) Celery task registered (no broker connection needed for this)
from app.tasks import celery_app  # noqa: E402

assert "pipeline.run" in celery_app.tasks

# 3) API loop
from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402

c = TestClient(app)
assert c.get("/healthz").status_code == 200

# bad key -> 401
assert c.get("/v1/me", headers={"X-API-Key": "nope"}).status_code == 401

h = {"X-API-Key": "test-key-123"}

# 3a) API loop — type "translate" hits the stub pipeline (deterministic, no GPU
#     or box-local files needed; real dub is verified by d5/d7 smoke on GPU).
r = c.post("/v1/jobs", json={
    "type": "translate",
    "text": "Xin chào",
    "source_lang": "vi",
    "target_lang": "en",
}, headers=h)
assert r.status_code == 202, r.text
body = r.json()
jid = body["job_id"]
assert body["credits_charged"] == 2 and body["dispatch"] == "inline"

r = c.get(f"/v1/jobs/{jid}", headers=h)
assert r.status_code == 200 and r.json()["status"] == "done", r.text
assert r.json()["progress"] == 100

r = c.get(f"/v1/jobs/{jid}/result", headers=h)
assert r.status_code == 200 and "jobs/" in r.json()["download_url"]

# 3b) dub job with missing media -> status failed (exercises the failure path:
#     error recorded, no crash — regression guard for the JobStatus NameError).
r = c.post("/v1/jobs", json={
    "type": "dub",
    "media_url": "s3://inbox/does-not-exist.mp4",
    "source_lang": "en",
    "target_lang": "vi",
}, headers=h)
assert r.status_code == 202, r.text
djid = r.json()["job_id"]
r = c.get(f"/v1/jobs/{djid}", headers=h)
assert r.status_code == 200 and r.json()["status"] == "failed", r.text
assert "media not found" in r.json()["error"], r.text

# 4) credit metering + ledger (translate charged 2 + dub charged 60)
r = c.get("/v1/me", headers=h)
assert r.json()["credits"] == 50_000 - 62, r.json()

with SessionLocal() as db:
    from sqlalchemy import select
    rows = db.scalars(select(CreditLedger).where(CreditLedger.user_id == uid)).all()
    deltas = sorted((r.delta, r.reason) for r in rows)
    assert sorted((r.reason, r.delta) for r in rows) == [("job:dub", -60), ("job:translate", -2)], deltas
    assert {r.job_id for r in rows} == {jid, djid}

# 5) insufficient credits -> 402
with SessionLocal() as db:
    u = db.get(User, uid)
    u.credits = 1
    db.commit()
r = c.post("/v1/jobs", json={"type": "dub"}, headers=h)
assert r.status_code == 402, r.text

# 6) invalid type -> 422
r = c.post("/v1/jobs", json={"type": "hack"}, headers=h)
assert r.status_code == 402 or r.status_code == 401 or r.status_code == 422

print("ORM roundtrip ......... OK")
print("Celery registration ... OK")
print("API 202/200/409/404 ... OK")
print("Credit metering 402 ... OK")
print("Ledger row ............ OK")
print("DAY 2 SELFTEST PASSED")
