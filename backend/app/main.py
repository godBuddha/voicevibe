"""
YupVox-Clone API.

Persistence: Postgres (prod) / SQLite (dev) + Celery dispatch + credit metering.
Feature surface mirrors YupVox:
  jobs:    tts | stt | translate | dub | subtitle   (async, credit-metered)
  voices:  reusable zero-shot voice profiles (5-10s reference clip)
  auth:    phiên cookie cho web + X-API-Key cho máy gọi (xem app/auth.py)

Lần đầu chạy KHÔNG có tài khoản nào → `/setup` tạo Admin. Sau đó chỉ Admin tạo được
người dùng; đăng ký công khai tắt mặc định (`auth.allow_signup`).
"""
from __future__ import annotations

import os
import secrets as _secrets
import time

from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, Response, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from . import auth as A
from .admin_ui import ADMIN_HTML
from .app_ui import APP_HTML
from .auth_ui import LOGIN_HTML, SETUP_HTML
from .db import engine as _engine
from .db import get_db
from .migrations import ensure_schema
from .models import (
    ApiKey,
    CreditLedger,
    FREE_CREDITS,
    Job,
    JobStatus,
    MediaObject,
    ROLE_ADMIN,
    ROLE_USER,
    User,
    Voice,
)
from .pipelines.subtitle import FORMATS as SUBTITLE_FORMATS
from .prompts import seed_prompts
from .providers_api import router as ai_admin_router
from .ratelimit import check_rate as _check_rate
from .ratelimit import _RATE  # noqa: F401 — giữ tên cũ cho test/ops
from .ratelimit import backend as rate_limit_backend
from .security import MIN_PASSWORD_LEN, hash_password, password_problem
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

VALID_TYPES = {"tts", "stt", "translate", "dub", "subtitle"}

# Placeholder pricing — D6 replaces with real metering (audio seconds / characters).
COSTS = {"tts": 10, "stt": 5, "translate": 2, "dub": 60, "subtitle": 8}

# Docs công khai mặc định TẮT: schema API lộ toàn bộ bề mặt tấn công. Bật khi cần
# xem Swagger trên máy cá nhân: YUPVOX_ENABLE_DOCS=1
_DOCS = os.getenv("YUPVOX_ENABLE_DOCS") == "1"

app = FastAPI(
    title="YupVox-Clone API",
    version="0.3.0",
    description="Open-source AI voice/dubbing platform — self-hosted, AGPL-3.0.",
    docs_url="/docs" if _DOCS else None,
    redoc_url="/redoc" if _DOCS else None,
    openapi_url="/openapi.json" if _DOCS else None,
)


def parse_cors_origins(raw: str) -> list[str]:
    """Danh sách origin được phép gọi API từ BẤT KỲ nguồn nào khác (tách frontend).

    Đầu vào: nội dung env `YUPVOX_CORS_ORIGINS` — phân tách bằng dấu phẩy, ví dụ
    `http://localhost:5173,https://app.example.com`. Chuỗi rỗng → rỗng (không bật
    CORS — trạng thái mặc định, web UI inline cùng origin không cần nó).

    `/` cuối bị cắt: `https://x.com/` và `https://x.com` phải là một origin, nếu
    không cấu hình tưởng đúng mà browser chặn.
    """
    return [o.strip().rstrip("/") for o in raw.split(",") if o.strip()]


def add_cors(app: FastAPI, origins: list[str]) -> None:
    # `allow_credentials=True` kết hợp wildcard là cặp BẤT HỢP LỆ theo spec CORS:
    # browser sẽ BỎ QUA allow-credentials khi danh sách là `*`, cookie phiên không
    # bao giờ được gửi — lỗi im lặng khó truy vết. Nên danh sách origin phải tường
    # minh, không bao giờ wildcard.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )


_CORS_ORIGINS = parse_cors_origins(os.getenv("YUPVOX_CORS_ORIGINS", ""))
if _CORS_ORIGINS:
    add_cors(app, _CORS_ORIGINS)

# Auto-migration: tạo bảng thiếu + THÊM CỘT thiếu vào bảng đã tồn tại (create_all một
# mình không làm được việc sau). Idempotent — xem app/migrations.py.
ensure_schema(_engine)

# Prompt hệ thống: tạo row cho các task còn thiếu để nút "Khôi phục mặc định" luôn có đích.
seed_prompts()

