"""Thư viện Prompt guard — prompt cá nhân theo user + chọn khi tạo job Dịch.

Mỗi nhóm là một yêu cầu thiết kế phải được MÁY kiểm:

  1.  401 chưa đăng nhập (endpoint user + admin)
  2.  CRUD + list RIÊNG TƯ (chỉ thấy prompt của mình) + validate 422
  3.  Ownership: user khác đụng prompt của mình → 404 (không 403 — không lộ tồn tại)
  4.  Biến tự dò unique giữ thứ tự; tags chuẩn hoá; vượt 8 tag → 422
  5.  History snapshot khi lưu + khôi phục version (lịch sử chỉ đi tới)
  6.  Cap 20 bản lịch sử — tràn thì bỏ bản cũ nhất
  7.  Job Dịch nhận prompt_id (ownership trước khi tạo; type khác → 422)
  8.  Override đi ra request THẬT: system message == prompt user ĐÃ render biến
  9.  Không prompt_id → hành vi cũ (system prompt mặc định, params không có key)
  10. Prompt bị xoá giữa lúc tạo job và lúc chạy → job dùng prompt mặc định +
      params["prompt_fallback"] (không chết job — resolve worker-safe)
  11. ChainTranslator: entry 1 hỏng → entry 2 vẫn nhận CÙNG override
  12. Admin endpoint read-only: thấy prompt của mọi user + email; user thường 403

Run:  cd backend && PYTHONPATH=. python tests/test_prompt_library.py
"""
from __future__ import annotations

import json
import os
import pathlib
import sys
import tempfile

WORK = pathlib.Path(tempfile.mkdtemp(prefix="vv_pl_"))
os.environ["DATABASE_URL"] = f"sqlite:///{WORK}/pl.db"
os.environ["MEDIA_ROOT"] = str(WORK / "media")
os.environ["VOICEVIBE_INLINE"] = "1"
os.environ.pop("VOICEVIBE_API_KEYS", None)
os.environ.pop("VOICEVIBE_ADMIN_KEY", None)

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

import httpx  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app import ratelimit as RL  # noqa: E402
from app.db import SessionLocal  # noqa: E402
from app.main import app  # noqa: E402
from app.models import User  # noqa: E402
from app.security import hash_password  # noqa: E402

c = TestClient(app)
RL.reset()
# --------------------------------------------------------- 1. chưa đăng nhập
# BẮT BUỘC trước /setup: setup trả cookie phiên admin và TestClient GIỮ luôn —
# gọi sau setup thì request "chưa đăng nhập" của c lại mang cookie admin.
anon = TestClient(app)
RL.reset()
for method, path in [("get", "/v1/prompts"), ("post", "/v1/prompts"),
                     ("get", "/v1/admin/prompt-library")]:
    r = anon.get(path) if method == "get" else anon.post(path, json={})
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

# -------------------------------------------- 2. CRUD + list riêng tư + 422
r = A.post("/v1/prompts", json={
    "name": "Dịch TikTok ngắn",
    "content": "Translate {source} to {target}. Style: TikTok, super short.",
    "description": "Phong cách video ngắn", "tags": ["tiktok", "ngắn"]})
assert r.status_code == 201, r.text
P1 = r.json()
assert P1["variables"] == ["source", "target"], P1["variables"]
assert P1["version"] == 1 and P1["history_count"] == 0

r = A.post("/v1/prompts", json={"name": "Học thuật", "content": "Formal academic {source}->{target}."})
assert r.status_code == 201
r = A.get("/v1/prompts")
assert r.status_code == 200
d = r.json()
assert d["total"] == 2 and all(p["content_preview"] for p in d["prompts"])
assert all("content" not in p for p in d["prompts"]), "list không trả content đầy đủ"

# list của B phải trống (riêng tư)
assert B.get("/v1/prompts").json()["total"] == 0

# validate
assert A.post("/v1/prompts", json={"name": "", "content": "x"}).status_code == 422
assert A.post("/v1/prompts", json={"name": "x", "content": "  "}).status_code == 422
assert A.post("/v1/prompts", json={"name": "x", "content": "y" * 20001}).status_code == 422
assert A.post("/v1/prompts", json={"name": "x", "content": "y", "tags": [f"t{i}" for i in range(9)]}).status_code == 422
print("2. CRUD + riêng tư + validate 422 ................. OK")

