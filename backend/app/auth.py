"""Xác thực & phân quyền — phiên cookie cho web, X-API-Key cho máy gọi.

HAI ĐƯỜNG, MỘT CHỮ KÝ:
  - **Cookie phiên** (`vv_session`) cho trình duyệt — đăng nhập bằng email/mật khẩu.
  - **X-API-Key** cho script/SDK/CI — không đổi so với trước.
Cả hai đều trả về cùng một `User`, nên **mọi endpoint `Depends(auth)` hiện có không
phải sửa một dòng nào** (13 chỗ).

Vì sao header API key phải khai `Header(None, ...)`: request chỉ-có-cookie không gửi
header đó; nếu để bắt buộc thì FastAPI trả 422 trước cả khi ta kịp đọc cookie. Chuỗi
rỗng cũng coi như không có — trình duyệt/JS dễ gửi `X-API-Key: ""`.

PHIÊN: token thô `secrets.token_urlsafe(32)` chỉ tồn tại trong cookie; DB giữ SHA-256
(cùng triết lý với API key — dump DB không dùng lại được). TTL tuyệt đối 14 ngày, gia
hạn trượt khi đã idle > 24 giờ (tránh một lượt ghi DB mỗi request).

CSRF: `SameSite=Lax` đã chặn POST/PUT/DELETE cross-site (Lax không gửi cookie cho
request khác site, trừ điều hướng GET cấp cao nhất). Thêm lớp hai: request **đã xác
thực bằng cookie** mà có `Origin` khác host thì chặn 403. Client dùng API key/curl
không bị ảnh hưởng vì không đi qua nhánh cookie.
"""
from __future__ import annotations

import hashlib
import os
import secrets
import time
from urllib.parse import urlparse

from fastapi import Depends, Header, HTTPException, Request, Response
from sqlalchemy import select
from sqlalchemy.orm import Session as OrmSession

from .db import get_db
from .models import ApiKey, ROLE_ADMIN, Session, SystemFlag, User, _now
from .ratelimit import check_rate
from .security import dummy_verify, verify_password

COOKIE_NAME = "vv_session"
SESSION_TTL = 14 * 24 * 3600      # tuyệt đối: 14 ngày
SESSION_RENEW_AFTER = 24 * 3600   # gia hạn trượt nếu idle quá 24h
SETUP_FLAG = "setup.completed"

# Dev API keys: CHỈ để tiện phát triển trên máy cá nhân.
# Bỏ default (trước đây là "dev-key-1") vì đó là backdoor luôn mở ở production,
# và nhánh này còn bị vô hiệu hoàn toàn khi đã có admin (xem `user_from_api_key`).
DEV_KEYS = set(filter(None, (k.strip() for k in os.getenv("VOICEVIBE_API_KEYS", "").split(","))))


# ------------------------------------------------------------------ mật khẩu
def hash_key(raw: str) -> str:
    """SHA-256 hex — dùng cho cả API key và token phiên (không lưu giá trị thô)."""
    return hashlib.sha256(raw.encode()).hexdigest()


# ------------------------------------------------------------------- cookie
def cookie_secure(request: Request) -> bool:
    """Cookie Secure? Ưu tiên biến môi trường, rồi scheme, rồi X-Forwarded-Proto.

    Cần cả header proxy vì app thường đứng sau Caddy/nginx/Cloudflare Tunnel: lúc đó
    `request.url.scheme` là http dù người dùng đang ở https, và cookie thiếu Secure
    sẽ bị trình duyệt coi là không an toàn.
    """
    forced = os.getenv("VOICEVIBE_SECURE_COOKIES")
    if forced is not None:
        return forced == "1"
    if request.url.scheme == "https":
        return True
    proto = request.headers.get("x-forwarded-proto", "").split(",")[0].strip().lower()
    return proto == "https"


def _client_ip(request: Request) -> str:
    fwd = request.headers.get("x-forwarded-for", "").split(",")[0].strip()
    return fwd or (request.client.host if request.client else "unknown")


def set_session_cookie(response: Response, token: str, request: Request) -> None:
    response.set_cookie(
        COOKIE_NAME, token,
        max_age=SESSION_TTL, httponly=True, samesite="lax", path="/",
        secure=cookie_secure(request),
    )


def clear_session_cookie(response: Response, request: Request) -> None:
    response.delete_cookie(COOKIE_NAME, path="/", httponly=True,
                           samesite="lax", secure=cookie_secure(request))


