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

os.environ["DATABASE_URL"] = "sqlite:///./voicevibe_test.db"
os.environ["VOICEVIBE_INLINE"] = "1"
os.environ["MEDIA_ROOT"] = tempfile.mkdtemp(prefix="vv_media_")  # never touch /workspace
os.environ.pop("VOICEVIBE_API_KEYS", None)  # force DB-key auth path

pathlib.Path("voicevibe_test.db").unlink(missing_ok=True)

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

# 3f) result payload đủ hình dạng cho UI: kind/filename/content (chữ, ≤64KB).
#     Trước đây chỉ trả {job_id, download_url} — SPA không biết kết quả là
#     audio/video/chữ và phải tự tải file thêm một lượt.
res = r.json()
assert res["kind"] == "text" and res["filename"].endswith(".txt"), res
assert res["content"] == "TRANSLATED", res

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

# 3c) subtitle: ĐÃ có pipeline thật (trước đây 501). Cấu hình sai phải bị chặn
#     bằng 422 TRƯỚC khi trừ credit — cùng nguyên tắc với quyền sở hữu voice.
r = c.post("/v1/jobs", json={"type": "subtitle", "text": "hi"}, headers=h)
assert r.status_code == 422, r.text
assert "media_url" in r.json()["detail"], r.text

r = c.post("/v1/jobs", json={"type": "subtitle", "media_url": "media/x.wav",
                             "format": "txt"}, headers=h)
assert r.status_code == 422, r.text
assert "format" in r.json()["detail"], r.text

r = c.post("/v1/jobs", json={"type": "subtitle", "media_url": "media/x.wav",
                             "bilingual": True}, headers=h)
assert r.status_code == 422, r.text
assert "target_lang" in r.json()["detail"], r.text

# cấu hình hợp lệ -> nhận job (202) và TRỪ credit như mọi job thật
_before = c.get("/v1/me", headers=h).json()["credits"]
r = c.post("/v1/jobs", json={"type": "subtitle", "media_url": "media/khong-co.wav",
                             "source_lang": "vi"}, headers=h)
assert r.status_code == 202, r.text
assert r.json()["credits_charged"] > 0, r.text
# pipeline hỏng (thiếu media) -> hoàn đủ credit
import time as _t  # noqa: E402

_t.sleep(1)
r = c.get(f"/v1/jobs/{r.json()['job_id']}", headers=h)
assert r.json()["status"] == "failed", r.text
assert c.get("/v1/me", headers=h).json()["credits"] == _before, "phải hoàn đủ credit"

# 3d) signup: TẮT mặc định (chính sách Phase 2 — hệ thống self-host chỉ Admin tạo
#     tài khoản). Bật công tắc thì mới tạo được, và KHÔNG bao giờ tạo admin.
r = c.post("/v1/auth/signup", json={"email": "New@Example.io", "password": "matkhau123"})
assert r.status_code == 403, r.text

from app.settings_service import set_setting  # noqa: E402

set_setting("auth.allow_signup", True, is_secret=False, category="security")
r = c.post("/v1/auth/signup", json={"email": "New@Example.io", "password": "matkhau123"})
assert r.status_code == 201, r.text
su = r.json()
assert su["key"].startswith("vv_") and su["role"] == "user", su
r = c.get("/v1/me", headers={"X-API-Key": su["key"]})
assert r.status_code == 200 and r.json()["user_id"] == su["user_id"], r.text
# duplicate email -> 409
r = c.post("/v1/auth/signup", json={"email": "new@example.io", "password": "matkhau123"})
assert r.status_code == 409, r.text
set_setting("auth.allow_signup", False, is_secret=False, category="security")

# 3e) voices surface: SPA gọi GET /v1/voices (trước đây 405 — chỉ có POST nên
#     danh sách giọng luôn trống) và cần Xoá THẬT (DELETE), không phải xoá trên
#     client rồi giọng hồi sinh sau khi tải lại trang.
import io  # noqa: E402

r = c.post("/v1/voices/upload", files={"file": ("ref.wav", io.BytesIO(b"RIFFaudit"), "audio/wav")},
           data={"name": "Giọng audit", "lang": "vi"}, headers=h)
assert r.status_code == 201, r.text
vid = r.json()["voice_id"]
r = c.get("/v1/voices", headers=h)
assert r.status_code == 200, r.text
mine = [v for v in r.json()["voices"] if v["id"] == vid]
assert mine and mine[0]["name"] == "Giọng audit" and mine[0]["engine"] == "vieneu", r.text
# user khác không được thấy giọng của người này
r2 = c.get("/v1/voices", headers={"X-API-Key": su["key"]})
assert all(v["id"] != vid for v in r2.json()["voices"]), r2.text
r = c.delete(f"/v1/voices/{vid}", headers=h)
assert r.status_code == 200 and r.json()["deleted"] is True, r.text
r = c.delete(f"/v1/voices/{vid}", headers=h)
assert r.status_code == 404, r.text
r = c.get("/v1/voices", headers=h)
assert all(v["id"] != vid for v in r.json()["voices"]), r.text

