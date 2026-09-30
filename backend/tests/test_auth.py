"""Phase 2 guard — tài khoản, phiên đăng nhập, phân quyền + bốn lỗ hổng đã vá.

Mọi ca ở đây tương ứng một hành vi BẢO MẬT cụ thể, không phải "cho có test":

  1.  /setup chỉ chạy được MỘT lần — kể cả khi hai request đồng thời
  2.  Cổng vào HTML ở tầng server (trước đây / và /admin trả HTML cho bất kỳ ai)
  3.  Đăng nhập / đăng xuất; sai mật khẩu trả lỗi chung, không lộ email nào tồn tại
  4.  Phiên hết hạn -> 401 và row bị xoá; gia hạn trượt khi dùng lại sau 24h
  5.  Phân quyền: user thường không vào được /admin/settings và /v1/admin/users
  6.  Dev key (VOICEVIBE_API_KEYS) CHẾT sau khi đã có admin — không còn backdoor env
  7.  X-Admin-Key chỉ hoạt động khi `admin.api_key` được đặt tường minh
  8.  Công tắc `auth.allow_signup` (mặc định TẮT) + signup không bao giờ tạo admin
  9.  voice_id của người khác -> 404 TRƯỚC khi tạo job (job không được sinh ra)
  10. /media: chủ sở hữu đọc được, người khác 404, key đã thu hồi 401, admin đọc được
  11. scrypt: verify đúng/sai, hash hỏng, needs_rehash
  12. Chống tự khoá admin cuối cùng

Run:  cd backend && PYTHONPATH=. python tests/test_auth.py
"""
from __future__ import annotations

import os
import pathlib
import sys
import tempfile

WORK = pathlib.Path(tempfile.mkdtemp(prefix="vv_auth_"))
DB = WORK / "auth.db"
os.environ["DATABASE_URL"] = f"sqlite:///{DB}"
os.environ["MEDIA_ROOT"] = str(WORK / "media")
os.environ["VOICEVIBE_INLINE"] = "1"
os.environ["VOICEVIBE_API_KEYS"] = "dev-key-1"   # để kiểm tra nhánh dev key BỊ VÔ HIỆU
os.environ.pop("VOICEVIBE_ADMIN_KEY", None)      # không có sẵn admin key từ env

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient  # noqa: E402

from app import auth as A  # noqa: E402
from app import ratelimit as RL  # noqa: E402
from app.db import SessionLocal  # noqa: E402
from app.main import app  # noqa: E402
from app.models import ApiKey, Job, JobStatus, User, Voice  # noqa: E402
from app.security import (  # noqa: E402
    hash_password,
    needs_rehash,
    password_problem,
    verify_password,
)

c = TestClient(app)
ADMIN_EMAIL, ADMIN_PW = "admin@local", "matkhau123"

# ------------------------------------------------------------------ 1. cổng vào
assert c.get("/", follow_redirects=False).status_code == 302
assert c.get("/", follow_redirects=False).headers["location"] == "/setup"
assert c.get("/setup").status_code == 200
assert c.get("/login", follow_redirects=False).headers["location"] == "/setup"
assert c.get("/admin", follow_redirects=False).headers["location"] == "/setup"
assert c.get("/docs").status_code == 404, "/docs phải TẮT mặc định"
print("cổng vào HTML chặn ở server ............ OK")
print("/docs tắt mặc định ..................... OK")

# --------------------------------------------------------------- 2. tạo Admin
r = c.post("/v1/auth/setup", json={"email": ADMIN_EMAIL, "password": ADMIN_PW})
assert r.status_code == 201, r.text
admin = r.json()
assert admin["role"] == "admin"
assert c.cookies.get(A.COOKIE_NAME), "không thấy cookie phiên sau setup"
print("setup tạo admin + phiên ................. OK")

# mật khẩu yếu bị từ chối (kiểm tra riêng trước khi setup để không khoá hệ thống)
with SessionLocal() as db:
    assert password_problem("abc") is not None
    assert password_problem("duokhong12") is None

