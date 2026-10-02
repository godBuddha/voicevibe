"""B5 — Guard đa TTS provider: interface 2 tầng + edge-tts + catalog + route.

Vì sao có test riêng:
- voice_id namespaced là LỚP ĐỌC: tên cũ không dấu ':' (giọng preset VieNeu +
  id giọng clone hex) PHẢI hiểu là local — sai một dòng là job cũ / trang
  Voices vỡ.
- Route clone → local ALWAYS là quy tắc chuẩn OpenAI (/audio/speech chỉ có
  preset voice, không clone) — phải giữ nguyên sau khi thêm backend.
- Dub thay backend giọng đọc là ĐỔI CHẤT LƯỢNG KẾT QUẢ → vân tay manifest
  phải đổi (không thì resume tái dùng audio giọng khác).
- Catalog endpoint phải trả đủ 3 backend và edge phải KHÔNG raise khi vắng
  mạng (listing giọng không được giết job).

Bootstrap khớp pattern repo. Chạy:
    cd backend && PYTHONPATH=. python tests/test_tts_backends.py
"""
from __future__ import annotations

import os
import pathlib
import sys
import tempfile

WORK = pathlib.Path(tempfile.mkdtemp(prefix="vv_ttsb_"))
os.environ["DATABASE_URL"] = f"sqlite:///{WORK}/ttsb.db"
os.environ["MEDIA_ROOT"] = str(WORK / "media")
os.environ["VOICEVIBE_INLINE"] = "1"
os.environ.pop("VOICEVIBE_API_KEYS", None)
os.environ.pop("VOICEVIBE_ADMIN_KEY", None)

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient  # noqa: E402

from app import ratelimit as RL  # noqa: E402
from app.main import app  # noqa: E402
from app.pipelines.manifest import params_fingerprint  # noqa: E402
from app.providers.base import TTSOptions, TTSEngine, TTSVoice  # noqa: E402
from app.providers.edge import EdgeTTSEngine, _mp3_to_wav_48k  # noqa: E402
from app.providers.tts_catalog import (  # noqa: E402
    BACKENDS, PRESET_VOICES, build_tts, parse_voice_ref, rotate_preset,
)

c = TestClient(app)
RL.reset()
assert c.post("/v1/auth/setup",
              json={"email": "admin@local", "password": "matkhau123"}).status_code == 201

# --------------------------------------------- 1. parse_voice_ref tương thích
assert parse_voice_ref(None) == ("local", None)
assert parse_voice_ref("Hải Đăng") == ("local", "Hải Đăng"), "LEGACY bare name"
assert parse_voice_ref("a1b2c3d4e5f6") == ("local", "a1b2c3d4e5f6"), "id clone hex"
assert parse_voice_ref("edge:vi-VN-HoaiMyNeural") == ("edge", "vi-VN-HoaiMyNeural")
assert parse_voice_ref("cloud:alloy") == ("cloud", "alloy")
assert parse_voice_ref("local:Thái Sơn") == ("local", "Thái Sơn")
try:
    parse_voice_ref("gpt:x")
except ValueError as e:
    assert "backend" in str(e), e
else:
    raise AssertionError("namespace lạ phải ValueError → create_job 422")
print("1. parse_voice_ref legacy + namespaced ............ OK")

# ------------------------------------------------------- 2. catalog + rotation
assert set(BACKENDS) == {"local", "edge", "cloud"}
assert any(v.recommended for v in PRESET_VOICES["local"]), "mỗi backend phải có giọng đề xuất"
assert "Hải Đăng" in [v.code for v in PRESET_VOICES["local"]], "tên preset cũ không được đổi"
assert rotate_preset("local", 0) == "Hải Đăng"
assert rotate_preset("local", 8) == "Hải Đăng", "xoay vòng đúng chu kỳ 8"
assert rotate_preset("edge", 0) == "vi-VN-HoaiMyNeural"
print("2. catalog + xoay giọng theo backend .............. OK")

