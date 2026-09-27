"""Thêm cột/bảng còn thiếu vào DB đang chạy — KHÔNG cần Alembic.

Vì sao cần: `Base.metadata.create_all()` chỉ tạo bảng **chưa tồn tại**; nó **không**
thêm cột vào bảng đã có. Mọi deployment đã chạy (và cả file SQLite dev của bạn) đều
có bảng `users` từ trước, nên khi Phase 2 thêm `password_hash`/`role`/... thì
`create_all` im lặng bỏ qua và app sẽ chết ở lần query đầu tiên.

Cách làm — dialect-neutral, chạy được cả SQLite lẫn Postgres:
  1. `create_all` trước: tạo `sessions`/`system_flags`/`media_objects` trên DB mới.
  2. So cột đang có (`inspect`) với cột đã khai báo trong model.
  3. `ALTER TABLE … ADD COLUMN` cho cột thiếu — **luôn nullable, không DEFAULT inline**.
     SQLite từ chối `ADD COLUMN … NOT NULL` không default trên bảng đã có dữ liệu, nên
     giữ mọi dialect giống nhau; ràng buộc NOT NULL do tầng ứng dụng đảm nhiệm
     (mọi chỗ tạo row đều set giá trị), riêng Postgres siết lại ở bước 5.
  4. `UPDATE` backfill theo `default` vô hướng của cột trong model.
  5. Tạo index còn thiếu (`checkfirst=True`). Trên Postgres, siết NOT NULL sau backfill.

Idempotent: chạy lại bao nhiêu lần cũng không đổi gì.
"""
from __future__ import annotations

import time

from sqlalchemy import BigInteger, Integer, inspect, text
from sqlalchemy.engine import Engine

from . import models  # noqa: F401 — BẮT BUỘC: đăng ký bảng vào Base.metadata.
# Không có dòng này, ai import `app.migrations` mà chưa import `app.models` sẽ thấy
# metadata RỖNG → ensure_schema im lặng không làm gì → app chết ở query đầu tiên.
from .db import Base


def _literal(value) -> str | None:
    """Chuyển default của model thành literal SQL, hoặc None nếu không backfill được."""
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, str):
        escaped = value.replace("'", "''")
        return f"'{escaped}'"
    return None


def _backfill_literal(col) -> str | None:
    """Literal để backfill cột vừa thêm, hoặc None nếu để NULL là đúng.

    - default vô hướng ('user', True, 60) -> dùng chính giá trị đó.
    - default dạng callable (`_now` cho created_at/updated_at) -> mốc thời gian hiện
      tại, tính bằng Python. KHÔNG dùng `CURRENT_TIMESTAMP` của SQL: nó trả datetime
      chuỗi, ghi vào cột BIGINT (unix giây) sẽ hỏng dữ liệu.
    - không có default (password_hash, last_login_at) -> None: giữ NULL, đúng nghĩa
      "user cũ chưa có mật khẩu".
    """
    default = getattr(col.default, "arg", None)
    if default is None:
        return None
    if callable(default):
        if isinstance(col.type, (Integer, BigInteger)):
            return str(int(time.time()))
        return None
    return _literal(default)


def ensure_schema(engine: Engine, verbose: bool = False) -> list[str]:
    """Tạo bảng thiếu + thêm cột thiếu. Trả về danh sách việc đã làm (để test/log)."""
    actions: list[str] = []

    # 1) bảng mới (create_all là "create if missing" nên an toàn trên DB cũ)
    Base.metadata.create_all(engine)

    insp = inspect(engine)
    existing_tables = set(insp.get_table_names())

    with engine.begin() as conn:
        for table in Base.metadata.sorted_tables:
            if table.name not in existing_tables:
                continue  # vừa được create_all tạo -> đã đủ cột
            have = {c["name"] for c in insp.get_columns(table.name)}
            for col in table.columns:
                if col.name in have:
                    continue
                ddl_type = col.type.compile(dialect=engine.dialect)
                conn.execute(text(
                    f'ALTER TABLE {table.name} ADD COLUMN {col.name} {ddl_type}'))
                actions.append(f"add column {table.name}.{col.name}")

                # 4) backfill (password_hash/last_login_at -> giữ NULL)
                lit = _backfill_literal(col)
                if lit is not None:
                    conn.execute(text(
                        f"UPDATE {table.name} SET {col.name} = {lit} "
                        f"WHERE {col.name} IS NULL"))
                    actions.append(f"backfill {table.name}.{col.name} = {lit}")

    # 5) index thiếu (unique index của users.email đã có sẵn từ trước)
    for table in Base.metadata.sorted_tables:
        for idx in table.indexes:
            idx.create(bind=engine, checkfirst=True)

    # 5b) Postgres: siết NOT NULL sau khi đã backfill (SQLite không hỗ trợ ALTER này)
    if engine.dialect.name == "postgresql":
        with engine.begin() as conn:
            for table in Base.metadata.sorted_tables:
                insp2 = inspect(engine)
                if table.name not in set(insp2.get_table_names()):
                    continue
                cols = {c["name"]: c for c in insp2.get_columns(table.name)}
                for col in table.columns:
                    info = cols.get(col.name)
                    if not info or info.get("nullable", True):
                        continue
                    if col.primary_key or col.nullable:
                        continue
                    conn.execute(text(
                        f"ALTER TABLE {table.name} ALTER COLUMN {col.name} SET NOT NULL"))
                    actions.append(f"set not null {table.name}.{col.name}")

    if verbose and actions:
        for a in actions:
            print("  [migrate]", a)
    return actions


def ensure_indexes(engine: Engine) -> None:
    """Chỉ tạo index thiếu (dùng ở nơi không muốn đụng cột)."""
    for table in Base.metadata.sorted_tables:
        for idx in table.indexes:
            idx.create(bind=engine, checkfirst=True)