# setup lần hai -> 409 (đã có admin)
RL.reset()
r = c.post("/v1/auth/setup", json={"email": "khac@local", "password": ADMIN_PW})
assert r.status_code == 409, r.text
print("setup lần hai bị chặn ................... OK")

# chốt nguyên tử: xoá hết admin nhưng GIỮ cờ -> vẫn 409 (cờ mới là cổng thật)
with SessionLocal() as db:
    for u in db.query(User).filter(User.role == "admin").all():
        db.delete(u)
    db.commit()
RL.reset()
r = c.post("/v1/auth/setup", json={"email": "ke@x.y", "password": ADMIN_PW})
assert r.status_code == 409, f"cờ setup.completed không chặn được: {r.status_code} {r.text}"
print("chốt nguyên tử setup.completed .......... OK")

# dựng lại admin để test tiếp
with SessionLocal() as db:
    from app.models import MediaObject, SystemFlag

    # xoá con trước cha (phiên/key trỏ tới user); cascade ở model cũng lo việc này
    # nhưng thứ tự tường minh giúp test không phụ thuộc hành vi cascade.
    db.query(A.Session).delete()
    db.query(ApiKey).delete()
    db.query(Voice).delete()
    db.query(Job).delete()
    db.query(MediaObject).delete()
    db.query(SystemFlag).delete()
    db.query(User).delete()
    db.commit()
RL.reset()
c.cookies.clear()
r = c.post("/v1/auth/setup", json={"email": ADMIN_EMAIL, "password": ADMIN_PW})
assert r.status_code == 201, r.text
print("dựng lại admin cho các ca sau ........... OK")

# ------------------------------------------------------- 3. cổng đã có admin
assert c.get("/setup", follow_redirects=False).headers["location"] == "/login"
anon = TestClient(app)
assert anon.get("/", follow_redirects=False).headers["location"].startswith("/login")
assert anon.get("/admin", follow_redirects=False).headers["location"] == "/login?next=/admin"
assert anon.get("/login").status_code == 200
assert anon.get("/v1/admin/settings").status_code == 401  # không cookie, không key
print("chưa đăng nhập -> về /login ............. OK")

# ------------------------------------------------------- 4. đăng nhập/sai/xuất
bad = anon.post("/v1/auth/login", json={"email": ADMIN_EMAIL, "password": "sai-mat-khau"})
assert bad.status_code == 401, bad.text
assert bad.json()["detail"] == "Email hoặc mật khẩu không đúng"
# email không tồn tại -> CÙNG một thông báo (không lộ email nào có thật)
ghost = anon.post("/v1/auth/login", json={"email": "khong-ton-tai@local", "password": "abc12345"})
assert ghost.status_code == 401 and ghost.json()["detail"] == bad.json()["detail"]
print("đăng nhập sai -> lỗi chung .............. OK")

