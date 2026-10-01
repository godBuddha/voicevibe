"""Settings Hub guard — hồ sơ/mật khẩu/phiên cá nhân + audit/overview/system/export.

Mỗi nhóm là một yêu cầu thiết kế phải được MÁY kiểm:

  1.  401 chưa đăng nhập (endpoint cá nhân + admin endpoint mới)
  2.  PATCH /v1/me: validate 422 + tên lưu DB + trả về ở /v1/me và /v1/auth/me
  3.  Đổi mật khẩu: sai mật khẩu hiện tại = 403 (KHÔNG 401 — client.js coi 401
      là hết phiên sẽ đá người dùng ra /login khi đang gõ mật khẩu); mật khẩu
      mới ngắn = 422; đổi thành công → mọi phiên KHÁC chết, phiên hiện tại
      sống, đăng nhập mật khẩu cũ 401, mật khẩu mới 200; rate-limit 429
  4.  Phiên: list có cờ current; DELETE hash lạ/người khác → 404; "đăng xuất
      mọi thiết bị khác" giữ nguyên phiên hiện tại
  5.  Audit: ≥7 action được ghi (login/login_failed/logout/name/password/
      session/setting); user thường GET /v1/admin/audit → 403; filter
      action/user_id/q + limit/offset/total
  6.  Overview: khớp job seed trực tiếp (2 done tts, 1 running dub) toàn hệ
  7.  /v1/admin/system: shape sqlite/inline/local + KHÔNG lộ secret
  8.  Export không chứa giá trị secret lẫn provider api_key; import 2 lần
      không drift (idempotent); shape xấu 422; stage provider lạ → warnings
  9.  CSRF: request POST cookie với Origin lạ → 403 cross-origin
  10. GET (đọc) KHÔNG sinh dòng audit

Run:  cd backend && PYTHONPATH=. python tests/test_settings_hub.py
"""
from __future__ import annotations

import json
import os
import pathlib
import sys
import tempfile

WORK = pathlib.Path(tempfile.mkdtemp(prefix="vv_sh_"))
os.environ["DATABASE_URL"] = f"sqlite:///{WORK}/sh.db"
os.environ["MEDIA_ROOT"] = str(WORK / "media")
os.environ["VOICEVIBE_INLINE"] = "1"
os.environ.pop("VOICEVIBE_API_KEYS", None)
os.environ.pop("VOICEVIBE_ADMIN_KEY", None)

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient  # noqa: E402

from app import ratelimit as RL  # noqa: E402
from app.db import SessionLocal  # noqa: E402
from app.main import app  # noqa: E402
from app.models import AuditLog, Job, JobStatus, User  # noqa: E402
from app.security import hash_password  # noqa: E402
from app.settings_service import set_setting  # noqa: E402

c = TestClient(app)
RL.reset()
# --------------------------------------------------------- 1. chưa đăng nhập
# BẮT BUỘC trước /setup: setup trả cookie phiên admin và TestClient GIỮ luôn —
# gọi sau setup thì request "chưa đăng nhập" của c lại mang cookie admin.
anon = TestClient(app)
RL.reset()
checks = [
    ("patch", "/v1/me"), ("post", "/v1/me/password"), ("get", "/v1/me/sessions"),
    ("delete", "/v1/me/sessions"), ("get", "/v1/admin/audit"),
    ("get", "/v1/admin/overview"), ("get", "/v1/admin/system"),
    ("get", "/v1/admin/config/export"),
]
for method, path in checks:
    kwargs = {"json": {"name": "x"}} if method == "patch" else {}
    r = getattr(anon, method)(path, **kwargs)
    assert r.status_code == 401, f"{method} {path} -> {r.status_code}"
print("1. chưa đăng nhập 401 ............................. OK")

assert c.post("/v1/auth/setup",
              json={"email": "admin@local", "password": "matkhau123"}).status_code == 201