# -------------------------------------------------------------------- phiên
def create_session(db: OrmSession, user: User, request: Request) -> str:
    """Tạo phiên mới, trả token THÔ để nhét vào cookie."""
    token = secrets.token_urlsafe(32)
    now = _now()
    db.add(Session(
        token_hash=hash_key(token), user_id=user.id,
        created_at=now, expires_at=now + SESSION_TTL, last_seen_at=now,
        ip=_client_ip(request)[:64],
        user_agent=(request.headers.get("user-agent") or "")[:255],
    ))
    return token


def resolve_session(db: OrmSession, token: str | None) -> User | None:
    """Cookie -> User, kèm kiểm tra hết hạn và gia hạn trượt."""
    if not token:
        return None
    row = db.get(Session, hash_key(token))
    if row is None:
        return None
    now = _now()
    if row.expires_at <= now:
        db.delete(row)  # dọn luôn, không để rác
        db.commit()
        return None
    user = db.get(User, row.user_id)
    if user is None or not user.is_active:
        return None
    if now - row.last_seen_at > SESSION_RENEW_AFTER:
        row.last_seen_at = now
        row.expires_at = now + SESSION_TTL
        db.commit()
    return user


def revoke_session(db: OrmSession, token: str | None) -> None:
    if not token:
        return
    row = db.get(Session, hash_key(token))
    if row is not None:
        db.delete(row)
        db.commit()


def revoke_user_sessions(db: OrmSession, user_id: str) -> int:
    """Thu hồi mọi phiên của một user — dùng khi đổi mật khẩu / khoá tài khoản."""
    rows = db.scalars(select(Session).where(Session.user_id == user_id)).all()
    for row in rows:
        db.delete(row)
    return len(rows)


def purge_expired_sessions(db: OrmSession) -> int:
    rows = db.scalars(select(Session).where(Session.expires_at <= _now())).all()
    for row in rows:
        db.delete(row)
    return len(rows)


# ------------------------------------------------------------- trạng thái hệ thống
def admin_exists(db: OrmSession) -> bool:
    """Đã có tài khoản quản trị chưa? Quyết định hệ thống ở chế độ /setup hay /login."""
    return db.scalar(select(User).where(User.role == ROLE_ADMIN)) is not None


def setup_completed(db: OrmSession) -> bool:
    return db.get(SystemFlag, SETUP_FLAG) is not None


def claim_setup(db: OrmSession) -> bool:
    """Giành quyền khởi tạo hệ thống — TRUE nếu thắng.

    Khoá chính unique của `system_flags` là chốt nguyên tử: hai người cùng mở /setup
    và cùng bấm thì chỉ một INSERT thành công, người kia nhận IntegrityError.
    """
    from sqlalchemy.exc import IntegrityError, OperationalError

    try:
        db.add(SystemFlag(key=SETUP_FLAG, value=str(_now())))
        db.flush()
        return True
    except (IntegrityError, OperationalError):
        db.rollback()
        return False


# --------------------------------------------------------------- xác thực
def user_from_api_key(db: OrmSession, raw: str | None,
                      *, rate_limit: bool = True) -> User | None:
    """X-API-Key -> User. Trả None nếu sai/đã thu hồi (không raise)."""
    if not raw:
        return None
    key = db.scalar(select(ApiKey).where(ApiKey.key == hash_key(raw),
                                         ApiKey.active.is_(True)))
    if key is not None:
        user = db.get(User, key.user_id)
        if user is not None and user.is_active:
            if rate_limit and not check_rate(f"key:{key.key}", key.rate_limit_per_min):
                raise HTTPException(status_code=429, detail="rate limit exceeded")
            return user

    # Dev key: chỉ khi CHƯA có admin. Sau /setup, "dev-key-1" chết dù env còn sót —
    # nếu không, một biến môi trường cũ sẽ là cửa hậu vĩnh viễn ở production.
    if raw in DEV_KEYS and not admin_exists(db):
        user = db.scalar(select(User).where(User.email == "dev@local"))
        if user is None:
            user = User(email="dev@local")
            db.add(user)
            db.commit()
            db.refresh(user)
        if rate_limit and not check_rate(f"user:{user.id}", 120):
            raise HTTPException(status_code=429, detail="rate limit exceeded")
        return user
    return None


