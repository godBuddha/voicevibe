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


# ---------------------------------------------------------------
# CSRF cookie-check (auth._check_csrf) — lớp hai sau CORS. Deploy tách frontend
# (SPA 8080 → API 18080) từng bị 403 TOÀN BỘ POST/PUT/DELETE có cookie dù CORS
# đã bật: origin lệch cổng so với Host là tình trạng bình thường của kiến trúc
# đó, không phải tấn công. Origin trong VOICEVIBE_CORS_ORIGINS phải được thông
# qua; origin lạ mới là CSRF thật.
def test_csrf_allowlist() -> None:
    import os

    from fastapi import HTTPException
    from starlette.requests import Request as StarletteRequest

    from app.auth import _check_csrf

    def _req(headers: dict) -> StarletteRequest:
        scope = {
            "type": "http", "method": "POST",
            "path": "/v1/jobs", "headers": [
                (k.lower().replace("_", "-").encode(), v.encode())
                for k, v in headers.items()
            ],
            "query_string": b"", "server": ("api.local", 8000),
            "scheme": "http", "root_path": "",
        }
        return StarletteRequest(scope)

    old = os.environ.get("VOICEVIBE_CORS_ORIGINS")
    os.environ["VOICEVIBE_CORS_ORIGINS"] = DEV
    # cùng host → luôn thông qua
    _check_csrf(_req({"origin": "http://api.local:8000", "host": "api.local:8000"}))
    # origin trong danh sách cho phép (SPA tách cổng) → thông qua
    _check_csrf(_req({"origin": DEV, "host": "api.local:8000"}))
    # biến thể có `/` cuối vẫn là MỘT origin (cùng quy ước với parse_cors_origins)
    _check_csrf(_req({"origin": DEV + "/", "host": "api.local:8000"}))
    # không có Origin (curl/SDK) → không phải vector CSRF
    _check_csrf(_req({"host": "api.local:8000"}))
    # origin lạ + cookie-authenticated POST → 403 (CSRF thật)
    try:
        _check_csrf(_req({"origin": "https://evil.example", "host": "api.local:8000"}))
        raise AssertionError("origin lạ phải bị chặn 403")
    except HTTPException as e:
        assert e.status_code == 403, e.status_code
    # tắt allow-list → mọi cross-origin đều bị chặn lại (không có cửa sau)
    os.environ["VOICEVIBE_CORS_ORIGINS"] = ""
    try:
        _check_csrf(_req({"origin": DEV, "host": "api.local:8000"}))
        raise AssertionError("allow-list rỗng phải chặn")
    except HTTPException as e:
        assert e.status_code == 403
    if old is None:
        os.environ.pop("VOICEVIBE_CORS_ORIGINS", None)
    else:
        os.environ["VOICEVIBE_CORS_ORIGINS"] = old
    print("CSRF allow-list VOICEVIBE_* .. OK")


if __name__ == "__main__":
    test_parser()
    test_preflight_allowed()
    test_real_request_allowed()
    test_origin_unknown_rejected()
    test_csrf_allowlist()
    print("CORS GUARD PASSED")