# Nhóm endpoint quản trị AI (nhà cung cấp / công đoạn / prompt) — xem app/providers_api.py
app.include_router(ai_admin_router)


def _hash_key(raw: str) -> str:
    """API keys are stored hashed — a DB dump exposes no usable keys."""
    return A.hash_key(raw)


# Tên cũ giữ nguyên để 13 endpoint `Depends(auth)` không phải sửa: giờ `auth` chấp
# nhận cookie phiên HOẶC X-API-Key nhưng vẫn trả về `User` như trước.
auth = A.auth
auth_optional = A.auth_optional
admin_auth = A.current_admin


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
    webhook_url: str | None = None
    # --- riêng cho type=dub
    # UI GỬI field này, nhưng JobIn trước đây không khai báo → pydantic ÂM THẦM
    # bỏ nó đi và pipeline luôn chạy background_mode="silence", bất kể người dùng
    # chọn gì trên dropdown. Đã phát hiện khi đi qua tham số cho Demucs.
    background_mode: str = Field(
        "silence", description="silence | source_low (nhạc nền kiểu karaoke)")
    # --- riêng cho type=subtitle
    format: str = Field("srt", description="srt | vtt | ass (chỉ dùng cho subtitle)")
    bilingual: bool = Field(
        False, description="phụ đề 2 dòng: bản gốc trên, bản dịch dưới "
                           "(cần target_lang)")
    show_speaker: bool = Field(True, description="ghi nhãn người nói vào phụ đề")


class VoiceIn(BaseModel):
    name: str
    lang: str = "auto"
    engine: str = "chatterbox"
    ref_s3_key: str = Field(..., description="S3 key of the 5-10s reference clip")


@app.get("/healthz")
def healthz() -> dict:
    # `ratelimit` có mặt để người vận hành THẤY ĐƯỢC hạn mức có đang chia sẻ hay
    # không. Chạy nhiều worker mà backend là "memory" thì hạn mức thực tế bị nhân
    # theo số worker — không có gì khác trong hệ thống nói ra điều đó.
    return {"ok": True, "time": int(time.time()),
            "ratelimit": rate_limit_backend()}


@app.post("/v1/jobs", status_code=202)
def create_job(
    job: JobIn, user: User = Depends(auth), db: Session = Depends(get_db)
) -> dict:
    if job.type not in VALID_TYPES:
        raise HTTPException(status_code=422, detail=f"type must be one of {sorted(VALID_TYPES)}")
    if job.type == "subtitle":
        # Kiểm TRƯỚC khi trừ credit — cùng nguyên tắc với quyền sở hữu voice bên
        # dưới: cấu hình sai phải bị chặn lúc tạo job, không phải sau khi đã thu tiền.
        if not job.media_url:
            raise HTTPException(status_code=422,
                                detail="subtitle cần media_url (audio hoặc video)")
        if job.format not in SUBTITLE_FORMATS:
            raise HTTPException(
                status_code=422,
                detail=f"format phải là một trong {list(SUBTITLE_FORMATS)}")
        if job.bilingual and not job.target_lang:
            raise HTTPException(
                status_code=422,
                detail="bilingual cần target_lang (bản dịch lấy gì?)")

    # Quyền sở hữu voice phải kiểm tra TRƯỚC khi trừ credit. Trước đây chỉ worker
    # kiểm tra (tasks.py), tức là job đã tạo, đã trừ tiền rồi mới fail → user mất
    # credit cho một job chắc chắn hỏng. Giữ kiểm tra ở worker làm lớp hai.
    if job.voice_id:
        voice = db.get(Voice, job.voice_id)
        if voice is None or voice.user_id != user.id:
            raise HTTPException(status_code=404, detail="voice not found")

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
    # Cố ý KHÔNG dùng presigned URL của S3. Media phải đi qua API để kiểm **quyền sở
    # hữu** (`_owns_media`); một presigned URL sẽ bỏ qua toàn bộ kiểm tra đó và biến
    # mọi key thành công khai trong thời gian URL còn hiệu lực.
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
        "email": user.email,
        "role": user.role,
        "credits": user.credits,
        "voices": [{"id": x.id, "name": x.name, "lang": x.lang} for x in voices],
    }


