"""Mật khẩu người dùng — băm bằng `hashlib.scrypt` (stdlib, có sẵn).

VÌ SAO scrypt của stdlib thay vì bcrypt/argon2-cffi:
  - **Không thêm dependency nào.** Image Docker `api` cài đúng `requirements-api.txt`
    trên `python:3.12-slim`; bcrypt/argon2 là wheel native (C/Rust) → thêm bước build
    và rủi ro vỡ wheel, trong khi scrypt đã có trong CPython (kể cả khi build thiếu
    OpenSSL — CPython kèm bản scrypt nội bộ).
  - scrypt là hàm **memory-hard** (RFC 7914), được thiết kế đúng cho việc lưu mật khẩu
    — mạnh hơn PBKDF2, tương đương bcrypt/argon2 trong mô hình đe doạ này.
  - `cryptography` (đã là dependency) không cấp API băm mật khẩu, nên không có lý do
    "đằng nào cũng ship native code" để chuyển sang argon2.

Tham số: N=2^14 (16 MiB, ~40–60ms trên máy để bàn), r=8, p=1, dklen=64.
Định dạng lưu:  scrypt$<N>$<r>$<p>$<salt_b64>$<hash_b64>   (~140 ký tự, < String(255))
  - base64url không padding → không có '$' trong giá trị, tách chuỗi an toàn.
  - tham số nằm TRONG chuỗi nên đổi tham số sau này vẫn verify được hash cũ;
    `needs_rehash()` phát hiện hash cũ để nâng cấp ngay lúc đăng nhập thành công.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import secrets

SCRYPT_N = 2 ** 14
SCRYPT_R = 8
SCRYPT_P = 1
SCRYPT_DKLEN = 64
SALT_BYTES = 16

_PREFIX = "scrypt"
MIN_PASSWORD_LEN = 8

# Hash giả để đăng nhập với email KHÔNG tồn tại vẫn tốn đúng thời gian như email
# có thật → không lộ danh sách email đã đăng ký qua chênh lệch thời gian phản hồi.
_DUMMY_HASH = ""  # sinh trễ ở lần dùng đầu (tránh tốn 50ms lúc import)


def _b64e(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def _b64d(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(SALT_BYTES)
    dk = hashlib.scrypt(password.encode(), salt=salt, n=SCRYPT_N, r=SCRYPT_R,
                        p=SCRYPT_P, dklen=SCRYPT_DKLEN)
    return f"{_PREFIX}${SCRYPT_N}${SCRYPT_R}${SCRYPT_P}${_b64e(salt)}${_b64e(dk)}"


def verify_password(password: str, stored: str | None) -> bool:
    """False khi hash trống/hỏng — KHÔNG raise, để caller trả lỗi đăng nhập chung."""
    if not stored:
        return False
    try:
        prefix, n, r, p, salt_b64, hash_b64 = stored.split("$")
        if prefix != _PREFIX:
            return False
        dk = hashlib.scrypt(password.encode(), salt=_b64d(salt_b64),
                            n=int(n), r=int(r), p=int(p), dklen=len(_b64d(hash_b64)))
    except (ValueError, TypeError, MemoryError):
        return False
    return hmac.compare_digest(dk, _b64d(hash_b64))


def needs_rehash(stored: str | None) -> bool:
    """True nếu hash dùng tham số khác hiện tại (hoặc không đọc được) → nâng cấp."""
    if not stored:
        return False
    try:
        prefix, n, r, p, _salt, _hash = stored.split("$")
    except ValueError:
        return True
    if prefix != _PREFIX:
        return True
    return (int(n), int(r), int(p)) != (SCRYPT_N, SCRYPT_R, SCRYPT_P)


def dummy_verify(password: str) -> None:
    """Chạy một lần băm vô ích để cân bằng thời gian khi email không tồn tại."""
    global _DUMMY_HASH
    if not _DUMMY_HASH:
        _DUMMY_HASH = hash_password("dummy-password-for-timing")
    verify_password(password, _DUMMY_HASH)


def password_problem(password: str) -> str | None:
    """Trả thông báo lỗi (tiếng Việt) nếu mật khẩu không đạt, None nếu hợp lệ."""
    if not password or len(password) < MIN_PASSWORD_LEN:
        return f"Mật khẩu phải có ít nhất {MIN_PASSWORD_LEN} ký tự"
    if len(password) > 200:
        return "Mật khẩu quá dài (tối đa 200 ký tự)"
    return None