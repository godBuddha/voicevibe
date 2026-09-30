"""Day 2 schema: users, api_keys, voices, jobs, credit_ledger.

Credits model mirrors the original voice-product landing page: free starting credits,
per-job metered spend (real metering lands D6 — placeholder pricing for now).

Phase 2 (accounts): `users` gains real credentials (`password_hash`, `role`,
`is_active`), plus the `sessions` / `system_flags` / `media_objects` tables.
Schema changes on EXISTING databases are applied by `app/migrations.py`
(`ensure_schema`) — there is no Alembic, and `create_all` alone cannot add a
column to a table that already exists.
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
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base

FREE_CREDITS = 50_000  # same hook as the original landing page

ROLE_USER = "user"
ROLE_ADMIN = "admin"


def _uid() -> str:
    return uuid.uuid4().hex[:12]


def _now() -> int:
    return int(time.time())


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(12), primary_key=True, default=_uid)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    # NULL = user chỉ dùng API key / chưa được đặt mật khẩu (user tạo trước Phase 2).
    password_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # "user" | "admin" — String chứ không SAEnum: tránh phải tạo/ALTER kiểu enum
    # của Postgres khi thêm giá trị mới.
    role: Mapped[str] = mapped_column(String(16), default=ROLE_USER)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    credits: Mapped[int] = mapped_column(Integer, default=FREE_CREDITS)
    last_login_at: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    created_at: Mapped[int] = mapped_column(BigInteger, default=_now)
    updated_at: Mapped[int] = mapped_column(BigInteger, default=_now, onupdate=_now)

    # cascade: xoá user thì phiên + API key đi theo. Nếu không, SQLAlchemy sẽ cố
    # set FK về NULL và vi phạm ràng buộc NOT NULL (lỗi thật đã gặp khi dọn DB).
    api_keys: Mapped[list["ApiKey"]] = relationship(
        back_populates="user", cascade="all, delete-orphan")
    voices: Mapped[list["Voice"]] = relationship(back_populates="owner")
    sessions: Mapped[list["Session"]] = relationship(
        back_populates="user", cascade="all, delete-orphan")

    @property
    def is_admin(self) -> bool:
        return self.role == ROLE_ADMIN

    @property
    def can_password_login(self) -> bool:
        return bool(self.password_hash) and self.is_active


class Session(Base):
    """Phiên đăng nhập web. Chỉ lưu SHA-256 của token — token thô không bao giờ vào DB."""

    __tablename__ = "sessions"

    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    created_at: Mapped[int] = mapped_column(BigInteger, default=_now)
    expires_at: Mapped[int] = mapped_column(BigInteger, index=True)
    last_seen_at: Mapped[int] = mapped_column(BigInteger, default=_now)
    ip: Mapped[str | None] = mapped_column(String(64), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(255), nullable=True)

    user: Mapped[User] = relationship(back_populates="sessions")


class SystemFlag(Base):
    """Cờ hệ thống dạng key/value.

    `setup.completed` là **chốt nguyên tử** cho `/setup`: khoá chính unique làm hai
    request setup đồng thời không thể cùng thắng (xem `main.setup`).
    """

    __tablename__ = "system_flags"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[str] = mapped_column(Text, default="")
    updated_at: Mapped[int] = mapped_column(BigInteger, default=_now, onupdate=_now)


class ApiKey(Base):
    __tablename__ = "api_keys"

    # Stores the SHA-256 hex of the raw key — a DB dump cannot recover usable
    # keys. `prefix` keeps the first chars for masked display ("vv_abcd…").
    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    prefix: Mapped[str] = mapped_column(String(16), default="")
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    rate_limit_per_min: Mapped[int] = mapped_column(Integer, default=60)
    created_at: Mapped[int] = mapped_column(BigInteger, default=_now)

    user: Mapped[User] = relationship(back_populates="api_keys")


class MediaObject(Base):
    """Sổ chủ sở hữu media đã upload.

    `/media/{key}` phải biết file thuộc ai; khoá storage không tự mang thông tin đó.
    Kết quả job tra qua `jobs.result_s3_key`, clip giọng qua `voices.ref_s3_key`,
    còn ảnh/audio người dùng upload thì ghi vào bảng này (xem `_owns_media`).
    """

    __tablename__ = "media_objects"

    key: Mapped[str] = mapped_column(String(512), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    created_at: Mapped[int] = mapped_column(BigInteger, default=_now)


# --------------------------------------------------- Phase 3: cấu hình AI (admin)

PROVIDER_OPENAI = "openai"   # bất kỳ endpoint chuẩn OpenAI (OpenAI, DeepSeek, Groq, vLLM…)
PROVIDER_OLLAMA = "ollama"   # Ollama native API (/api/tags, /api/pull, …)
PROVIDER_KINDS = (PROVIDER_OPENAI, PROVIDER_OLLAMA)

STAGES = ("stt", "translate", "retranslate", "tts", "dub")


class AiProvider(Base):
    """Nhà cung cấp AI do người vận hành cấu hình trong /admin.

    API key mã hóa at rest bằng Fernet (dùng lại `_fernet()` của settings_service),
    và chỉ lưu thêm 4 ký tự cuối để hiển thị — **giá trị thật không bao giờ trả ra API**.
    """

    __tablename__ = "ai_providers"

    id: Mapped[str] = mapped_column(String(12), primary_key=True, default=_uid)
    name: Mapped[str] = mapped_column(String(120))
    kind: Mapped[str] = mapped_column(String(16), default=PROVIDER_OPENAI)
    base_url: Mapped[str] = mapped_column(String(512))
    api_key_enc: Mapped[str | None] = mapped_column(Text, nullable=True)
    api_key_hint: Mapped[str | None] = mapped_column(String(16), nullable=True)
    prefix_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[int] = mapped_column(BigInteger, default=_now)
    updated_at: Mapped[int] = mapped_column(BigInteger, default=_now, onupdate=_now)


class StageModel(Base):
    """Gắn một công đoạn của pipeline với (provider, model).

    `order` cho phép khai chuỗi fallback: order=0 là lựa chọn chính, 1 là dự phòng.
    Bảng này bổ sung — KHÔNG thay — các setting `translate.*` cũ, để deployment
    đang chạy không vỡ khi nâng cấp (xem app/pipelines/translate.py).
    """

    __tablename__ = "stage_models"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    stage: Mapped[str] = mapped_column(String(24), index=True)
    provider_id: Mapped[str | None] = mapped_column(
        ForeignKey("ai_providers.id"), nullable=True)
    model: Mapped[str] = mapped_column(String(200), default="")
    params: Mapped[dict] = mapped_column(JSON, default=dict)
    order: Mapped[int] = mapped_column(Integer, default=0)


class Prompt(Base):
    """Prompt hệ thống cho từng tác vụ LLM — sửa được trong /admin.

    `is_default` = người vận hành chưa sửa (hoặc đã bấm Khôi phục mặc định), nên UI
    luôn biết prompt nào đang lệch khỏi mặc định của code.
    """

    __tablename__ = "prompts"

    task_key: Mapped[str] = mapped_column(String(64), primary_key=True)
    content: Mapped[str] = mapped_column(Text, default="")
    description: Mapped[str] = mapped_column(String(255), default="")
    variables: Mapped[list] = mapped_column(JSON, default=list)
    is_default: Mapped[bool] = mapped_column(Boolean, default=True)
    updated_at: Mapped[int] = mapped_column(BigInteger, default=_now, onupdate=_now)


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
    cancelled = "cancelled"


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
    # Celery task id — cần để HỦY được job đang chờ/đang chạy (revoke theo id).
    # KHÔNG có cột này thì không có cách nào ra lệnh cho Celery quăng task.
    task_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
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
