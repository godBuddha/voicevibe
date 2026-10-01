"""Settings Hub API — phần CÁ NHÂN (profile/mật khẩu/phiên) + phần HỆ THỐNG
(audit/overview/system/config export-import) của Control Center /settings.

Quy tắc chung:
- Endpoint cá nhân `Depends(auth)`; endpoint hệ thống `Depends(current_admin)`.
- CSRF KHÔNG cần code thêm: `_check_csrf` nằm trong `auth_optional` (auth.py),
  tự áp cho mọi request non-GET đã xác thực bằng cookie.
- Sai MẬT KHẨU hiện tại trả **403**, KHÔNG 401: client.js coi 401 là "hết phiên"
  và redirect /login — nếu trả 401 thì người dùng bị đá khỏi trang đang gõ mật
  khẩu. 401 chỉ dành cho "chưa đăng nhập".
- Export KHÔNG BAO GIỜ chứa secret (giá trị secret settings + provider api_key):
  file xuất ra có thể nằm trong Downloads / đám mây / email.
"""
from __future__ import annotations

import os
import platform
import shutil
import time

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from . import prompts as P
from .audit import log_action
from .auth import COOKIE_NAME, auth, current_admin, hash_key
from .db import SessionLocal, get_db
from .models import (
    ROLE_ADMIN,
    AiModel,
    AiProvider,
    ApiKey,
    AuditLog,
    Job,
    JobStatus,
    Prompt,
    Session as DbSession,
    StageModel,
    STAGES,
    User,
    Voice,
)
from .ratelimit import check_rate
from .security import MIN_PASSWORD_LEN, hash_password, password_problem, verify_password
from .settings_service import list_settings, set_setting

router = APIRouter(tags=["settings-hub"])


class MeUpdate(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)


class PasswordChange(BaseModel):
    current_password: str
    new_password: str


# ------------------------------------------------------------- tiện ích riêng
def _cookie_hash(request: Request) -> str | None:
    """SHA-256 của token phiên trong cookie — so trực tiếp với cột PK của sessions."""
    token = request.cookies.get(COOKIE_NAME)
    return hash_key(token) if token else None


def _session_out(row: DbSession, current_hash: str | None) -> dict:
    return {
        "token_hash": row.token_hash,
        "current": bool(current_hash and row.token_hash == current_hash),
        "created_at": row.created_at,
        "last_seen_at": row.last_seen_at,
        "expires_at": row.expires_at,
        "ip": row.ip,
        "user_agent": (row.user_agent or "")[:100],
    }


# ------------------------------------------------------------------ HỒ SƠ (me)
@router.patch("/v1/me")
def me_update(body: MeUpdate, user: User = Depends(auth),
              db: Session = Depends(get_db)) -> dict:
    user.name = body.name.strip()
    db.commit()
    log_action("me.name_change", user_id=user.id, target=user.email)
    return {"user_id": user.id, "email": user.email, "name": user.name,
            "role": user.role}


@router.post("/v1/me/password")
def me_password(body: PasswordChange, request: Request,
                user: User = Depends(auth), db: Session = Depends(get_db)) -> dict:
    """Đổi mật khẩu CỦA CHÍNH MÌNH — thu hồi mọi phiên KHÁC, giữ phiên hiện tại.

    Khoá 5 lần/phút: mặc định session 240/phút quá thoáng cho việc DÒ
    `current_password` bằng cách lặp POST (ai có phiên cũng là người biết mật khẩu
    cũ, nhưng khoá cửa vẫn đúng nguyên tắc — giống login:acct).
    """
    if not check_rate(f"pwchange:{user.id}", 5, window=60):
        raise HTTPException(status_code=429, detail="thử đổi mật khẩu quá nhanh, vui lòng đợi")
    if not user.password_hash:
        raise HTTPException(status_code=403, detail="tài khoản chưa có mật khẩu (chỉ dùng API key)")
    if not verify_password(body.current_password, user.password_hash):
        # 403 (phải 401 — client.js redirect /login khi 401). 403 = "biết ai mà sai".
        raise HTTPException(status_code=403, detail="mật khẩu hiện tại không đúng")
    problem = password_problem(body.new_password)
    if problem:
        raise HTTPException(status_code=422, detail=problem)

    current_hash = _cookie_hash(request)
    rows = db.scalars(select(DbSession).where(
        DbSession.user_id == user.id, DbSession.token_hash != current_hash)).all()
    revoked = len(rows)
    for row in rows:
        db.delete(row)
    # hash_password luôn tạo tham số scrypt mới — tự nâng cấp hash khi đổi.
    user.password_hash = hash_password(body.new_password)
    db.commit()
    log_action("me.password_change", user_id=user.id, target=user.email,
               detail=f"other_sessions_revoked={revoked}")
    return {"ok": True, "sessions_revoked": revoked}