# ------------------------------------------------------- Phase 2: trang & đăng nhập
#
# Cổng vào ở tầng SERVER, không phải JS: trước đây `/` và `/admin` trả HTML cho bất
# kỳ ai, gate chỉ nằm ở client (ai tắt JS hoặc curl là thấy hết khung). Giờ HTML chỉ
# được trả khi đã xác thực đúng.


def _origin(request: Request) -> str:
    """URL gốc để dựng đường dẫn redirect, tôn trọng proxy (X-Forwarded-*)."""
    proto = request.headers.get("x-forwarded-proto", "").split(",")[0].strip()
    host = request.headers.get("x-forwarded-host") or request.headers.get("host") or ""
    scheme = proto or request.url.scheme
    fwd_prefix = request.headers.get("x-forwarded-prefix", "").rstrip("/")
    return f"{scheme}://{host}{fwd_prefix}" if host else str(request.base_url).rstrip("/")


def _redirect(path: str) -> RedirectResponse:
    return RedirectResponse(path, status_code=302)


def _render(page: str, request: Request) -> str:
    """Nội suy các placeholder của một trang HTML."""
    from html import escape

    return (page
            .replace("__SOURCE_URL__", escape(str(get_setting("app.source_url", "")),
                                              quote=True))
            .replace("__NEXT__", escape(request.query_params.get("next", "/"), quote=True)))


@app.get("/setup", response_class=HTMLResponse)
def setup_page(request: Request, db: Session = Depends(get_db)):
    """Trang tạo Admin lần đầu. Đã có admin thì không vào được nữa."""
    if A.admin_exists(db):
        return _redirect("/login")
    return _render(SETUP_HTML, request)


@app.get("/login", response_class=HTMLResponse)
def login_page(request: Request, db: Session = Depends(get_db)):
    if not A.admin_exists(db):
        return _redirect("/setup")
    if A.auth_optional(request, None, db) is not None:
        return _redirect("/")
    return _render(LOGIN_HTML, request)


class SetupIn(BaseModel):
    email: str
    password: str


class LoginIn(BaseModel):
    email: str
    password: str


def _valid_email(email: str) -> bool:
    """Kiểm tra tối thiểu, KHÔNG đòi TLD.

    Self-host hay dùng email nội bộ không có dấu chấm (`admin@local`, `user@nas`) —
    đòi `.` trong domain sẽ chặn oan. Xác thực email thật là việc của luồng gửi thư
    xác nhận, không phải của bước tạo tài khoản.
    """
    e = email.strip().lower()
    if not (3 <= len(e) <= 255) or e.count("@") != 1 or " " in e:
        return False
    local, _, domain = e.partition("@")
    return bool(local) and bool(domain) and "." not in (local[0], local[-1])


@app.post("/v1/auth/setup", status_code=201)
def setup(body: SetupIn, request: Request, response: Response,
          db: Session = Depends(get_db)) -> dict:
    """Tạo tài khoản quản trị ĐẦU TIÊN. Chỉ chạy được một lần cho mỗi hệ thống."""
    if not _check_rate(f"setup:{A._client_ip(request)}", 5):
        raise HTTPException(status_code=429, detail="quá nhiều lần thử, vui lòng đợi")
    if A.admin_exists(db):
        raise HTTPException(status_code=409, detail="hệ thống đã có tài khoản quản trị")
    if not _valid_email(body.email):
        raise HTTPException(status_code=422, detail="email không hợp lệ")
    problem = password_problem(body.password)
    if problem:
        raise HTTPException(status_code=422, detail=problem)

    # Chốt nguyên tử: hai request /setup đồng thời thì chỉ một INSERT thắng.
    if not A.claim_setup(db):
        raise HTTPException(status_code=409, detail="hệ thống đã có tài khoản quản trị")
    user = User(email=body.email.strip().lower(), role=ROLE_ADMIN,
                password_hash=hash_password(body.password),
                credits=FREE_CREDITS, last_login_at=int(time.time()))
    db.add(user)
    db.commit()
    db.refresh(user)
    token = A.create_session(db, user, request)
    db.commit()
    A.set_session_cookie(response, token, request)
    return {"user_id": user.id, "email": user.email, "role": user.role,
            "credits": user.credits, "redirect": "/"}


