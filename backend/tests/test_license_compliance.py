"""License-compliance guard (AGPL-3.0) — bảo vệ các nghĩa vụ THẬT của giấy phép.

Vì sao cần: chọn AGPL-3.0 kèm theo nghĩa vụ cụ thể, không chỉ là một file văn bản.
Test này biến chúng thành thứ máy kiểm được, để không ai vô tình phá:

  1. `LICENSE` phải là AGPL-3.0 (không phải Apache-2.0 như trước)
  2. §13 — app chạy qua mạng phải **chỉ đường lấy mã nguồn**: UI phải có liên kết
     "Mã nguồn", và placeholder phải được thay bằng URL thật khi render (không được
     lọt `__SOURCE_URL__` ra HTML — lúc đó là liên kết gãy, vi phạm §13)
  3. URL đó phải đổi được qua Settings (`app.source_url`) — AGPL yêu cầu trỏ tới
     **bản mã nguồn tương ứng đang chạy**, mà bản self-host đã sửa thì khác bản gốc
  4. README phải nêu cảnh báo weights CC-BY-NC, kèm bảng liệt kê model — người
     self-host phải biết hạn chế này đi theo họ

Run:  cd backend && PYTHONPATH=. python tests/test_license_compliance.py
"""
from __future__ import annotations

import os
import pathlib
import sys
import tempfile

REPO = pathlib.Path(__file__).resolve().parents[2]

os.environ["DATABASE_URL"] = f"sqlite:///{tempfile.mkdtemp(prefix='vv_lic_')}/lic.db"
os.environ["VOICEVIBE_INLINE"] = "1"
os.environ["MEDIA_ROOT"] = tempfile.mkdtemp(prefix="vv_lic_media_")
os.environ["VOICEVIBE_API_KEYS"] = "lic-test-key"
os.environ.pop("VOICEVIBE_ADMIN_KEY", None)

sys.path.insert(0, str(REPO / "backend"))

# ---------------------------------------------------------------- 1. LICENSE file
lic = (REPO / "LICENSE").read_text(encoding="utf-8")
assert "GNU AFFERO GENERAL PUBLIC LICENSE" in lic, "LICENSE không phải AGPL-3.0"
assert "Version 3, 19 November 2007" in lic, "LICENSE không phải AGPL-3.0 (version 3)"
assert "Apache License" not in lic, "LICENSE còn sót nội dung Apache-2.0"

# ------------------------------------------------- 4. README có cảnh báo NC
readme = (REPO / "README.md").read_text(encoding="utf-8")
assert "CC-BY-NC" in readme, "README thiếu cảnh báo weights CC-BY-NC"
assert "không dùng thương mại" in readme.lower(), "README thiếu ghi chú cấm thương mại"
assert "AGPL-3.0" in readme, "README chưa nêu license AGPL-3.0"
for model in ("wav2vec2-base-vietnamese-250h", "mms-1b-fl102", "F5-TTS"):
    assert model in readme, f"README thiếu model NC '{model}' trong bảng cảnh báo"

# ------------------------------------------------------------ 2 + 3. §13 source link
from fastapi.testclient import TestClient  # noqa: E402

from app.db import Base, engine  # noqa: E402

Base.metadata.create_all(engine)

from app.main import app  # noqa: E402

c = TestClient(app)

# Phase 2: `/` chỉ được trả khi đã có admin VÀ đã đăng nhập (cổng ở server).
# Trên DB trắng thì phải là redirect về /setup, KHÔNG phải HTML ứng dụng.
assert c.get("/", follow_redirects=False).status_code == 302
assert c.get("/", follow_redirects=False).headers["location"] == "/setup"

r = c.post("/v1/auth/setup", json={"email": "admin@local", "password": "matkhau123"})
assert r.status_code == 201, r.text
r = c.get("/")
assert r.status_code == 200, r.text
html = r.text

assert "__SOURCE_URL__" not in html, (
    "placeholder __SOURCE_URL__ lọt ra HTML — liên kết mã nguồn bị gãy (vi phạm AGPL §13)"
)
assert "Mã nguồn" in html, "UI thiếu liên kết 'Mã nguồn' — AGPL §13 yêu cầu chỉ đường lấy source"
assert "github.com/godBuddha/voicevibe" in html, "liên kết mã nguồn mặc định sai"

# Đổi được qua Settings (self-host bản sửa phải trỏ về source của CHÍNH HỌ)
from app.settings_service import set_setting  # noqa: E402

mine = "https://git.example.org/toi/voicevibe-fork"
set_setting("app.source_url", mine, is_secret=False, category="general")
html2 = c.get("/").text
assert mine in html2 and "github.com/godBuddha/voicevibe" not in html2, (
    "app.source_url không điều khiển được liên kết mã nguồn"
)

print("LICENSE = AGPL-3.0 ....................... OK")
print("README có cảnh báo NC + bảng model ....... OK")
print("§13 liên kết Mã nguồn render đúng ........ OK")
print("§13 đổi được qua app.source_url .......... OK")
print("LICENSE COMPLIANCE GUARD PASSED")