"""Day 2 schema: users, api_keys, voices, jobs, credit_ledger.

Credits model mirrors the YupVox landing page: free starting credits,
per-job metered spend (real metering lands D6 — placeholder pricing for now).
"""
from __future__ import annotations

import enum
import time
import uuid

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    Enum as SAEnum,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base

FREE_CREDITS = 50_000  # same hook as the original landing page


def _uid() -> str:
    return uuid.uuid4().hex[:12]


def _now() -> int:
    return int(time.time())


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(12), primary_key=True, default=_uid)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    credits: Mapped[int] = mapped_column(Integer, default=FREE_CREDITS)
    created_at: Mapped[int] = mapped_column(BigInteger, default=_now)

    api_keys: Mapped[list["ApiKey"]] = relationship(back_populates="user")
    voices: Mapped[list["Voice"]] = relationship(back_populates="owner")


class ApiKey(Base):
    __tablename__ = "api_keys"

    # Stores the SHA-256 hex of the raw key — a DB dump cannot recover usable
    # keys. `prefix` keeps the first chars for masked display ("yv_abcd…").
    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    prefix: Mapped[str] = mapped_column(String(16), default="")
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    rate_limit_per_min: Mapped[int] = mapped_column(Integer, default=60)
    created_at: Mapped[int] = mapped_column(BigInteger, default=_now)

    user: Mapped[User] = relationship(back_populates="api_keys")


class Voice(Base):
    """Zero-shot voice profile cloned from a 5-10s reference clip."""

    __tablename__ = "voices"

    id: Mapped[str] = mapped_column(String(12), primary_key=True, default=_uid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    lang: Mapped[str] = mapped_column(String(12), default="auto")
    engine: Mapped[str] = mapped_column(String(32), default="chatterbox")
    ref_s3_key: Mapped[str] = mapped_column(String(512))
    created_at: Mapped[int] = mapped_column(BigInteger, default=_now)

    owner: Mapped[User] = relationship(back_populates="voices")


class JobStatus(str, enum.Enum):
    queued = "queued"
    running = "running"
    done = "done"
    failed = "failed"


class Job(Base):
    __tablename__ = "jobs"

    id: Mapped[str] = mapped_column(String(12), primary_key=True, default=_uid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    type: Mapped[str] = mapped_column(String(16))  # tts|stt|translate|dub|subtitle
    status: Mapped[JobStatus] = mapped_column(SAEnum(JobStatus), default=JobStatus.queued)
    progress: Mapped[int] = mapped_column(Integer, default=0)
    params: Mapped[dict] = mapped_column(JSON, default=dict)
    result_s3_key: Mapped[str | None] = mapped_column(String(512), nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    credits_charged: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[int] = mapped_column(BigInteger, default=_now)
    updated_at: Mapped[int] = mapped_column(BigInteger, default=_now, onupdate=_now)

    user: Mapped[User] = relationship()


class CreditLedger(Base):
    """Append-only credit movements — never mutate `users.credits` without a row here."""

    __tablename__ = "credit_ledger"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    delta: Mapped[int] = mapped_column(Integer)  # negative = spend
    reason: Mapped[str] = mapped_column(String(64))
    job_id: Mapped[str | None] = mapped_column(String(12), nullable=True)
    created_at: Mapped[int] = mapped_column(BigInteger, default=_now)


class Setting(Base):
    """Runtime configuration — managed via the admin Settings UI (Day 6).

    Secrets are stored as Fernet tokens (encrypted at rest); everything else is
    JSON plaintext. This table REPLACES hardcoded .env config.
    """

    __tablename__ = "settings"

    key: Mapped[str] = mapped_column(String(128), primary_key=True)
    value: Mapped[str] = mapped_column(Text)
    is_secret: Mapped[bool] = mapped_column(Boolean, default=False)
    category: Mapped[str] = mapped_column(String(32), default="general")
    updated_at: Mapped[int] = mapped_column(BigInteger, default=_now, onupdate=_now)
