"""
YupVox-Clone API — Day 2: real persistence (Postgres in prod / SQLite in dev)
+ Celery dispatch + credit metering.

Feature surface mirrors YupVox:
  jobs:    tts | stt | translate | dub | subtitle   (async, credit-metered)
  voices:  reusable zero-shot voice profiles (5-10s reference clip)
"""
from __future__ import annotations

import hashlib
import os
import secrets as _secrets
import time

from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .db import get_db
from .models import ApiKey, CreditLedger, Job, JobStatus, User, Voice
from .admin_ui import ADMIN_HTML
from .app_ui import APP_HTML
from .settings_service import (
    SETTING_DEFS,
    delete_setting,
    get_setting,
    list_settings,
    mask,
    set_setting,
)
from .storage import get_storage
from .tasks import dispatch

# Dev fallback keys (docker-compose sets YUPVOX_API_KEYS); production keys live in DB.
DEV_KEYS = set(filter(None, os.getenv("YUPVOX_API_KEYS", "dev-key-1").split(",")))
VALID_TYPES = {"tts", "stt", "translate", "dub", "subtitle"}

# Placeholder pricing — D6 replaces with real metering (audio seconds / characters).
COSTS = {"tts": 10, "stt": 5, "translate": 2, "dub": 60, "subtitle": 8}

app = FastAPI(
    title="YupVox-Clone API",
    version="0.2.0",
    description="Open-source clone of an AI voice/dubbing SaaS — 7-day challenge.",
)

# Auto-migration: create missing tables on startup (idempotent, dev-friendly).
from .db import Base as _Base, engine as _engine  # noqa: E402

_Base.metadata.create_all(_engine)


# In-memory sliding-window rate limiter (single process; D7: Redis-backed).
_RATE: dict[str, list[float]] = {}


def _check_rate(ident: str, limit: int) -> bool:
    now = time.time()
    lst = [t for t in _RATE.get(ident, []) if now - t < 60.0]
    if len(lst) >= limit:
        return False
    lst.append(now)
    _RATE[ident] = lst
    return True


def _hash_key(raw: str) -> str:
    """API keys are stored hashed — a DB dump exposes no usable keys."""
    return hashlib.sha256(raw.encode()).hexdigest()


def admin_auth(x_admin_key: str = Header(..., alias="X-Admin-Key")) -> None:
    expected = str(get_setting("admin.api_key", "admin-dev-key",
                               env_fallback="YUPVOX_ADMIN_KEY"))
    if not _secrets.compare_digest(x_admin_key, expected):  # timing-safe
        raise HTTPException(status_code=401, detail="invalid admin key")


def auth(
    x_api_key: str = Header(..., alias="X-API-Key"),
    db: Session = Depends(get_db),
) -> User:
    key = db.scalar(select(ApiKey).where(ApiKey.key == _hash_key(x_api_key),
                                         ApiKey.active.is_(True)))
    if key:
        user = db.get(User, key.user_id)
        if user:
            if not _check_rate(f"key:{key.key}", key.rate_limit_per_min):
                raise HTTPException(status_code=429, detail="rate limit exceeded")
            return user
    if x_api_key in DEV_KEYS:  # dev fallback: auto-provision local dev user
        user = db.scalar(select(User).where(User.email == "dev@local"))
        if not user:
            user = User(email="dev@local")
            db.add(user)
            db.commit()
            db.refresh(user)
        if not _check_rate(f"user:{user.id}", 120):
            raise HTTPException(status_code=429, detail="rate limit exceeded")
        return user
    raise HTTPException(status_code=401, detail="invalid API key")


def _charge(db: Session, user: User, job_id: str, jtype: str) -> int:
    cost = int(get_setting(f"pricing.{jtype}", COSTS[jtype]))
    if user.credits < cost:
        raise HTTPException(status_code=402, detail=f"need {cost} credits, have {user.credits}")
    user.credits -= cost
    db.add(CreditLedger(user_id=user.id, delta=-cost, reason=f"job:{jtype}", job_id=job_id))
    return cost


