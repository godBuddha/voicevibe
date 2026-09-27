"""Provider-layer self-test — fully offline, OpenAI wire format mocked via
httpx.MockTransport. Verifies: chat parsing, retry/backoff, TTS/STT bodies,
fallback chains (cloud->cloud, local-missing->cloud), lazy init, registry.

Run:  cd backend && PYTHONPATH=. python tests/test_providers.py
"""
from __future__ import annotations

import json
import os

import app.providers.openai_compat as oc
import httpx

oc._sleep = lambda *_: None  # skip backoff in tests

from app.providers.local import LocalVieneuTTSProvider  # noqa: E402
from app.providers.openai_compat import (  # noqa: E402
    OpenAIChatProvider, OpenAISTTProvider, OpenAITTSProvider,
)
from app.providers.registry import LazyProvider, ProviderChain, build_chain  # noqa: E402

os.environ["TEST_API_KEY"] = "test-key"


def mock_client(handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))


# 1) Chat: parse OpenAI shape + auth header + endpoint path
def chat_handler(req: httpx.Request) -> httpx.Response:
    assert req.url.path == "/v1/chat/completions"
    assert req.headers["Authorization"] == "Bearer test-key"
    body = json.loads(req.content)
    assert body["messages"][0]["role"] == "system"
    return httpx.Response(200, json={"choices": [{"message": {"content": "Xin chào thế giới"}}]})


p = OpenAIChatProvider("http://mock/v1", "test-key", "gpt-x", client=mock_client(chat_handler))
assert p.complete("sys", "Hello world") == "Xin chào thế giới"
print("chat parse + auth .......... OK")

# 2) Retry: 429 -> 200
attempts = {"n": 0}


def flaky_handler(req: httpx.Request) -> httpx.Response:
    attempts["n"] += 1
    if attempts["n"] == 1:
        return httpx.Response(429, text="rate limited")
    return httpx.Response(200, json={"choices": [{"message": {"content": "ok"}}]})


p2 = OpenAIChatProvider("http://mock/v1", "test-key", "m", client=mock_client(flaky_handler))
assert p2.complete("s", "u") == "ok" and attempts["n"] == 2
print("retry on 429 ............... OK")

# 3) TTS body + binary passthrough
def tts_handler(req: httpx.Request) -> httpx.Response:
    assert req.url.path == "/v1/audio/speech"
    body = json.loads(req.content)
    assert body["model"] == "tts-1" and body["voice"] == "alloy" and body["input"] == "Xin chào"
    return httpx.Response(200, content=b"RIFF....WAVE")


tts = OpenAITTSProvider("http://mock/v1", "test-key", "tts-1", client=mock_client(tts_handler))
assert tts.synthesize("Xin chào", voice="alloy") == b"RIFF....WAVE"
print("tts body + bytes ........... OK")

# 4) STT multipart + segment parsing (tạo file WAV thật 0.1s im lặng)
import wave as _wave
with _wave.open("/tmp/a.wav", "wb") as _w:
    _w.setnchannels(1)
    _w.setsampwidth(2)
    _w.setframerate(16000)
    _w.writeframes(b"\x00\x00" * 1600)


def stt_handler(req: httpx.Request) -> httpx.Response:
    assert req.url.path == "/v1/audio/transcriptions"
    assert "multipart/form-data" in req.headers["content-type"]
    return httpx.Response(200, json={"segments": [
        {"start": 0.0, "end": 4.2, "text": " Hello world "},
        {"start": 4.5, "end": 9.0, "text": " Second line"},
    ]})


stt = OpenAISTTProvider("http://mock/v1", "test-key", "whisper-1", client=mock_client(stt_handler))
segs = stt.transcribe("/tmp/a.wav", language="en")
assert len(segs) == 2 and segs[0].text == "Hello world" and abs(segs[1].start - 4.5) < 1e-9
assert segs[0].speaker is None  # diarization is NOT in the OpenAI standard
print("stt multipart + parse ...... OK")

# 5) Chain fallback: bad endpoint -> good endpoint
def route_handler(req: httpx.Request) -> httpx.Response:
    if req.url.host == "bad":
        return httpx.Response(500, text="boom")
    if req.url.path == "/v1/audio/speech":
        return httpx.Response(200, content=b"RIFF....WAVE")
    return httpx.Response(200, json={"choices": [{"message": {"content": "from-good"}}]})


chain = ProviderChain([
    OpenAIChatProvider("http://bad/v1", "test-key", "m", client=mock_client(route_handler)),
    OpenAIChatProvider("http://good/v1", "test-key", "m", client=mock_client(route_handler)),
])
assert chain.call("complete", "s", "u") == "from-good"
print("chain cloud->cloud ......... OK")

# 6) Local engine unavailable -> falls back to cloud.
# Poison sys.modules so the lazy factory raises ImportError -> RuntimeError —
# deterministic whether or not vieneu is actually installed on this host.
import sys as _sys
_saved = _sys.modules.pop("vieneu", None)
_sys.modules["vieneu"] = None  # importing a None entry raises ImportError
try:
    tts_chain = build_chain([
        {"provider": "local_vieneu"},
        {"provider": "openai_tts", "base_url": "http://good/v1",
         "api_key_env": "TEST_API_KEY", "model": "tts-1"},
    ], client_factory=lambda: mock_client(route_handler))
    audio = tts_chain.call("synthesize", "Xin chào", voice="alloy")
    assert audio == b"RIFF....WAVE"
finally:
    _sys.modules.pop("vieneu", None)
    if _saved is not None:
        _sys.modules["vieneu"] = _saved
print("chain local-missing->cloud . OK")

# 7) Guarded import: clear error message, not a stack trace (same poison trick)
_saved7 = _sys.modules.pop("vieneu", None)
_sys.modules["vieneu"] = None
try:
    LocalVieneuTTSProvider()
    raise AssertionError("should have raised")
except RuntimeError as exc:
    assert "pip install vieneu" in str(exc)
finally:
    _sys.modules.pop("vieneu", None)
    if _saved7 is not None:
        _sys.modules["vieneu"] = _saved7
print("guarded local import ....... OK")

# 8) LazyProvider defers init
lazy = LazyProvider(lambda: (_ for _ in ()).throw(RuntimeError("never built")))
assert lazy._instance is None  # not built at construction
try:
    lazy.synthesize("x")
    raise AssertionError("should have raised")
except RuntimeError as exc:
    assert "never built" in str(exc)
print("lazy init .................. OK")

print("PROVIDER LAYER SELFTEST PASSED")
