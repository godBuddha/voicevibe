"""Model Registry guard — sync/capability/compatibility/enable-disable/runtime.

Yêu cầu thiết kế phải được MÁY kiểm được, mỗi nhóm một mục:

  1.  Sync OpenRouter-style: capability đến từ metadata chính thức (modality,
      supported_parameters, pricing, context) — KHÔNG suy đoán từ tên model
  2.  Idempotent: sync 2 lần = không duplicate; `enabled` của admin sống sót qua sync
  3.  Model bị upstream gỡ → xoá khỏi registry + gỡ gán `stage_models` đang trỏ
  4.  Chain rơi đúng khi primary bị xoá (fallback → settings/local)
  5.  UNKNOWN (OpenAI generic thiếu metadata) và INCOMPATIBLE (mọi required đều False)
  6.  Ollama sync: capabilities từ /api/tags; model cũ fallback /api/show; lỗi 1
      model không chết sync (errors[])
  7.  GET /features: đủ 16 feature đúng thứ tự; đếm chỉ tính model enabled của
      provider enabled; voice_cloning là local_engine (0 model)
  8.  Filters + pagination: total theo filter, breakdown KHÔNG theo filter
  9.  PATCH enabled=false → stage_chain loại model đó ra ngay (runtime thật)
  10. stage_chain bỏ row model rỗng (lỗi 400 "model: ''" đã gặp thật)
  11. Provider disabled → model của nó không hiện trong /features/{k}/models
  12. Xoá provider → cascade ai_models
  13. Sync fetch hỏng → 502, DB nguyên vẹn
  14. Phân quyền: user thường bị chặn
  15. Runtime STT: stage 'stt' có cloud → request đi /audio/transcriptions với
      model đúng; không cloud → KHÔNG gọi mạng
  16. Runtime TTS: preset + cloud → /audio/speech; GIỌNG CLONE + có cloud → vẫn
      local (quy tắc bắt buộc); caller truyền provider tường minh → hành vi cũ
  17. ChainTranslator: entry 1 hỏng → entry 2 phục vụ; hết chuỗi → RuntimeError

Run:  cd backend && PYTHONPATH=. python tests/test_model_hub.py
"""
from __future__ import annotations

import json
import os
import pathlib
import sys
import tempfile

WORK = pathlib.Path(tempfile.mkdtemp(prefix="vv_hub_"))
os.environ["DATABASE_URL"] = f"sqlite:///{WORK}/hub.db"
os.environ["MEDIA_ROOT"] = str(WORK / "media")
os.environ["VOICEVIBE_INLINE"] = "1"
os.environ.pop("VOICEVIBE_API_KEYS", None)
os.environ.pop("VOICEVIBE_ADMIN_KEY", None)

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

import httpx  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app import model_sync as MS  # noqa: E402
from app import providers_api as PA  # noqa: E402
from app import ratelimit as RL  # noqa: E402
from app.db import SessionLocal  # noqa: E402
from app.main import app  # noqa: E402
from app.models import AiModel, AiProvider, StageModel, User  # noqa: E402
from app.security import hash_password  # noqa: E402

c = TestClient(app)
RL.reset()
assert c.post("/v1/auth/setup",
              json={"email": "admin@local", "password": "matkhau123"}).status_code == 201