# ------------------------------------------------------------- 3. ownership
for method, path, body in [
    ("get", f"/v1/prompts/{P1['id']}", None),
    ("put", f"/v1/prompts/{P1['id']}", {"content": "hack"}),
    ("post", f"/v1/prompts/{P1['id']}/restore", {"version": 1}),
    ("delete", f"/v1/prompts/{P1['id']}", None),
]:
    if method == "get":
        r = B.get(path)
    elif method == "put":
        r = B.put(path, json=body)
    elif method == "post":
        r = B.post(path, json=body)
    else:
        r = B.delete(path)
    assert r.status_code == 404, f"{method} -> {r.status_code} (phải 404 không 403)"
print("3. ownership: user khác → 404 ..................... OK")

# ---------------------------------------- 4. variables/tags chuẩn hoá
r = A.post("/v1/prompts", json={
    "name": "biến", "content": "Dịch {source} sang {target}, {source} {custom}",
    "tags": ["a", " a ", "", "a", "b"]})
d = r.json()
assert d["variables"] == ["source", "target", "custom"], d["variables"]
assert d["tags"] == ["a", "b"], d["tags"]
print("4. biến tự dò + tags chuẩn hoá .................... OK")

# ------------------------------------------------- 5. history + restore
r = A.put(f"/v1/prompts/{P1['id']}", json={"content": "Bản v2.", "note": "đổi giọng"})
d = r.json()
assert d["history_count"] == 1 and d["version"] == 2, d
assert d["history"][0]["v"] == 1 and d["history"][0]["content"].startswith("Translate"), d["history"]
r = A.put(f"/v1/prompts/{P1['id']}", json={"content": "Bản v3."})
assert r.json()["history_count"] == 2
# restore v1: content quay về bản gốc, bản hiện tại (v3) được chụp thành v4
r = A.post(f"/v1/prompts/{P1['id']}/restore", json={"version": 1})
assert r.status_code == 200
d = r.json()
assert d["content"].startswith("Translate"), d["content"]
assert [e["v"] for e in d["history"]] == [3, 2, 1], d["history"]
assert A.post(f"/v1/prompts/{P1['id']}/restore", json={"version": 99}).status_code == 404
print("5. history snapshot + restore ..................... OK")

# ------------------------------------------------------------ 6. cap 20
r = A.post("/v1/prompts", json={"name": "cap", "content": "v-gốc"})
CAP = r.json()
for i in range(25):
    A.put(f"/v1/prompts/{CAP['id']}", json={"content": f"v-{i}"})
d = A.get(f"/v1/prompts/{CAP['id']}").json()
assert len(d["history"]) == 20, len(d["history"])
assert d["history"][0]["content"] == "v-23", "mới nhất ở đầu"
assert d["history"][-1]["content"] == "v-4", "bản cũ nhất bị pop"
print("6. cap 20 bản lịch sử ............................ OK")

# --------------------------------------------------------- 7. job + prompt
PICK = A.post("/v1/prompts", json={"name": "job prompt", "content": "Casual {source}->{target}."}).json()
r = A.post("/v1/jobs", json={"type": "translate", "text": "xin chào",
                             "source_lang": "vi", "target_lang": "en",
                             "prompt_id": PICK["id"]})
assert r.status_code in (200, 202), r.text
JID = r.json()["job_id"]
d = A.get(f"/v1/jobs/{JID}").json()
assert d["params"].get("prompt_id") == PICK["id"]
# prompt của B → 404; id lạ → 404; type khác → 422
B2 = B.post("/v1/jobs", json={"type": "translate", "text": "x", "prompt_id": PICK["id"]})
assert B2.status_code == 404, B2.text
assert A.post("/v1/jobs", json={"type": "translate", "text": "x", "prompt_id": "khongtonai"}).status_code == 404
assert A.post("/v1/jobs", json={"type": "tts", "text": "x", "prompt_id": PICK["id"]}).status_code == 422
print("7. job nhận prompt_id + ownership ................. OK")

# --------------------------- 8+9. override đi ra request THẬT (inline dispatch)
from app import providers_api as PA  # noqa: E402
from app.providers import openai_compat as _OA  # noqa: E402

CHAT_BODIES: list[dict] = []


def handler(req: httpx.Request) -> httpx.Response:
    if req.url.path.endswith("/chat/completions"):
        CHAT_BODIES.append(json.loads(req.content))
        return httpx.Response(200, json={"choices": [{"message": {"content": "mock translation"}}]})
    return httpx.Response(404, text="nf")


TRANSPORT = httpx.MockTransport(handler)
_REAL = httpx


class _FakeHttpx:
    @staticmethod
    def Client(*a, **kw):
        kw["transport"] = TRANSPORT
        return _REAL.Client(*a, **kw)

    def __getattr__(self, name):
        return getattr(_REAL, name)


_OA.httpx = _FakeHttpx()

