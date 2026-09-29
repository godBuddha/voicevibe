"""CORS guard — tách frontend chạy khác origin phải gửi được cookie phiên.

Vì sao cần: khi frontend là SPA riêng (dev server Vite trên :5173), mọi fetch
đi từ origin khác → browser buộc preflight và **chỉ gửi cookie nếu response
preflight khai đúng** `Access-Control-Allow-Origin` (tường minh) +
`Access-Control-Allow-Credentials: true`. Cặp `allow_credentials=True` với
wildcard là bất hợp lệ theo spec — browser âm thầm bỏ qua credentials, fetch
không báo lỗi, session cookie không bao giờ tới server. Trạng thái này rất
dễ nhầm là "backend hỏng" trong khi thực ra là cấu hình CORS.

Kiểm tra:
  1. `parse_cors_origins` — tách đúng, cắt `/` cuối, bỏ phần tử rỗng/khoảng trắng
  2. Preflight OPTIONS: header allow-origin echo ĐÚNG origin yêu cầu + credentials=true
  3. Request thật (GET) từ origin được phép: có allow-origin + credentials=true
  4. Origin KHÔNG được liệt kê: KHÔNG có header allow-origin (từ chối im lặng đúng spec)

Run:  cd backend && PYTHONPATH=. python tests/test_cors.py
"""
from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.main import add_cors, parse_cors_origins  # noqa: E402

DEV = "http://localhost:5173"
PROD = "https://app.example.com"


def _client(origins: str):
    raw = parse_cors_origins(origins)
    app = FastAPI()

    @app.get("/v1/me")
    def me() -> dict:
        return {"id": 1}

    add_cors(app, raw)
    return TestClient(app)


def test_parser() -> None:
    got = parse_cors_origins(f" {DEV}/ , {PROD},,")
    assert got == [DEV, PROD], got  # cắt `/` cuối, bỏ phần tử rỗng
    assert parse_cors_origins("") == []
    assert parse_cors_origins("  ") == []
    print("parse_cors_origins ............ OK")


def test_preflight_allowed() -> None:
    c = _client(f"{DEV},{PROD}")
    r = c.options("/v1/me", headers={
        "Origin": DEV,
        "Access-Control-Request-Method": "GET",
    })
    assert r.status_code == 200, r.status_code
    # echo ĐÚNG origin yêu cầu — wildcard (cho phép mọi origin) kết hợp
    # credentials là bất hợp lệ, nếu thấy `*` ở đây thì cấu hình đã sai thật.
    assert r.headers["access-control-allow-origin"] == DEV, dict(r.headers)
    assert r.headers["access-control-allow-credentials"] == "true"
    print("preflight origin hợp lệ ....... OK")


def test_real_request_allowed() -> None:
    c = _client(f"{DEV},{PROD}")
    r = c.get("/v1/me", headers={"Origin": DEV})
    assert r.status_code == 200
    assert r.headers["access-control-allow-origin"] == DEV
    assert r.headers["access-control-allow-credentials"] == "true"
    print("GET từ origin hợp lệ .......... OK")


def test_origin_unknown_rejected() -> None:
    c = _client(DEV)
    r = c.get("/v1/me", headers={"Origin": "https://evil.example"})
    # Không có header allow-origin → browser tự chặn response. Server vẫn trả
    # 200 (spec CORS đặt việc chặn ở browser) — điều quan trọng là header vắng.
    assert "access-control-allow-origin" not in r.headers, dict(r.headers)
    print("origin lạ không được phép ..... OK")


if __name__ == "__main__":
    test_parser()
    test_preflight_allowed()
    test_real_request_allowed()
    test_origin_unknown_rejected()
    print("CORS GUARD PASSED")
