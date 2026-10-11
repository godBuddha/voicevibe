"""Máy trạng thái job — NƠI DUY NHẤT đổi `Job.status` (GC1, C1 của lộ trình C).

Trước đây 9 hàm `_run_*` + 3 endpoint (create/cancel/retry) mỗi chỗ tự gán
`job.status = ...` — kết quả: nhánh thành công không có guard chống đè lên
`cancelled` (race 2 giây của abort cache), không ai biết job nào chuyển lúc nào
(kẹt `running` mãi sau khi worker chết không có ai phát hiện), và SSE (GC2)
không có nguồn sự kiện.

Quy tắc máy trạng thái:
- `done` BẤT BIẾN — không gì ghi đè một kết quả đã xong.
- `cancelled` chỉ được ghi bởi cancel endpoint + handler JobCancelled; sau đó
  chỉ `retry` đưa về `queued` (bảo vệ tuyệt đối — hủy là hủy).
- `interrupted` (sweep phát hiện job mồ côi) CHO PHÉP bị `done`/`failed` đè:
  "hoàn thành muộn thắng" — task thật kết thúc sau khi sweep đánh dấu thì trạng
  thái tự chữa về done, không mất kết quả (hóa giải false-positive với STT dài
  im lặng không phát progress).

KHÔNG import pipelines (manifest.py:28-29 cố tình tách DB khỏi pipeline) —
jobstate nằm giữa models và pipeline: models → jobstate → tasks/main.
"""
from __future__ import annotations

import time as _time

from sqlalchemy import and_, func, or_, update

from .models import Job, JobEvent, JobStatus

# --- Hằng số (không đưa vào Settings — ngưỡng kỹ thuật, không phải núm user)
ORPHAN_RUNNING_S = 900    # running đứng yên quá 15 phút → coi là mồ côi
ORPHAN_QUEUED_S = 3600    # queued đứng yên quá 60 phút (broker chết) → mồ côi
EVENT_TTL_S = 7 * 24 * 3600   # prune JobEvent cũ hơn 7 ngày (trong sweep)
SWEEP_INTERVAL_S = 30.0   # nhịp sweep-on-read (throttle theo tiến trình)

INTERRUPTED_MSG = ("Bị gián đoạn (worker/hệ thống dừng giữa đường) — bấm "
                   "«Chạy lại» để tiếp tục từ công đoạn đã xong")

TERMINAL = {JobStatus.done, JobStatus.failed, JobStatus.cancelled,
            JobStatus.interrupted}

# from → tập các to được phép. Quy tắc đọc quan trọng nhất:
#   running → interrupted/done/failed/cancelled: bình thường.
#   interrupted → done/failed: hoàn thành muộn thắng (đọc docstring đầu file).
#   failed/cancelled → queued: CHỈ qua nút Chạy lại.
#   done → ∅: kết quả không bao giờ bị đè.
TRANSITIONS: dict[JobStatus, set[JobStatus]] = {
    JobStatus.queued: {JobStatus.running, JobStatus.cancelled,
                       JobStatus.interrupted},
    JobStatus.running: {JobStatus.done, JobStatus.failed, JobStatus.cancelled,
                        JobStatus.interrupted},
    JobStatus.interrupted: {JobStatus.queued, JobStatus.done, JobStatus.failed,
                            JobStatus.cancelled},
    JobStatus.failed: {JobStatus.queued},
    JobStatus.cancelled: {JobStatus.queued},
    JobStatus.done: set(),
}


def _now() -> int:
    return int(_time.time())


def transition(db, job: Job, to: JobStatus, *, error: str | None = None,
               progress: int | None = None, result_key: str | None = None,
               extra_params: dict | None = None) -> bool:
    """Chuyển trạng thái DUY NHẤT của hệ thống. Trả True nếu ghi.

    - Guard from→to theo `TRANSITIONS` — sai đường trả False, KHÔNG đụng job
      (vá race done-vs-cancelled: nhánh thành công gọi transition(done) khi job
      vừa bị hủy → False, trạng thái giữ nguyên).
    - `started_at` set MỘT LẦN khi lần đầu chạy; `finished_at` đặt khi chạm
      trạng thái kết thúc, xoá khi quay về queued (retry).
    - Ghi JobEvent kind="status" — nguồn của SSE + lịch sử. KHÔNG tự commit:
      caller giữ quyền soát lỗi rồi commit (pattern của toàn repo).
    """
    current = job.status
    if to not in TRANSITIONS.get(current, set()):
        return False
    now = _now()
    job.status = to
    if to is JobStatus.running and job.started_at is None:
        job.started_at = now
    if to in TERMINAL:
        job.finished_at = now
    elif to is JobStatus.queued:
        # Retry: xoá nợ lỗi cũ (queued = chạy lại sạch); result_s3_key CỐ Ý
        # giữ — kết quả cũ vẫn tải được tới khi lần chạy mới hoàn thành.
        job.finished_at = None
        job.progress = 0
        job.error = None
    if error is not None:
        job.error = error
    if progress is not None:
        job.progress = int(progress)
    if result_key is not None:
        job.result_s3_key = result_key
    if extra_params:
        job.params = {**(job.params or {}), **extra_params}
    db.add(JobEvent(job_id=job.id, user_id=job.user_id, kind="status",
                    data={"status": to.value,
                          **({"error": error} if error else {}),
                          **({"progress": int(progress)}
                             if progress is not None else {})},
                    created_at=now))
    return True


