"""Phase 3 guard — quản lý AI (Cloud API + Ollama), công đoạn, prompt hệ thống.

Các ca tập trung vào hành vi BẢO MẬT và đúng đắn, không phải "cho có":

  1.  CRUD nhà cung cấp; `kind`/`base_url` sai bị từ chối
  2.  **API key không bao giờ xuất hiện trong payload GET** (chỉ hint + cờ api_key_set)
  3.  PATCH semantics: vắng = giữ nguyên · "" = xoá · có giá trị = thay
  4.  Kiểm tra kết nối: OpenAI `GET /models`, Ollama `GET /api/version`; lỗi mạng trả ok=false
     (KHÔNG raise 500 — UI cần hiển thị được thông báo)
  5.  Liệt kê model cho cả hai kind, đúng field (Ollama có parameter_size/quantization)
  6.  Proxy tải model: chuyển tiếp từng dòng NDJSON (tiến trình) và cả dòng lỗi
  7.  Xoá model; kind không phải Ollama -> 422
  8.  Gán công đoạn + dòng tóm tắt đọc được; xoá nhà cung cấp thì gỡ luôn gán
  9.  Prompt: sửa -> is_default=false; khôi phục mặc định -> về đúng bản trong code
  10. Phân quyền: user thường không gọi được bất kỳ endpoint nào ở đây

Toàn bộ dùng httpx.MockTransport — KHÔNG gọi mạng thật, không cần Ollama.

Run:  cd backend && PYTHONPATH=. python tests/test_providers_admin.py
"""
from __future__ import annotations

import json
import os
import pathlib
import sys
import tempfile

WORK = pathlib.Path(tempfile.mkdtemp(prefix="vv_ai_"))
os.environ["DATABASE_URL"] = f"sqlite:///{WORK}/ai.db"
os.environ["MEDIA_ROOT"] = str(WORK / "media")
os.environ["VOICEVIBE_INLINE"] = "1"
os.environ.pop("VOICEVIBE_API_KEYS", None)
os.environ.pop("VOICEVIBE_ADMIN_KEY", None)

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

import httpx  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app import providers_api as PA  # noqa: E402
from app import ratelimit as RL  # noqa: E402
from app.db import SessionLocal  # noqa: E402
from app.main import app  # noqa: E402
from app.models import AiProvider, User  # noqa: E402
from app.prompts import DEFAULT_PROMPTS, get_prompt  # noqa: E402
from app.security import hash_password  # noqa: E402

c = TestClient(app)
RL.reset()
assert c.post("/v1/auth/setup",
              json={"email": "admin@local", "password": "matkhau123"}).status_code == 201

# ------------------------------------------------ mạng giả: không gọi ra ngoài thật
CALLS: list[tuple[str, str]] = []
CHAT_BODIES: list[dict] = []
OLLAMA_TAGS = {"models": [
    {"name": "qwen2.5:7b-instruct", "size": 4_700_000_000,
     "details": {"parameter_size": "7.6B", "quantization_level": "Q4_K_M"}},
    {"name": "llama3.2:3b", "size": 2_000_000_000,
     "details": {"parameter_size": "3.2B", "quantization_level": "Q4_K_M"}},
]}
OPENAI_MODELS = {"data": [{"id": "deepseek-chat"}, {"id": "deepseek-reasoner"}]}


def handler(req: httpx.Request) -> httpx.Response:
    path = req.url.path
    CALLS.append((req.method, path))
    # giữ nguyên thân request của các lời gọi chat để kiểm prompt có đi ra thật không
    if path.endswith("/chat/completions"):
        CHAT_BODIES.append(json.loads(req.content))
        return httpx.Response(200, json={"choices": [
            {"message": {"content": "mock translation"}}]})
    # host "bad" mô phỏng nhà cung cấp hỏng: mọi đường đều 500
    if req.url.host == "bad":
        return httpx.Response(500, text="boom")
    if path in ("/v1/models", "/models"):
        assert req.headers.get("authorization") == "Bearer sk-test-secret", \
            "API key không được gửi tới nhà cung cấp!"
        return httpx.Response(200, json=OPENAI_MODELS)
    if path == "/api/version":
        return httpx.Response(200, json={"version": "0.12.3"})
    if path == "/api/tags":
        return httpx.Response(200, json=OLLAMA_TAGS)
    if path == "/api/pull":
        body = json.loads(req.content)
        assert body["stream"] is True, "pull phải dùng stream"
        lines = [
            json.dumps({"status": "pulling manifest"}),
            json.dumps({"status": "downloading", "total": 1000, "completed": 250}),
            json.dumps({"status": "downloading", "total": 1000, "completed": 1000}),
            json.dumps({"status": "success"}),
        ]
        return httpx.Response(200, content="\n".join(lines) + "\n",
                              headers={"content-type": "application/x-ndjson"})
    if path == "/api/delete":
        return httpx.Response(200, json={})
    return httpx.Response(404, text="not found")