RL.reset()
lr = anon.post("/v1/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PW})
assert lr.status_code == 200, lr.text
assert anon.cookies.get(A.COOKIE_NAME)
assert anon.get("/v1/auth/me").json()["email"] == ADMIN_EMAIL
assert anon.get("/", follow_redirects=False).status_code == 200
assert anon.get("/admin").status_code == 200
print("đăng nhập + vào app/admin ............... OK")

anon.post("/v1/auth/logout")
assert not anon.cookies.get(A.COOKIE_NAME), "logout phải xoá cookie"
assert anon.get("/v1/auth/me").status_code == 401
print("đăng xuất .............................. OK")

# --------------------------------------------------- 5. phiên hết hạn + gia hạn
RL.reset()
c.cookies.clear()
c.post("/v1/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PW})
tok = c.cookies.get(A.COOKIE_NAME)
with SessionLocal() as db:
    row = db.get(A.Session, A.hash_key(tok))
    row.expires_at = int(__import__("time").time()) - 10   # ép hết hạn
    db.commit()
assert c.get("/v1/auth/me").status_code == 401
with SessionLocal() as db:
    assert db.get(A.Session, A.hash_key(tok)) is None, "phiên hết hạn phải bị xoá khỏi DB"
print("phiên hết hạn -> 401 + xoá row .......... OK")

RL.reset()
c.cookies.clear()
c.post("/v1/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PW})
tok = c.cookies.get(A.COOKIE_NAME)
import time as _t  # noqa: E402

_now = int(_t.time())
with SessionLocal() as db:
    row = db.get(A.Session, A.hash_key(tok))
    # Giả lập "phiên tạo từ lâu, sắp hết hạn": idle quá ngưỡng + chỉ còn 1 giờ.
    # (Nếu chỉ so expires_at cũ/mới thì test vô nghĩa — chạy trong cùng một giây,
    #  giá trị mới sẽ trùng giá trị cũ dù renewal có xảy ra hay không.)
    row.last_seen_at = _now - (A.SESSION_RENEW_AFTER + 60)
    row.expires_at = _now + 3600
    db.commit()
assert c.get("/v1/auth/me").status_code == 200
with SessionLocal() as db:
    row = db.get(A.Session, A.hash_key(tok))
    assert row.expires_at >= _now + A.SESSION_TTL - 5, (
        f"phiên phải được gia hạn trượt: {row.expires_at} vs {_now + A.SESSION_TTL}")
    assert row.last_seen_at >= _now - 5, "last_seen_at phải được cập nhật"
print("gia hạn trượt sau khi idle .............. OK")

# --------------------------------------------------------------- 6. phân quyền
RL.reset()
with SessionLocal() as db:
    plain = User(email="user@local", role="user",
                 password_hash=hash_password("matkhau456"))
    db.add(plain)
    db.commit()
    plain_id = plain.id

uc = TestClient(app)
RL.reset()
assert uc.post("/v1/auth/login",
               json={"email": "user@local", "password": "matkhau456"}).status_code == 200
assert uc.get("/admin", follow_redirects=False).status_code == 302, "user thường không vào /admin"
assert uc.get("/v1/admin/settings").status_code == 403
assert uc.get("/v1/admin/users").status_code == 403
assert uc.get("/v1/me").status_code == 200
print("phân quyền: user thường bị chặn ......... OK")

RL.reset()
c.cookies.clear()
c.post("/v1/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PW})
assert c.get("/v1/admin/users").status_code == 200
print("admin vào được /v1/admin/users .......... OK")

# ------------------------------------------------- 7. dev key chết sau setup
# Dùng client KHÔNG có cookie — nếu dùng `c` thì chính phiên admin của nó xác thực
# (auth_optional thử API key trước, không được thì rơi xuống cookie), và test sẽ
# "pass" một cách vô nghĩa.
nokey = TestClient(app)
assert nokey.get("/v1/me", headers={"X-API-Key": "dev-key-1"}).status_code == 401, (
    "dev-key-1 vẫn dùng được sau khi có admin — backdoor env còn sống!"
)
print("dev key chết sau setup .................. OK")

# ------------------------------------------- 8. X-Admin-Key chỉ khi cấu hình
RL.reset()
assert c.get("/v1/admin/settings", headers={"X-Admin-Key": "admin-dev-key"}).status_code == 401, (
    "admin-dev-key mặc định vẫn vào được — backdoor còn sống!"
)
from app.settings_service import delete_setting, get_setting, set_setting  # noqa: E402

assert get_setting("admin.api_key") in (None, ""), "admin.api_key phải KHÔNG có default"
set_setting("admin.api_key", "adm-key-that", is_secret=True)
assert c.get("/v1/admin/settings", headers={"X-Admin-Key": "adm-key-that"}).status_code == 200
assert c.get("/v1/admin/settings", headers={"X-Admin-Key": "sai"}).status_code == 401
delete_setting("admin.api_key")
assert c.get("/v1/admin/settings", headers={"X-Admin-Key": "adm-key-that"}).status_code == 401
print("X-Admin-Key chỉ chạy khi được đặt ...... OK")

# --------------------------------------------------------- 9. công tắc signup
RL.reset()
r = c.post("/v1/auth/signup", json={"email": "moi@local", "password": "matkhau789"})
assert r.status_code == 403, f"signup phải TẮT mặc định: {r.status_code} {r.text}"
print("signup tắt mặc định ..................... OK")

RL.reset()
set_setting("auth.allow_signup", True, is_secret=False, category="security")
r = c.post("/v1/auth/signup", json={"email": "moi@local", "password": "matkhau789"})
assert r.status_code == 201, r.text
assert r.json()["role"] == "user", "signup không bao giờ được tạo admin"
assert r.json()["key"].startswith("vv_")
set_setting("auth.allow_signup", False, is_secret=False, category="security")
print("bật signup -> tạo user thường ........... OK")

# ------------------------------------------- 10. quyền sở hữu voice (trước khi tạo job)
RL.reset()
with SessionLocal() as db:
    other = db.scalar(__import__("sqlalchemy").select(User).where(User.email == "user@local"))
    v = Voice(user_id=other.id, name="Giọng của người khác", lang="vi",
              engine="vieneu", ref_s3_key=f"voices/{other.id}/ref.wav")
    db.add(v)
    db.commit()
    vid, other_id = v.id, other.id

r = c.post("/v1/jobs", json={"type": "tts", "text": "xin chào", "voice_id": vid})
assert r.status_code == 404, f"admin dùng voice của người khác phải 404: {r.text}"
with SessionLocal() as db:
    # job KHÔNG được phép sinh ra (trước đây job vẫn tạo rồi fail ở worker).
    from sqlalchemy import select as _sel
    assert db.scalar(_sel(__import__("sqlalchemy").func.count())
                     .select_from(Job).where(Job.user_id == other_id)) == 0
print("voice của người khác -> 404, không tạo job OK")

# ------------------------------------------------------- 11. quyền sở hữu media
RL.reset()
uc.cookies.clear()
RL.reset()
uc.post("/v1/auth/login", json={"email": "user@local", "password": "matkhau456"})
up = uc.post("/v1/media/upload", files={"file": ("a.wav", b"RIFFfake-audio", "audio/wav")})
assert up.status_code == 201, up.text
a_key = up.json()["media_key"]
assert a_key.startswith(f"media/{plain_id}/"), f"khoá phải có tiền tố chủ sở hữu: {a_key}"

cc = TestClient(app)
RL.reset()
cc.post("/v1/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PW})
RL.reset()
with SessionLocal() as db:
    from app.models import MediaObject
    owner = db.scalar(__import__("sqlalchemy").select(User).where(User.email == "admin@local"))
    assert db.scalar(__import__("sqlalchemy").select(MediaObject)
                     .where(MediaObject.key == a_key)) is not None, "thiếu sổ media_objects"
print("upload ghi tiền tố + sổ chủ sở hữu ...... OK")

# chủ sở hữu đọc được
assert uc.get(f"/media/{a_key}").status_code == 200
# admin đọc được (quản trị)
assert cc.get(f"/media/{a_key}").status_code == 200
print("chủ sở hữu + admin đọc được media ....... OK")

# người khác (user thứ hai) -> 404
RL.reset()
with SessionLocal() as db:
    intruder = User(email="ke@local", role="user", password_hash=hash_password("matkhau999"))
    db.add(intruder)
    db.commit()
x = TestClient(app)
RL.reset()
x.post("/v1/auth/login", json={"email": "ke@local", "password": "matkhau999"})
assert x.get(f"/media/{a_key}").status_code == 404, "người khác đọc được media của chủ sở hữu!"
print("người khác -> 404 (không lộ tồn tại) .... OK")

# key đã thu hồi -> 401 (lỗ hổng cũ: bỏ qua cờ `active`)
RL.reset()
mk = x.post("/v1/keys").json()["key"]      # key thô của kẻ thứ ba
RL.reset()
r = x.delete(f"/v1/keys/{mk}")
assert r.status_code == 200
rev = TestClient(app)
assert rev.get(f"/media/{a_key}?api_key={mk}").status_code == 401, (
    "API key đã thu hồi vẫn đọc được media!"
)
print("key đã thu hồi -> 401 ................... OK")

# kết quả job: chỉ chủ job đọc được
RL.reset()
with SessionLocal() as db:
    jkey = f"jobs/{plain_id}/ket-qua.wav"
    db.add(Job(user_id=plain_id, type="tts", status=JobStatus.done,
               result_s3_key=jkey, params={"type": "tts"}))
    db.commit()
    (WORK / "media").mkdir(parents=True, exist_ok=True)
    from app.storage import get_storage
    get_storage().put(jkey, b"RIFF-ket-qua")
assert uc.get(f"/media/{jkey}").status_code == 200
assert x.get(f"/media/{jkey}").status_code == 404
print("kết quả job: chỉ chủ sở hữu ............. OK")

# ----------------------------------------- 12. chống khoá admin cuối cùng
RL.reset()
# Lấy id admin HIỆN TẠI (admin ở đầu test đã bị xoá lúc dựng lại DB ở trên).
with SessionLocal() as db:
    current_admin_id = db.scalar(
        __import__("sqlalchemy").select(User.id).where(User.role == "admin"))
assert current_admin_id, "không tìm thấy admin hiện tại"
r = c.post(f"/v1/admin/users/{current_admin_id}/deactivate")
assert r.status_code == 409, f"phải chặn khoá admin cuối: {r.text}"
print("chặn khoá admin cuối cùng ............... OK")

# ------------------------------------------------ 13. quản lý người dùng (admin)
RL.reset()
r = c.post("/v1/admin/users", json={"email": "tao-boi-admin@local",
                                    "password": "matkhau000", "role": "user"})
assert r.status_code == 201, r.text
created = r.json()
# hệ thống credits đã gỡ: payload user không còn field `credits`
assert "credits" not in created, created
rl = c.get("/v1/admin/users").json()["users"]
assert any(u["user_id"] == created["user_id"] for u in rl)
assert all("credits" not in u for u in rl), "admin list còn field credits!"
# endpoint cấp credit cũ phải biến mất hẳn (404 — route không tồn tại)
r = c.post(f"/v1/admin/users/{created['user_id']}/credits", json={"delta": -1000})
assert r.status_code == 404, f"endpoint cấp credit còn sống: {r.text}"
r = c.post(f"/v1/admin/users/{created['user_id']}/deactivate")
assert r.status_code == 200 and r.json()["is_active"] is False
# user bị khoá thì không đăng nhập được
RL.reset()
blk = TestClient(app)
assert blk.post("/v1/auth/login",
                json={"email": "tao-boi-admin@local",
                      "password": "matkhau000"}).status_code == 401
print("admin tạo/khoá user (không credits) ..... OK")

# reset mật khẩu -> đá phiên cũ ra
# Lưu ý: KHÔNG dùng `c` để đăng nhập user thường — nó sẽ ghi đè cookie admin của `c`.
RL.reset()
sz = TestClient(app)
sz.post("/v1/auth/login", json={"email": "moi@local", "password": "matkhau789"})
assert sz.get("/v1/auth/me").status_code == 200
with SessionLocal() as db:
    target = db.scalar(__import__("sqlalchemy").select(User).where(User.email == "moi@local"))
assert c.get("/v1/auth/me").json()["role"] == "admin", "client admin đã mất phiên"
r = c.post(f"/v1/admin/users/{target.id}/reset-password", json={"password": "matkhaumoi123"})
assert r.status_code == 200 and r.json()["sessions_revoked"] >= 1, r.text
assert sz.get("/v1/auth/me").status_code == 401, "đổi mật khẩu phải đá phiên cũ"
RL.reset()
fresh = TestClient(app)
assert fresh.post("/v1/auth/login",
                  json={"email": "moi@local", "password": "matkhaumoi123"}).status_code == 200
assert fresh.post("/v1/auth/login",
                  json={"email": "moi@local", "password": "matkhau789"}).status_code == 401
print("đổi mật khẩu đá phiên cũ ............... OK")

# --------------------------------------------------------------- 14. scrypt
h = hash_password("matkhau123")
assert verify_password("matkhau123", h) and not verify_password("sai", h)
assert not verify_password("x", None) and not verify_password("x", "")
assert not verify_password("x", "rác") and not verify_password("x", "scrypt$a$b$c$d$e")
assert not needs_rehash(h) and needs_rehash("scrypt$8192$8$1$YQ$YQ") and needs_rehash("xxx")
assert "matkhau123" not in h
print("scrypt verify/needs_rehash .............. OK")

print("AUTH GUARD PASSED")