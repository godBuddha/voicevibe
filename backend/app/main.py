"""
VoiceVibe API.

Persistence: Postgres (prod) / SQLite (dev) + Celery dispatch.
Feature surface (mirrors sản phẩm gốc — xem README):
  jobs:    tts | stt | translate | dub | subtitle   (async — self-host, miễn phí)
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
    Job,
    JobStatus,
    MediaObject,
    PromptLibrary,
    ROLE_ADMIN,
    ROLE_USER,
    User,
    Voice,
)
from .pipelines.subtitle import FORMATS as SUBTITLE_FORMATS
from .pipelines.download import QUALITIES as _DOWNLOAD_QUALITIES
from .pipelines.download import validate_url as _download_validate_url
from .prompt_library import router as prompt_library_router
from .prompts import seed_prompts
from .providers_api import router as ai_admin_router
from .settings_api import router as settings_hub_router
from .audit import log_action as _audit
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

VALID_TYPES = {"tts", "stt", "translate", "dub", "subtitle", "download", "render"}

# Docs công khai mặc định TẮT: schema API lộ toàn bộ bề mặt tấn công. Bật khi cần
# xem Swagger trên máy cá nhân: VOICEVIBE_ENABLE_DOCS=1
_DOCS = os.getenv("VOICEVIBE_ENABLE_DOCS") == "1"

app = FastAPI(
    title="VoiceVibe API",
    version="0.3.0",
    description="Open-source AI voice/dubbing platform — self-hosted, AGPL-3.0.",
    docs_url="/docs" if _DOCS else None,
    redoc_url="/redoc" if _DOCS else None,
    openapi_url="/openapi.json" if _DOCS else None,
)


def parse_cors_origins(raw: str) -> list[str]:
    """Danh sách origin được phép gọi API từ BẤT KỲ nguồn nào khác (tách frontend).

    Đầu vào: nội dung env `VOICEVIBE_CORS_ORIGINS` — phân tách bằng dấu phẩy, ví dụ
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


_CORS_ORIGINS = parse_cors_origins(os.getenv("VOICEVIBE_CORS_ORIGINS", ""))
if _CORS_ORIGINS:
    add_cors(app, _CORS_ORIGINS)

# Auto-migration: tạo bảng thiếu + THÊM CỘT thiếu vào bảng đã tồn tại (create_all một
# mình không làm được việc sau). Idempotent — xem app/migrations.py.
ensure_schema(_engine)

# Prompt hệ thống: tạo row cho các task còn thiếu để nút "Khôi phục mặc định" luôn có đích.
seed_prompts()

# Nhóm endpoint quản trị AI (nhà cung cấp / công đoạn / prompt) — xem app/providers_api.py
app.include_router(ai_admin_router)
app.include_router(prompt_library_router)
# Settings Hub (hồ sơ/mật khẩu/phiên cá nhân + audit/overview/system/export-import)
app.include_router(settings_hub_router)


def _hash_key(raw: str) -> str:
    """API keys are stored hashed — a DB dump exposes no usable keys."""
    return A.hash_key(raw)


# Tên cũ giữ nguyên để 13 endpoint `Depends(auth)` không phải sửa: giờ `auth` chấp
# nhận cookie phiên HOẶC X-API-Key nhưng vẫn trả về `User` như trước.
auth = A.auth
auth_optional = A.auth_optional
admin_auth = A.current_admin


