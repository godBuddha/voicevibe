"""Migration guard — thêm cột vào DB ĐÃ CÓ, không Alembic.

Vì sao cần: mọi deployment đã chạy (và file SQLite dev) đều có bảng `users` từ trước
Phase 2. `create_all` **không** thêm cột vào bảng đã tồn tại, nên nếu bước migrate
hỏng thì app chết ở query đầu tiên — mà chỉ trên máy đã cài, không phải trên CI với
DB trắng. Test này dựng đúng tình huống đó:

  1. Tạo bảng `users` **hình dạng cũ** bằng SQL thô + một row dữ liệu thật
  2. Chạy `ensure_schema` → cột mới xuất hiện, row cũ được backfill, bảng mới có mặt
  3. Chạy lại `ensure_schema` → không làm gì (idempotent)
  4. Dữ liệu cũ không mất, không đổi (credits/email giữ nguyên)

Run:  cd backend && PYTHONPATH=. python tests/test_migrations.py
"""
from __future__ import annotations

import os
import pathlib
import sqlite3
import sys
import tempfile

WORK = pathlib.Path(tempfile.mkdtemp(prefix="yv_mig_"))
DB = WORK / "legacy.db"

# Bảng users + api_keys + settings HÌNH DẠNG CŨ (trước Phase 2), có sẵn index.
con = sqlite3.connect(DB)
con.executescript(
    """
    CREATE TABLE users (
        id VARCHAR(12) PRIMARY KEY,
        email VARCHAR(255) UNIQUE,
        credits INTEGER,
        created_at BIGINT
    );
    CREATE INDEX ix_users_email ON users (email);
    CREATE TABLE api_keys (
        key VARCHAR(64) PRIMARY KEY,
        user_id VARCHAR(12),
        active BOOLEAN,
        rate_limit_per_min INTEGER,
        created_at BIGINT
    );
    CREATE INDEX ix_api_keys_user_id ON api_keys (user_id);
    """
)
con.execute("INSERT INTO users (id, email, credits, created_at) "
            "VALUES (?, ?, ?, ?)", ("olduser1", "cu@local", 12_345, 1_700_000_000))
con.execute("INSERT INTO api_keys (key, user_id, active, rate_limit_per_min, created_at) "
            "VALUES (?, ?, ?, ?, ?)", ("deadbeef", "olduser1", 1, 60, 1_700_000_000))
con.commit()
con.close()

os.environ["DATABASE_URL"] = f"sqlite:///{DB}"
os.environ["MEDIA_ROOT"] = str(WORK / "media")

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from sqlalchemy import create_engine as _create_engine  # noqa: E402
from sqlalchemy import inspect, text  # noqa: E402

from app.db import Base, engine  # noqa: E402
from app.migrations import ensure_schema  # noqa: E402

insp = inspect(engine)
before_tables = set(insp.get_table_names())
before_cols = {c["name"] for c in insp.get_columns("users")}
assert before_cols == {"id", "email", "credits", "created_at"}, before_cols
assert "password_hash" not in before_cols, "DB test chưa phải hình dạng cũ!"

# 1) migrate
actions = ensure_schema(engine)
assert actions, "ensure_schema không làm gì trên DB cũ — migration hỏng"

insp = inspect(engine)
cols = {c["name"] for c in insp.get_columns("users")}
added = cols - before_cols
assert added == {"password_hash", "role", "is_active", "last_login_at", "updated_at"}, added
print(f"thêm cột users ({len(added)}) ............... OK")

# 2) bảng mới của Phase 2 có mặt (create_all cũng tạo các bảng khác còn thiếu —
#    DB test chỉ có users+api_keys, nên đó là hành vi đúng, không phải lỗi)
new_tables = set(insp.get_table_names()) - before_tables
need = {"sessions", "system_flags", "media_objects"}
assert need <= new_tables, f"thiếu bảng Phase 2: {need - new_tables}"
print(f"tạo bảng mới {sorted(need)} ... OK")

# 3) cột api_keys.prefix (Phase 2 thêm cho key đã băm) cũng được thêm
api_cols = {c["name"] for c in insp.get_columns("api_keys")}
assert "prefix" in api_cols, api_cols
print("thêm cột api_keys.prefix ................ OK")

