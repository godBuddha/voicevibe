"""Day 6 selftest — Settings service + admin API + keys management.

Verifies:
  1. Secret settings are ENCRYPTED at rest (raw DB value is a Fernet token)
  2. Masking on read (•••• + last 4)
  3. Env fallback when DB has no entry; registry defaults
  4. Admin API: list (masked), PUT, DELETE, 401 on bad key
  5. Translate backend pick driven by Settings (cloud via settings, else local)
  6. API keys management: create / list masked / revoke -> 401

Run:  cd backend && PYTHONPATH=. python tests/test_settings.py
"""
from __future__ import annotations

import os
import pathlib
import sqlite3

os.environ["DATABASE_URL"] = "sqlite:///./voicevibe_test_settings.db"
os.environ.pop("VOICEVIBE_API_KEYS", None)
os.environ.pop("VOICEVIBE_ADMIN_KEY", None)
pathlib.Path("voicevibe_test_settings.db").unlink(missing_ok=True)

from app.db import Base, SessionLocal, engine  # noqa: E402
from app import models  # noqa: E402

Base.metadata.create_all(engine)

from app.settings_service import (  # noqa: E402
    delete_setting,
    get_setting,
    list_settings,
    mask,
    set_setting,
)

# 1) secret round-trip + encryption at rest
set_setting("hf_token", "hf_super_secret_value")
assert get_setting("hf_token") == "hf_super_secret_value"
raw = sqlite3.connect("voicevibe_test_settings.db").execute(
    "select value from settings where key='hf_token'").fetchone()[0]
assert "hf_super_secret_value" not in raw, "SECRET STORED IN PLAINTEXT!"
assert raw.startswith("gAAAA"), raw[:20]  # Fernet token prefix
print("secret encrypted at rest .. OK")

# 2) masking
assert mask("hf_super_secret_value") == "••••alue"
assert mask("abc") == "••••"
assert mask(None) is None
print("masking ................... OK")

# 3) plain setting + registry default + caller default
set_setting("max_speed", 1.4)
assert get_setting("max_speed") == 1.4
assert get_setting("no.such.key", "fallback") == "fallback"
assert get_setting("pricing.dub") == 60
print("defaults + custom get ..... OK")

# 4) env fallback when DB empty
os.environ["TRANSLATE_BASE_URL"] = "http://env-fallback/v1"
assert get_setting("translate.base_url", env_fallback="TRANSLATE_BASE_URL") == "http://env-fallback/v1"
os.environ.pop("TRANSLATE_BASE_URL")
print("env fallback .............. OK")

# 5) delete -> falls back to registry default
assert delete_setting("max_speed") is True
assert get_setting("max_speed") == 1.35
print("delete -> default ......... OK")

# 6) admin API
set_setting("admin.api_key", "adm-key-123")
from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402

c = TestClient(app)
AH = {"X-Admin-Key": "adm-key-123"}
assert c.get("/v1/admin/settings", headers={"X-Admin-Key": "wrong"}).status_code == 401
r = c.get("/v1/admin/settings", headers=AH)
assert r.status_code == 200
items = {s["key"]: s for s in r.json()["settings"]}
assert items["hf_token"]["value"].startswith("••••")
assert items["hf_token"]["is_secret"] is True
assert items["hf_token"]["set_in_db"] is True
assert items["pricing.dub"]["value"] == 60

r = c.put("/v1/admin/settings/translate.model", headers=AH, json={"value": "deepseek-chat"})
assert r.status_code == 200
assert get_setting("translate.model") == "deepseek-chat"
r = c.delete("/v1/admin/settings/translate.model", headers=AH)
assert r.status_code == 200 and r.json()["deleted"] is True
assert get_setting("translate.model") is None
print("admin API CRUD ............ OK")

# 7) translate backend pick driven by Settings
from app.pipelines.translate import _pick_backend  # noqa: E402

set_setting("translate.base_url", "http://mock/v1")
set_setting("translate.api_key", "k")
set_setting("translate.model", "m")
assert _pick_backend("vi", "en") == "cloud"
set_setting("translate.backend", "local")
assert _pick_backend("vi", "en") == "local"  # explicit local overrides cloud
set_setting("translate.backend", "auto")
delete_setting("translate.base_url")
delete_setting("translate.api_key")
delete_setting("translate.model")
assert _pick_backend("vi", "en") == "local"
print("translate via settings .... OK")

# 8) keys management
import hashlib

with SessionLocal() as db:
    from app.models import ApiKey, User

    u = User(email="d6-admin@local")
    db.add(u)
    db.flush()
    db.add(ApiKey(key=hashlib.sha256(b"d6-test-key").hexdigest(),
                  prefix="d6-test-key"[:12], user_id=u.id))
    db.commit()

KH = {"X-API-Key": "d6-test-key"}
r = c.post("/v1/keys", headers=KH)
assert r.status_code == 201
new_key = r.json()["key"]
assert new_key.startswith("vv_")
r = c.get("/v1/keys", headers=KH)
# list shows the masked PREFIX (only a SHA-256 hash of the raw key is stored)
assert any(k["key"] == "••••" + new_key[:12][-4:] for k in r.json()["keys"])
r = c.delete(f"/v1/keys/{new_key}", headers=KH)
assert r.status_code == 200
assert c.get("/v1/me", headers={"X-API-Key": new_key}).status_code == 401
print("keys management ........... OK")

# 9) rate limit
import time as _time

import app.main as _m  # noqa: E402

_RATE = _m._RATE
_RATE.clear()
_RATE["rl-test"] = [_time.time()] * 60  # full window of RECENT hits
assert _m._check_rate("rl-test", 60) is False
_RATE.clear()
assert _m._check_rate("rl-test", 60) is True
print("rate limiter .............. OK")

print("DAY 6 SELFTEST PASSED")