class JobIn(BaseModel):
    type: str = Field(..., description="tts | stt | translate | dub | subtitle")
    media_url: str | None = None
    text: str | None = None
    source_lang: str | None = None
    target_lang: str | None = None
    voice_id: str | None = None
    prompt_id: str | None = Field(
        None, description="translate: id prompt cá nhân (thư viện prompt) thay system prompt")
    max_speed: float = 1.35
    webhook_url: str | None = None
    # --- riêng cho type=dub
    # Hai field này UI GỬI, nhưng JobIn trước đây không khai báo → pydantic ÂM
    # THẦM bỏ đi (đã gặp thật): background_mode thì pipeline luôn chạy "silence"
    # bất kể dropdown; speaker_voices thì mọi speaker bị xoay vòng preset, giọng
    # người dùng chọn không bao giờ được dùng. Khai báo tường minh để worker
    # nhận đủ.
    background_mode: str = Field(
        "silence", description="silence | source_low (nhạc nền kiểu karaoke)")
    speaker_voices: dict[str, str] | None = Field(
        None,
        description='dub: map SPEAKER_xx (hoặc "*" = áp cho mọi người nói) '
                    '→ tên giọng preset/clone')
    # --- riêng cho type=subtitle
    format: str = Field("srt", description="srt | vtt | ass (chỉ dùng cho subtitle)")
    bilingual: bool = Field(
        False, description="phụ đề 2 dòng: bản gốc trên, bản dịch dưới "
                           "(cần target_lang)")
    show_speaker: bool = Field(True, description="ghi nhãn người nói vào phụ đề")
    # --- riêng cho type=download (B1: nhập từ URL, yt-dlp) + các job media dán link
    # KHAI TƯỜNG MINH — bài học pydantic: field không khai là bị ÂM THẦM bỏ đi
    # (background_mode/speaker_voices từng vậy). UI gửi source_url phải tới worker.
    source_url: str | None = Field(
        None, description="link video/âm thanh (dán link) — tải bằng yt-dlp")
    quality: str = Field(
        "1080", description="download: 1080 | 720 | 480 | audio")
    sub_source: str = Field(
        "auto", description="dán link YouTube — auto (mặc định): lấy phụ đề "
                            "sẵn có nếu video có, không thì tự nghe lại; "
                            "youtube: chỉ phụ đề YouTube; whisper: luôn nghe lại")
    tts_backend: str = Field(
        "local", description="B5: engine giọng đọc — local (VieNeu, mặc định) | "
                             "edge (Microsoft miễn phí qua mạng) | cloud "
                             "(model gán trong Model Hub)")
    # --- riêng cho type=render (B3+B4: burn phụ đề + dọc 9:16 + banner)
    subtitle_key: str | None = Field(
        None, description="render: storage key file phụ đề (.srt/.vtt/.ass)")
    subtitle_job_id: str | None = Field(
        None, description="render: job subtitle/dub đã xong — lấy file phụ đề "
                          "từ kết quả của job đó")
    burn_subtitles: bool = Field(
        False, description="render: in phụ đề vào video (ASS 2 style song ngữ)")
    vertical: bool = Field(
        False, description="render: cắt dọc 9:16 (720×1280, Shorts/TikTok)")
    banner: dict | None = Field(
        None, description="render: banner tiêu đề — {'major': 'Chính', "
                          "'minor': 'Phụ'} (dải đen 250px phía trên)")
    with_subs: bool = Field(
        False, description="dub (B4b): xuất thêm phụ đề song ngữ bilingual.srt "
                           "kèm video — tái dùng được cho job render")


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
    if job.type in ("dub", "stt", "subtitle"):
        # B1: job media nhận CẢ upload (media_url) lẫn dán link (source_url)
        if not job.media_url and not job.source_url:
            raise HTTPException(
                status_code=422,
                detail=f"type {job.type} cần file upload (media_url) hoặc "
                       "link (source_url)")
    if job.sub_source not in ("auto", "youtube", "whisper"):
        raise HTTPException(
            status_code=422,
            detail="sub_source phải là auto | youtube | whisper")
    if job.tts_backend not in ("local", "edge", "cloud"):
        raise HTTPException(
            status_code=422,
            detail="tts_backend phải là local | edge | cloud")
    if job.source_url:
        # B1: dán link thì validate LUÔN ở MỌI type (download/dub/stt/subtitle)
        # — link xấu phải bị chặn lúc tạo job, không phải để worker fail.
        try:
            job.source_url = _download_validate_url(job.source_url)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
    if job.type == "subtitle":
        # Kiểm cấu hình TRƯỚC khi tạo job — cùng nguyên tắc với quyền sở hữu voice
        # bên dưới: cấu hình sai phải bị chặn lúc tạo job, không phải để worker fail.
        if job.format not in SUBTITLE_FORMATS:
            raise HTTPException(
                status_code=422,
                detail=f"format phải là một trong {list(SUBTITLE_FORMATS)}")
        if job.bilingual and not job.target_lang:
            raise HTTPException(
                status_code=422,
                detail="bilingual cần target_lang (bản dịch lấy gì?)")
    if job.type == "download":
        # Kiểm cấu hình TRƯỚC khi tạo job — job lỗi phải bị chặn lúc tạo, không
        # phải để worker fail rồi user chờ vô ích.
        if not job.source_url:
            raise HTTPException(status_code=422,
                                detail="download cần source_url (link video)")
        if job.quality not in _DOWNLOAD_QUALITIES:
            raise HTTPException(
                status_code=422,
                detail=f"quality phải là một trong {list(_DOWNLOAD_QUALITIES)}")
    if job.type == "render":
        # B3+B4: ít nhất 1 toggle; burn phụ đề cần NGUỒN (key XOR job id)
        if not (job.burn_subtitles or job.vertical or job.banner):
            raise HTTPException(
                status_code=422,
                detail="render cần ít nhất một lựa chọn: burn phụ đề / cắt dọc "
                       "9:16 / banner tiêu đề")
        if job.burn_subtitles and not (job.subtitle_key or job.subtitle_job_id):
            raise HTTPException(
                status_code=422,
                detail="burn phụ đề cần subtitle_key (file) hoặc subtitle_job_id "
                       "(job phụ đề đã xong)")
        if job.subtitle_key and job.subtitle_job_id:
            raise HTTPException(
                status_code=422,
                detail="chỉ chọn MỘT nguồn phụ đề: subtitle_key hoặc "
                       "subtitle_job_id")

    # Quyền sở hữu voice phải kiểm tra TRƯỚC khi tạo job. Trước đây chỉ worker
    # kiểm tra (tasks.py), tức là job đã tạo rồi mới fail trong pipeline. Giữ
    # kiểm tra ở worker làm lớp hai.
    if job.voice_id:
        voice = db.get(Voice, job.voice_id)
        if voice is None or voice.user_id != user.id:
            raise HTTPException(status_code=404, detail="voice not found")

    # Quyền sở hữu prompt cá nhân — cùng nguyên tắc voice: chặn TRƯỚC khi tạo
    # job thay vì để worker fail. Dùng cho translate (từng câu) và dub (A3, thay
    # system prompt của bộ dịch batch); type khác + prompt_id → 422.
    if job.prompt_id:
        if job.type not in ("translate", "dub"):
            raise HTTPException(
                status_code=422,
                detail="prompt_id chỉ dùng cho job translate hoặc dub")
        prompt = db.get(PromptLibrary, job.prompt_id)
        if prompt is None or prompt.user_id != user.id:
            raise HTTPException(status_code=404, detail="prompt not found")

    j = Job(user_id=user.id, type=job.type, params=job.model_dump(exclude_none=True))
    db.add(j)
    # flush cần thiết: Job.id do Python sinh (_uid) nhưng chỉ được gán lúc flush —
    # dispatch(j.id) bên dưới cần giá trị thật.
    db.flush()
    db.commit()
    mode, task_id = dispatch(j.id, j.params)
    # task_id để HỦY được sau này — lưu ngay cả khi dispatch inline (None).
    j.task_id = task_id
    db.commit()
    return {"job_id": j.id, "status": j.status.value, "dispatch": mode}