TRANSPORT = httpx.MockTransport(handler)
_REAL = httpx  # giữ module thật để lấy Client/HTTPError/Timeout


class _FakeHttpx:
    """Chỉ chặn get/request/stream/Client; mọi thuộc tính khác (HTTPError, Timeout…)
    vẫn trỏ về module httpx thật — nếu thay cả module thì `except httpx.HTTPError`
    trong providers_api sẽ nổ AttributeError (đã gặp thật khi viết test này).

    `Client` phải chặn riêng: provider layer (`openai_compat`) tự dựng
    `httpx.Client(...)` chứ không gọi hàm module-level, nên nếu để nguyên thì các
    lời gọi chat trong pipeline sẽ đi ra MẠNG THẬT (đã gặp thật).
    """

    @staticmethod
    def get(url, **kw):
        with _REAL.Client(transport=TRANSPORT, timeout=5) as cl:
            return cl.get(url, **kw)

    @staticmethod
    def request(method, url, **kw):
        with _REAL.Client(transport=TRANSPORT, timeout=5) as cl:
            return cl.request(method, url, **kw)

    @staticmethod
    def stream(method, url, **kw):
        return _REAL.Client(transport=TRANSPORT, timeout=None).stream(method, url, **kw)

    @staticmethod
    def Client(*a, **kw):
        kw["transport"] = TRANSPORT          # buộc mọi client đi qua mạng giả
        return _REAL.Client(*a, **kw)

    def __getattr__(self, name):
        return getattr(_REAL, name)


PA.httpx = _FakeHttpx()
# pipeline dùng httpx của chính module này — không vá thì lời gọi chat đi ra mạng thật
from app.providers import openai_compat as _OA  # noqa: E402

_OA.httpx = _FakeHttpx()

# ------------------------------------------------------------------ 1. CRUD
r = c.post("/v1/admin/providers", json={
    "name": "DeepSeek", "kind": "openai", "base_url": "https://api.deepseek.com/v1/",
    "api_key": "sk-test-secret"})
assert r.status_code == 201, r.text
ds = r.json()
assert ds["api_key_set"] is True and ds["api_key_hint"] == "••••cret", ds
assert ds["base_url"] == "https://api.deepseek.com/v1", "base_url phải được chuẩn hoá"

r = c.post("/v1/admin/providers", json={
    "name": "Ollama local", "kind": "ollama", "base_url": "http://localhost:11434"})
assert r.status_code == 201, r.text
ol = r.json()
assert ol["api_key_set"] is False

assert c.post("/v1/admin/providers", json={
    "name": "x", "kind": "sai", "base_url": "http://x"}).status_code == 422
assert c.post("/v1/admin/providers", json={
    "name": "x", "kind": "openai", "base_url": "  "}).status_code == 422
print("CRUD nhà cung cấp + validate ........... OK")

# ------------------------------------------- 2. key KHÔNG BAO GIỜ lộ trong GET
r = c.get("/v1/admin/providers")
body = r.text
assert "sk-test-secret" not in body, "API KEY THẬT LỌT RA API!"
for p in r.json()["providers"]:
    assert "api_key" not in p, f"payload chứa trường api_key: {p.keys()}"
    assert "api_key_enc" not in p
print("API key không lộ trong GET ............. OK")

# ------------------------------------------------- 3. PATCH semantics của key
with SessionLocal() as db:
    enc_before = db.get(AiProvider, ds["id"]).api_key_enc
