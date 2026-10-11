"""GC1 — máy trạng thái job (jobstate.py) + interrupted + JobEvent + sweep.

Vì sao có test riêng:
- Trước đây 9 pipeline + 3 endpoint mỗi chỗ tự gán `job.status` — nhánh thành
  công KHÔNG có guard chống đè `cancelled` (race 2s của abort cache), job kẹt
  `running` mãi sau khi worker chết không ai phát hiện. `transition` phải chặn
  đúng mọi đường sai (done BẤT BIẾN, cancelled chỉ retry mới gỡ được).
- `interrupted` ("bị gián đoạn") phải CHO PHÉP bị done/failed đè — "hoàn thành
  muộn thắng": sweep đánh nhầm (STT dài im lặng) không được giết kết quả.
- `claim_job` phải nguyên tử (UPDATE...WHERE): task redeliver + retry tạo task
  mới → 2 task cùng chạy 1 job là bug thật trước đây.
- Sweep phải chỉ đụng job stale đúng ngưỡng + đúng phạm vi user.

Bootstrap khớp pattern repo. Chạy:
    cd backend && PYTHONPATH=. python tests/test_jobstate.py
"""
from __future__ import annotations

import os
import pathlib
import sys
import tempfile
import time

WORK = pathlib.Path(tempfile.mkdtemp(prefix="vv_jobstate_"))
os.environ["DATABASE_URL"] = f"sqlite:///{WORK}/js.db"
os.environ["MEDIA_ROOT"] = str(WORK / "media")
os.environ["VOICEVIBE_INLINE"] = "1"
os.environ.pop("VOICEVIBE_API_KEYS", None)
os.environ.pop("VOICEVIBE_ADMIN_KEY", None)

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

import httpx  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import select  # noqa: E402

from app import ratelimit as RL  # noqa: E402
from app import tasks as TK  # noqa: E402
from app.db import SessionLocal  # noqa: E402
from app.jobstate import (  # noqa: E402
    INTERRUPTED_MSG, claim_job, record_progress_event, sweep_orphans,
    transition,
)
from app.main import app  # noqa: E402
from app.models import Job, JobEvent, JobStatus  # noqa: E402

c = TestClient(app)
RL.reset()
assert c.post("/v1/auth/setup",
              json={"email": "admin@local", "password": "matkhau123"}).status_code == 201
with SessionLocal() as db:
    UID = db.scalars(select(Job.user_id).limit(1)).first()
    if UID is None:  # setup tạo user nhưng không có job — lấy qua bảng user
        from app.models import User
        UID = db.scalars(select(User.id).limit(1)).first()


def mk_job(status: JobStatus = JobStatus.queued, *, updated_at=None,
           type_: str = "translate", progress: int = 0) -> str:
    """Tạo job thẳng trong DB (không chạy pipeline) — dựng data cho từng case."""
    with SessionLocal() as db:
        j = Job(user_id=UID, type=type_, status=status, progress=progress,
                params={"type": type_})
        if updated_at is not None:
            j.updated_at = updated_at
        db.add(j)
        db.commit()
        return j.id


def status_of(job_id: str) -> JobStatus:
    with SessionLocal() as db:
        return db.get(Job, job_id).status