@app.get("/v1/jobs/{job_id}")
def get_job(
    job_id: str, user: User = Depends(auth), db: Session = Depends(get_db)
) -> dict:
    j = db.get(Job, job_id)
    if j is None or j.user_id != user.id:
        raise HTTPException(status_code=404, detail="job not found")
    # params + updated_at: UI cần hiển thị "file nào / text nào" và mốc hoàn thành
    # — không có hai field này panel chi tiết chỉ ra N/A vĩnh viễn.
    return {
        "job_id": j.id, "type": j.type, "status": j.status.value,
        "progress": j.progress, "error": j.error,
        "params": j.params, "updated_at": j.updated_at,
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
    key = j.result_s3_key
    ext = key.rsplit(".", 1)[-1].lower() if "." in key else ""
    kind = ("text" if ext in {"srt", "vtt", "ass", "txt"}
            else "video" if ext in {"mp4", "mkv", "webm", "mov"} else "audio")
    out = {"job_id": j.id, "download_url": f"/media/{key}",
           "filename": os.path.basename(key), "kind": kind}
    # Kết quả dạng chữ (SRT/TXT) gửi kèm nội dung để UI không phải tải lần 2 —
    # chặn 64KB để endpoint không trở thành bơm-ram-vô-tận với kết quả khổng lồ.
    if kind == "text":
        try:
            data = get_storage().get(key)
            if len(data) <= 64 * 1024:
                out["content"] = data.decode("utf-8", "replace")
        except Exception:
            pass  # đọc lỗi thì UI tự fallback sang download_url
    return out


@app.post("/v1/voices", status_code=201)
def create_voice(
    v: VoiceIn, user: User = Depends(auth), db: Session = Depends(get_db)
) -> dict:
    row = Voice(user_id=user.id, name=v.name, lang=v.lang,
                engine=v.engine, ref_s3_key=v.ref_s3_key)
    db.add(row)
    db.commit()
    return {"voice_id": row.id, "name": row.name, "engine": row.engine}


@app.get("/v1/voices")
def list_voices(user: User = Depends(auth), db: Session = Depends(get_db)) -> dict:
    """Danh sách giọng của CHÍNH mình — trang Voices + bộ chọn giọng TTS/Dub.

    Trước đây chỉ `GET /v1/me` trả voices kèm profile; SPA gọi `GET /v1/voices`
    và nhận 405 (route POST-only), nên danh sách giọng luôn trống (đã gặp thật
    khi dò UI: 405 Method Not Allowed × 2 trang).
    """
    rows = db.scalars(select(Voice).where(Voice.user_id == user.id)
                      .order_by(Voice.created_at.desc())).all()
    return {"voices": [{"id": v.id, "name": v.name, "lang": v.lang,
                        "engine": v.engine, "created_at": v.created_at}
                       for v in rows]}


@app.delete("/v1/voices/{voice_id}")
def delete_voice(voice_id: str, user: User = Depends(auth),
                 db: Session = Depends(get_db)) -> dict:
    """Xoá giọng + clip mẫu trên storage. Chỉ chủ sở hữu được xoá."""
    v = db.get(Voice, voice_id)
    if v is None or v.user_id != user.id:
        raise HTTPException(status_code=404, detail="voice not found")
    storage = get_storage()
    for key in (v.ref_s3_key, f"voices/{v.id}/ref_clean.wav"):
        # key "pending" (row tạo lỗi trước khi put) không có trên storage — bỏ qua.
        if key and key != "pending":
            try:
                storage.delete(key)
            except Exception:
                pass  # dọn file là best-effort; row DB phải chết chắc
    db.delete(v)
    db.commit()
    return {"voice_id": v.id, "deleted": True}


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
        "name": user.name,
        "role": user.role,
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
                last_login_at=int(time.time()))
    db.add(user)
    db.commit()
    db.refresh(user)
    token = A.create_session(db, user, request)
    db.commit()
    A.set_session_cookie(response, token, request)
    _audit("auth.setup", user_id=user.id, target=user.email,
           ip=A._client_ip(request))
    return {"user_id": user.id, "email": user.email, "role": user.role,
            "redirect": "/"}


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
        # Audit GHI THẬT email đã thử (target) — log dò mật khẩu là mục đích chính
        # của audit; dòng login_failed không tiết lộ gì cho kẻ dò (chỉ admin xem).
        _audit("auth.login_failed", target=email, ip=A._client_ip(request))
        raise HTTPException(status_code=401, detail="Email hoặc mật khẩu không đúng")
    A.mark_login(db, user, body.password)
    token = A.create_session(db, user, request)
    db.commit()
    A.set_session_cookie(response, token, request)
    _audit("auth.login", user_id=user.id, target=email, ip=A._client_ip(request))
    return {"user_id": user.id, "email": user.email, "role": user.role,
            "redirect": "/admin" if user.is_admin else "/"}