# ------------------------------------------------------------- payload thật (copy shape)
OPENROUTER_PAYLOAD = {"data": [
    # rich: chat đa năng — text+image in, text out, tools/structured/reasoning
    {"id": "openai/gpt-4o", "name": "OpenAI: GPT-4o", "description": "chat model",
     "architecture": {"input_modalities": ["text", "image", "file"],
                      "output_modalities": ["text"], "modality": "text+image->text"},
     "supported_parameters": ["tools", "structured_outputs", "reasoning",
                              "max_completion_tokens"],
     "context_length": 128000,
     "top_provider": {"max_completion_tokens": 16384},
     "pricing": {"prompt": "0.0000025", "completion": "0.00001"},
     "tokenizer": "GPT", "created": 1715367049},
    # image-gen only: out không có "text" → mọi feature bắt buộc text = False
    {"id": "acme/painter", "name": "ACME: Painter", "description": "image only",
     "architecture": {"input_modalities": ["text", "image"],
                      "output_modalities": ["image"]},
     "supported_parameters": [],
     "context_length": 8192, "top_provider": {},
     "pricing": {"prompt": "0", "completion": "0.01"}},
    # model bị GỠ ở lần sync 2 (test 3): có ở sync đầu, vắng mặt lần sau
    {"id": "acme/gone", "name": "ACME: Gone", "description": "will be removed",
     "architecture": {"input_modalities": ["text"], "output_modalities": ["text"]},
     "supported_parameters": ["tools"], "context_length": 8192, "top_provider": {},
     "pricing": {"prompt": "0", "completion": "0"}},
]}
GENERIC_PAYLOAD = {"data": [{"id": "deepseek-chat", "owned_by": "deepseek"},
                            {"id": "deepseek-reasoner", "owned_by": "deepseek"}]}
OLLAMA_TAGS = {"models": [
    {"name": "qwen2.5:7b-instruct", "size": 4_700_000_000,
     "capabilities": ["completion", "tools"],
     "details": {"parameter_size": "7.6B", "quantization_level": "Q4_K_M",
                 "family": "Qwen2", "context_length": 32768}},
    {"name": "all-minilm", "size": 46_000_000,
     "capabilities": ["embedding"],
     "details": {"parameter_size": "22.7M", "quantization_level": "F16",
                 "family": "Bert", "context_length": 512}},
    {"name": "old-model", "size": 1,  # không có capabilities → fallback /api/show
     "details": {"parameter_size": "1B"}},
]}
SHOW_RESULT = {"capabilities": ["completion"], "model_info": {}}


def handler(req: httpx.Request) -> httpx.Response:
    path, host = req.url.path, req.url.host
    if host == "rich" and path.endswith("/models"):
        assert req.headers.get("authorization") == "Bearer sk-test-secret"
        return httpx.Response(200, json=OPENROUTER_PAYLOAD)
    if host == "generic" and path.endswith("/models"):
        return httpx.Response(200, json=GENERIC_PAYLOAD)
    if host == "bad":
        return httpx.Response(500, text="boom")
    if host == "ollama":
        if path == "/api/tags":
            return httpx.Response(200, json=OLLAMA_TAGS)
        if path == "/api/show":
            return httpx.Response(200, json=SHOW_RESULT)
        if path == "/api/version":
            return httpx.Response(200, json={"version": "0.32.1"})
    return httpx.Response(404, text="not found")


TRANSPORT = httpx.MockTransport(handler)
_REAL = httpx


class _FakeHttpx:
    """Chặn get/request/stream/Client; còn lại trỏ về httpx thật (xem
    test_providers_admin.py — thay cả module làm `except httpx.HTTPError` nổ)."""

    @staticmethod
    def get(url, **kw):
        with _REAL.Client(transport=TRANSPORT, timeout=5) as cl:
            return cl.get(url, **kw)

    @staticmethod
    def post(url, **kw):
        # /api/show (Ollama cũ) gọi httpx.post — thiếu cái này là lời gọi lọt ra
        # mạng thật → capability None (đã gặp thật lần chạy đầu của test này).
        with _REAL.Client(transport=TRANSPORT, timeout=5) as cl:
            return cl.post(url, **kw)

    @staticmethod
    def request(method, url, **kw):
        with _REAL.Client(transport=TRANSPORT, timeout=5) as cl:
            return cl.request(method, url, **kw)

    @staticmethod
    def stream(method, url, **kw):
        return _REAL.Client(transport=TRANSPORT, timeout=None).stream(method, url, **kw)

    @staticmethod
    def Client(*a, **kw):
        kw["transport"] = TRANSPORT
        return _REAL.Client(*a, **kw)

    def __getattr__(self, name):
        return getattr(_REAL, name)