# cấu hình đường settings cloud (đơn giản nhất — không đụng stage)
os.environ["TRANSLATE_BASE_URL"] = "https://api.example/v1"
os.environ["TRANSLATE_API_KEY"] = "sk-pl"
os.environ["TRANSLATE_MODEL"] = "test-model"

r = A.post("/v1/jobs", json={"type": "translate", "text": "xin chào",
                             "source_lang": "vi", "target_lang": "en",
                             "prompt_id": PICK["id"]})
assert r.status_code in (200, 202)
J2 = r.json()["job_id"]
d = A.get(f"/v1/jobs/{J2}").json()
assert d["status"] == "done", d
assert len(CHAT_BODIES) >= 1
sys_msg = CHAT_BODIES[-1]["messages"][0]["content"]
assert sys_msg == "Casual vi->en.", f"system prompt phải là prompt user ĐÃ render biến: {sys_msg!r}"
assert CHAT_BODIES[-1]["messages"][1]["content"] == "xin chào"

# không prompt_id → system prompt mặc định (render từ bảng prompts)
n_before = len(CHAT_BODIES)
r = A.post("/v1/jobs", json={"type": "translate", "text": "xin chào",
                             "source_lang": "vi", "target_lang": "en"})
assert r.status_code in (200, 202)
J3 = r.json()["job_id"]
d = A.get(f"/v1/jobs/{J3}").json()
assert d["status"] == "done" and "prompt_id" not in d["params"]
sys_msg = CHAT_BODIES[-1]["messages"][0]["content"]
assert "from vi to en" in sys_msg, sys_msg
print("8+9. override render biến đi ra request thật ...... OK")

# ------------------------------------------- 10. prompt xoá trước khi worker chạy
# dispatch INLINE chạy NGAY trong POST (prompt còn sống lúc pipeline resolve),
# nên dựng job row thủ công, xoá prompt, rồi gọi dispatch_inline — mô phỏng đúng
# thứ tự thật với Celery: job nằm đợi, user xoá prompt, worker mới nhặt job.
from app.tasks import dispatch_inline  # noqa: E402
from app.models import Job as JobRow  # noqa: E402

PICK2 = A.post("/v1/prompts", json={"name": "sẽ xoá", "content": "KHÔNG được dùng {source}."}).json()
with SessionLocal() as db:
    jr = JobRow(user_id=A.get("/v1/auth/me").json()["user_id"], type="translate",
                params={"type": "translate", "text": "hello lại", "source_lang": "vi",
                        "target_lang": "en", "prompt_id": PICK2["id"]})
    db.add(jr)
    db.commit()
    J4 = jr.id
assert A.delete(f"/v1/prompts/{PICK2['id']}").status_code == 200
res = dispatch_inline(J4, {"type": "translate", "text": "hello lại",
                           "source_lang": "vi", "target_lang": "en",
                           "prompt_id": PICK2["id"]})
assert res.get("ok") is True, res
d = A.get(f"/v1/jobs/{J4}").json()
assert d["status"] == "done", d
assert d["params"].get("prompt_fallback") == "not found", d["params"]
assert "from vi to en" in CHAT_BODIES[-1]["messages"][0]["content"]
print("10. prompt xoá → fallback + ghi chú, job không chết OK")

# --------------------------------------------------- 11. ChainTranslator override
from app.pipelines.translate import CloudChatTranslator, ChainTranslator  # noqa: E402
from app.providers.registry import ProviderChain  # noqa: E402


class _Die:
    def translate(self, t):
        raise RuntimeError("entry 1 hỏng")

    def retranslate_shorter(self, t, m):
        raise RuntimeError("entry 1 hỏng")


n_calls = len(CHAT_BODIES)
tr = ChainTranslator(ProviderChain([
    _Die(),
    CloudChatTranslator("https://api.example/v1", "sk-x", "m2", "vi", "en",
                        system_prompt="PROMPT RIÊNG"),
]))
assert tr.translate("abc") == "mock translation"
sys_msg = CHAT_BODIES[-1]["messages"][0]["content"]
assert sys_msg == "PROMPT RIÊNG", sys_msg
print("11. ChainTranslator: fallback giữ nguyên override . OK")

# ------------------------------------------------------- 12. admin endpoint
ra = c.get("/v1/admin/prompt-library")
assert ra.status_code == 200
d = ra.json()
assert d["total"] >= 1
assert all(i.get("user_email") for i in d["items"]), d["items"]
ra = c.get("/v1/admin/prompt-library", params={"user_id": d["items"][0]["user_id"]})
assert ra.status_code == 200
assert B.get("/v1/admin/prompt-library").status_code == 403
print("12. admin read-only + filter user .................. OK")

print("PROMPT LIBRARY GUARD PASSED")