@app.post("/v1/auth/logout")
def logout(request: Request, response: Response,
           db: Session = Depends(get_db)) -> dict:
    token = request.cookies.get(A.COOKIE_NAME)
    # Xác định chủ phiên TRƯỚC khi xoá (xong là mất dấu để lấy user_id).
    owner_id = None
    if token:
        from .models import Session as DbSession
        row = db.get(DbSession, A.hash_key(token))
        owner_id = row.user_id if row else None
    A.revoke_session(db, token)
    A.clear_session_cookie(response, request)
    if owner_id:
        _audit("auth.logout", user_id=owner_id, ip=A._client_ip(request))
    return {"ok": True, "redirect": "/login"}


@app.get("/v1/auth/me")
def auth_me(user: User | None = Depends(auth_optional)) -> dict:
    if user is None:
        raise HTTPException(status_code=401, detail="chưa đăng nhập")
    return {"user_id": user.id, "email": user.email, "name": user.name,
            "role": user.role, "is_admin": user.is_admin}


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


class DownloadPreviewIn(BaseModel):
    url: str


@app.post("/v1/download/preview")
def download_preview(body: DownloadPreviewIn, user: User = Depends(auth),
                     db: Session = Depends(get_db)) -> dict:
    """B1 — xem metadata link TRƯỚC khi tạo job (UI hiện title/thumbnail).

    Chạy probe trong tiến trình API: socket-timeout 15s + timeout 60s cứng nên
    không treo worker; rate limit riêng để không bị dùng làm công cụ quét link.
    """
    if not _check_rate(f"dlpreview:{user.id}", 20):
        raise HTTPException(status_code=429,
                            detail="quá nhiều lần xem trước, vui lòng đợi")
    from .pipelines.download import probe
    from .settings_service import get_setting

    try:
        return probe(body.url,
                     cookies_file=get_setting("download.cookies_file") or None,
                     proxy=get_setting("download.proxy") or None)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.get("/v1/tts/presets")