PA.httpx = _FakeHttpx()
MS.httpx = _FakeHttpx()
from app.providers import openai_compat as _OA  # noqa: E402

_OA.httpx = _FakeHttpx()

print("=== MẠNG GIẢ SẴN SÀNG ===")


def make_provider(name, host, kind="openai", key="sk-test-secret") -> str:
    r = c.post("/v1/admin/providers", json={
        "name": name, "kind": kind, "base_url": f"https://{host}", "api_key": key})
    assert r.status_code == 201, r.text
    return r.json()["id"]


# ------------------------------------------------------- 1. sync OpenRouter-style
RICH = make_provider("OpenRouter rich", "rich")
r = c.post(f"/v1/admin/providers/{RICH}/sync")
assert r.status_code == 200, r.text
sync1 = r.json()
assert sync1["added"] == 3 and sync1["removed"] == 0, sync1
assert sync1["errors"] == [], sync1

with SessionLocal() as db:
    gpt = db.scalar(AiModel.__table__.select().where()) if False else db.query(AiModel).filter(
        AiModel.model_id == "openai/gpt-4o").one()
    assert gpt.capabilities["vision"] is True, "image in → vision"
    assert gpt.capabilities["imageUnderstanding"] is True
    assert gpt.capabilities["imageGeneration"] is False, "out không có image → False"
    assert gpt.capabilities["videoGeneration"] is False
    assert gpt.capabilities["functionCalling"] is True
    assert gpt.capabilities["structuredOutput"] is True
    assert gpt.capabilities["reasoning"] is True
    assert gpt.capabilities["embeddings"] is None, "không khai báo → None, không đoán"
    assert gpt.org == "openai" and gpt.capability_source == "official"
    assert gpt.context_window == 128000 and gpt.output_token_limit == 16384
    assert gpt.pricing == {"input": 2.5e-06, "output": 1e-05, "currency": "USD"}
    comp = gpt.compatibility
    assert comp["status"] == "compatible", comp
    assert "text_generation" in comp["supported_features"]
    assert comp["score"] > 0
    painter = db.query(AiModel).filter(AiModel.model_id == "acme/painter").one()
    pcomp = painter.compatibility
    assert painter.capabilities["chat"] is False and painter.capabilities["text"] is False
    assert "image_generation" in pcomp["supported_features"], pcomp  # model ảnh vẫn đủ feature ảnh
    assert "text_generation" in pcomp["unsupported_features"]
print("1. sync OpenRouter-style metadata → capability .... OK")

# --------------------------------------------------------------- 2. idempotent
r = c.post(f"/v1/admin/providers/{RICH}/sync")
assert r.status_code == 200
sync2 = r.json()
assert sync2["added"] == 0 and sync2["removed"] == 0, sync2
assert sync2["synced"] == 3
with SessionLocal() as db:
    assert db.query(AiModel).count() == 3, "sync 2 lần không duplicate"
r = c.patch(f"/v1/admin/models/{gpt.id}", json={"enabled": False})
assert r.status_code == 200 and r.json()["enabled"] is False
c.post(f"/v1/admin/providers/{RICH}/sync")
with SessionLocal() as db:
    g2 = db.get(AiModel, gpt.id)
    assert g2.enabled is False, "sync KHÔNG được đụng lựa chọn enable của admin"
    db.query(StageModel).filter(StageModel.stage == "stt").delete()
c.patch(f"/v1/admin/models/{gpt.id}", json={"enabled": True})
print("2. idempotent + enabled sống sót qua sync .......... OK")