# --------------------------------------------------------------- PHIÊN (me)
@router.get("/v1/me/sessions")
def me_sessions(request: Request, user: User = Depends(auth),
                db: Session = Depends(get_db)) -> dict:
    current_hash = _cookie_hash(request)
    rows = db.scalars(select(DbSession).where(DbSession.user_id == user.id)
                      .order_by(DbSession.last_seen_at.desc())).all()
    return {"current": current_hash,
            "sessions": [_session_out(row, current_hash) for row in rows]}


@router.delete("/v1/me/sessions/{token_hash}")
def me_session_revoke(token_hash: str, request: Request,
                      user: User = Depends(auth), db: Session = Depends(get_db)) -> dict:
    row = db.get(DbSession, token_hash)
    # 404 (không 403) — không tiết lộ hash có tồn tại nhưng thuộc người khác
    # (cùng quy ước ownership của job/voice/prompt).
    if row is None or row.user_id != user.id:
        raise HTTPException(status_code=404, detail="session not found")
    current = row.token_hash == _cookie_hash(request)
    db.delete(row)
    db.commit()
    log_action("me.session_revoke", user_id=user.id,
               detail="current=true" if current else "current=false")
    return {"revoked": token_hash[:16], "current": current}


@router.delete("/v1/me/sessions")
def me_sessions_revoke_others(request: Request, user: User = Depends(auth),
                              db: Session = Depends(get_db)) -> dict:
    """Đăng xuất mọi thiết bị KHÁC — phiên hiện tại giữ nguyên (nút "quên quách")."""
    current_hash = _cookie_hash(request)
    rows = db.scalars(select(DbSession).where(
        DbSession.user_id == user.id, DbSession.token_hash != current_hash)).all()
    for row in rows:
        db.delete(row)
    revoked = len(rows)
    db.commit()
    log_action("me.session_revoke", user_id=user.id, detail=f"revoked_others={revoked}")
    return {"revoked": revoked}


# ---------------------------------------------------------------- HỆ THỐNG (admin)
@router.get("/v1/admin/audit")
def admin_audit(q: str | None = None, action: str | None = None,
                user_id: str | None = None, limit: int = 50, offset: int = 0,
                _: object = Depends(current_admin),
                db: Session = Depends(get_db)) -> dict:
    """Nhật ký hành động — filter q/action/user_id + phân trang.

    `q` lọc python-side trên action+target+detail: SQL LIKE khác cú pháp giữa
    SQLite/Postgres (pattern `_filter_models` của providers_api cũng chọn đường
    này), và volume nhật ký là vừa phải (chỉ ghi hành động hiếm, không log GET).
    """
    limit = min(max(limit, 1), 200)
    if offset < 0:
        offset = 0
    stmt = select(AuditLog).order_by(AuditLog.created_at.desc(), AuditLog.id.desc())
    if action:
        stmt = stmt.where(AuditLog.action == action)
    if user_id:
        stmt = stmt.where(AuditLog.user_id == user_id)
    rows = db.scalars(stmt).all()
    if q:
        needle = q.strip().lower()
        rows = [r for r in rows if needle in " ".join(
            (r.action, r.target or "", r.detail or "")).lower()]
    total = len(rows)
    rows = rows[offset:offset + limit]
    users = {}
    ids = {r.user_id for r in rows if r.user_id}
    if ids:
        users = {u.id: u.email for u in db.scalars(
            select(User).where(User.id.in_(ids))).all()}
    items = [{
        "id": r.id, "user_id": r.user_id,
        "user_email": users.get(r.user_id),
        "action": r.action, "target": r.target, "detail": r.detail,
        "ip": r.ip, "created_at": r.created_at,
    } for r in rows]
    return {"items": items, "total": total, "limit": limit, "offset": offset}