# (a) vắng trường -> giữ nguyên
r = c.patch(f"/v1/admin/providers/{ds['id']}", json={"name": "DeepSeek API"})
assert r.status_code == 200 and r.json()["api_key_set"] is True
with SessionLocal() as db:
    assert db.get(AiProvider, ds["id"]).api_key_enc == enc_before, "key bị đổi khi không gửi!"
# (b) chuỗi rỗng -> xoá
r = c.patch(f"/v1/admin/providers/{ds['id']}", json={"api_key": ""})
assert r.status_code == 200 and r.json()["api_key_set"] is False
assert r.json()["api_key_hint"] is None
# (c) có giá trị -> thay
r = c.patch(f"/v1/admin/providers/{ds['id']}", json={"api_key": "sk-test-secret"})
assert r.status_code == 200 and r.json()["api_key_set"] is True
assert "sk-test-secret" not in r.text
print("PATCH semantics (vắng/rỗng/mới) ....... OK")

# ------------------------------------------------------- 4. kiểm tra kết nối
r = c.post(f"/v1/admin/providers/{ds['id']}/test")
assert r.status_code == 200 and r.json()["ok"] is True, r.text
assert "2 model" in r.json()["detail"]
r = c.post(f"/v1/admin/providers/{ol['id']}/test")
assert r.json()["ok"] is True and "0.12.3" in r.json()["detail"], r.text
# đích thật của probe: OpenAI -> {base}/models, Ollama -> {base}/api/version
assert ("GET", "/v1/models") in CALLS, CALLS
assert ("GET", "/api/version") in CALLS, CALLS
print("kiểm tra kết nối (2 loại) ............. OK")

# nhà cung cấp lỗi -> ok=false, KHÔNG raise 500
r = c.post("/v1/admin/providers", json={"name": "Bad", "kind": "ollama",
                                        "base_url": "http://bad"})
bad_id = r.json()["id"]
r = c.post(f"/v1/admin/providers/{bad_id}/test")
assert r.status_code == 200, "probe lỗi phải trả ok=false, không phải 500"
assert r.json()["ok"] is False and "500" in r.json()["detail"], r.json()
print("probe lỗi -> ok=false (không 500) ..... OK")

# -------------------------------------------------------- 5. liệt kê model
r = c.get(f"/v1/admin/providers/{ol['id']}/models")
assert r.status_code == 200, r.text
ms = r.json()["models"]
assert [m["name"] for m in ms] == ["qwen2.5:7b-instruct", "llama3.2:3b"], ms
assert ms[0]["parameter_size"] == "7.6B" and ms[0]["quantization"] == "Q4_K_M", ms[0]
r = c.get(f"/v1/admin/providers/{ds['id']}/models")
assert [m["name"] for m in r.json()["models"]] == ["deepseek-chat", "deepseek-reasoner"]
print("liệt kê model (Ollama + OpenAI) ....... OK")

# --------------------------------------------------- 6. proxy tải model (stream)
with c.stream("POST", f"/v1/admin/providers/{ol['id']}/pull",
              json={"model": "qwen2.5:7b-instruct"}) as resp:
    assert resp.status_code == 200, resp.read()
    lines = [json.loads(x) for x in resp.iter_lines() if x.strip()]
assert [x.get("status") for x in lines] == ["pulling manifest", "downloading",
                                            "downloading", "success"], lines
assert lines[1]["total"] == 1000 and lines[1]["completed"] == 250
assert lines[2]["completed"] == 1000
print("proxy tải model -> NDJSON tiến trình .. OK")

# kind không phải Ollama -> 422 (không gọi ra ngoài)
r = c.post(f"/v1/admin/providers/{ds['id']}/pull", json={"model": "x"})
assert r.status_code == 422, r.text
r = c.post(f"/v1/admin/providers/{ol['id']}/pull", json={"model": "  "})
assert r.status_code == 422
print("pull chỉ dành cho Ollama .............. OK")

# ------------------------------------------------------------- 7. xoá model
r = c.delete(f"/v1/admin/providers/{ol['id']}/models/qwen2.5:7b-instruct")
assert r.status_code == 200 and r.json()["deleted"] is True, r.text
assert c.delete(f"/v1/admin/providers/{ds['id']}/models/x").status_code == 422
print("xoá model .............................. OK")

# ---------------------------------------------------------- 8. gán công đoạn
r = c.put("/v1/admin/stages/translate",
          json={"provider_id": ds["id"], "model": "deepseek-chat", "order": 0})