# --------------------------------------------- 3. interface 2 tầng + edge fake
class _FakeEdge:
    """Đủ cả 2 tầng — không đụng mạng."""

    def synthesize(self, text, voice=None):
        return f"FAKE-EDGE:{voice}:{text}".encode()

    def synthesize_ex(self, opts: TTSOptions):
        return f"FAKE-EDGE-EX:{opts.voice}:{opts.speed}:{opts.text}".encode()

    def list_voices(self):
        return [TTSVoice(code="vi-VN-HoaiMyNeural", name="Hà My", language="vi",
                         gender="female", provider="edge", kind="preset")]

# isinstance Protocol runtime_checkable chỉ kiểm tên method — mức cấu trúc
assert isinstance(_FakeEdge(), TTSEngine)
fake = _FakeEdge()
assert fake.synthesize("x", "v") == b"FAKE-EDGE:v:x"
assert fake.synthesize_ex(TTSOptions(text="y", voice="v", speed=1.2)) == \
    b"FAKE-EDGE-EX:v:1.2:y"
print("3. interface 2 tầng (tầng 1 + tầng 2) ............. OK")

# --------------------------------------------- 4. edge mp3 → wav 48k mono (ffmpeg)
import subprocess  # noqa: E402
HAVE_FFMPEG = subprocess.run(["ffmpeg", "-version"], capture_output=True).returncode == 0
if HAVE_FFMPEG:
    # ffmpeg sinh mp3 24k stereo 0.3s
    mp3 = tempfile.mktemp(suffix=".mp3")
    subprocess.run(["ffmpeg", "-y", "-f", "lavfi", "-i",
                    "sine=frequency=440:duration=0.3", "-ar", "24000", "-ac", "2",
                    mp3], check=True, capture_output=True)
    wav = _mp3_to_wav_48k(open(mp3, "rb").read())
    os.unlink(mp3)
    import wave
    buf = __import__("io").BytesIO(wav)
    with wave.open(buf) as w:
        assert w.getframerate() == 48000, w.getframerate()
        assert w.getnchannels() == 1, w.getnchannels()
    print("4. edge mp3 → wav 48kHz mono (ffmpeg) ............. OK")
else:
    print("4. edge mp3 → wav — BỎ QUA (không có ffmpeg) ...... OK")

# ------------------------------- 5. vân tay đổi theo tts_backend (dub resume)
base = {"source_lang": "vi", "target_lang": "en", "speaker_voices": {},
        "background_mode": "silence", "max_speed": 1.35, "media_url": "/x.mp4"}
fp_local = params_fingerprint({**base}, "tag")
fp_edge = params_fingerprint({**base, "tts_backend": "edge"}, "tag")
assert fp_local != fp_edge, "đổi backend giọng đọc phải đổi vân tay"
print("5. vân tay gồm tts_backend ........................ OK")

# ------------------------------------------ 6. build_tts + route synthesize
try:
    build_tts("laser")
except ValueError:
    pass
else:
    raise AssertionError("backend lạ phải bị chặn")
try:
    build_tts("cloud")
except ValueError as e:
    assert "Model Hub" in str(e), e  # chưa gán stage tts → message rõ
else:
    raise AssertionError("cloud chưa gán stage phải báo rõ")
# local build engine thật chỉ khi vieneu có — KHÔNG dựng trong test env:
try:
    build_tts("local")
except RuntimeError as e:
    assert "vieneu" in str(e), e  # env test không có model — message đúng
print("6. build_tts guard backend lạ + cloud chưa gán .... OK")

from app.pipelines.tts import synthesize_with_voice  # noqa: E402
from app.storage import LocalStorage  # noqa: E402

storage = LocalStorage(tempfile.mkdtemp(prefix="vv_ttsb_s"))


class FakeProvider:
    def synthesize(self, text, voice=None, ref_audio=None, denoise=True):
        return f"FAKE:{voice}".encode()


class VoiceRow:
    def __init__(self, name, ref_key=None):
        self.id = "v1"
        self.name = name
        self.ref_s3_key = ref_key


