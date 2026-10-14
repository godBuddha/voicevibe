"""Database engine/session — Postgres in prod, SQLite fallback for dev/tests."""
from __future__ import annotations

import os

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./voicevibe.db")

# Pool mặc định 5+10: audit mở 22 trang + SSE query mỗi giây từng kết nối đã
# cạn pool (QueuePool timeout 30s → 500 hàng loạt, GC5). Nâng lên 20+40 và
# chờ tối đa 10s — self-host 1-2 user đủ dư; timeout ngắn để lỗi lộ ra sớm
# thay vì treo request 30 giây.
engine = create_engine(DATABASE_URL, pool_pre_ping=True,
                       pool_size=20, max_overflow=40, pool_timeout=10)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
