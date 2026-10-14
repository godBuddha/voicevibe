"""GC2 — SSE tiến độ job (job_events.py) + endpoint /v1/jobs/events.

Vì sao có test riêng:
- Cursor phải TIẾP DIỄN (Last-Event-ID): mất kết nối phát lại từ điểm cũ là
  spam, phát trôi qua sự kiện là SÓT. Ca thật: client reconnect sau khi server
  tự đóng (10 phút).
- Phân quyền: user A KHÔNG được thấy event của job user B (user_id trên
  JobEvent là nguồn lọc — không FK nhưng mọi query phải có WHERE user_id).
- Heartbeat phải giữ kết nối sống qua proxy; lifetime phải tự đóng (không treo
  FD mãi trên self-host).
- Cap 3 kết nối/user phải chặn kết nối thứ 4 (429) — in-process đếm là đủ vì
  compose không scale api.
- Format SSE chuẩn: `id:` + `event:` + `data:` + dòng trống — sai là
  EventSource bỏ sự kiện.

Chạy:
    cd backend && PYTHONPATH=. python tests/test_jobs_events.py
"""
from __future__ import annotations

import asyncio
import os
import pathlib
import sys
import tempfile

WORK = pathlib.Path(tempfile.mkdtemp(prefix="vv_sse_"))
os.environ["DATABASE_URL"] = f"sqlite:///{WORK}/sse.db"
os.environ["MEDIA_ROOT"] = str(WORK / "media")
os.environ["VOICEVIBE_INLINE"] = "1"
os.environ.pop("VOICEVIBE_API_KEYS", None)
os.environ.pop("VOICEVIBE_ADMIN_KEY", None)

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import select  # noqa: E402

from app import ratelimit as RL  # noqa: E402
from app.db import SessionLocal  # noqa: E402
from app.job_events import job_event_stream  # noqa: E402
from app.main import (  # noqa: E402
    _SSE_COUNT, _SSE_EVICTIONS, _SSE_GEN, _SSE_OLDEST,
    _sse_acquire, _sse_evicted, _sse_release, app,
)
from app.models import Job, JobEvent, User  # noqa: E402

c = TestClient(app)
RL.reset()
assert c.post("/v1/auth/setup",
              json={"email": "admin@local", "password": "matkhau123"}).status_code == 201
with SessionLocal() as db:
    UID = db.scalars(select(User.id).limit(1)).first()
    u2 = User(email="k2@local", password_hash="x", role="user")
    db.add(u2)
    db.commit()
    db.refresh(u2)
    UID2 = u2.id
    j1 = Job(user_id=UID, type="translate", status="running", params={})
    j2 = Job(user_id=UID2, type="translate", status="running", params={})
    db.add_all([j1, j2])
    db.commit()
    JID, JID2 = j1.id, j2.id
    db.add_all([
        JobEvent(job_id=JID, user_id=UID, kind="status",
                 data={"status": "running"}),
        JobEvent(job_id=JID, user_id=UID, kind="status",
                 data={"status": "done"}),
        JobEvent(job_id=JID2, user_id=UID2, kind="status",
                 data={"status": "running"}),
    ])
    db.commit()
    MAX_A = db.scalars(select(JobEvent.id).where(JobEvent.user_id == UID)
                       .order_by(JobEvent.id.desc()).limit(1)).first()


def run_stream(user_id, cursor=0, **kw):
    """Gọi generator trực tiếp, thu chuỗi phát ra (sync qua asyncio.run)."""
    kw.setdefault("poll_interval", 0.05)
    kw.setdefault("max_lifetime_s", 0.3)

    async def collect():
        out = []
        async for chunk in job_event_stream(user_id, cursor, **kw):
            out.append(chunk)
        return out

    return asyncio.run(collect())


# --------------------------------- 1. chỉ thấy event của MÌNH + cursor đúng
chunks = run_stream(UID)
assert chunks, "phải có event ngay khi có dữ liệu"
assert "event: change" in chunks[0], chunks[0]
assert f'"job_ids": ["{JID}"]' in chunks[0], chunks[0]  # KHÔNG có job của user B
assert f"id: {MAX_A}" in chunks[0], "id: phải là event id max của user"
assert JID2 not in chunks[0], "job người khác không được lộ"
# format chuẩn SSE: id → event → data → dòng trống ×2 (kết thúc sự kiện)
lines = chunks[0].split("\n")
assert lines[0].startswith("id: ") and lines[1] == "event: change" \
    and lines[2].startswith("data: ") and lines[3] == "" and lines[4] == "", chunks[0]
print("1. phân quyền event + format SSE chuẩn ............ OK")

# --------------------------------- 2. cursor tiếp diễn: không lặp, có mới là phát
chunks = run_stream(UID, cursor=MAX_A, max_lifetime_s=0.25, heartbeat_s=0.05)
assert set(chunks) == {": ping\n\n"}, f"cursor đã tới đầu phải chỉ có heartbeat: {chunks}"
# ghi thêm event mới → phát tiếp đúng event mới
with SessionLocal() as db:
    db.add(JobEvent(job_id=JID, user_id=UID, kind="status",
                    data={"status": "failed"}))
    db.commit()
    NEW_ID = db.scalars(select(JobEvent.id).order_by(JobEvent.id.desc())
                        .limit(1)).first()