def _check_csrf(request: Request) -> None:
    """Chặn CSRF cho request đã xác thực bằng cookie (lớp hai sau SameSite=Lax).

    Cross-origin ĐƯỢC PHÉP nếu origin nằm trong `VOICEVIBE_CORS_ORIGINS`: đó là
    danh sách admin chủ động cho phép (lớp CORS đã gate trình duyệt ở trên),
    vector CSRF thật là trang NGOÀI danh sách. Trước đây deploy tách frontend
    (SPA 8080 → API 18080) bị 403 toàn bộ POST/PUT/DELETE dù CORS đã bật — origin
    lệch cổng so với Host là tình trạng bình thường của kiến trúc đó (đã gặp thật
    khi dò UI: nút "Tạo" nào cũng "HTTP 403").
    """
    origin = request.headers.get("origin")
    if not origin:
        return  # curl/SDK/API-key: không có Origin, không phải vector CSRF
    host = request.headers.get("host") or urlparse(str(request.url)).netloc
    if urlparse(origin).netloc == host:
        return
    # Cùng quy ước phân tích với parse_cors_origins (main.py): cắt `/` cuối để
    # `https://x.com/` và `https://x.com` là một origin.
    allowed = {o.strip().rstrip("/") for o in os.getenv("VOICEVIBE_CORS_ORIGINS", "").split(",") if o.strip()}
    if origin.rstrip("/") in allowed:
        return
    raise HTTPException(status_code=403, detail="cross-origin request blocked")


def auth_optional(
    request: Request,
    x_api_key: str | None = Header(None, alias="X-API-Key"),
    db: OrmSession = Depends(get_db),
) -> User | None:
    """Danh tính hiện tại, hoặc None. Dùng cho trang cần biết 'đã đăng nhập chưa'."""
    api_key = (x_api_key or "").strip()
    if api_key:
        user = user_from_api_key(db, api_key)
        if user is not None:
            return user

    token = request.cookies.get(COOKIE_NAME)
    user = resolve_session(db, token)
    if user is not None:
        if request.method not in ("GET", "HEAD", "OPTIONS"):
            _check_csrf(request)
        # Cookie phiên cũng có hạn mức riêng, chống một tab lỗi spam hàng nghìn request.
        if not check_rate(f"session:{hash_key(token or '')[:16]}", 240):
            raise HTTPException(status_code=429, detail="rate limit exceeded")
    return user


def auth(
    user: User | None = Depends(auth_optional),
) -> User:
    """Dependency của mọi endpoint cần đăng nhập — giữ nguyên chữ ký `-> User`."""
    if user is None:
        raise HTTPException(status_code=401, detail="cần đăng nhập (cookie phiên hoặc X-API-Key)")
    return user


def current_admin(
    request: Request,
    x_admin_key: str | None = Header(None, alias="X-Admin-Key"),
    db: OrmSession = Depends(get_db),
) -> User | None:
    """Quyền quản trị: phiên có role=admin, HOẶC X-Admin-Key nếu được cấu hình.

    Header admin key giờ **chỉ hoạt động khi `admin.api_key` được đặt tường minh** —
    bỏ default `admin-dev-key` để không còn backdoor ở bản cài mới. Trả `None` khi
    vào bằng key (không có User tương ứng); caller không dùng giá trị này.
    """
    key = (x_admin_key or "").strip()
    if key:
        from .settings_service import get_setting

        expected = str(get_setting("admin.api_key", "") or "")
        if expected and secrets.compare_digest(key, expected):
            return None
        raise HTTPException(status_code=401, detail="invalid admin key")

    user = auth_optional(request, None, db)
    if user is None:
        raise HTTPException(status_code=401, detail="cần đăng nhập")
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="cần quyền quản trị")
    return user


# ------------------------------------------------------------------ đăng nhập
def authenticate(db: OrmSession, email: str, password: str) -> User | None:
    """Xác thực email/mật khẩu. Luôn tốn thời gian như nhau dù email có tồn tại hay không."""
    user = db.scalar(select(User).where(User.email == email.strip().lower()))
    if user is None or not user.password_hash:
        dummy_verify(password)  # cân bằng thời gian -> không lộ email nào đã đăng ký
        return None
    if not verify_password(password, user.password_hash):
        return None
    if not user.is_active:
        return None
    return user


def mark_login(db: OrmSession, user: User, password: str) -> None:
    """Cập nhật last_login + tự nâng cấp hash nếu tham số scrypt đã đổi."""
    from .security import hash_password, needs_rehash

    user.last_login_at = _now()
    if needs_rehash(user.password_hash):
        user.password_hash = hash_password(password)
    db.commit()


def check_login_rate(email: str, ip: str) -> bool:
    """Chống dò mật khẩu: theo IP và theo tài khoản (hai cửa sổ khác nhau)."""
    if not check_rate(f"login:ip:{ip}", 10, window=60):
        return False
    # Băm email trước khi dùng làm khoá: không để email thật nằm trong bộ nhớ khoá.
    return check_rate(f"login:acct:{hash_key(email.strip().lower())[:16]}", 20, window=900)