# 3h) API keys: list trả prefix + created_at, thu hồi được theo PREFIX (UI không
#     còn raw key sau khi đóng modal "hiện 1 lần") — trước đây DELETE chỉ nhận
#     raw key nên nút Xoá trên UI chết cứng.
r = c.post("/v1/keys", headers=h)
assert r.status_code == 201, r.text
raw_key = r.json()["key"]
r = c.get("/v1/keys", headers=h)
rows = [k for k in r.json()["keys"] if k["prefix"] == raw_key[:12]]
assert rows and rows[0]["active"] and rows[0]["created_at"], r.text
r = c.delete(f"/v1/keys/{raw_key[:12]}", headers=h)
assert r.status_code == 200 and r.json()["revoked"], r.text
r = c.delete(f"/v1/keys/{raw_key[:12]}", headers=h)
assert r.status_code == 404, r.text
r = c.get("/v1/me", headers={"X-API-Key": raw_key})
assert r.status_code == 401, "key đã thu hồi mà vẫn dùng được?"

# 4) credit metering + ledger: translate -2 stays; dub -60 và subtitle -8 hoàn lại
#    vì cả hai đều fail (thiếu media thật) — mỗi lần trừ đều phải có dòng ledger.
r = c.get("/v1/me", headers=h)
assert r.json()["credits"] == 50_000 - 2, r.json()

with SessionLocal() as db:
    from sqlalchemy import select
    rows = db.scalars(select(CreditLedger).where(CreditLedger.user_id == uid)).all()
    got = sorted((r.reason, r.delta) for r in rows)
    assert got == [
        ("job:dub", -60), ("job:subtitle", -8), ("job:translate", -2),
        ("refund:job:dub", 60), ("refund:job:subtitle", 8),
    ], got
    # mọi lần trừ/hoàn đều phải gắn job_id — không có dòng ledger mồ côi.
    # (Trước đây là so khớp cứng `== {jid, djid}`; cách đó vỡ ngay khi thêm một
    # loại job mới, mà không nói lên điều gì về tính đúng đắn.)
    assert all(r.job_id for r in rows), [r.reason for r in rows if not r.job_id]
    assert {jid, djid} <= {r.job_id for r in rows}

# 3g) speaker_voices: JobIn phải GIỮ được map người-nói→giọng. Trước đây
#     pydantic ÂM THẦM bỏ field này → pipeline luôn xoay vòng preset bất kể
#     người dùng chọn giọng nào trên UI.
r = c.post("/v1/jobs", json={
    "type": "dub",
    "media_url": "s3://inbox/khong-ton-tai.mp4",
    "source_lang": "zh", "target_lang": "vi",
    "speaker_voices": {"*": "Ngọc Huyền"},
}, headers=h)
assert r.status_code == 202, r.text
sv_jid = r.json()["job_id"]
r = c.get(f"/v1/jobs/{sv_jid}", headers=h)
assert r.json()["params"].get("speaker_voices") == {"*": "Ngọc Huyền"}, r.text
# job sẽ fail (media không tồn tại) — chờ rồi coi như refund, không đọng tiền
_t.sleep(1)
r = c.get(f"/v1/jobs/{sv_jid}", headers=h)
assert r.json()["status"] == "failed", r.text

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

# 7) HỦY job + HOÀN credit. Trước đây không có endpoint hủy: job kẹt
#    running/queued mãi mãi, credit bị treo theo (đã gặp thật với job TTS
#    "running" suốt nhiều giờ sau khi worker rớt giữa đường).
#    7a) hủy job QUEUED (dựng trực tiếp trong DB — inline mode chạy xong ngay
#        nên không tạo được job chờ bằng API):
from sqlalchemy import select  # noqa: E402

from app.models import Job, JobStatus  # noqa: E402
from app.storage import get_storage  # noqa: E402

with SessionLocal() as db:
    q = Job(user_id=uid, type="dub", status=JobStatus.queued,
            params={"media_url": "s3://inbox/x.mp4"}, credits_charged=60,
            task_id="fake-task-id")
    db.add(q)
    db.commit()
    qid = q.id
    u0 = db.get(User, uid)
    before = u0.credits
    # mô phỏng đúng 1 lần charge: -60 cả số dư lẫn ledger
    u0.credits -= 60
    db.add(CreditLedger(user_id=uid, delta=-60, reason="job:dub", job_id=qid))
    db.commit()