def tts_presets(lang: str = "vi", user: User = Depends(auth)) -> dict:
    """B5 — catalog giọng đọc theo backend (dropdown TTS/Dub).

    edge: thử lấy danh sách thật từ Microsoft (cache 24h) — vắng mạng giữ
    catalog tĩnh trong code. Filter theo prefix ngôn ngữ (mặc định vi — hệ
    tiếng Việt; edge trả hàng trăm giọng, không lọc là dropdown vô dụng).
    """
    from .providers.tts_catalog import BACKENDS, PRESET_VOICES

    def _voice_out(v) -> dict:
        return {"code": v.code, "name": v.name, "language": v.language,
                "gender": v.gender, "kind": v.kind, "recommended": v.recommended}

    out: dict[str, list] = {}
    for b in BACKENDS:
        if b != "edge":
            out[b] = [_voice_out(v) for v in PRESET_VOICES[b]]
            continue
        voices: list = []
        try:
            from .providers.edge import EdgeTTSEngine

            for v in EdgeTTSEngine().list_voices():
                if v.language.lower().startswith((lang or "vi").lower()):
                    voices.append(v)
        except Exception:  # noqa: BLE001 — thiếu package/mạng: giữ catalog tĩnh
            voices = []
        out[b] = [_voice_out(v) for v in voices or PRESET_VOICES[b]]
    return {"backends": out}


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
    if db.scalar(select(Voice).where(Voice.ref_s3_key == key,
                                    Voice.user_id == user.id)) is not None:
        return True
    # B4b — HỌ KHOÁ `jobs/{job_id}/…`: output PHỤ (bilingual.srt, workdir) không
    # là result_s3_key của job nào → trước đây 404 ngay khi chủ job tự tải.
    # Đối chiếu CHỦ JOB của đoạn thứ hai — không phải chỉ cần tiền tố đúng là
    # đọc được (khác user cùng tiền tố phải 404). Khoá "jobs/" không có id thì
    # không thuộc họ này (bỏ qua, rơi về các khớp chính xác phía trên).
    if len(parts) >= 2 and parts[0] == "jobs" and parts[1]:
        job = db.get(Job, parts[1])
        if job is not None and job.user_id == user.id:
            return True
    return False


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
                      "error": j.error, "created_at": j.created_at,
                      "params": j.params, "updated_at": j.updated_at} for j in rows]}


def _own_job(job_id: str, user: User, db: Session) -> Job:
    """Fetch job + kiểm quyền sở hữu (chủ job hoặc admin) — dùng chung cho
    cancel/delete. IDOR đã là lớp bắt buộc ở mọi endpoint nhận id."""
    job = db.get(Job, job_id)
    if job is None or (job.user_id != user.id and user.role != "admin"):
        raise HTTPException(status_code=404, detail="job not found")
    return job


