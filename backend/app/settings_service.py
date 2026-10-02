"""Day 6: DB-backed settings with encrypted secrets — NO hardcoded config.

Bootstrap secrets that MUST stay in env (unavoidable at boot):
  DATABASE_URL, SETTINGS_MASTER_KEY (encrypts secret settings at rest)

Everything else — API keys, provider endpoints, model configs, feature
flags — lives in the `settings` table, edited via the admin UI.
Env vars act as dev fallback ONLY when the DB has no entry for a key.

Selftest: tests/test_settings.py
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import time

from cryptography.fernet import Fernet

from .db import SessionLocal
from .models import Setting

_CACHE: dict = {}
_CACHE_TS = 0.0
_TTL = 5.0  # seconds

# The registry the admin UI renders. env = dev fallback key name.
SETTING_DEFS: list[dict] = [
    # AGPL-3.0 §13: app chạy qua mạng phải chỉ đường lấy mã nguồn. Self-host bản
    # sửa thì ĐỔI giá trị này sang kho của bạn — đó là nghĩa vụ giấy phép.
    {"key": "app.source_url", "category": "general", "secret": False,
     "label": "Liên kết mã nguồn (AGPL-3.0 §13)",
     "default": "https://github.com/godBuddha/voicevibe"},
    {"key": "hf_token", "category": "credentials", "secret": True,
     "label": "Hugging Face token (pyannote gated)", "env": "HF_TOKEN"},
    {"key": "translate.backend", "category": "translation", "secret": False,
     "label": "Backend: auto | cloud | local", "default": "auto"},
    {"key": "translate.base_url", "category": "translation", "secret": False,
     "label": "OpenAI-compatible base URL", "env": "TRANSLATE_BASE_URL"},
    {"key": "translate.api_key", "category": "translation", "secret": True,
     "label": "Translation API key", "env": "TRANSLATE_API_KEY"},
    {"key": "translate.model", "category": "translation", "secret": False,
     "label": "Translation model name", "env": "TRANSLATE_MODEL"},
    {"key": "media_root", "category": "storage", "secret": False,
     "label": "Media storage root (Local mode)", "env": "MEDIA_ROOT",
     "default": "./media"},
    {"key": "max_speed", "category": "dubbing", "secret": False,
     "label": "Max speech tempo before re-translate", "default": 1.35},
    {"key": "auth.allow_signup", "category": "security", "secret": False,
     "label": "Cho phép đăng ký công khai", "default": False},
    {"key": "admin.api_key", "category": "security", "secret": True,
     "label": "Admin API key (để trống = tắt đường key, chỉ dùng phiên đăng nhập)",
     "env": "VOICEVIBE_ADMIN_KEY", "default": ""},
    {"key": "webhook.secret", "category": "security", "secret": True,
     "label": "Webhook HMAC secret (X-VoiceVibe-Signature)", "default": ""},
    # B1 — nhập từ URL (yt-dlp). cookies_file là ĐƯỜNG DẪN file cookies.txt
    # định dạng Netscape do operator mount vào container (ví dụ
    # /run/secrets/youtube-cookies.txt) — NỘI DUNG cookie mới là secret, đường
    # dẫn không phải. proxy có thể chứa user:pass → secret thật.
    {"key": "download.cookies_file", "category": "download", "secret": False,
     "label": "File cookies.txt (Netscape) cho link cần đăng nhập — để trống = tắt",
     "default": ""},
    {"key": "download.proxy", "category": "download", "secret": True,
     "label": "Proxy cho yt-dlp (http/socks5, có thể chứa user:pass)",
     "default": ""},
]


def _fernet() -> Fernet:
    key = os.getenv("SETTINGS_MASTER_KEY")
    if not key:
        # DEV fallback: stable key derived from DATABASE_URL.
        # Set SETTINGS_MASTER_KEY in production — documented in README.
        seed = os.getenv("DATABASE_URL", "dev").encode()
        key = base64.urlsafe_b64encode(hashlib.sha256(seed).digest())
    return Fernet(key)


def _encode(value, is_secret: bool) -> str:
    raw = json.dumps(value)
    if is_secret:
        return _fernet().encrypt(raw.encode()).decode()
    return raw


def _decode(row: Setting):
    raw = row.value
    if row.is_secret:
        raw = _fernet().decrypt(raw.encode()).decode()
    return json.loads(raw)


def _reload() -> None:
    global _CACHE_TS
    _CACHE.clear()
    try:
        with SessionLocal() as db:
            rows = db.query(Setting).all()
        for r in rows:
            try:
                _CACHE[r.key] = _decode(r)
            except Exception:  # corrupt/undecryptable — surface as missing
                pass
    except Exception:  # table missing on a fresh DB — treat as empty
        pass
    _CACHE_TS = time.time()


def _maybe_reload() -> None:
    if time.time() - _CACHE_TS > _TTL:
        _reload()


def get_setting(key: str, default=None, env_fallback: str | None = None):
    """DB value -> env fallback -> registry default -> caller default."""
    _maybe_reload()
    if key in _CACHE and _CACHE[key] is not None:
        return _CACHE[key]
    if env_fallback and os.getenv(env_fallback):
        return os.getenv(env_fallback)
    d = next((d for d in SETTING_DEFS if d["key"] == key), None)
    if d and "default" in d:
        return d["default"]
    return default


def set_setting(key: str, value, is_secret: bool | None = None,
                category: str | None = None) -> None:
    d = next((d for d in SETTING_DEFS if d["key"] == key), None)
    if is_secret is None:
        is_secret = bool(d and d.get("secret"))
    if category is None:
        category = d["category"] if d else "custom"
    with SessionLocal() as db:
        row = db.get(Setting, key)
        if row is None:
            db.add(Setting(key=key, value=_encode(value, is_secret),
                           is_secret=is_secret, category=category))
        else:
            row.value = _encode(value, is_secret)
            row.is_secret = is_secret
            row.category = category
            row.updated_at = int(time.time())
        db.commit()
    global _CACHE_TS  # noqa: F811 — invalidate cache (bugfix: was a local var)
    _CACHE_TS = 0.0  # force reload on next read


def delete_setting(key: str) -> bool:
    with SessionLocal() as db:
        row = db.get(Setting, key)
        if row is None:
            return False
        db.delete(row)
        db.commit()
    global _CACHE_TS  # noqa: F811 — invalidate cache
    _CACHE_TS = 0.0
    return True


def mask(value) -> str | None:
    if value is None:
        return None
    s = str(value)
    if len(s) <= 4:
        return "••••"
    return "••••" + s[-4:]


def list_settings() -> list[dict]:
    _maybe_reload()
    out = []
    defs = {d["key"]: d for d in SETTING_DEFS}
    for d in SETTING_DEFS:
        k = d["key"]
        if k in _CACHE and _CACHE[k] is not None:
            v, src = _CACHE[k], "db"
        elif d.get("env") and os.getenv(d["env"]):
            v, src = os.getenv(d["env"]), "env"
        elif "default" in d:
            v, src = d["default"], "default"
        else:
            v, src = None, "unset"
        out.append({
            "key": k, "label": d["label"], "category": d["category"],
            "is_secret": bool(d.get("secret")),
            "value": mask(v) if d.get("secret") else v,
            "source": src, "set_in_db": k in _CACHE and _CACHE[k] is not None,
        })
    for k, v in _CACHE.items():  # custom keys added via the UI
        if k not in defs and v is not None:
            out.append({"key": k, "label": k, "category": "custom",
                        "is_secret": False, "value": v,
                        "source": "db", "set_in_db": True})
    return out