# ------------------------------------------------------------ helper: users
def make_user(email: str):
    with SessionLocal() as db:
        db.add(User(email=email, role="user", password_hash=hash_password("matkhau456")))
        db.commit()
    cl = TestClient(app)
    RL.reset()
    assert cl.post("/v1/auth/login",
                   json={"email": email, "password": "matkhau456"}).status_code == 200
    return cl


A = make_user("a@local")
B = make_user("b@local")
RL.reset()

# ------------------------------------------------------------- 2. hồ sơ (name)
assert A.patch("/v1/me", json={"name": ""}).status_code == 422
assert A.patch("/v1/me", json={"name": "x" * 121}).status_code == 422
r = A.patch("/v1/me", json={"name": "  Nam Tuoi Tre  "})
assert r.status_code == 200 and r.json()["name"] == "Nam Tuoi Tre", r.text
assert A.get("/v1/me").json()["name"] == "Nam Tuoi Tre"
assert A.get("/v1/auth/me").json()["name"] == "Nam Tuoi Tre"
# user khác không bị ảnh hưởng
assert B.get("/v1/me").json()["name"] in (None, "")
print("2. PATCH /v1/me validate + persist + expose ... OK")

# --------------------------------------------------------- 3. đổi mật khẩu
# Tạo phiên phụ của A (thiết bị khác) — sẽ bị đá khi A đổi mật khẩu.
A2 = TestClient(app)
RL.reset()
assert A2.post("/v1/auth/login",
               json={"email": "a@local", "password": "matkhau456"}).status_code == 200

r = A.post("/v1/me/password", json={"current_password": "SAI", "new_password": "matkhaumoi99"})
assert r.status_code == 403, f"sai mật khẩu hiện tại phải 403 (không 401) — got {r.status_code}"
assert "không đúng" in r.json()["detail"]
r = A.post("/v1/me/password", json={"current_password": "matkhau456", "new_password": "ngan"})
assert r.status_code == 422
r = A.post("/v1/me/password", json={"current_password": "matkhau456", "new_password": "matkhaumoi99"})
assert r.status_code == 200, r.text
assert r.json()["ok"] is True and r.json()["sessions_revoked"] >= 1

# Phiên phụ đã chết (401), phiên chính sống, mật khẩu cũ chết, mới sống.
assert A2.get("/v1/me").status_code == 401
assert A.get("/v1/me").status_code == 200
assert A.post("/v1/auth/logout", json={}).status_code == 200  # biết rõ mình còn sống
RL.reset()
assert A.post("/v1/auth/login", json={"email": "a@local", "password": "matkhau456"}).status_code == 401
RL.reset()
assert A.post("/v1/auth/login", json={"email": "a@local", "password": "matkhaumoi99"}).status_code == 200
# Rate-limit: 5 lần sai liên tiếp rồi lần 6 phải 429.
RL.reset()
for _ in range(5):
    assert A.post("/v1/me/password", json={
        "current_password": "SAI", "new_password": "matkhaumoi99"}).status_code == 403
assert A.post("/v1/me/password", json={
    "current_password": "SAI", "new_password": "matkhaumoi99"}).status_code == 429
print("3. đổi mật khẩu 403/422/thu-hồi-phiên/429 ....... OK")

# ----------------------------------------------------------------- 4. phiên
r = A.get("/v1/me/sessions")
assert r.status_code == 200
rows = r.json()["sessions"]
current = [s for s in rows if s["current"]]
assert len(current) == 1, rows
foreign = "0" * 64
assert A.delete(f"/v1/me/sessions/{foreign}").status_code == 404
# B tạo phiên riêng rồi A không xoá được phiên của B.
b_hash = B.get("/v1/me/sessions").json()["sessions"][0]["token_hash"]
assert A.delete(f"/v1/me/sessions/{b_hash}").status_code == 404
# Tạo thêm phiên A rồi "đăng xuất mọi thiết bị khác".
A3 = TestClient(app)
RL.reset()
assert A3.post("/v1/auth/login", json={"email": "a@local", "password": "matkhaumoi99"}).status_code == 200
r = A.delete("/v1/me/sessions")
assert r.json()["revoked"] >= 1
assert A.get("/v1/me").status_code == 200          # phiên hiện tại vẫn sống
assert A3.get("/v1/me").status_code == 401         # phiên khác đã chết
print("4. phiên: current/404/revoke-others ............. OK")