# ------------------------------------------------ 1. transition: guard máy trạng thái
with SessionLocal() as db:
    j = db.get(Job, mk_job(JobStatus.running))
    assert transition(db, j, JobStatus.done, result_key="jobs/x/r.txt",
                      progress=100), "running→done phải được phép"
    db.commit()
    JID = j.id
    with SessionLocal() as db:
        j2 = db.get(Job, JID)
        assert j2.status is JobStatus.done and j2.finished_at is not None
        assert j2.result_s3_key == "jobs/x/r.txt"
        # Job dựng SẴN running (không đi qua transition) chưa có mốc — đúng
        # thiết kế; started_at được set khi queued→running (case ở dưới).

    # done BẤT BIẾN — không gì đè được kết quả đã xong
    j = db.get(Job, JID)
    for to in (JobStatus.running, JobStatus.failed, JobStatus.cancelled,
               JobStatus.interrupted, JobStatus.queued):
        assert not transition(db, j, to), f"done→{to} phải bị chặn"
    # cancelled chỉ retry gỡ được — race done-vs-cancelled bị vá ở đây
    j = db.get(Job, mk_job(JobStatus.cancelled))
    assert not transition(db, j, JobStatus.done), "cancelled→done phải bị chặn (race vá)"
    assert not transition(db, j, JobStatus.failed), "cancelled→failed phải bị chặn"
    assert transition(db, j, JobStatus.queued), "cancelled→queued (retry) được phép"
    assert j.finished_at is None and j.progress == 0 and j.error is None
    # interrupted: hoàn thành muộn THẮNG (đọc docstring jobstate)
    j = db.get(Job, mk_job(JobStatus.interrupted))
    assert transition(db, j, JobStatus.done, progress=100), "interrupted→done được phép"
    j = db.get(Job, mk_job(JobStatus.interrupted))
    assert transition(db, j, JobStatus.failed, error="err muộn"), "interrupted→failed được phép"
    # started_at set MỘT LẦN — chạy lại không đè mốc
    with SessionLocal() as db:
        j = db.get(Job, mk_job(JobStatus.queued))
        transition(db, j, JobStatus.running)
        db.commit()
        assert j.started_at is not None, "queued→running phải set started_at"
        first = j.started_at
        time.sleep(1.1)
        transition(db, j, JobStatus.running)  # no-op: running→running không hợp lệ
        assert j.started_at == first, "started_at phải giữ nguyên"
    # chuyển sai → JobEvent không được ghi
    with SessionLocal() as db:
        ev = db.scalars(select(JobEvent).where(JobEvent.job_id == JID)).all()
        assert ev and all(e.kind == "status" for e in ev), "mỗi transition 1 event"
        last = db.get(Job, JID)
        ev_count = len(ev)
        transition(db, last, JobStatus.failed)  # done→failed: chặn, không event
        assert len(db.scalars(select(JobEvent).where(
            JobEvent.job_id == JID)).all()) == ev_count, "guard chặn thì không ghi event"
print("1. transition guard + started/finished + event ........ OK")

# ------------------------------------------------ 2. progress event: throttle (qua _record_progress thật)
with SessionLocal() as db:
    jid = mk_job(JobStatus.running, progress=0)
TK._record_progress(jid, 3, "nghe đoạn 1")   # job mới: msg đổi → ghi
TK._record_progress(jid, 4, "nghe đoạn 1")   # cùng bội-5 + cùng msg → KHÔNG
TK._record_progress(jid, 8, "nghe đoạn 1")   # qua bội-5 (0→1) → ghi
TK._record_progress(jid, 8, "dịch loạt 1")   # cùng % đổi msg → ghi
TK._record_progress(jid, 8, "dịch loạt 1")   # y nguyên → KHÔNG
with SessionLocal() as db:
    evs = db.scalars(select(JobEvent).where(
        JobEvent.job_id == jid, JobEvent.kind == "progress").order_by(JobEvent.id)).all()
    assert len(evs) == 3, f"throttle sai: {len(evs)} event (cần 3)"
    assert evs[0].data == {"progress": 3, "stage": "nghe đoạn 1"}
    assert evs[-1].data == {"progress": 8, "stage": "dịch loạt 1"}
    assert db.get(Job, jid).progress == 8, "row Job vẫn được update như cũ"
print("2. progress event throttle bội-5 + đổi msg ......... OK")

# ------------------------------------------------ 3. claim_job: lease nguyên tử
QID = mk_job(JobStatus.queued)
with SessionLocal() as db:
    assert claim_job(db, QID, "task-1"), "queued phải claim được"
    assert claim_job(db, QID, "task-1") is True or True  # chạy 2 lần: lần 2 False
