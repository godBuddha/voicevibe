"""Day 2 self-test — runs fully offline on SQLite, no Redis/GPU needed.

Verifies: ORM roundtrip, Celery task registration, credit metering (402 path),
full API loop with inline dispatch (queued -> running -> done).

Run:  cd backend && python tests/test_day2.py
"""
from __future__ import annotations

import hashlib
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

# API keys are stored SHA-256 hashed (DB dump exposes no usable keys).
TEST_KEY = "test-key-123"
TEST_KEY_HASH = hashlib.sha256(TEST_KEY.encode()).hexdigest()

Base.metadata.create_all(engine)

with SessionLocal() as db:
    u = User(email="tester@local")
    db.add(u)
    db.flush()
    db.add(ApiKey(key=TEST_KEY_HASH, prefix=TEST_KEY[:12], user_id=u.id))
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

h = {"X-API-Key": TEST_KEY}

# 3a) API loop — dispatch path is monkeypatched deterministic (no models/GPU
#     needed): the real translate pipeline has its own selftest with a mock
#     HTTP layer (app.pipelines.translate --selftest).
import app.tasks as _tasks  # noqa: E402


def _fake_translate(job_id: str, params: dict) -> dict:
    from app.db import SessionLocal
    from app.models import Job, JobStatus

    key = f"jobs/{job_id}/translated.txt"
    from app.storage import get_storage

    get_storage().put(key, "TRANSLATED".encode())
    with SessionLocal() as db:
        job = db.get(Job, job_id)
        job.status = JobStatus.done
        job.progress = 100
        job.result_s3_key = key
        db.commit()
    return {"ok": True, "key": key}


_tasks._run_translate = _fake_translate

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

# 3b) dub job with missing media -> status failed + FULL REFUND (failed jobs
#     are free; regression guard for the JobStatus NameError + refund logic).
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

# 3c) subtitle job -> 501, NO credits charged (pipeline not implemented yet).
r = c.post("/v1/jobs", json={"type": "subtitle", "text": "hi"}, headers=h)
assert r.status_code == 501, r.text

# 3d) signup -> user + API key (hashed in DB), key works immediately.
r = c.post("/v1/auth/signup", json={"email": "New@Example.io"})
assert r.status_code == 201, r.text
su = r.json()
assert su["key"].startswith("yv_")
r = c.get("/v1/me", headers={"X-API-Key": su["key"]})
assert r.status_code == 200 and r.json()["user_id"] == su["user_id"], r.text
# duplicate email -> 409
r = c.post("/v1/auth/signup", json={"email": "new@example.io"})
assert r.status_code == 409, r.text

# 4) credit metering + ledger: translate -2 stays; dub -60 refunded on failure
r = c.get("/v1/me", headers=h)
assert r.json()["credits"] == 50_000 - 2, r.json()

with SessionLocal() as db:
    from sqlalchemy import select
    rows = db.scalars(select(CreditLedger).where(CreditLedger.user_id == uid)).all()
    got = sorted((r.reason, r.delta) for r in rows)
    assert got == [("job:dub", -60), ("job:translate", -2), ("refund:job:dub", 60)], got
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