@app.post("/v1/auth/login")
def login(body: LoginIn, request: Request, response: Response,
          db: Session = Depends(get_db)) -> dict:
    if not _check_rate(f"login:ip:{A._client_ip(request)}", 10):
        raise HTTPException(status_code=429, detail="quá nhiều lần thử, vui lòng đợi")
    email = body.email.strip().lower()
    if not A.check_login_rate(email, A._client_ip(request)):
        raise HTTPException(status_code=429, detail="quá nhiều lần thử, vui lòng đợi")
    user = A.authenticate(db, email, body.password)
    if user is None:
        # Một thông báo chung cho mọi trường hợp sai — không lộ email nào tồn tại.
        raise HTTPException(status_code=401, detail="Email hoặc mật khẩu không đúng")
    A.mark_login(db, user, body.password)
    token = A.create_session(db, user, request)
    db.commit()
    A.set_session_cookie(response, token, request)
    return {"user_id": user.id, "email": user.email, "role": user.role,
            "credits": user.credits,
            "redirect": "/admin" if user.is_admin else "/"}


@app.post("/v1/auth/logout")
def logout(request: Request, response: Response,
           db: Session = Depends(get_db)) -> dict:
    A.revoke_session(db, request.cookies.get(A.COOKIE_NAME))
    A.clear_session_cookie(response, request)
    return {"ok": True, "redirect": "/login"}


@app.get("/v1/auth/me")
def auth_me(user: User | None = Depends(auth_optional)) -> dict:
    if user is None:
        raise HTTPException(status_code=401, detail="chưa đăng nhập")
    return {"user_id": user.id, "email": user.email, "role": user.role,
            "credits": user.credits, "is_admin": user.is_admin}


# ---------------------------------------------------------------- Day 6: admin


@app.get("/admin", response_class=HTMLResponse)
def admin_page(request: Request, db: Session = Depends(get_db)):
    """Settings UI — chỉ Admin đã đăng nhập (phiên cookie)."""
    if not A.admin_exists(db):
        return _redirect("/setup")
    user = A.auth_optional(request, None, db)
    if user is None:
        return _redirect("/login?next=/admin")
    if not user.is_admin:
        return _redirect("/")
    return ADMIN_HTML


@app.get("/", response_class=HTMLResponse)
def app_page(request: Request, db: Session = Depends(get_db)):
    """Giao diện người dùng — Dub / TTS / Voices / Jobs.

    Chỉ trả HTML khi đã có phiên hợp lệ (cổng ở SERVER, không phải JS).
    AGPL-3.0 §13: liên kết "Mã nguồn" phải trỏ tới bản mã nguồn tương ứng đang chạy.
    Đọc từ Settings (`app.source_url`) để self-host đổi được mà không sửa code.
    """
    if not A.admin_exists(db):
        return _redirect("/setup")
    if A.auth_optional(request, None, db) is None:
        return _redirect("/login")
    return _render(APP_HTML, request)


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
    # Khoá mang tiền tố chủ sở hữu -> /media tự kiểm tra được quyền mà không cần
    # bảng phụ; đồng thời ghi sổ `media_objects` để tra cứu khi khoá không có tiền tố.
    safe_name = os.path.basename(file.filename or "upload.bin")[:120] or "upload.bin"
    key = f"media/{user.id}/{_secrets.token_hex(6)}/{safe_name}"
    get_storage().put(key, data)
    db.add(MediaObject(key=key, user_id=user.id))
    db.commit()
    return {"media_key": key, "size": len(data), "filename": safe_name}


def _owns_media(db: Session, user: User, key: str) -> bool:
    """User có quyền đọc storage key này không?

    Ba họ khoá cần phủ: upload của người dùng (`media/…`, có sổ `media_objects`),
    kết quả job (`jobs/…` -> `jobs.result_s3_key`), clip giọng (`voices/…` ->
    `voices.ref_s3_key`). Admin đọc được tất cả.
    """
    if user.is_admin:
        return True
    # Khoá dạng mới có sẵn user id ở đoạn thứ hai -> khỏi tốn query.
    parts = key.split("/")
    if len(parts) >= 2 and parts[0] == "media" and parts[1] == user.id:
        return True
    if db.scalar(select(MediaObject).where(MediaObject.key == key,
                                           MediaObject.user_id == user.id)):
        return True
    if db.scalar(select(Job).where(Job.result_s3_key == key,
                                   Job.user_id == user.id)):
        return True
    return db.scalar(select(Voice).where(Voice.ref_s3_key == key,
                                        Voice.user_id == user.id)) is not None