chunks = run_stream(UID, cursor=MAX_A, max_lifetime_s=0.25)
assert any(f'"job_ids": ["{JID}"]' in ch for ch in chunks), chunks
assert any(f"id: {NEW_ID}" in ch for ch in chunks), chunks
print("2. cursor Last-Event-ID: phát tiếp không lặp ....... OK")

# --------------------------------- 3. heartbeat + lifetime
chunks = run_stream(UID, cursor=NEW_ID, heartbeat_s=0.1, poll_interval=0.02,
                    max_lifetime_s=0.5)
pings = [ch for ch in chunks if ch == ": ping\n\n"]
assert pings, "heartbeat : ping phải xuất hiện"
# collect() trả về đúng hạn (không treo) chính là chứng cứ lifetime hoạt động
assert all(ch == ": ping\n\n" for ch in chunks), "không event mới → chỉ heartbeat"
print("3. heartbeat giữ sống + tự đóng đúng lifetime ...... OK")

# --------------------------------- 4. endpoint auth + headers + cap 429
# BẪY: /v1/auth/setup trả kèm cookie phiên → TestClient giữ nó ở MỌI request
# sau — muốn ca 401 thật thì phải xóa cookie trước (nếu không, "không đăng
# nhập" lại 200 và stream chạy cả 10 phút → test treo — đã gặp thật).
c.cookies.clear()
r = c.get("/v1/jobs/events")
assert r.status_code == 401, (r.status_code, r.text[:120])
r = c.get("/v1/jobs/events?api_key=kkk-sai")
assert r.status_code == 401, (r.status_code, r.text[:120])
# đăng nhập phiên đúng
r = c.post("/v1/auth/login", json={"email": "admin@local", "password": "matkhau123"})
assert r.status_code in (200, 204), r.text
# Endpoint chạy lifetime 600s mặc định — TestClient đọc stream HẾT sẽ treo 600s.
# Neo generator về lifetime ngắn cho ca test (main giữ tham chiếu module-level).
from app import main as MAIN  # noqa: E402

real_stream = MAIN.job_event_stream
MAIN.job_event_stream = (lambda uid, cur, **kw: real_stream(
    uid, cur, max_lifetime_s=0.3, poll_interval=0.05, **kw))
try:
    r = c.get("/v1/jobs/events", headers={"Last-Event-ID": str(MAX_A)})
    # TestClient đọc stream hết → status cuối vẫn là 200 + headers chuẩn
    assert r.status_code == 200, r.status_code
    assert r.headers["content-type"].startswith("text/event-stream"), r.headers
    assert r.headers["cache-control"] == "no-cache"
    assert r.headers["x-accel-buffering"] == "no"
    body = r.text
    assert "event: change" in body and "id:" in body, body[:200]
finally:
    MAIN.job_event_stream = real_stream
print("4. endpoint: 401 sai credential / 200 + headers .... OK")

# --------------------------------- 5. cap 1 kết nối/user + evict khi mở mới
# GC5 bài học thật: stream giữ 600s + query mỗi giây/kết nối → nhiều kết nối
# cùng lúc cạn connection pool (500 hàng loạt trong audit). Hợp đồng mới: MỖI
# user 1 kết nối — mở kết nối mới khi còn kết nối cũ → kết nối CŨ bị evict
# (đuổi), slot giao cho kết nối MỚI (tab hiện tại). None chỉ khi user không có
# kết nối nào để evict.
from app.main import _SSE_EVICTIONS, _SSE_GEN, _SSE_OLDEST  # noqa: E402
_SSE_COUNT.clear(); _SSE_OLDEST.clear(); _SSE_EVICTIONS.clear(); _SSE_GEN[0] = 0
g1 = _sse_acquire("u1")
assert g1 is not None
g2 = _sse_acquire("u1")
assert g2 is not None, "mở mới phải được phục vụ (evict cũ)"
assert g1 in _SSE_EVICTIONS and _sse_evicted(g1), "kết nối cũ phải bị evict"
assert not _sse_evicted(g2), "kết nối mới không bị evict"
assert _SSE_COUNT["u1"] == 1, f"chỉ 1 slot/user — got {_SSE_COUNT['u1']}"
assert _SSE_OLDEST["u1"] == g2
assert _sse_acquire("u2") is not None, "user khác không bị ảnh hưởng"
_sse_release("u1", g2)
assert not _sse_evicted(g2), "release phải xoá cờ evict của chính nó"
assert _sse_acquire("u1") is not None, "nhả slot phải lấy lại được"
_SSE_COUNT.clear(); _SSE_OLDEST.clear(); _SSE_EVICTIONS.clear()
print("5. cap 1/user + evict khi mở mới .................. OK")

# --------------------------------- 6. throttle sweep trong luồng SSE không nổ
# sweep tất cả users không được đụng job terminal + không giết stream
chunks = run_stream(UID, cursor=NEW_ID, sweep_every_s=0.05, max_lifetime_s=0.25)
assert all(ch == ": ping\n\n" for ch in chunks), "không có event mới → chỉ heartbeat"
print("6. sweep tích hợp trong luồng không giết stream .... OK")

print("JOBS EVENTS SUITE PASSED")