@router.get("/v1/admin/overview")
def admin_overview(_: object = Depends(current_admin),
                   db: Session = Depends(get_db)) -> dict:
    """Thống kê jobs TOÀN hệ + số lượng entity — cho section Quan sát.

    Đếm JOB (self-host miễn phí, không có đơn vị tiền tệ) — cùng quy ước
    /v1/usage nhưng BỎ filter user. Không trả secret."""
    rows = db.execute(
        select(Job.type, Job.status, func.count()).group_by(Job.type, Job.status)).all()
    by_type: dict[str, int] = {}
    by_status: dict[str, int] = {}
    for jtype, status, n in rows:
        by_type[jtype] = by_type.get(jtype, 0) + int(n)
        by_status[status.value if hasattr(status, "value") else str(status)] = \
            by_status.get(status.value if hasattr(status, "value") else str(status), 0) + int(n)
    admins = int(db.scalar(select(func.count()).select_from(User)
                           .where(User.role == ROLE_ADMIN)) or 0)
    active_users = int(db.scalar(select(func.count()).select_from(User)
                                 .where(User.is_active.is_(True))) or 0)
    total_users = int(db.scalar(select(func.count()).select_from(User)) or 0)
    return {
        "total_jobs": sum(by_type.values()), "by_type": by_type,
        "by_status": by_status, "running": by_status.get("running", 0),
        "users": {"total": total_users, "admins": admins, "active": active_users},
        "voices": int(db.scalar(select(func.count()).select_from(Voice)) or 0),
        "api_keys": {"total": int(db.scalar(select(func.count()).select_from(ApiKey)) or 0),
                     "active": int(db.scalar(select(func.count()).select_from(ApiKey)
                                             .where(ApiKey.active.is_(True))) or 0)},
        "providers": {"total": int(db.scalar(select(func.count()).select_from(AiProvider)) or 0),
                      "enabled": int(db.scalar(select(func.count()).select_from(AiProvider)
                                               .where(AiProvider.enabled.is_(True))) or 0)},
        "models": {"total": int(db.scalar(select(func.count()).select_from(AiModel)) or 0),
                   "enabled": int(db.scalar(select(func.count()).select_from(AiModel)
                                            .where(AiModel.enabled.is_(True))) or 0)},
    }