@app.get("/media/{key:path}")
def serve_media(key: str, request: Request, response: Response,
                api_key: str = "", db: Session = Depends(get_db)) -> FileResponse:
    """Serve media — cookie phiên (trình duyệt) hoặc `?api_key=` (thẻ media/curl).

    Vá lỗ hổng: trước đây chỉ cần MỘT credential hợp lệ bất kỳ là đọc được media của
    người khác, và API key đã thu hồi vẫn dùng được (không kiểm `active`). Giờ đi qua
    đúng `user_from_api_key` (có kiểm `active`) rồi kiểm tra quyền sở hữu.
    """
    query_key = (api_key or "").strip()
    user = A.user_from_api_key(db, query_key, rate_limit=False) if query_key else None
    if user is None:
        user = A.auth_optional(request, None, db)
    if user is None:
        raise HTTPException(status_code=401, detail="cần đăng nhập hoặc api_key hợp lệ")

    if not _owns_media(db, user, key):
        # 404 chứ không 403: không xác nhận sự tồn tại của file cho người không có quyền.
        raise HTTPException(status_code=404, detail="not found")

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


# --------------------------------------------------- Phase 2: đăng ký & người dùng


class SignupIn(BaseModel):
    email: str
    password: str | None = None


@app.post("/v1/auth/signup", status_code=201)
def signup(body: SignupIn, request: Request,
           db: Session = Depends(get_db)) -> dict:
    """Đăng ký công khai — TẮT mặc định (`auth.allow_signup`).

    Hệ thống self-host mặc định chỉ Admin tạo được tài khoản: mở đăng ký công khai
    nghĩa là ai biết URL cũng tạo được tài khoản trong hệ thống của bạn. Ai muốn mở
    thì bật trong /admin/settings.
    """
    if not bool(get_setting("auth.allow_signup", False)):
        raise HTTPException(
            status_code=403,
            detail="đăng ký công khai đang tắt — liên hệ quản trị viên để được cấp tài khoản")
    ip = A._client_ip(request)
    if not _check_rate(f"signup:{ip}", 5):
        raise HTTPException(status_code=429, detail="too many signups, retry later")
    email = body.email.strip().lower()
    if not _valid_email(email):
        raise HTTPException(status_code=422, detail="email không hợp lệ")
    if db.scalar(select(User).where(User.email == email)):
        raise HTTPException(status_code=409, detail="email already registered")
    pw_hash = None
    if body.password:
        problem = password_problem(body.password)
        if problem:
            raise HTTPException(status_code=422, detail=problem)
        pw_hash = hash_password(body.password)
    u = User(email=email, role=ROLE_USER, password_hash=pw_hash)  # không bao giờ admin
    db.add(u)
    db.flush()
    raw = "yv_" + _secrets.token_hex(16)
    db.add(ApiKey(key=_hash_key(raw), prefix=raw[:12], user_id=u.id))
    db.commit()
    return {"user_id": u.id, "email": email, "role": u.role, "credits": u.credits,
            "key": raw, "note": "store it now — shown once"}


# -------------------------------------------------- Phase 2: quản lý người dùng


class CreateUserIn(BaseModel):
    email: str
    password: str
    role: str = ROLE_USER
    credits: int | None = None


class ResetPasswordIn(BaseModel):
    password: str


class CreditsIn(BaseModel):
    delta: int
    reason: str | None = None


def _admin_count(db: Session) -> int:
    return int(db.scalar(select(func.count()).select_from(User)
                         .where(User.role == ROLE_ADMIN, User.is_active.is_(True))) or 0)


def _user_out(u: User) -> dict:
    return {"user_id": u.id, "email": u.email, "role": u.role,
            "is_active": u.is_active, "credits": u.credits,
            "has_password": bool(u.password_hash),
            "created_at": u.created_at, "last_login_at": u.last_login_at}


@app.get("/v1/admin/users")
def admin_list_users(_: User | None = Depends(admin_auth),
                     db: Session = Depends(get_db)) -> dict:
    rows = db.scalars(select(User).order_by(User.created_at.desc())).all()
    return {"users": [_user_out(u) for u in rows]}


