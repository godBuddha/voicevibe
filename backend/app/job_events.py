"""Luồng SSE tiến độ job (GC2, C2 của lộ trình C) — thay 3 đường polling.

Giao thức (đơn giản hơn WebSocket, theo pattern OpenCreator):
- Mỗi thay đổi job → một sự kiện `event: change` + `data: {"job_ids": [...]}` +
  `id: <JobEvent.id>`. Payload KHÔNG chứa tiến độ — client nhận tín hiệu rồi tự
  `GET /v1/jobs` refetch: một đường parse duy nhất, thêm shape job không phải
  đụng client.
- Cursor = id sự kiện: client mất kết nối → EventSource tự gửi lại
  `Last-Event-ID` → phát TIẾP, không trùng không sót.
- Heartbeat `: ping` 15 giây giữ kết nối sống qua proxy (bình luận SSE không
  đếm là message — EventSource bỏ qua im lặng).
- Tự đóng sau `max_lifetime_s` (10 phút): EventSource tự reconnect với
  Last-Event-ID — vòng đời kết nối giới hạn để không phình FD trên self-host.

Generator tách khỏi endpoint để test gọi trực tiếp (không qua streaming).
DB query chạy SYNC trong async loop: 1 query ~1ms mỗi giây — chấp nhận cho
self-host (1-2 user); nếu thấy nặng thì bọc run_in_threadpool sau.
"""
from __future__ import annotations

import asyncio
import json
import time

from sqlalchemy import select

from .db import SessionLocal
from .jobstate import sweep_orphans, sweep_should_run
from .models import JobEvent


async def job_event_stream(user_id: str, cursor: int = 0, *,
                           poll_interval: float = 1.0,
                           heartbeat_s: float = 15.0,
                           max_lifetime_s: float = 600.0,
                           sweep_every_s: float = 30.0,
                           limit: int = 500):
    """Async generator phát chuỗi SSE cho MỘT user. Kết thúc (return) sau
    `max_lifetime_s` — client tự reconnect và phát tiếp từ Last-Event-ID."""
    start = time.monotonic()
    last_beat = start
    last_sweep = start
    while True:
        now = time.monotonic()
        events, max_id = await asyncio.to_thread(_fetch_events, user_id, cursor, limit)
        if events:
            cursor = max_id
            ids = sorted({e["job_id"] for e in events})
            yield _format({"job_ids": ids}, event_id=cursor, event_name="change")
            last_beat = now
        elif now - last_beat >= heartbeat_s:
            yield ": ping\n\n"
            last_beat = now
        # Sweep tích hợp — miễn phí vì vòng lặp đã thức dậy mỗi giây: job mồ côi
        # được phát hiện cả khi người dùng chỉ mở trang (lớp 3 của GC1).
        if now - last_sweep >= sweep_every_s and sweep_should_run(
                job_event_stream._last_sweep[0], sweep_every_s):
            job_event_stream._last_sweep[0] = now
            await asyncio.to_thread(_sweep_all)
            last_sweep = now
        if time.monotonic() - start >= max_lifetime_s:
            return
        await asyncio.sleep(poll_interval)


# Throttle sweep CHUNG cho mọi luồng SSE (không mỗi kết nối quét một lần)
job_event_stream._last_sweep = [0.0]


def _fetch_events(user_id: str, cursor: int, limit: int) -> tuple[list[dict], int]:
    """Đọc sự kiện mới hơn cursor của user — SYNC (chạy qua asyncio.to_thread)."""
    with SessionLocal() as db:
        rows = db.scalars(
            select(JobEvent)
            .where(JobEvent.id > cursor, JobEvent.user_id == user_id)
            .order_by(JobEvent.id).limit(limit)
        ).all()
        out = [{"id": e.id, "job_id": e.job_id, "kind": e.kind,
                "data": e.data or {}} for e in rows]
    return out, max((e["id"] for e in out), default=cursor)


def _sweep_all() -> None:
    try:
        with SessionLocal() as db:
            sweep_orphans(db)
            db.commit()
    except Exception:  # noqa: BLE001 — sweep không được giết luồng SSE
        pass


def _format(data: dict, *, event_id: int, event_name: str = "change") -> str:
    """Format một sự kiện SSE — `id` để EventSource nhớ cursor (Last-Event-ID)."""
    return (f"id: {event_id}\n"
            f"event: {event_name}\n"
            f"data: {json.dumps(data, ensure_ascii=False)}\n\n")