class JobIn(BaseModel):
    type: str = Field(..., description="tts | stt | translate | dub | subtitle")
    media_url: str | None = None
    text: str | None = None
    source_lang: str | None = None
    target_lang: str | None = None
    voice_id: str | None = None
    max_speed: float = 1.35
    webhook_url: str | None = None  # TODO(D6): POST result on completion


class VoiceIn(BaseModel):
    name: str
    lang: str = "auto"
    engine: str = "chatterbox"
    ref_s3_key: str = Field(..., description="S3 key of the 5-10s reference clip")


@app.get("/healthz")
def healthz() -> dict:
    return {"ok": True, "time": int(time.time())}


@app.post("/v1/jobs", status_code=202)
def create_job(
    job: JobIn, user: User = Depends(auth), db: Session = Depends(get_db)
) -> dict:
    if job.type not in VALID_TYPES:
        raise HTTPException(status_code=422, detail=f"type must be one of {sorted(VALID_TYPES)}")
    if job.type == "subtitle":
        # Chưa có pipeline thật — không nhận tiền của user (501, không trừ credits).
        raise HTTPException(status_code=501,
                            detail="subtitle pipeline chưa triển khai — job không bị trừ credits")
    j = Job(user_id=user.id, type=job.type, params=job.model_dump(exclude_none=True))
    db.add(j)
    db.flush()  # need j.id for the ledger row
    cost = _charge(db, user, j.id, job.type)
    j.credits_charged = cost
    db.commit()
    mode = dispatch(j.id, j.params)
    return {"job_id": j.id, "status": j.status.value, "credits_charged": cost, "dispatch": mode}


@app.get("/v1/jobs/{job_id}")
def get_job(
    job_id: str, user: User = Depends(auth), db: Session = Depends(get_db)
) -> dict:
    j = db.get(Job, job_id)
    if j is None or j.user_id != user.id:
        raise HTTPException(status_code=404, detail="job not found")
    return {
        "job_id": j.id, "type": j.type, "status": j.status.value,
        "progress": j.progress, "error": j.error, "credits_charged": j.credits_charged,
    }


@app.get("/v1/jobs/{job_id}/result")
def get_result(
    job_id: str, user: User = Depends(auth), db: Session = Depends(get_db)
) -> dict:
    j = db.get(Job, job_id)
    if j is None or j.user_id != user.id:
        raise HTTPException(status_code=404, detail="job not found")
    if j.status != JobStatus.done:
        raise HTTPException(status_code=409, detail=f"job is {j.status.value}")
    # TODO(D3): presigned S3/MinIO URL with expiry
    return {"job_id": j.id, "download_url": f"/media/{j.result_s3_key}"}


@app.post("/v1/voices", status_code=201)
def create_voice(
    v: VoiceIn, user: User = Depends(auth), db: Session = Depends(get_db)
) -> dict:
    row = Voice(user_id=user.id, name=v.name, lang=v.lang,
                engine=v.engine, ref_s3_key=v.ref_s3_key)
    db.add(row)
    db.commit()
    return {"voice_id": row.id, "name": row.name, "engine": row.engine}


@app.post("/v1/voices/upload", status_code=201)
async def upload_voice(
    name: str = Form(...),
    lang: str = Form("auto"),
    file: UploadFile = File(...),
    user: User = Depends(auth),
    db: Session = Depends(get_db),
) -> dict:
    """Register a voice profile from a 3-8s reference clip (multipart upload)."""
    data = await file.read()
    if len(data) > 15 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="reference clip too large (max 15MB)")
    if not data:
        raise HTTPException(status_code=422, detail="empty file")
    row = Voice(user_id=user.id, name=name, lang=lang, engine="vieneu", ref_s3_key="pending")
    db.add(row)
    db.flush()
    key = f"voices/{row.id}/ref.wav"
    get_storage().put(key, data)
    row.ref_s3_key = key
    db.commit()
    return {"voice_id": row.id, "name": row.name, "ref_key": key}