assert r.status_code == 200, r.text
r = c.get("/v1/admin/stages")
st = r.json()
assert st["stages"]["translate"][0]["model"] == "deepseek-chat"
assert st["stages"]["translate"][0]["provider_name"] == "DeepSeek API"
assert st["summary"]["translate"] == "deepseek-chat qua DeepSeek API", st["summary"]
# công đoạn chưa gán -> tóm tắt nói rõ đang dùng đường mặc định
assert "local" in st["summary"]["stt"] or "mặc định" in st["summary"]["stt"]
assert c.put("/v1/admin/stages/sai", json={"model": "x"}).status_code == 422
assert c.put("/v1/admin/stages/tts",
             json={"provider_id": "khong-ton-tai", "model": "x"}).status_code == 404
print("gán công đoạn + tóm tắt đọc được ...... OK")

# pipeline dùng được cấu hình này (stage_chain trả provider + key đã giải mã)
with SessionLocal() as db:
    chain = PA.stage_chain("translate", db)
assert chain and chain[0]["model"] == "deepseek-chat"
assert chain[0]["api_key"] == "sk-test-secret", "key phải được giải mã cho pipeline"
assert chain[0]["base_url"] == "https://api.deepseek.com/v1"
print("stage_chain cho pipeline .............. OK")

# xoá nhà cung cấp -> gỡ luôn gán công đoạn (không còn trỏ vào hư không)
r = c.delete(f"/v1/admin/providers/{ds['id']}")
assert r.status_code == 200
r = c.get("/v1/admin/stages")
assert r.json()["stages"]["translate"] == [], r.json()["stages"]["translate"]
print("xoá provider -> gỡ gán công đoạn ...... OK")

# --------------------------------------------------------------- 9. prompt
r = c.get("/v1/admin/prompts")
ps = {p["task_key"]: p for p in r.json()["prompts"]}
assert set(ps) == set(DEFAULT_PROMPTS), ps.keys()
assert ps["translate"]["is_default"] is True
assert "{source}" in ps["translate"]["content"]
assert ps["retranslate_timing"]["variables"] == ["source", "target", "text", "max_chars"]

r = c.put("/v1/admin/prompts/translate", json={"content": "DỊCH NGẮN: {text}"})
assert r.status_code == 200 and r.json()["is_default"] is False, r.text
assert get_prompt("translate") == "DỊCH NGẮN: {text}"
r = c.get("/v1/admin/prompts")
assert {p["task_key"]: p for p in r.json()["prompts"]}["translate"]["is_default"] is False
# biến chưa điền -> trả nguyên template, không crash job
from app.prompts import render  # noqa: E402

assert render("translate") == "DỊCH NGẮN: {text}"
print("sửa prompt + render an toàn .......... OK")

assert c.put("/v1/admin/prompts/translate", json={"content": "   "}).status_code == 422
r = c.post("/v1/admin/prompts/translate/reset")
assert r.status_code == 200 and r.json()["is_default"] is True
assert get_prompt("translate") == DEFAULT_PROMPTS["translate"]["content"]
assert c.post("/v1/admin/prompts/khong-co/reset").status_code == 404
print("khôi phục mặc định ................... OK")

# ------------------------------------- 9b. prompt DB -> thực sự đi ra request
# Đây là đường nối mà Giai đoạn 3 tạo ra và là loại lỗi im lặng điển hình: sửa
# prompt trong /admin, lưu thành công, API trả 200 — mà nội dung gửi cho nhà
# cung cấp vẫn là bản mặc định. Không có gì trong UI phát hiện được điều đó.
# Vì vậy phải khẳng định trên THÂN REQUEST thật, không chỉ trên giá trị trong DB.
r = c.post("/v1/admin/providers", json={
    "name": "P", "kind": "openai", "base_url": "https://api.p.example/v1",
    "api_key": "sk-test-secret"})
p_id = r.json()["id"]
c.put("/v1/admin/stages/translate",
      json={"provider_id": p_id, "model": "deepseek-chat", "order": 0})

from app.pipelines.translate import build_translator  # noqa: E402

CHAT_BODIES.clear()
t = build_translator("vi", "en")
assert type(t).__name__ == "CloudChatTranslator", type(t).__name__
# (a) system prompt lấy từ DB, đã render biến
c.put("/v1/admin/prompts/translate",
      json={"content": "RENDER [{source}->{target}]: {text}"})