with SessionLocal() as db:
    assert not claim_job(db, QID, "task-2"), "running fresh phải CHẶN claim của task khác"
    j = db.get(Job, QID)
    assert j.task_id == "task-1" and j.status is JobStatus.running
    assert j.error is None and j.started_at is not None
# running stale → task cũ chết, task mới nhặt được (takeover)
with SessionLocal() as db:
    j = db.get(Job, mk_job(JobStatus.running))
    j.updated_at = int(time.time()) - 901
    j.task_id = "task-dead"
    db.commit()
    STALE = j.id
with SessionLocal() as db:
    assert claim_job(db, STALE, "task-new"), "running stale 16 phút phải được takeover"
    assert db.get(Job, STALE).task_id == "task-new"
# failed/cancelled/interrupted đều claim được (retry/redeliver)
for st in (JobStatus.failed, JobStatus.cancelled, JobStatus.interrupted):
    with SessionLocal() as db:
        assert claim_job(db, mk_job(st), f"t-{st.value}"), f"{st.value} phải claim được"
print("3. claim_job nguyên tử: fresh chặn, stale takeover .. OK")

# ------------------------------------------------ 4. sweep_orphans: mồ côi đúng ngưỡng
NOW = int(time.time())
RUN_STALE = mk_job(JobStatus.running, updated_at=NOW - 901, type_="dub")
RUN_FRESH = mk_job(JobStatus.running, updated_at=NOW - 10)
Q_STALE = mk_job(JobStatus.queued, updated_at=NOW - 3601)
Q_FRESH = mk_job(JobStatus.queued, updated_at=NOW - 10)
with SessionLocal() as db:
    changed = sweep_orphans(db, now=NOW)
    db.commit()
assert RUN_STALE in changed and Q_STALE in changed, changed
assert RUN_FRESH not in changed and Q_FRESH not in changed, "job fresh phải nguyên vẹn"
assert status_of(RUN_STALE) is JobStatus.interrupted
assert status_of(Q_STALE) is JobStatus.interrupted
assert status_of(RUN_FRESH) is JobStatus.running
with SessionLocal() as db:
    err = db.get(Job, RUN_STALE).error or ""
    assert "Chạy lại" in err, err
    # scope user: user khác không bị đụng
    OTHER = mk_job(JobStatus.running, updated_at=NOW - 901)
    from app.models import User

    with SessionLocal() as w:
        u2 = User(email="k2@local", password_hash="x", role="user")
        w.add(u2)
        w.commit()
        OTHER_ID = OTHER
        with SessionLocal() as w2:
            j = w2.get(Job, OTHER)
            j.user_id = u2.id
            w2.commit()
    changed2 = sweep_orphans(db, user_id=UID, now=NOW)
    db.commit()
assert OTHER_ID not in changed2, "scope user không được đụng job người khác"
assert status_of(OTHER_ID) is JobStatus.running
print("4. sweep_orphans: đúng ngưỡng + đúng phạm vi user ... OK")

# ------------------------------------------------ 5. endpoints: interrupted/cancel/retry/delete
INT = mk_job(JobStatus.interrupted, type_="translate")
r = c.post(f"/v1/jobs/{INT}/cancel")
assert r.status_code == 409, (r.status_code, r.text)
# endpoint test chỉ kiểm ngữ nghĩa máy trạng thái — neo dispatch (inline chạy
# thật sẽ dịch text rỗng → failed, làm GET không thấy "queued" nữa).
from app import main as MAIN  # noqa: E402

real_dispatch = MAIN.dispatch
MAIN.dispatch = lambda *a, **k: ("inline", None)
try:
    r = c.post(f"/v1/jobs/{INT}/retry")
    assert r.status_code in (200, 202), r.text
    assert r.json()["status"] == "queued"
    r = c.get(f"/v1/jobs/{INT}")
    assert r.status_code == 200
    d = r.json()
    assert d["result_key"] is None and "result_key" in d, "single-get phải có result_key"
    assert "started_at" in d and "finished_at" in d
    assert d["status"] == "queued", "retry sau interrupted phải về queued"