@app.post("/v1/jobs/{job_id}/cancel")
def cancel_job(job_id: str, user: User = Depends(auth),
               db: Session = Depends(get_db)) -> dict:
    """Hủy job đang chờ/đang chạy. Job miễn phí (self-host) — không trừ, không
    hoàn credit.

    - Hủy = gạch trên DB luôn (nhanh, chắc chắn đổi trạng thái) KÈM revoke
      task Celery theo task_id nếu có: đang chờ → bị vứt không bao giờ chạy;
      đang chạy → worker dừng giữa đường. Guard `_aborted` trong tasks.py
      chặn trường hợp task vẫn nhặt được sau hủy (requeue) — nó tự thoát mà
      không ghi đè trạng thái.
    - Job đã done/failed/cancelled → 409: không còn gì để hủy.
    """
    job = _own_job(job_id, user, db)
    if job.status in (JobStatus.done, JobStatus.failed, JobStatus.cancelled):
        raise HTTPException(status_code=409,
                            detail=f"job {job.status.value} rồi — không hủy được nữa")
    if job.task_id:
        try:
            from .tasks import celery_app
            # terminate=True: task đang chạy cũng bị dừng; task chờ → bị vứt.
            celery_app.control.revoke(job.task_id, terminate=True)
        except Exception:  # noqa: BLE001 — broker chết vẫn phải hủy được trên DB
            pass
    job.status = JobStatus.cancelled
    job.error = "Đã hủy bởi người dùng"
    job.progress = 100
    db.commit()
    _audit("job.cancel", user_id=user.id, target=job.id)
    return {"job_id": job.id, "status": "cancelled"}


@app.post("/v1/jobs/{job_id}/retry")
def retry_job(job_id: str, user: User = Depends(auth),
              db: Session = Depends(get_db)) -> dict:
    """Chạy lại job đã hỏng/đã hủy — TIẾP TỤC từ công đoạn đã xong (A1).

    Chỉ job failed/cancelled mới được chạy lại (queued/running → 409 — đang
    chạy; done → 409 — muốn làm lại thì tạo job mới). Giữ nguyên `params` +
    `result_s3_key`: kết quả cũ vẫn tải được tới khi lần chạy mới hoàn thành
    (endpoint /result chỉ trả khi done — không có cửa sổ bất nhất). Sổ tay
    công đoạn trong `media/jobs/{id}/work/` là thứ quyết định chạy lại từ đâu —
    endpoint này chỉ xếp hàng lại.
    """
    job = _own_job(job_id, user, db)
    if job.status == JobStatus.done:
        raise HTTPException(status_code=409,
                            detail="job đã xong — muốn làm lại hãy tạo job mới")
    if job.status in (JobStatus.queued, JobStatus.running):
        raise HTTPException(status_code=409,
                            detail="job đang chờ/chạy — hủy trước nếu muốn làm lại")
    job.status = JobStatus.queued
    job.progress = 0
    job.error = None
    db.commit()
    mode, task_id = dispatch(job.id, job.params)
    job.task_id = task_id
    db.commit()
    _audit("job.retry", user_id=user.id, target=job.id)
    return {"job_id": job.id, "status": "queued", "dispatch": mode}


@app.delete("/v1/jobs/{job_id}")
def delete_job(job_id: str, user: User = Depends(auth),
               db: Session = Depends(get_db)) -> dict:
    """Xóa job khỏi lịch sử (chỉ job đã kết thúc — đang chờ/chạy phải HỦY trước).

    Dọn SẠCH mọi file dưới tiền tố `jobs/<id>/` — kết quả + thư mục làm việc
    (sổ tay công đoạn, checkpoint). File TTS dùng chung (`jobs/tts/<hash>.wav`)
    KHÔNG đụng — có thể đang được job khác tham chiếu. Kết quả cũ của job dub
    legacy (`jobs/dub/<hash>…`, tạo trước khi có key_prefix) cũng được dọn
    best-effort — trước đây chúng để lại rác vĩnh viễn trên đĩa (bug thật).
    """
    job = _own_job(job_id, user, db)
    if job.status in (JobStatus.queued, JobStatus.running):
        raise HTTPException(status_code=409,
                            detail="job đang chờ/chạy — hãy HỦY trước khi xóa")
    key = job.result_s3_key
    storage = get_storage()
    try:
        storage.delete_prefix(f"jobs/{job_id}/")
    except Exception:  # noqa: BLE001 — lỗi dọn không chặn việc xóa row
        pass
    if key and not key.startswith(f"jobs/{job_id}/") and job.type == "dub":
        # Key dub legacy ngoài tiền tố (`jobs/dub/<hash>…` — tạo trước khi có
        # key_prefix): dọn riêng. CHỈ dub — file TTS dùng chung (`jobs/tts/…`)
        # có thể đang được job khác tham chiếu, xóa là gãy kết quả người khác.
        try:
            storage.delete(key)
        except Exception:  # noqa: BLE001
            pass
    db.delete(job)
    db.commit()
    _audit("job.delete", user_id=user.id, target=job_id)
    return {"deleted": job_id}