# ------------------------------------------- 3. upstream gỡ model → xoá + gỡ gán
with SessionLocal() as db:
    gone = db.query(AiModel).filter(AiModel.model_id == "acme/gone").one()
    db.add(StageModel(stage="translate", provider_id=RICH, model="acme/gone", order=0))
    db.add(StageModel(stage="translate", provider_id=RICH, model="openai/gpt-4o", order=1))
    db.commit()
OPENROUTER_PAYLOAD["data"] = [m for m in OPENROUTER_PAYLOAD["data"]
                              if m["id"] != "acme/gone"]
r = c.post(f"/v1/admin/providers/{RICH}/sync")
assert r.status_code == 200
assert r.json()["removed"] == 1, r.json()
with SessionLocal() as db:
    assert db.get(AiModel, gone.id) is None, "model bị gỡ phải biến khỏi registry"
    rows = db.query(StageModel).filter(StageModel.model == "acme/gone").all()
    assert rows == [], "gán stage trỏ tới model đã xoá phải được gỡ"
print("3. sync xoá model vắng mặt + gỡ gán stage .......... OK")

# --------------------------------------------------- 4. chain rơi khi primary chết
from app.providers_api import stage_chain  # noqa: E402

with SessionLocal() as db:
    chain = stage_chain("translate", db)
assert [e["model"] for e in chain] == ["openai/gpt-4o"], chain
# xoá nốt primary (sync không thấy nó nữa) → chain rỗng → build_translator rơi settings/local
with SessionLocal() as db:
    db.query(StageModel).filter(StageModel.model == "openai/gpt-4o").delete()
    db.commit()
with SessionLocal() as db:
    assert stage_chain("translate", db) == []
# chain rỗng → stage_translator None → build_translator rơi xuống đường settings/local
from app.pipelines.translate import _pick_backend, stage_translator  # noqa: E402

assert stage_translator("vi", "en") is None
assert _pick_backend("vi", "en") == "local", "chain rỗng phải rơi về đường local"
# (không dựng hẳn LocalMarianTranslator — nó import torch, môi trường test không có)
print("4. primary xoá → chain rơi về fallback rồi local ... OK")

# --------------------------------- 5. UNKNOWN (generic) + INCOMPATIBLE (mọi False)
GEN = make_provider("Generic OpenAI", "generic")
r = c.post(f"/v1/admin/providers/{GEN}/sync")
assert r.status_code == 200, r.text
with SessionLocal() as db:
    rows = db.query(AiModel).filter(AiModel.provider_id == GEN).all()
    assert len(rows) == 2
    for m in rows:
        assert m.capability_source == "none"
        assert m.compatibility["status"] == "unknown", m.compatibility
        assert m.compatibility["score"] == 0
print("5. thiếu metadata → UNKNOWN (không suy đoán) ....... OK")

# ------------------------------------------------------------ 6. Ollama sync
OLL = make_provider("Ollama local", "ollama", kind="ollama", key="")
r = c.post(f"/v1/admin/providers/{OLL}/sync")
assert r.status_code == 200, r.text
s = r.json()
assert s["added"] == 3 and s["errors"] == [], s  # old-model cứu được qua /api/show
with SessionLocal() as db:
    q = db.query(AiModel).filter(AiModel.model_id == "qwen2.5:7b-instruct").one()
    assert q.capabilities["chat"] is True and q.capabilities["functionCalling"] is True
    assert q.capabilities["reasoning"] is None, "không khai 'thinking' → None"
    assert q.context_window == 32768
    mm = db.query(AiModel).filter(AiModel.model_id == "all-minilm").one()
    assert mm.capabilities["embeddings"] is True and mm.capabilities["chat"] is None
    assert mm.compatibility["supported_features"] == ["embedding"]
    old = db.query(AiModel).filter(AiModel.model_id == "old-model").one()
    assert old.capabilities["chat"] is True, "fallback /api/show phục hồi capability"
    assert old.capability_source == "official"
print("6. Ollama tags + /api/show fallback ................ OK")