@app.get("/v1/me")
def me(user: User = Depends(auth), db: Session = Depends(get_db)) -> dict:
    voices = db.scalars(select(Voice).where(Voice.user_id == user.id)).all()
    return {
        "user_id": user.id,
        "credits": user.credits,
        "voices": [{"id": x.id, "name": x.name, "lang": x.lang} for x in voices],
    }


# ---------------------------------------------------------------- Day 6: admin


@app.get("/admin", response_class=HTMLResponse)
def admin_page() -> str:
    """Settings UI — single page, no build step. Auth via X-Admin-Key in JS."""
    return ADMIN_HTML


@app.get("/", response_class=HTMLResponse)
def app_page() -> str:
    """Giao diện người dùng — Dub / TTS / Voices / Jobs.

    AGPL-3.0 §13: liên kết "Mã nguồn" phải trỏ tới bản mã nguồn tương ứng đang chạy.
    Đọc từ Settings (`app.source_url`) để self-host đổi được mà không sửa code.
    """
    from html import escape

    url = escape(str(get_setting("app.source_url", "")), quote=True)
    return APP_HTML.replace("__SOURCE_URL__", url)


@app.get("/v1/pricing")
def pricing(user: User = Depends(auth)) -> dict:
    """Bảng giá credits/job — nguồn sự thật là Settings (admin sửa được)."""
    return {"pricing": {t: int(get_setting(f"pricing.{t}", COSTS[t])) for t in COSTS}}


@app.post("/v1/media/upload", status_code=201)
async def upload_media(file: UploadFile = File(...), user: User = Depends(auth),
                       db: Session = Depends(get_db)) -> dict:
    """Upload audio/video -> storage key (dùng làm media_url cho jobs)."""
    data = await file.read()
    if len(data) > 200 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="file too large (max 200MB)")
    if not data:
        raise HTTPException(status_code=422, detail="empty file")
    key = f"media/{_secrets.token_hex(6)}/{file.filename}"
    get_storage().put(key, data)
    return {"media_key": key, "size": len(data), "filename": file.filename}


@app.get("/media/{key:path}")
def serve_media(key: str, api_key: str = "", db: Session = Depends(get_db)) -> FileResponse:
    """Serve kết quả — auth qua query param (media tag không gửi header được)."""
    ok = api_key in DEV_KEYS or db.scalar(
        select(ApiKey).where(ApiKey.key == _hash_key(api_key))) is not None
    if not ok:
        raise HTTPException(status_code=401, detail="invalid api key")
    storage = get_storage()
    if not storage.exists(key):
        raise HTTPException(status_code=404, detail="not found")
    path = storage.get_to_temp(key)
    from mimetypes import guess_type

    media_type = guess_type(path)[0] or "application/octet-stream"
    return FileResponse(path, media_type=media_type, filename=os.path.basename(key))


@app.get("/v1/jobs")
def list_jobs(limit: int = 20, user: User = Depends(auth),
              db: Session = Depends(get_db)) -> dict:
    rows = db.scalars(
        select(Job).where(Job.user_id == user.id)
        .order_by(Job.created_at.desc()).limit(min(limit, 100))
    ).all()
    return {"jobs": [{"job_id": j.id, "type": j.type, "status": j.status.value,
                      "progress": j.progress, "result_key": j.result_s3_key,
                      "error": j.error, "created_at": j.created_at} for j in rows]}