@app.get("/v1/usage")
def usage(user: User = Depends(auth), db: Session = Depends(get_db)) -> dict:
    """Số liệu THẬT cho donut dashboard — ĐẾM JOB theo loại/trạng thái.

    Self-host miễn phí nên không có đơn vị tiền tệ: thống kê = số job. Một query
    group_by(type, status) là đủ cho cả donut theo loại lẫn thẻ "đang chạy".
    """
    rows = db.execute(
        select(Job.type, Job.status, func.count())
        .where(Job.user_id == user.id)
        .group_by(Job.type, Job.status)
    ).all()
    by_type: dict[str, int] = {}
    by_status: dict[str, int] = {}
    for jtype, status, n in rows:
        by_type[jtype] = by_type.get(jtype, 0) + n
        key = status.value if hasattr(status, "value") else str(status)
        by_status[key] = by_status.get(key, 0) + n
    total = sum(by_type.values())
    return {"total_jobs": total, "by_type": by_type, "by_status": by_status,
            "running": by_status.get("running", 0)}


# Settings nằm trong gia đình /v1/admin/* — KHÔNG nằm ở /admin/settings:
# đường đó là route của SPA (gõ thẳng/F5 phải mở ứng dụng, không phải trả JSON
# qua proxy — đã gặp thật: trình duyệt hiển thị JSON thô thay vì app).
@app.get("/v1/admin/settings")
def admin_list(_: None = Depends(admin_auth)) -> dict:
    return {"settings": list_settings()}


@app.put("/v1/admin/settings/{key}")
def admin_set(key: str, body: dict, admin: User | None = Depends(admin_auth)) -> dict:
    value = body.get("value")
    if value is None or not isinstance(value, (str, int, float, bool)):
        raise HTTPException(status_code=422, detail='body must be {"value": str|number|bool}')
    d = next((d for d in SETTING_DEFS if d["key"] == key), None)
    is_secret = body.get("is_secret") if isinstance(body.get("is_secret"), bool) \
        else bool(d and d.get("secret"))
    set_setting(key, value, is_secret=is_secret,
                category=d["category"] if d else "custom")
    # detail KHÔNG bao giờ chứa giá trị secret — chỉ ghi kiểu dữ liệu.
    _audit("setting.set", user_id=admin.id if admin else None, target=key,
           detail=f"is_secret={is_secret}")
    return {"key": key, "ok": True}


@app.delete("/v1/admin/settings/{key}")
def admin_delete(key: str, admin: User | None = Depends(admin_auth)) -> dict:
    _audit("setting.delete", user_id=admin.id if admin else None, target=key)
    return {"key": key, "deleted": delete_setting(key)}


# ------------------------------------------------------- Day 6: API keys mgmt


@app.post("/v1/keys", status_code=201)
def create_api_key(user: User = Depends(auth), db: Session = Depends(get_db)) -> dict:
    raw = "vv_" + _secrets.token_hex(16)
    db.add(ApiKey(key=_hash_key(raw), prefix=raw[:12], user_id=user.id))
    db.commit()
    # Chỉ ghi PREFIX (12 ký tự hiển thị công khai) — raw key không bao giờ vào audit.
    _audit("key.create", user_id=user.id, target=raw[:12])
    return {"key": raw, "rate_limit_per_min": 60,
            "note": "store it now — shown once (only a SHA-256 hash is stored)"}


@app.get("/v1/keys")
def list_api_keys(user: User = Depends(auth), db: Session = Depends(get_db)) -> dict:
    keys = db.scalars(select(ApiKey).where(ApiKey.user_id == user.id)).all()
    # prefix (raw, không phải hash) KHÔNG phải secret — đã hiện qua "mask" từ trước.
    # Trả nguyên để UI thu hồi được khi người dùng không giữ raw key nữa.
    return {"keys": [{"key": mask(k.prefix), "prefix": k.prefix, "active": k.active,
                      "rate_limit_per_min": k.rate_limit_per_min,
                      "created_at": k.created_at} for k in keys]}