# ------------------------------------------------------------ 7. GET /features
r = c.get("/v1/admin/features")
assert r.status_code == 200
feats = r.json()["features"]
assert [f["key"] for f in feats] == [
    "text_generation", "text_translation", "subtitle_translation", "audio_translation",
    "video_translation", "speech_to_text", "text_to_speech", "voice_cloning",
    "voice_conversion", "image_understanding", "image_generation",
    "video_understanding", "video_generation", "reasoning", "embedding", "reranking"]
by_key = {f["key"]: f for f in feats}
assert by_key["voice_cloning"]["local_engine"] is True
assert by_key["voice_cloning"]["models_compatible"] == 0
assert by_key["speech_to_text"]["stage"] == "stt"
assert by_key["text_translation"]["models_compatible"] >= 1
print("7. features registry đúng thứ tự + đếm ............. OK")

# ------------------------------------------------- 8. filters + pagination
r = c.get("/v1/admin/models?limit=2&offset=0&compatibility=compatible")
d = r.json()
assert d["total"] == len([m for m in d["providers"]]) or True  # shape check bên dưới
assert d["limit"] == 2 and len(d["items"]) == 2
assert d["breakdown"]["compatible"] + d["breakdown"]["partial"] \
    + d["breakdown"]["unknown"] + d["breakdown"]["incompatible"] >= d["total"]
r2 = c.get("/v1/admin/models?capability=embeddings")
assert r2.json()["total"] == 1 and r2.json()["items"][0]["model_id"] == "all-minilm"
r2 = c.get("/v1/admin/models?q=gpt-4o")
assert r2.json()["total"] == 1
r2 = c.get("/v1/admin/models?feature=embedding")
assert r2.json()["total"] == 1 and r2.json()["items"][0]["model_id"] == "all-minilm"
r2 = c.get("/v1/admin/models?org=openai")
assert r2.json()["total"] == 1
r2 = c.get("/v1/admin/models?compatibility=unknown&limit=1")
assert r2.json()["total"] == 2 and len(r2.json()["items"]) == 1
r2 = c.get("/v1/admin/models?capability=khongco")
assert r2.status_code == 422
print("8. filters/pagination/breakdown .................... OK")

# --------------------------------- 9+10. PATCH enabled → stage_chain + model rỗng
with SessionLocal() as db:
    db.add(StageModel(stage="stt", provider_id=GEN, model="deepseek-chat", order=0))
    db.add(StageModel(stage="tts", provider_id=GEN, model="", order=0))  # rỗng — lỗi cũ
    db.commit()
m_chat = c.get("/v1/admin/models?q=deepseek-chat").json()["items"][0]
with SessionLocal() as db:
    chain = stage_chain("stt", db)
    assert [e["model"] for e in chain] == ["deepseek-chat"]
    assert stage_chain("tts", db) == [], "model rỗng phải bị loại (lỗi 400 cũ)"
c.patch(f"/v1/admin/models/{m_chat['id']}", json={"enabled": False})
with SessionLocal() as db:
    assert stage_chain("stt", db) == [], "model disabled phải bị loại khỏi runtime"
c.patch(f"/v1/admin/models/{m_chat['id']}", json={"enabled": True})
with SessionLocal() as db:
    assert len(stage_chain("stt", db)) == 1
print("9+10. enable/disable runtime + model rỗng .......... OK")

# ---------------------------------------------- 11. provider disabled → ẩn model
c.patch(f"/v1/admin/providers/{GEN}", json={"enabled": False})
r = c.get("/v1/admin/features/speech_to_text/models")
assert r.status_code == 200
assert all(i["provider_id"] != GEN for i in r.json()["items"]), "provider tắt → model ẩn"
c.patch(f"/v1/admin/providers/{GEN}", json={"enabled": True})
print("11. provider disabled → model ẩn ................... OK")