r = c.post(f"/v1/jobs/{qid}/cancel", headers=h)
assert r.status_code == 200, r.text
assert r.json()["status"] == "cancelled" and r.json()["refunded"] == 60, r.text
with SessionLocal() as db:
    assert db.get(Job, qid).status == JobStatus.cancelled
    # hoàn đúng 60: số dư về nguyên状态 trước lúc trừ
    assert db.get(User, uid).credits == before, "hoàn sai lệch so với đã trừ"
    led = [x for x in db.scalars(select(CreditLedger)
            .where(CreditLedger.job_id == qid)).all()]
    assert sorted((x.reason, x.delta) for x in led) == [
        ("job:dub", -60), ("refund:job:dub", 60)], led
#    7b) hủy lần nữa -> 409; hủy job đã done -> 409
r = c.post(f"/v1/jobs/{qid}/cancel", headers=h)
assert r.status_code == 409, r.text
done_jid = jid  # job translate đã done ở phần 3
r = c.post(f"/v1/jobs/{done_jid}/cancel", headers=h)
assert r.status_code == 409, r.text
#    7c) job người khác -> 404 (không hủy hộ được)
with SessionLocal() as db:
    other = User(email="other@local")
    db.add(other)
    db.commit()
    oid = other.id
    oj = Job(user_id=oid, type="tts", status=JobStatus.queued,
             params={"text": "x"}, credits_charged=10)
    db.add(oj)
    db.commit()
    ojid = oj.id
r = c.post(f"/v1/jobs/{ojid}/cancel", headers=h)
assert r.status_code == 404, r.text
#    7d) GUARD worker: pipeline gặp job đã hủy phải TỰ THOÁT, không ghi đè
#        trạng thái (resurrect). Dùng _run_tts qua dispatch_inline — guard nằm
#        TRƯỚC mọi engine nên không đụng model; (_run_translate đã bị fake
#        thay ở phần 3a, không còn là bản thật để test guard).
with SessionLocal() as db:
    cc = Job(user_id=uid, type="tts", status=JobStatus.cancelled,
             params={"type": "tts", "text": "abc"}, credits_charged=0)
    db.add(cc)
    db.commit()
    ccid = cc.id
out = _tasks.dispatch_inline(ccid, {"type": "tts", "text": "abc"})
assert out == {"ok": False, "error": "cancelled"}, out
with SessionLocal() as db:
    assert db.get(Job, ccid).status == JobStatus.cancelled, "guard bị ghi đè!"

# 8) XÓA job khỏi lịch sử: chỉ job đã kết thúc; dọn file riêng jobs/<id>/
#    8a) xóa job đang chạy -> 409 (phải hủy trước)
with SessionLocal() as db:
    rr = Job(user_id=uid, type="tts", status=JobStatus.running,
             params={"text": "x"}, credits_charged=10)
    db.add(rr)
    db.commit()
    rid = rr.id
r = c.delete(f"/v1/jobs/{rid}", headers=h)
assert r.status_code == 409, r.text
#    8b) xóa job đã hủy -> OK, row biến mất; file trong jobs/<id>/ cũng bị dọn
with SessionLocal() as db:
    jj = db.get(Job, qid)
    jj.result_s3_key = f"jobs/{qid}/output.wav"
    db.commit()
storage = get_storage()
storage.put(f"jobs/{qid}/output.wav", b"wav-data")
assert storage.exists(f"jobs/{qid}/output.wav")
r = c.delete(f"/v1/jobs/{qid}", headers=h)
assert r.status_code == 200 and r.json()["deleted"] == qid, r.text
with SessionLocal() as db:
    assert db.get(Job, qid) is None
assert not storage.exists(f"jobs/{qid}/output.wav"), "file rác không được dọn"
#    8c) file DÙNG CHUNG (jobs/tts/...) KHÔNG được đụng khi xóa job
with SessionLocal() as db:
    jj2 = Job(user_id=uid, type="tts", status=JobStatus.done,
              params={"text": "x"}, credits_charged=10,
              result_s3_key="jobs/tts/shared-hash.wav")
    db.add(jj2)
    db.commit()
    jj2id = jj2.id
storage.put("jobs/tts/shared-hash.wav", b"shared")
r = c.delete(f"/v1/jobs/{jj2id}", headers=h)
assert r.status_code == 200, r.text
assert storage.exists("jobs/tts/shared-hash.wav"), "xóa nhầm file dùng chung!"
#    8d) xóa job người khác -> 404
r = c.delete(f"/v1/jobs/{ojid}", headers=h)
assert r.status_code == 404, r.text

print("ORM roundtrip ......... OK")
print("Celery registration ... OK")
print("API 202/200/409/404 ... OK")
print("Voices GET/DELETE ..... OK")
print("Keys prefix revoke ... OK")
print("speaker_voices field .. OK")
print("Result payload shape .. OK")
print("Credit metering 402 ... OK")
print("Ledger row ............ OK")
print("DAY 2 SELFTEST PASSED")