# route edge tường minh (patch TẠI MODULE NGUỒN providers.edge — tts.py import
# local `from ..providers.edge import EdgeTTSEngine` lúc gọi)
import app.providers.edge as EDGEMOD  # noqa: E402

real_edge = EDGEMOD.EdgeTTSEngine
EDGEMOD.EdgeTTSEngine = lambda: _FakeEdge()
try:
    k = synthesize_with_voice("Xin chào", VoiceRow("vi-VN-HoaiMyNeural"),
                              storage, backend="edge", out_key="jobs/e.wav")
    assert storage.get(k) == "FAKE-EDGE:vi-VN-HoaiMyNeural:Xin chào".encode(), storage.get(k)
finally:
    EDGEMOD.EdgeTTSEngine = real_edge
# cloud tường minh chưa gán stage → ValueError rõ
try:
    synthesize_with_voice("x", VoiceRow("alloy"), storage, backend="cloud",
                          out_key="jobs/c.wav")
except ValueError as e:
    assert "Model Hub" in str(e), e
else:
    raise AssertionError("cloud chưa gán stage phải ValueError")
# legacy (không backend) + provider tường minh → hành vi cũ không vỡ
k = synthesize_with_voice("Preset", VoiceRow("Hải Đăng"), storage,
                          provider=FakeProvider(), out_key="jobs/l.wav")
assert storage.get(k) == "FAKE:Hải Đăng".encode(), storage.get(k)
print("6. route backend edge/cloud/local + legacy ........ OK")

# ------------------------------------------------------------- 7. endpoint
r = c.get("/v1/tts/presets")
assert r.status_code == 200, r.text
d = r.json()["backends"]
assert set(d) == {"local", "edge", "cloud"}, d
assert any(v["code"] == "Hải Đăng" for v in d["local"])
assert any(v["code"].startswith("vi-VN") for v in d["edge"]), d["edge"]
anon = TestClient(app)
RL.reset()
assert anon.get("/v1/tts/presets").status_code == 401
print("7. GET /v1/tts/presets 3 backend + 401 anon ....... OK")

# ------------------------------------------ 8. dub job tts_backend đổi được
from app.pipelines import dub_pipeline as DUBMOD  # noqa: E402

_dub_calls: list[dict] = []


def fake_dub(src_path, source_lang, target_lang, speaker_voices, storage, *,
             workdir=None, job_id=None, tts_backend=None, **_kw):
    _dub_calls.append({"tts_backend": tts_backend})
    return f"jobs/{job_id}/dub.mp4", []


real_dub = DUBMOD.dub_audio
DUBMOD.dub_audio = fake_dub
try:
    r = c.post("/v1/jobs", json={"type": "tts", "text": "xin chào", "voice_id": "nolàl"},
               )
    assert r.status_code == 404, "voice lạ phải 404 ownership"
    # media phải TỒN TẠI (path local) — _resolve_media đọc file thật trước dub
    fake_media = os.path.join(WORK, "media_src.mp4")
    with open(fake_media, "wb") as f:
        f.write(b"MP4")
    r = c.post("/v1/jobs", json={"type": "dub", "media_url": fake_media,
                                 "source_lang": "vi", "target_lang": "en",
                                 "tts_backend": "edge"})
    assert r.status_code in (200, 202), r.text
    J = r.json()["job_id"]
    d = c.get(f"/v1/jobs/{J}").json()
    assert d["params"].get("tts_backend") == "edge", d["params"]
    # inline chạy ngay — fake_dub nhận đúng backend
    assert _dub_calls and _dub_calls[-1]["tts_backend"] == "edge"
finally:
    DUBMOD.dub_audio = real_dub
r = c.post("/v1/jobs", json={"type": "dub", "media_url": "https://x/v.mp4",
                             "tts_backend": "laser"})
assert r.status_code == 422, r.text
print("8. dub nhận tts_backend + validate 422 ............ OK")

print("TTS BACKENDS SUITE PASSED")