@app.post("/v1/admin/users", status_code=201)
def admin_create_user(body: CreateUserIn, _: User | None = Depends(admin_auth),
                      db: Session = Depends(get_db)) -> dict:
    """Admin tạo tài khoản cho người khác (đường tạo user chính khi signup đóng)."""
    email = body.email.strip().lower()
    if not _valid_email(email):
        raise HTTPException(status_code=422, detail="email không hợp lệ")
    problem = password_problem(body.password)
    if problem:
        raise HTTPException(status_code=422, detail=problem)
    if body.role not in (ROLE_USER, ROLE_ADMIN):
        raise HTTPException(status_code=422, detail=f"role phải là {ROLE_USER} hoặc {ROLE_ADMIN}")
    if db.scalar(select(User).where(User.email == email)):
        raise HTTPException(status_code=409, detail="email đã tồn tại")
    credits = FREE_CREDITS if body.credits is None else int(body.credits)
    u = User(email=email, role=body.role, password_hash=hash_password(body.password),
             credits=credits)
    db.add(u)
    db.flush()
    if credits:
        db.add(CreditLedger(user_id=u.id, delta=credits, reason="grant:signup"))
    db.commit()
    return _user_out(u)


def _get_user_or_404(db: Session, user_id: str) -> User:
    u = db.get(User, user_id)
    if u is None:
        raise HTTPException(status_code=404, detail="user not found")
    return u


def _guard_last_admin(db: Session, target: User) -> None:
    """Không cho tự khoá/hạ quyền admin cuối cùng — nếu không, hệ thống mất quyền quản trị."""
    if target.is_admin and target.is_active and _admin_count(db) <= 1:
        raise HTTPException(status_code=409,
                            detail="đây là quản trị viên duy nhất — không thể khoá hoặc hạ quyền")


@app.post("/v1/admin/users/{user_id}/reset-password")
def admin_reset_password(user_id: str, body: ResetPasswordIn,
                         _: User | None = Depends(admin_auth),
                         db: Session = Depends(get_db)) -> dict:
    u = _get_user_or_404(db, user_id)
    problem = password_problem(body.password)
    if problem:
        raise HTTPException(status_code=422, detail=problem)
    u.password_hash = hash_password(body.password)
    revoked = A.revoke_user_sessions(db, u.id)  # đổi mật khẩu -> đá mọi phiên cũ ra
    db.commit()
    return {"user_id": u.id, "sessions_revoked": revoked}


@app.post("/v1/admin/users/{user_id}/credits")
def admin_grant_credits(user_id: str, body: CreditsIn,
                        _: User | None = Depends(admin_auth),
                        db: Session = Depends(get_db)) -> dict:
    """Cấp/trừ credit. Luôn ghi `credit_ledger` — không bao giờ sửa số dư mà thiếu vết."""
    u = _get_user_or_404(db, user_id)
    new_balance = u.credits + int(body.delta)
    if new_balance < 0:
        raise HTTPException(status_code=422,
                            detail=f"không thể trừ quá số dư ({u.credits} credits)")
    u.credits = new_balance
    db.add(CreditLedger(user_id=u.id, delta=int(body.delta),
                        reason=(body.reason or "grant:admin")))
    db.commit()
    return {"user_id": u.id, "credits": u.credits, "delta": int(body.delta)}


@app.post("/v1/admin/users/{user_id}/deactivate")
def admin_deactivate_user(user_id: str, _: User | None = Depends(admin_auth),
                          db: Session = Depends(get_db)) -> dict:
    u = _get_user_or_404(db, user_id)
    _guard_last_admin(db, u)
    u.is_active = False
    revoked = A.revoke_user_sessions(db, u.id)
    keys = db.scalars(select(ApiKey).where(ApiKey.user_id == u.id)).all()
    for k in keys:
        k.active = False  # khoá tài khoản thì API key cũng phải chết
    db.commit()
    return {"user_id": u.id, "is_active": False,
            "sessions_revoked": revoked, "keys_disabled": len(keys)}


@app.post("/v1/admin/users/{user_id}/activate")
def admin_activate_user(user_id: str, _: User | None = Depends(admin_auth),
                        db: Session = Depends(get_db)) -> dict:
    u = _get_user_or_404(db, user_id)
    u.is_active = True
    db.commit()
    return {"user_id": u.id, "is_active": True,
            "note": "API key đã bị khoá trước đó cần được cấp lại"}