# ------------------------------------------------------------------ 5. audit
def audit_actions(cl):
    r = cl.get("/v1/admin/audit?limit=200")
    assert r.status_code == 200, r.text
    return [i["action"] for i in r.json()["items"]], r.json()["total"]

r = c.put("/v1/admin/settings/max_speed", json={"value": 1.4})
assert r.status_code == 200
actions, total = audit_actions(c)
for expect in ("auth.login", "auth.login_failed", "auth.logout", "auth.setup",
               "me.name_change", "me.password_change", "me.session_revoke",
               "setting.set"):
    assert expect in actions, f"thiếu action {expect} — có: {sorted(set(actions))}"
# user thường không được xem audit (không phải 401 — đã đăng nhập)
assert B.get("/v1/admin/audit").status_code == 403
# filter theo action
r = c.get("/v1/admin/audit?action=auth.login_failed")
assert {i["action"] for i in r.json()["items"]} == {"auth.login_failed"}
assert r.json()["items"] and "a@local" in r.json()["items"][0]["target"]
# filter user_id: lấy user id của A từ /v1/me
a_id = A.get("/v1/me").json()["user_id"]
r = c.get(f"/v1/admin/audit?user_id={a_id}&limit=5")
assert r.json()["items"] and all(i["user_id"] == a_id for i in r.json()["items"])
assert r.json()["total"] >= 1 and len(r.json()["items"]) <= 5
# q substring + phân trang
r = c.get("/v1/admin/audit?q=matkhau")  # không nên khớp gì (không log giá trị)
assert r.json()["total"] == 0
full = c.get("/v1/admin/audit?limit=200").json()
page1 = c.get("/v1/admin/audit?limit=1&offset=0").json()
page2 = c.get("/v1/admin/audit?limit=1&offset=1").json()
assert page1["items"][0]["id"] != page2["items"][0]["id"]
assert page1["total"] == full["total"] == page2["total"]
print("5. audit: ghi đủ action + 403 + filter + phân trang OK")

# -------------------------------------------------------------- 6. overview
with SessionLocal() as db:
    for t, s in [("tts", JobStatus.done), ("tts", JobStatus.done),
                 ("dub", JobStatus.running), ("stt", JobStatus.queued)]:
        db.add(Job(user_id=a_id, type=t, status=s))
    db.commit()
ov = c.get("/v1/admin/overview").json()
assert ov["by_type"]["tts"] == 2, ov["by_type"]
assert ov["by_type"]["dub"] == 1 and ov["by_type"]["stt"] == 1
assert ov["running"] == 1
assert ov["total_jobs"] == 4
assert ov["users"]["total"] >= 3 and ov["users"]["admins"] >= 1
assert "settings" not in ov and "secret" not in json.dumps(ov).lower()
print("6. overview khớp job seed toàn hệ ............... OK")

# ---------------------------------------------------------------- 7. system
set_setting("hf_token", "SECRET-HF-VALUE-XYZ", is_secret=True)
set_setting("translate.api_key", "SECRET-TK-VALUE-XYZ", is_secret=True)
sysinfo = c.get("/v1/admin/system").json()
assert sysinfo["db"]["dialect"] == "sqlite", sysinfo
assert sysinfo["queue"]["mode"] == "inline"
assert sysinfo["storage"]["mode"] == "local"
assert sysinfo["password_min_length"] == 8
assert sysinfo["python"]
blob = json.dumps(sysinfo)
assert "SECRET-HF-VALUE-XYZ" not in blob and "SECRET-TK-VALUE-XYZ" not in blob
print("7. /v1/admin/system shape + không lộ secret ..... OK")

