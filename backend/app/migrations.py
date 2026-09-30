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


def _q(engine: Engine, ident: str) -> str:
    """Trích dẫn định danh theo dialect.

    BẮT BUỘC, không phải cho đẹp: `stage_models.order` là **từ khoá dành riêng** của
    SQL, nên `ALTER TABLE stage_models ALTER COLUMN order SET NOT NULL` là lỗi cú
    pháp. Đã gặp thật trên Postgres (`syntax error at or near "order"`) — app chết
    ngay lúc khởi động vì `ensure_schema` chạy trước khi phục vụ request.

    Vì sao test SQLite không bắt được: nhánh `SET NOT NULL` chỉ chạy trên Postgres,
    và bảng `stage_models` trên DB mới được `create_all` tạo sẵn (không đi qua
    `ADD COLUMN`). Tức là đường sinh ra lỗi chưa từng được chạy.

    Dùng `identifier_preparer` của dialect: nó biết luật trích dẫn của từng loại DB
    (`"order"` với Postgres/SQLite) thay vì tự đoán.
    """
    return engine.dialect.identifier_preparer.quote(ident)


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

    # 1b) Postgres: THÊM GIÁ TRỊ ENUM còn thiếu. create_all KHÔNG đụng enum type
    # đã tồn tại, nên thêm giá trị mới vào JobStatus (vd 'cancelled') trên DB cũ
    # sẽ nổ "invalid input value for enum jobstatus" ở lần ghi đầu tiên (đã gặp
    # thật: POST /v1/jobs/<id>/cancel -> HTTP 500). SQLite không có enum type
    # riêng — bỏ qua.
    if engine.dialect.name == "postgresql":
        from sqlalchemy import Enum as SAEnum

        with engine.begin() as conn:
            for table in Base.metadata.sorted_tables:
                if table.name not in existing_tables:
                    continue
                for col in table.columns:
                    if not isinstance(col.type, SAEnum):
                        continue
                    enum_name = col.type.name
                    wanted = ([v.value for v in col.type.enum_class]
                              if col.type.enum_class else list(col.type.enums))
                    have = set(conn.execute(text(
                        "SELECT e.enumlabel FROM pg_enum e "
                        "JOIN pg_type t ON t.oid = e.enumtypid "
                        "WHERE t.typname = :n"), {"n": enum_name}).scalars())
                    for v in wanted:
                        if v in have:
                            continue
                        esc = str(v).replace("'", "''")
                        # IF NOT EXISTS: idempotent; ADD VALUE chạy được trong
                        # transaction từ PG 12 (giá trị mới dùng ở transaction SAU
                        # là hợp lệ — request ghi 'cancelled' là transaction riêng).
                        conn.execute(text(
                            f'ALTER TYPE {_q(engine, enum_name)} '
                            f"ADD VALUE IF NOT EXISTS '{esc}'"))
                        actions.append(f"add enum value {enum_name}.{v}")

    with engine.begin() as conn:
        for table in Base.metadata.sorted_tables:
            if table.name not in existing_tables:
                continue  # vừa được create_all tạo -> đã đủ cột
            have = {c["name"] for c in insp.get_columns(table.name)}
            for col in table.columns:
                if col.name in have:
                    continue
                ddl_type = col.type.compile(dialect=engine.dialect)
                tbl, cn = _q(engine, table.name), _q(engine, col.name)
                conn.execute(text(
                    f'ALTER TABLE {tbl} ADD COLUMN {cn} {ddl_type}'))
                actions.append(f"add column {table.name}.{col.name}")

                # 4) backfill (password_hash/last_login_at -> giữ NULL)
                lit = _backfill_literal(col)
                if lit is not None:
                    conn.execute(text(
                        f"UPDATE {tbl} SET {cn} = {lit} "
                        f"WHERE {cn} IS NULL"))
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
                    # CHỈ siết khi DB còn nullable mà model yêu cầu NOT NULL —
                    # tức cột vừa ADD COLUMN + backfill ở bước 3/4.
                    # Bẫy đã gặp thật: điều kiện cũ kiểm ngược (`info.get("nullable",
                    # True)` -> continue khi cột ĐANG nullable) khiến bước này chạy
                    # `ALTER ... SET NOT NULL` LẠI trên mọi cột đã NOT NULL trong
                    # MỌI lần boot. ALTER no-op vẫn lấy AccessExclusiveLock toàn
                    # bảng -> boot đụng request đang chạy -> Postgres giết một
                    # bên vì deadlock -> POST /v1/jobs trả 500 ngẫu nhiên
                    # (đã gặp thật 2 lần trên deployment thật, "ALTER TABLE
                    # sessions ALTER COLUMN user_id SET NOT NULL" trong pg log).
                    if not info or not info.get("nullable", True):
                        continue  # DB đã NOT NULL (hoặc không thấy cột) -> không đụng
                    if col.primary_key or col.nullable:
                        continue  # PK tự nhiên NOT NULL; model cho NULL thì bỏ qua
                    conn.execute(text(
                        f"ALTER TABLE {_q(engine, table.name)} "
                        f"ALTER COLUMN {_q(engine, col.name)} SET NOT NULL"))
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