@app.get("/v1/usage")
def usage(user: User = Depends(auth), db: Session = Depends(get_db)) -> dict:
    """Số liệu THẬT cho donut dashboard — aggregate credit_ledger theo loại job."""
    rows = db.execute(
        select(CreditLedger.reason, func.sum(CreditLedger.delta))
        .where(CreditLedger.user_id == user.id)
        .group_by(CreditLedger.reason)
    ).all()
    by_type: dict[str, int] = {}
    for reason, delta in rows:
        t = reason.replace("job:", "") if (reason or "").startswith("job:") else "other"
        by_type[t] = by_type.get(t, 0) + abs(int(delta or 0))
    used = sum(by_type.values())
    return {"free_quota": 50_000, "used": used,
            "total": user.credits + used, "by_type": by_type}


@app.get("/admin/settings")
def admin_list(_: None = Depends(admin_auth)) -> dict:
    return {"settings": list_settings()}


@app.put("/admin/settings/{key}")
def admin_set(key: str, body: dict, _: None = Depends(admin_auth)) -> dict:
    value = body.get("value")
    if value is None or not isinstance(value, (str, int, float, bool)):
        raise HTTPException(status_code=422, detail='body must be {"value": str|number|bool}')
    d = next((d for d in SETTING_DEFS if d["key"] == key), None)
    is_secret = body.get("is_secret") if isinstance(body.get("is_secret"), bool) \
        else bool(d and d.get("secret"))
    set_setting(key, value, is_secret=is_secret,
                category=d["category"] if d else "custom")
    return {"key": key, "ok": True}


@app.delete("/admin/settings/{key}")
def admin_delete(key: str, _: None = Depends(admin_auth)) -> dict:
    return {"key": key, "deleted": delete_setting(key)}


# ------------------------------------------------------- Day 6: API keys mgmt


@app.post("/v1/keys", status_code=201)
def create_api_key(user: User = Depends(auth), db: Session = Depends(get_db)) -> dict:
    raw = "yv_" + _secrets.token_hex(16)
    db.add(ApiKey(key=_hash_key(raw), prefix=raw[:12], user_id=user.id))
    db.commit()
    return {"key": raw, "rate_limit_per_min": 60,
            "note": "store it now — shown once (only a SHA-256 hash is stored)"}


@app.get("/v1/keys")
def list_api_keys(user: User = Depends(auth), db: Session = Depends(get_db)) -> dict:
    keys = db.scalars(select(ApiKey).where(ApiKey.user_id == user.id)).all()
    return {"keys": [{"key": mask(k.prefix), "active": k.active,
                      "rate_limit_per_min": k.rate_limit_per_min} for k in keys]}


@app.delete("/v1/keys/{key}")
def revoke_api_key(key: str, user: User = Depends(auth),
                   db: Session = Depends(get_db)) -> dict:
    # Accepts the RAW key (the only form a client still holds); lookup is hashed.
    row = db.get(ApiKey, _hash_key(key))
    if row is None or row.user_id != user.id:
        raise HTTPException(status_code=404, detail="key not found")
    db.delete(row)
    db.commit()
    return {"key": mask(row.prefix), "revoked": True}


# --------------------------------------------------------- Day 6.1: signup


class SignupIn(BaseModel):
    email: str


@app.post("/v1/auth/signup", status_code=201)
def signup(body: SignupIn, request: Request,
           db: Session = Depends(get_db)) -> dict:
    """Tạo user + API key đầu tiên. Không cần auth — rate limit theo IP (5/phút)."""
    ip = request.client.host if request.client else "unknown"
    if not _check_rate(f"signup:{ip}", 5):
        raise HTTPException(status_code=429, detail="too many signups, retry later")
    email = body.email.strip().lower()
    if "@" not in email or len(email) > 255:
        raise HTTPException(status_code=422, detail="invalid email")
    if db.scalar(select(User).where(User.email == email)):
        raise HTTPException(status_code=409, detail="email already registered")
    u = User(email=email)
    db.add(u)
    db.flush()
    raw = "yv_" + _secrets.token_hex(16)
    db.add(ApiKey(key=_hash_key(raw), prefix=raw[:12], user_id=u.id))
    db.commit()
    return {"user_id": u.id, "email": email, "credits": u.credits,
            "key": raw, "note": "store it now — shown once"}