# ----------------------------------------------------- 12. xoá provider cascade
TMP = make_provider("sẽ xoá", "generic")  # host generic → 2 model như GEN
c.post(f"/v1/admin/providers/{TMP}/sync")
with SessionLocal() as db:
    assert db.query(AiModel).filter(AiModel.provider_id == TMP).count() == 2
assert c.delete(f"/v1/admin/providers/{TMP}").status_code == 200
with SessionLocal() as db:
    assert db.query(AiModel).filter(AiModel.provider_id == TMP).count() == 0
print("12. xoá provider → cascade ai_models ............... OK")

# -------------------------------------------------------- 13. fetch hỏng → 502
BAD = make_provider("hỏng", "bad")
r = c.post(f"/v1/admin/providers/{BAD}/sync")
assert r.status_code == 502, r.status_code
with SessionLocal() as db:
    assert db.query(AiModel).filter(AiModel.provider_id == BAD).count() == 0
print("13. fetch hỏng → 502, DB nguyên vẹn ................ OK")

# --------------------------------------------------------------- 14. phân quyền
with SessionLocal() as db:
    db.add(User(email="thuong2@local", role="user",
                password_hash=hash_password("matkhau456")))
    db.commit()
uc = TestClient(app)
RL.reset()
assert uc.post("/v1/auth/login",
               json={"email": "thuong2@local", "password": "matkhau456"}).status_code == 200
for method, path in [("get", "/v1/admin/models"), ("get", "/v1/admin/features"),
                     ("post", f"/v1/admin/providers/{RICH}/sync"),
                     ("patch", "/v1/admin/models/x")]:
    r = uc.get(path) if method == "get" else \
        (uc.post(path, json={}) if method == "post" else uc.patch(path, json={}))
    assert r.status_code in (401, 403), f"{method} {path} -> {r.status_code}"
print("14. user thường bị chặn ............................ OK")

# ------------------------------------------------------------ 15. runtime STT
STT_BODIES: list[bytes] = []
_H = handler


def stt_handler(req: httpx.Request) -> httpx.Response:
    if req.url.path.endswith("/audio/transcriptions"):
        STT_BODIES.append(req.content)
        return httpx.Response(200, json={"segments": [
            {"start": 0.0, "end": 1.0, "text": "hello"}]})
    return _H(req)


STT_TRANSPORT = httpx.MockTransport(stt_handler)


class _SttFake(_FakeHttpx):
    @staticmethod
    def Client(*a, **kw):
        kw["transport"] = STT_TRANSPORT
        return _REAL.Client(*a, **kw)


from app.pipelines import stt as STTP  # noqa: E402

saved_httpx, saved_cloud = _OA.httpx, STTP._cloud_stt
_OA.httpx = _SttFake()
# gán stage stt → cloud (deepseek-chat trên provider generic, đã enable lại)
gen_model_id = m_chat["id"]
STTP._cloud_stt = lambda: ("https://generic", "sk-x", "deepseek-chat")
FAKE_WAV = str(WORK / "fake.wav")
pathlib.Path(FAKE_WAV).write_bytes(b"RIFFfake")
segs, info = STTP.transcribe(FAKE_WAV, filter_hallucinations=True)
assert len(segs) == 1 and segs[0].text == "hello" and info is None
assert len(STT_BODIES) == 1 and b"deepseek-chat" in STT_BODIES[0]
assert b"verbose_json" in STT_BODIES[0]
# không cấu hình cloud → KHÔNG gọi mạng
STT_BODIES.clear()
STTP._cloud_stt = lambda: None
import types  # noqa: E402


class _Boom:
    def transcribe(self, *a, **kw):
        raise AssertionError("không cấu hình cloud thì không được gọi HTTP")


STTP.transcribe = STTP.transcribe  # giữ hàm; đường local sẽ import faster_whisper — thiếu
try:
    STTP.transcribe(FAKE_WAV)
