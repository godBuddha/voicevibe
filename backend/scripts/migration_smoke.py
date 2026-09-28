"""Kiểm chứng migration + fallback trên DB hình dạng CŨ (trước Phase 2/3).

Đây chính là rủi ro mà Phase 3 mang lại: pipeline dịch giờ đọc cấu hình công đoạn
từ DB (`stage_models` / `ai_providers`). Một deployment đang chạy có DB CHƯA có
hai bảng đó — nếu `stage_translator()` ném lỗi thì cả pipeline dubbing chết.

Script dựng đúng DB cũ đó rồi khẳng định:
  1. `stage_translator()` trả None (KHÔNG raise) khi bảng còn thiếu
  2. `build_translator()` rơi về đường cũ, không chết
  3. `ensure_schema()` thêm cột/bảng mới mà KHÔNG mất row nào, và backfill `role`
  4. `ensure_schema()` idempotent (chạy lại nhiều lần vô hại)
  5. sau migrate + gán công đoạn, `stage_translator()` dùng được cấu hình mới

Chạy trên box GPU:
  cd /workspace/yupvox-clone && source .venv/bin/activate
  cd backend && PYTHONPATH=. python scripts/migration_smoke.py
"""
from __future__ import annotations

import os
import pathlib
import sqlite3
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

tmp = pathlib.Path(tempfile.mkdtemp(prefix="yvmig_"))
db = tmp / "old.db"

# --- DB hình dạng CŨ: users thiếu mọi cột Phase 2, chưa có bảng AI nào
con = sqlite3.connect(db)
con.executescript(
    """
    CREATE TABLE users (id INTEGER PRIMARY KEY, email VARCHAR(255), credits INTEGER DEFAULT 0);
    INSERT INTO users (id, email, credits) VALUES (1, 'old@user', 42);
    CREATE TABLE api_keys (id INTEGER PRIMARY KEY, user_id INTEGER, key VARCHAR(64));
    INSERT INTO api_keys (id, user_id, key) VALUES (1, 1, 'abc');
    """
)
con.commit()
con.close()
before = sqlite3.connect(db).execute("SELECT count(*) FROM users").fetchone()[0]

os.environ["DATABASE_URL"] = f"sqlite:///{db}"

from app.db import SessionLocal, engine  # noqa: E402
from app.migrations import ensure_schema  # noqa: E402
from app.pipelines.translate import build_translator, stage_translator  # noqa: E402

# (1) Trước khi migrate: phải trả None, tuyệt đối không được ném lỗi.
st = stage_translator("vi", "en")
print(f"1. stage_translator trên DB chưa migrate: {st!r} "
      f"-> {'OK' if st is None else 'SAI'}")
assert st is None, "DB chưa migrate KHÔNG được làm chết stage_translator"

# (2) build_translator phải rơi về đường cũ (opus-mt local) mà không chết.
t = build_translator("vi", "en")
print(f"2. build_translator rơi về đường cũ: {type(t).__name__}")
assert "Marian" in type(t).__name__ or "Cloud" in type(t).__name__

# (3) Migrate thật.
ensure_schema(engine)
con = sqlite3.connect(db)
cols = {r[1] for r in con.execute("PRAGMA table_info(users)")}
tables = {r[0] for r in con.execute(
    "SELECT name FROM sqlite_master WHERE type='table'")}
rows = con.execute("SELECT count(*) FROM users").fetchone()[0]
role = con.execute("SELECT role FROM users WHERE id=1").fetchone()[0]
keys = con.execute("SELECT count(*) FROM api_keys").fetchone()[0]
con.close()

new_cols = sorted(cols & {"password_hash", "role", "is_active", "last_login_at",
                          "updated_at"})
new_tabs = sorted(tables & {"sessions", "system_flags", "media_objects",
                            "ai_providers", "stage_models", "prompts"})
print(f"3. cột mới của users: {new_cols}")
print(f"4. bảng mới: {new_tabs}")
print(f"5. row cũ còn nguyên: {before} -> {rows} | api_keys = {keys} | "
      f"role backfill = {role!r}")
assert rows == before == 1, "migration làm mất row!"
assert keys == 1, "migration làm mất api_keys!"
assert role == "user", f"backfill role sai: {role!r}"
assert len(new_cols) == 5 and len(new_tabs) == 6

# (6) Idempotent.
ensure_schema(engine)
ensure_schema(engine)
print("6. chạy ensure_schema thêm 2 lần: OK (idempotent)")

# (7) Sau migrate + gán công đoạn -> cấu hình mới phải được dùng.
from app.models import AiProvider, StageModel  # noqa: E402
from app.providers_api import _encrypt  # noqa: E402

with SessionLocal() as s:
    p = AiProvider(name="Fake", kind="openai", base_url="https://api.example.com/v1",
                   api_key_enc=_encrypt("sk-x"), api_key_hint="••••sk-x")
    s.add(p)
    s.flush()
    s.add(StageModel(stage="translate", provider_id=p.id, model="m1", order=0))
    s.commit()

st = stage_translator("vi", "en")
# `CloudChatTranslator` bọc một provider OpenAI-compatible; base_url/model nằm trên
# provider đó, không phải trên lớp bọc. Đọc qua `_chat` — chấp nhận được trong
# smoke script, và điều cần khẳng định là cấu hình công đoạn ĐÃ được dùng.
chat = st._chat
print(f"7. sau migrate + gán công đoạn: {type(st).__name__} | "
      f"model = {chat.model} | base_url = {chat.base_url}")
assert st is not None and chat.model == "m1"
assert chat.base_url == "https://api.example.com/v1", chat.base_url

print("\nMIGRATION + FALLBACK SMOKE: PASS")