def record_progress_event(db, job: Job, pct: int, msg: str) -> None:
    """Ghi JobEvent kind="progress" theo throttle — gọi TRƯỚC khi update row
    Job (helper đọc giá trị cũ từ `job` để so). Throttle: tiến độ đổi qua bội
    5, HOẶC thông điệp công đoạn đổi. Không throttle row Job — giữ nguyên nhịp
    update hiện tại của pipeline (không phá timing đang được test kỹ)."""
    old_pct = int(job.progress or 0)
    new_pct = max(old_pct, int(pct))
    old_msg = (job.params or {}).get("stage")
    msg = str(msg)[:80]
    if new_pct // 5 != old_pct // 5 or msg != old_msg:
        db.add(JobEvent(job_id=job.id, user_id=job.user_id, kind="progress",
                        data={"progress": new_pct, "stage": msg},
                        created_at=_now()))


def sweep_orphans(db, *, user_id: str | None = None, now: int | None = None,
                  max_age_running: int = ORPHAN_RUNNING_S,
                  max_age_queued: int = ORPHAN_QUEUED_S) -> list[str]:
    """Đánh dấu `interrupted` các job mồ côi (worker/api dừng giữa đường).

    Chạy ở 3 lớp (không thread nền): boot api + boot worker, mỗi lần đọc list/
    detail job (throttle 30s), và trong vòng lặp SSE. `user_id` thu hẹp phạm vi
    cho sweep-on-read — người dùng chỉ "làm việc" trên job của mình. KHÔNG
    commit — caller commit (endpoint giữ quyền soát lỗi).
    """
    now = now or _now()
    q = db.query(Job).filter(or_(
        and_(Job.status == JobStatus.running,
             Job.updated_at < now - max_age_running),
        and_(Job.status == JobStatus.queued,
             Job.updated_at < now - max_age_queued),
    ))
    if user_id:
        q = q.filter(Job.user_id == user_id)
    changed: list[str] = []
    for job in q.all():
        # GIỮ progress hiện tại — người dùng cần biết job chết ở đâu
        # (42% mới gián đoạn có ích hơn thanh đầy 100%).
        if transition(db, job, JobStatus.interrupted, error=INTERRUPTED_MSG):
            changed.append(job.id)
    db.query(JobEvent).filter(
        JobEvent.created_at < now - EVENT_TTL_S).delete(synchronize_session=False)
    return changed


def claim_job(db, job_id: str, task_id: str, *,
              stale_after: int = ORPHAN_RUNNING_S,
              now: int | None = None) -> bool:
    """Lease chống double-run — ATOMIC `UPDATE...WHERE`, không read-then-write
    (cửa sổ giữa read và write cho phép 2 worker cùng thấy queued rồi cùng chạy).
    Task nhặt được job khi: đang queued (bình thường), hoặc đang đứng ở trạng
    thái có thể chạy lại (failed/cancelled/interrupted — retry/redeliver), hoặc
    `running` nhưng stale quá `stale_after` (task cũ chết, nhặt lại).
    Trả True = thắng lease; False = task khác đang giữ (task redeliver bỏ qua).
    """
    now = now or _now()
    # Idiomatic SQLAlchemy 2.0: execution_options là method của STATEMENT, không
    # phải kwarg của Session.execute (db.execute(stmt, execution_options=...) là
    # sai cú pháp — Python đọc `kwarg=a=b` là lỗi).
    stmt = (update(Job)
            .where(Job.id == job_id)
            .where(or_(
                Job.status.in_([JobStatus.queued, JobStatus.failed,
                                JobStatus.cancelled, JobStatus.interrupted]),
                and_(Job.status == JobStatus.running,
                     Job.updated_at < now - stale_after),
            ))
            .values(status=JobStatus.running,
                    task_id=task_id,
                    started_at=func.coalesce(Job.started_at, now),
                    updated_at=now,
                    error=None)
            .execution_options(synchronize_session=False))
    res = db.execute(stmt)
    if res.rowcount != 1:
        db.rollback()
        return False
    job = db.get(Job, job_id)
    db.add(JobEvent(job_id=job_id, user_id=job.user_id if job else "",
                    kind="status", data={"status": JobStatus.running.value},
                    created_at=now))
    db.commit()
    return True


def sweep_should_run(last_ts: float, interval_s: float = SWEEP_INTERVAL_S) -> bool:
    """Throttle sweep-on-read (theo monotonic của tiến trình)."""
    return _time.monotonic() - last_ts >= interval_s