t = build_translator("vi", "en")
assert t.system == "RENDER [vi->en]: {text}", t.system
t.translate("xin chào")
assert CHAT_BODIES, "không có request chat nào được gửi!"
sent = CHAT_BODIES[-1]
assert sent["model"] == "deepseek-chat", sent["model"]
assert sent["messages"][0]["content"] == "RENDER [vi->en]: {text}", sent["messages"]
assert sent["messages"][1]["content"] == "xin chào", sent["messages"]
print("prompt trong DB đi ra request ......... OK")

# (b) prompt 'retranslate_timing' cũng phải đi ra — đây là đường timing-fit dùng.
# Lưu ý: đường này gửi prompt ở message USER (system để rỗng) vì prompt đã bao
# trọn câu cần dịch ở cuối template.
CHAT_BODIES.clear()
c.put("/v1/admin/prompts/retranslate_timing",
      json={"content": "NGẮN HƠN {max_chars} ký tự cho {text}"})
t.retranslate_shorter("một câu dài", 42)
_sent = CHAT_BODIES[-1]["messages"]
assert _sent[0]["content"] == "", _sent
assert _sent[1]["content"] == "NGẮN HƠN 42 ký tự cho một câu dài", _sent
print("prompt dịch-lại-timing đi ra request .. OK")

# (c) khôi phục mặc định -> request quay về đúng bản trong code, ĐÃ điền biến
CHAT_BODIES.clear()
c.put("/v1/admin/prompts/translate", json={"content": "TẠM: {text}"})
c.post("/v1/admin/prompts/translate/reset")
t2 = build_translator("vi", "en")
assert "TẠM" not in t2.system, t2.system
assert "from vi to en" in t2.system, t2.system
assert "{source}" not in t2.system, t2.system
print("reset prompt -> quay về bản trong code OK")

# (d) HỒI QUY cho lỗi thật đã gặp: `str.format` ném KeyError khi thiếu MỘT biến,
# và bản cũ bắt lỗi rồi trả về nguyên template -> MẤT HẾT biến, không chỉ biến
# thiếu. Nghĩa là system prompt mặc định gửi cho model đúng chuỗi
# "from {source} to {target}" — model không hề biết cặp ngôn ngữ.
from app.prompts import render as _render  # noqa: E402

_sys = _render("translate", source="vi", target="en")   # thiếu `text` (đúng thực tế)
assert "{source}" not in _sys and "{target}" not in _sys, \
    f"thiếu một biến làm mất luôn các biến khác: {_sys!r}"
assert "from vi to en" in _sys, _sys
# biến thiếu vẫn phải giữ nguyên chỗ trống (không crash, không nuốt)
c.post("/v1/admin/prompts/retranslate_timing/reset")
_part = _render("retranslate_timing", source="vi", target="en")
assert "{source}" not in _part and "{target}" not in _part, _part
assert "{max_chars}" in _part and "{text}" in _part, _part
# giá trị vừa thay KHÔNG được bị thay tiếp (bản dịch chứa `{source}`)
assert _render("retranslate_timing", source="vi", target="en",
               text="giữ {source} nguyên", max_chars=5).endswith("giữ {source} nguyên")
print("hồi quy: thiếu biến không mất biến .. OK")
c.delete(f"/v1/admin/providers/{p_id}")

# ------------------------------------------------------------ 10. phân quyền
RL.reset()
with SessionLocal() as db:
    db.add(User(email="thuong@local", role="user",
                password_hash=hash_password("matkhau456")))
    db.commit()
uc = TestClient(app)
RL.reset()
assert uc.post("/v1/auth/login",
               json={"email": "thuong@local", "password": "matkhau456"}).status_code == 200
for method, path in [("get", "/v1/admin/providers"), ("get", "/v1/admin/stages"),
                     ("get", "/v1/admin/prompts"), ("post", "/v1/admin/providers")]:
    r = uc.get(path) if method == "get" else uc.post(path, json={})
    assert r.status_code in (401, 403), f"{method} {path} -> {r.status_code} (phải bị chặn)"
print("user thường bị chặn toàn bộ .......... OK")

print("PROVIDERS ADMIN GUARD PASSED")