# -------------------------------------------------- 8. export / import cấu hình
c.post("/v1/admin/providers", json={"name": "prov-demo", "kind": "openai",
                                    "base_url": "https://api.demo/v1",
                                    "api_key": "sk-demo-secret-123"})
c.put("/v1/admin/settings/app.source_url", json={"value": "https://github.com/demo/fork"})
export = c.get("/v1/admin/config/export").json()
export_blob = json.dumps(export)
assert "sk-demo-secret-123" not in export_blob
assert "SECRET-HF-VALUE-XYZ" not in export_blob
for p in export["providers"]:
    assert "api_key" not in p and "api_key_enc" not in p, p
    if p["name"] == "prov-demo":
        assert p["base_url"] == "https://api.demo/v1"
sec_stub = [s for s in export["settings"] if s["key"] == "hf_token"]
assert sec_stub and sec_stub[0].get("secret") is True and "value" not in sec_stub[0]
plain = [s for s in export["settings"] if s["key"] == "app.source_url"]
assert plain and plain[0]["value"] == "https://github.com/demo/fork"
assert export["_meta"]["version"] == 1

# Nhập 2 LẦN — idempotent (không dup provider/stage).
prov_before = c.get("/v1/admin/providers").json()["providers"]
imp1 = c.post("/v1/admin/config/import", json=export)
assert imp1.status_code == 200, imp1.text
assert imp1.json()["warnings"] == [] or all("secret" in w for w in imp1.json()["warnings"])
prov_after1 = c.get("/v1/admin/providers").json()["providers"]
assert len(prov_after1) == len(prov_before), "import không được tạo dup provider"
imp2 = c.post("/v1/admin/config/import", json=export)
prov_after2 = c.get("/v1/admin/providers").json()["providers"]
assert len(prov_after2) == len(prov_before), "import lần 2 phải idempotent"
assert imp2.json()["imported"]["providers"] >= 1

# Shape xấu → 422 trước khi ghi bất kỳ gì.
assert c.post("/v1/admin/config/import", json=[]).status_code == 422
assert c.post("/v1/admin/config/import", json={"nope": 1}).status_code == 422
assert c.post("/v1/admin/config/import", json={"settings": "not-a-list"}).status_code == 422
# Stage trỏ provider lạ → warnings, không chết.
bad = {"stages": [{"stage": "translate", "order": 0,
                   "provider_name": "khong-ton-tai", "model": "m"}]}
r = c.post("/v1/admin/config/import", json=bad)
assert r.status_code == 200 and r.json()["imported"]["stages"] == 0
assert any("khong-ton-tai" in w for w in r.json()["warnings"])
print("8. export không-secret + import idempotent + 422 OK")

# ------------------------------------------------------------------ 9. CSRF
r = A.post("/v1/me/password", headers={"Origin": "http://evil.example"},
           json={"current_password": "matkhaumoi99", "new_password": "matkhaumoi99"})
assert r.status_code == 403 and "cross-origin" in r.json()["detail"], r.text
print("9. CSRF chặn Origin lạ .......................... OK")

# ------------------------------------------------------- 10. GET không audit
before = c.get("/v1/admin/audit?limit=1").json()["total"]
c.get("/v1/admin/settings")
c.get("/v1/admin/overview")
c.get("/v1/admin/system")
c.get("/v1/admin/audit?limit=1")
after = c.get("/v1/admin/audit?limit=1").json()["total"]
assert before == after, f"GET không được sinh audit: {before} -> {after}"
# bảng audit_logs tồn tại với shape đúng (không FK user) — idempotency migration
with SessionLocal() as db:
    n = db.query(AuditLog).count()
    assert n >= 8, f"audit rows phải >= 8 — có {n}"
print("10. GET không sinh audit + bảng audit_logs ...... OK")

print("TẤT CẢ 10 NHÓM — Settings Hub PASS")