@app.delete("/v1/keys/{key}")
def revoke_api_key(key: str, user: User = Depends(auth),
                   db: Session = Depends(get_db)) -> dict:
    # Chấp nhận raw key (hình thức duy nhất client còn giữ) HOẶC prefix — UI chỉ
    # còn prefix sau khi đóng modal "hiện 1 lần". Lookup raw là hash; prefix thì
    # so trực tiếp, vẫn giới hạn trong key của chính user.
    row = db.get(ApiKey, _hash_key(key))
    if row is None or row.user_id != user.id:
        row = db.scalar(select(ApiKey).where(ApiKey.prefix == key,
                                             ApiKey.user_id == user.id))
    if row is None:
        raise HTTPException(status_code=404, detail="key not found")
    db.delete(row)
    db.commit()
    _audit("key.revoke", user_id=user.id, target=row.prefix)
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
    raw = "vv_" + _secrets.token_hex(16)
    db.add(ApiKey(key=_hash_key(raw), prefix=raw[:12], user_id=u.id))
    db.commit()
    _audit("auth.signup", user_id=u.id, target=email, ip=ip)
    return {"user_id": u.id, "email": email, "role": u.role,
            "key": raw, "note": "store it now — shown once"}


# -------------------------------------------------- Phase 2: quản lý người dùng


class CreateUserIn(BaseModel):
    email: str
    password: str
    role: str = ROLE_USER


class ResetPasswordIn(BaseModel):
    password: str


def _admin_count(db: Session) -> int:
    return int(db.scalar(select(func.count()).select_from(User)
                         .where(User.role == ROLE_ADMIN, User.is_active.is_(True))) or 0)


def _user_out(u: User) -> dict:
    return {"user_id": u.id, "email": u.email, "name": u.name, "role": u.role,
            "is_active": u.is_active,
            "has_password": bool(u.password_hash),
            "created_at": u.created_at, "last_login_at": u.last_login_at}


@app.get("/v1/admin/users")
def admin_list_users(_: User | None = Depends(admin_auth),
                     db: Session = Depends(get_db)) -> dict:
    rows = db.scalars(select(User).order_by(User.created_at.desc())).all()
    return {"users": [_user_out(u) for u in rows]}


@app.post("/v1/admin/users", status_code=201)
def admin_create_user(body: CreateUserIn, admin: User | None = Depends(admin_auth),
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
    u = User(email=email, role=body.role,
             password_hash=hash_password(body.password))
    db.add(u)
    db.commit()
    _audit("user.create", user_id=admin.id if admin else None, target=u.email)
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
                         admin: User | None = Depends(admin_auth),
                         db: Session = Depends(get_db)) -> dict:
    u = _get_user_or_404(db, user_id)
    problem = password_problem(body.password)
    if problem:
        raise HTTPException(status_code=422, detail=problem)
    u.password_hash = hash_password(body.password)
    revoked = A.revoke_user_sessions(db, u.id)  # đổi mật khẩu -> đá mọi phiên cũ ra
    db.commit()
    _audit("user.reset_password", user_id=admin.id if admin else None, target=u.email)
    return {"user_id": u.id, "sessions_revoked": revoked}


@app.post("/v1/admin/users/{user_id}/deactivate")
def admin_deactivate_user(user_id: str, admin: User | None = Depends(admin_auth),
                          db: Session = Depends(get_db)) -> dict:
    u = _get_user_or_404(db, user_id)
    _guard_last_admin(db, u)
    u.is_active = False
    revoked = A.revoke_user_sessions(db, u.id)
    keys = db.scalars(select(ApiKey).where(ApiKey.user_id == u.id)).all()
    for k in keys:
        k.active = False  # khoá tài khoản thì API key cũng phải chết
    db.commit()
    _audit("user.deactivate", user_id=admin.id if admin else None, target=u.email)
    return {"user_id": u.id, "is_active": False,
            "sessions_revoked": revoked, "keys_disabled": len(keys)}


@app.post("/v1/admin/users/{user_id}/activate")
def admin_activate_user(user_id: str, admin: User | None = Depends(admin_auth),
                        db: Session = Depends(get_db)) -> dict:
    u = _get_user_or_404(db, user_id)
    u.is_active = True
    db.commit()
    _audit("user.activate", user_id=admin.id if admin else None, target=u.email)
    return {"user_id": u.id, "is_active": True,
            "note": "API key đã bị khoá trước đó cần được cấp lại"}