@router.get("/v1/admin/system")
def admin_system(_: object = Depends(current_admin),
                 db: Session = Depends(get_db)) -> dict:
    """Tình trạng hệ thống read-only (Hệ thống → Tổng quan). KHÔNG giá trị secret.

    `storage.root` phải lấy từ ENV (get_storage chọn theo env) — setting DB
    `media_root` chỉ là HIỂN THỊ, không điều khiển runtime; UI phải ghi chú đúng
    điều đó, không nói dối self-host.
    """
    engine = db.get_bind()
    dialect = engine.dialect.name
    version = ""
    try:
        if dialect == "postgresql":
            version = str(db.execute(text("select version()")).scalar())[:80]
        else:
            version = str(db.execute(text("select sqlite_version()")).scalar())
    except Exception:  # noqa: BLE001 — version không bắt buộc
        version = ""

    inline = os.getenv("VOICEVIBE_INLINE", "") == "1"
    broker = "inline"
    if not inline:
        broker = "redis-down"
        try:
            import redis  # có sẵn qua celery[redis] (pattern ratelimit.py:75)
            client = redis.Redis.from_url(
                os.getenv("REDIS_URL", "redis://localhost:6379/0"),
                socket_connect_timeout=2, socket_timeout=2)
            if client.ping():
                broker = "redis-ok"
        except Exception:  # noqa: BLE001
            pass

    endpoint = os.getenv("S3_ENDPOINT")
    if endpoint:
        storage_mode = "s3"
        storage_root = os.getenv("S3_BUCKET", "voicevibe")
        free_bytes = None
    else:
        storage_mode = "local"
        storage_root = os.getenv("MEDIA_ROOT", "./media")
        free_bytes = None
        try:
            free_bytes = shutil.disk_usage(storage_root).free
        except Exception:  # noqa: BLE001 — root chưa tạo được thì không đo được
            pass

    sessions_expired = int(db.scalar(select(func.count()).select_from(DbSession)
                                     .where(DbSession.expires_at <= int(time.time()))) or 0)
    jobs_running = int(db.scalar(select(func.count()).select_from(Job)
                                 .where(Job.status == JobStatus.running)) or 0)
    return {
        "db": {"dialect": dialect, "version": version},
        "queue": {"mode": "inline" if inline else "celery", "broker": broker},
        "storage": {"mode": storage_mode, "root": storage_root, "free_bytes": free_bytes},
        "python": platform.python_version(),
        "password_min_length": MIN_PASSWORD_LEN,
        "jobs_running": jobs_running,
        "sessions_expired": sessions_expired,
    }


# ------------------------------------------------- EXPORT / IMPORT cấu hình
_EXPORT_KEYS = ("settings", "providers", "stages", "prompts")


@router.get("/v1/admin/config/export")
def admin_config_export(_: object = Depends(current_admin),
                        db: Session = Depends(get_db)) -> dict:
    """Xuất cấu hình dạng JSON — KHÔNG secret (secret settings chỉ là stub).

    Provider api_key KHÔNG xuất (đã mã hoá theo SETTINGS_MASTER_KEY của hệ NÀY;
    đem qua hệ khác là vô nghĩa nhưng lộ hint là lộ rủi ro). Import upsert được
    bao nhiêu lần cũng không tạo dup — cặp (stage, order) + tên provider là chốt."""
    settings_out = []
    for row in list_settings():
        if not row.get("set_in_db"):
            continue
        if row.get("is_secret"):
            settings_out.append({"key": row["key"], "secret": True})
        else:
            settings_out.append({"key": row["key"], "value": row.get("value"),
                                 "category": row.get("category")})
    providers_out = [{
        "name": p.name, "kind": p.kind, "base_url": p.base_url,
        "prefix_id": p.prefix_id, "enabled": p.enabled,
    } for p in db.scalars(select(AiProvider).order_by(AiProvider.created_at)).all()]
    providers_by_id = {p.id: p.name for p in db.scalars(select(AiProvider)).all()}
    stages_out = [{
        "stage": r.stage, "order": r.order,
        "provider_name": providers_by_id.get(r.provider_id),
        "model": r.model, "params": r.params or {},
    } for r in db.scalars(select(StageModel)
                          .order_by(StageModel.stage, StageModel.order)).all()]
    prompts_out = [{"task_key": p.task_key, "content": p.content}
                   for p in db.scalars(select(Prompt)).all() if p.content]
    return {"_meta": {"version": 1, "exported_at": int(time.time())},
            "settings": settings_out, "providers": providers_out,
            "stages": stages_out, "prompts": prompts_out}