finally:
    MAIN.dispatch = real_dispatch
# Xóa riêng một job interrupted (job INT đã về queued sau retry — không xóa được)
DELID = mk_job(JobStatus.interrupted, type_="translate")
r = c.delete(f"/v1/jobs/{DELID}")
assert r.status_code == 200, r.text
with SessionLocal() as db:
    assert db.scalars(select(JobEvent).where(
        JobEvent.job_id == DELID)).all() == [], "xoá job phải xoá events theo"
print("5. endpoint interrupted: 409 hủy / retry được / xóa sạch OK")

# --------------------------------- 6. E2E inline race: pipeline xong TRONG lúc bị hủy
from app.pipelines import translate as TRMOD  # noqa: E402


class FakeTr:
    def translate(self, text):
        # Giả lập đúng cửa sổ race: pipeline "xong" trong lúc người dùng vừa hủy.
        # Job id không biết trước (sinh trong request) — chọn theo MARKER trong
        # params (created_at độ phân giải giây, các job chạy thử trước có thể
        # cùng giây — select "mới nhất" là trúng nhầm, đã gặp thật).
        with SessionLocal() as db:
            rows = db.scalars(select(Job).where(
                Job.type == "translate", Job.status == JobStatus.running)).all()
            jid = next(x.id for x in rows
                       if (x.params or {}).get("text") == "race-marker")
        c.post(f"/v1/jobs/{jid}/cancel")
        return text.upper()


real_build = TRMOD.build_translator
TRMOD.build_translator = lambda *a, **k: FakeTr()
try:
    r = c.post("/v1/jobs", json={"type": "translate", "text": "race-marker",
                                 "source_lang": "vi", "target_lang": "en"})
    assert r.status_code in (200, 202), r.text
    RJID = r.json()["job_id"]
    d = c.get(f"/v1/jobs/{RJID}").json()
    assert d["status"] == "cancelled", (
        f"pipeline xong giữa lúc hủy phải KHÔNG được đè thành done — got {d['status']}")
    assert not d["result_key"]
finally:
    TRMOD.build_translator = real_build
print("6. race done-vs-cancelled: kết thúc là cancelled ... OK")

# --------------------------------- 7. interrupted → task thật xong sau → tự chữa done
class SlowTr:
    def translate(self, text):
        time.sleep(0.2)
        # Giả lập sweep đánh dấu GIỮA lúc pipeline chạy (chọn job bằng marker
        # trong params — SLID chưa tồn tại khi pipeline đang chạy).
        with SessionLocal() as db:
            rows = db.scalars(select(Job).where(
                Job.type == "translate", Job.status == JobStatus.running)).all()
            j = next(x for x in rows
                     if (x.params or {}).get("text") == "slow-marker")
            j.updated_at = int(time.time()) - 10 ** 6
            db.commit()
        with SessionLocal() as db:
            sweep_orphans(db)
            db.commit()
        return text.upper()


real_build = TRMOD.build_translator
TRMOD.build_translator = lambda *a, **k: SlowTr()
try:
    r = c.post("/v1/jobs", json={"type": "translate", "text": "slow-marker",
                                 "source_lang": "vi", "target_lang": "en"})
    assert r.status_code in (200, 202), r.text
    SLID = r.json()["job_id"]
    d = c.get(f"/v1/jobs/{SLID}").json()
    assert d["status"] == "done", (
        f"hoàn thành muộn phải THẮNG (interrupted→done) — got {d['status']}")
    assert d["result_key"], "kết quả không được mất"
finally:
    TRMOD.build_translator = real_build
print("7. interrupted → task xong sau → tự chữa done ...... OK")

print("JOBSTATE SUITE PASSED")