# 4) backfill: row cũ nhận role='user', is_active=1, password_hash NULL
with engine.connect() as conn:
    row = conn.execute(text(
        "SELECT id, email, credits, role, is_active, password_hash, updated_at "
        "FROM users WHERE id = 'olduser1'")).one()
assert row.email == "cu@local", row
assert row.credits == 12_345, "backfill đã làm hỏng dữ liệu cũ!"
assert row.role == "user", f"role không được backfill: {row.role!r}"
assert row.is_active in (1, True), row.is_active
assert row.password_hash is None, "password_hash phải NULL cho user cũ"
assert row.updated_at is not None, "updated_at phải được backfill"
print("backfill row cũ (role/is_active) ......... OK")
print("dữ liệu cũ giữ nguyên (credits/email) .... OK")

# 5) idempotent: chạy lần hai không đổi gì
again = ensure_schema(engine)
assert again == [], f"ensure_schema không idempotent: {again}"
print("idempotent (chạy lần 2 = no-op) .......... OK")

# 6) FK/unique vẫn ổn: tạo được session trỏ tới user cũ
with engine.begin() as conn:
    conn.execute(text(
        "INSERT INTO sessions (token_hash, user_id, expires_at, last_seen_at, created_at) "
        "VALUES ('h1', 'olduser1', 9999999999, 1700000000, 1700000000)"))
    got = conn.execute(text(
        "SELECT user_id FROM sessions WHERE token_hash = 'h1'")).scalar()
assert got == "olduser1", got
print("session dùng được row user cũ ............ OK")

# 7) HỒI QUY: cột trùng TỪ KHOÁ SQL.
# `stage_models.order` là từ khoá dành riêng của SQL. Bản đầu tiên nội suy định danh
# trần, nên `ALTER TABLE stage_models ALTER COLUMN order SET NOT NULL` là lỗi cú pháp
# — Postgres báo `syntax error at or near "order"` và app CHẾT lúc khởi động, vì
# ensure_schema chạy trước khi phục vụ request.
#
# Vì sao lọt qua test cũ: bảng `stage_models` trên DB mới do `create_all` tạo sẵn
# nên KHÔNG đi qua đường ADD COLUMN, còn nhánh SET NOT NULL thì chỉ chạy trên
# Postgres. Nay dựng một bảng `stage_models` **hình dạng cũ** (thiếu cột `order`) để
# buộc đường đó phải chạy — và nó hỏng trên cả SQLite lẫn Postgres nếu thiếu trích dẫn.
tbl = Base.metadata.tables["stage_models"]
colexpr = tbl.c["order"].type.compile(dialect=engine.dialect)


def _old_shape_conn():
    """DB riêng (file khác) để không đụng DB của các ca trên."""
    e = _create_engine(f"sqlite:///{tempfile.mkdtemp(prefix='yvmig_order_')}/old.db")
    with e.begin() as c:
        # thiếu hẳn cột `order` -> ensure_schema phải ADD COLUMN nó
        c.execute(text(
            "CREATE TABLE stage_models ("
            "  id INTEGER PRIMARY KEY, stage VARCHAR(16) NOT NULL,"
            "  provider_id INTEGER, model VARCHAR(128) NOT NULL,"
            "  params JSON)"))
        c.execute(text(
            "INSERT INTO stage_models (id, stage, model) "
            "VALUES (1, 'translate', 'm1')"))
    return e


old = _old_shape_conn()
acts = ensure_schema(old)
assert any("stage_models.order" in a for a in acts), acts
print("thêm cột trùng từ khoá (order) ........... OK")
# Dữ liệu cũ giữ nguyên; cột mới được BACKFILL theo default của model (`order` mặc
# định 0 = lựa chọn chính), đúng như thiết kế `_backfill_literal`.
with old.begin() as conn:
    row = conn.execute(text(
        'SELECT stage, model, "order" FROM stage_models WHERE id = 1')).fetchone()
assert row is not None and row[0] == "translate" and row[1] == "m1", row
assert row[2] == 0, f"cột mới phải backfill theo default (0), nhận {row[2]!r}"
print("row cũ sống sót sau ADD COLUMN ........... OK")
# idempotent trên DB đó
assert ensure_schema(old) == [], "ensure_schema không idempotent với bảng cũ"
print("idempotent trên bảng hình dạng cũ ........ OK")

print("MIGRATION GUARD PASSED")