@router.post("/v1/admin/config/import")
def admin_config_import(body: dict, _: object = Depends(current_admin),
                        db: Session = Depends(get_db)) -> dict:
    """Nhập cấu hình export ở trên — idempotent, phần thiếu là warnings không lỗi.

    Shape xấu (không dict / key lạ / giá trị không list) → 422 NGAY trước khi
    ghi bất kỳ gì — import nửa vời là bẫy kinh điển của tính năng kiểu này."""
    if not isinstance(body, dict) or set(body) - (set(_EXPORT_KEYS) | {"_meta"}):
        raise HTTPException(
            status_code=422, detail=f"body chỉ được chứa các nhóm {list(_EXPORT_KEYS)}")
    for key in _EXPORT_KEYS:
        if key in body and not isinstance(body[key], list):
            raise HTTPException(status_code=422, detail=f"'{key}' phải là một danh sách")

    imported = {"settings": 0, "providers": 0, "stages": 0, "prompts": 0}
    warnings: list[str] = []

    for entry in body.get("settings", []):
        if not isinstance(entry, dict) or "key" not in entry:
            warnings.append("settings: một dòng không có key — bỏ")
            continue
        if entry.get("secret"):
            # Stub secret xuất ra chỉ để NHỚ TÊN — giá trị không thể đem qua hệ khác
            # (Fernet theo SETTINGS_MASTER_KEY của hệ xuất).
            warnings.append(f"settings: '{entry['key']}' là secret — hãy nhập thủ công")
            continue
        set_setting(str(entry["key"]), entry.get("value"))
        imported["settings"] += 1

    for entry in body.get("providers", []):
        if not isinstance(entry, dict) or not entry.get("name"):
            warnings.append("providers: một dòng không có name — bỏ")
            continue
        name = str(entry["name"]).strip()
        row = db.scalar(select(AiProvider).where(AiProvider.name == name))
        if row is None:
            row = AiProvider(name=name)
            db.add(row)
        # PATCH semantics: CHỈ đụng trường phi-secret — api_key_enc hiện có giữ nguyên.
        row.kind = str(entry.get("kind") or row.kind)
        row.base_url = str(entry.get("base_url") or row.base_url)
        row.prefix_id = entry.get("prefix_id")
        row.enabled = bool(entry.get("enabled", row.enabled))
        imported["providers"] += 1

    stages = {s: [] for s in STAGES}
    for entry in body.get("stages", []):
        if not isinstance(entry, dict) or not entry.get("stage"):
            warnings.append("stages: một dòng không có stage — bỏ")
            continue
        stage = str(entry["stage"])
        if stage not in stages:
            warnings.append(f"stages: '{stage}' không phải công đoạn hợp lệ — bỏ")
            continue
        provider_name = entry.get("provider_name")
        provider = None
        if provider_name:
            provider = db.scalar(select(AiProvider).where(AiProvider.name == str(provider_name)))
        if provider_name and provider is None:
            # Hệ nhập chưa có provider này: KHÔNG 422 (export một phần vẫn nhập được)
            # — gom vào warnings để UI hiện rõ.
            warnings.append(f"stages: provider '{provider_name}' chưa tồn tại — bỏ gán '{stage}'")
            continue
        order = int(entry.get("order") or 0)
        row = db.scalar(select(StageModel)
                        .where(StageModel.stage == stage, StageModel.order == order))
        if row is None:
            row = StageModel(stage=stage, order=order)
            db.add(row)
        row.provider_id = provider.id if provider else None
        row.model = str(entry.get("model") or "").strip()
        row.params = entry.get("params") or {}
        imported["stages"] += 1

    for entry in body.get("prompts", []):
        if not isinstance(entry, dict) or not entry.get("task_key"):
            warnings.append("prompts: một dòng không có task_key — bỏ")
            continue
        try:
            P.set_prompt(str(entry["task_key"]), str(entry.get("content") or ""))
            imported["prompts"] += 1
        except ValueError as exc:
            warnings.append(f"prompts: '{entry['task_key']}' — {exc}")

    db.commit()
    log_action("config.import", target="settings-hub",
               detail="imported=" + ",".join(f"{k}:{v}" for k, v in imported.items()))
    return {"imported": imported, "warnings": warnings}