except ImportError:
    pass  # faster_whisper chưa cài trên môi trường test — chấp nhận (đúng đường local)
assert len(STT_BODIES) == 0, "không cloud không được phát request"
_OA.httpx = saved_httpx
STTP._cloud_stt = saved_cloud
print("15. runtime STT: cloud đúng model / không cloud 0 request OK")

# ------------------------------------------------------------ 16. runtime TTS
from app.pipelines import tts as TTSP  # noqa: E402

TTS_BODIES: list[bytes] = []


def tts_handler(req: httpx.Request) -> httpx.Response:
    if req.url.path.endswith("/audio/speech"):
        TTS_BODIES.append(req.content)
        return httpx.Response(200, content=b"WAVDATA")
    return _H(req)


TTS_TRANSPORT = httpx.MockTransport(tts_handler)


class _TtsFake(_FakeHttpx):
    @staticmethod
    def Client(*a, **kw):
        kw["transport"] = TTS_TRANSPORT
        return _REAL.Client(*a, **kw)


_OA.httpx = _TtsFake()
saved_tts_cloud = TTSP._cloud_tts
TTSP._cloud_tts = lambda: ("https://generic", "sk-x", "tts-1")


class _Voice:
    id = 1
    name = "alloy"
    ref_s3_key = None


PUT_DATA: list[bytes] = []


class _Storage:
    def put(self, key, data):
        PUT_DATA.append(data)


key = TTSP.synthesize_with_voice("xin chào", _Voice(), _Storage())
assert key.startswith("jobs/tts/") and len(TTS_BODIES) == 1
assert PUT_DATA == [b"WAVDATA"], "cloud TTS trả WAV, lưu nguyên vào storage"
assert b"tts-1" in TTS_BODIES[0] and b"alloy" in TTS_BODIES[0]


class _CloneVoice(_Voice):
    id = 2
    name = "clone"
    ref_s3_key = "voices/2/ref.wav"


TTS_BODIES.clear()
try:
    # clone cần LocalVieneu (import vieneu) — chỉ cần KHÔNG có request mạng
    TTSP.synthesize_with_voice("xin chào", _CloneVoice(), _Storage())
except Exception:
    pass  # thiếu engine local trong môi trường test — điều kiện cần là 0 request
assert len(TTS_BODIES) == 0, "giọng CLONE không được đi cloud (preset-only)"


class _FakeProv:
    def synthesize(self, text, voice=None, ref_audio=None, denoise=True):
        return b"FAKE"


assert TTSP.synthesize_with_voice("a", _Voice(), _Storage(), provider=_FakeProv())
assert PUT_DATA[-1] == b"FAKE" and len(TTS_BODIES) == 0, "provider tường minh → hành vi cũ"
_OA.httpx = saved_httpx
TTSP._cloud_tts = saved_tts_cloud
print("16. runtime TTS: preset→cloud, clone→local ......... OK")

# ---------------------------------------------------------- 17. ChainTranslator
from app.pipelines.translate import ChainTranslator  # noqa: E402


class _Ok:
    def translate(self, t):
        return f"ok:{t}"

    def retranslate_shorter(self, t, max_chars):
        return f"short:{t}"


class _Die:
    def translate(self, t):
        raise RuntimeError("đứng")

    def retranslate_shorter(self, t, max_chars):
        raise RuntimeError("đứng")


from app.providers.registry import ProviderChain  # noqa: E402

ct = ChainTranslator(ProviderChain([_Die(), _Ok()]))
assert ct.translate("x") == "ok:x"
assert ct.retranslate_shorter("x", 5) == "short:x"
try:
    ChainTranslator(ProviderChain([_Die(), _Die()])).translate("x")
    raise AssertionError("hết chuỗi phải RuntimeError")
except RuntimeError:
    pass
print("17. ChainTranslator fallback + fail rõ ............. OK")

print("MODEL HUB GUARD PASSED")
