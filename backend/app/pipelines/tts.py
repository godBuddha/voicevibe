"""Day 4: TTS job pipeline — preset voices + zero-shot cloning via voice profiles.

Voice profile = a 3-8s reference clip in media storage:
  voices/{voice_id}/ref.wav        original upload
  voices/{voice_id}/ref_clean.wav  denoised cache (created on first use,
                                   reused with denoise=False afterwards)

Offline selftest (no GPU, no models — fake provider + real LocalStorage):
  PYTHONPATH=. python -m app.pipelines.tts --selftest
"""
from __future__ import annotations

import os
import tempfile

from ..providers.local import LocalVieneuTTSProvider


def _clean_ref(provider: LocalVieneuTTSProvider, voice_id: str,
               storage, ref_key: str) -> str:
    """Path to a clean reference clip — denoise once, cache forever."""
    clean_key = f"voices/{voice_id}/ref_clean.wav"
    if storage.exists(clean_key):
        return storage.get_to_temp(clean_key)
    ref_tmp = storage.get_to_temp(ref_key)
    clean_tmp = os.path.join(tempfile.gettempdir(), f"ref_{voice_id}_clean.wav")
    provider.denoise_to(ref_tmp, clean_tmp)
    with open(clean_tmp, "rb") as f:
        storage.put(clean_key, f.read())
    return clean_tmp


def _cloud_tts() -> tuple[str, str, str] | None:
    """(base_url, api_key, model) của stage 'tts' khi admin đã gán model cloud —
    None nếu không cấu hình/lỗi DB (cùng hình dạng _cloud_stt của STT)."""
    try:
        from ..db import SessionLocal
        from ..providers_api import stage_entry

        with SessionLocal() as db:
            e = stage_entry("tts", db)
    except Exception:  # noqa: BLE001
        return None
    if not e:
        return None
    return e["base_url"], e["api_key"], e["model"]


def synthesize_with_voice(text: str, voice, storage, provider=None,
                          out_key: str | None = None) -> str:
    """Synthesize `text` using a Voice row (clone) or a preset name.

    voice.ref_s3_key set -> zero-shot clone from the reference clip.
    otherwise            -> preset voice (voice.name), or engine default.
    Returns the storage key of the output WAV.

    Chọn engine (chỉ khi caller KHÔNG truyền provider tường minh — selftest
    truyền FakeProvider để test logic voice, không phải test engine):
    - GIỌNG CLONE (ref_s3_key) → local ALWAYS: chuẩn OpenAI /audio/speech chỉ
      có preset voice, không hỗ trợ zero-shot clone (docstring
      providers/openai_compat.py).
    - GIỌNG PRESET, stage 'tts' có model cloud → OpenAI-compatible cloud
      provider (OpenAITTSProvider); hỏng → job failed (không fallback lặng lẽ,
      cùng quy tắc của translate/stt).
    - Không cloud → local VieNeu như cũ.
    """
    if provider is None:
        if voice is not None and getattr(voice, "ref_s3_key", None):
            provider = LocalVieneuTTSProvider()   # clone → local ALWAYS (rule trên)
        else:
            cloud = _cloud_tts()
            if cloud is not None:
                from ..providers.openai_compat import OpenAITTSProvider
                provider = OpenAITTSProvider(*cloud)
            else:
                provider = LocalVieneuTTSProvider()
    if voice is not None and getattr(voice, "ref_s3_key", None):
        ref_path = _clean_ref(provider, str(voice.id), storage, voice.ref_s3_key)
        audio = provider.synthesize(text, ref_audio=ref_path, denoise=False)
    else:
        audio = provider.synthesize(text, voice=getattr(voice, "name", None))
    key = out_key or f"jobs/tts/{os.urandom(6).hex()}.wav"
    storage.put(key, audio)
    return key


def _selftest() -> None:
    import tempfile

    from ..storage import LocalStorage

    class FakeProvider:
        def __init__(self):
            self.denoise_calls = 0
            self.clone_calls = 0
            self.preset_calls = 0

        def denoise_to(self, src: str, dst: str) -> None:
            self.denoise_calls += 1
            with open(dst, "wb") as f:
                f.write(b"CLEAN")

        def synthesize(self, text, voice=None, ref_audio=None, denoise=True):
            if ref_audio is not None:
                self.clone_calls += 1
                assert denoise is False, "clone path must reuse the clean cache"
                return b"AUDIO-CLONE:" + text.encode()
            self.preset_calls += 1
            return b"AUDIO-PRESET:" + (voice or "default").encode()

    class VoiceRow:  # minimal stand-in for the ORM row
        def __init__(self, vid, name, ref_key):
            self.id, self.name, self.ref_s3_key = vid, name, ref_key

    with tempfile.TemporaryDirectory() as tmp:
        storage = LocalStorage(tmp)
        storage.put("voices/v1/ref.wav", b"RAW-REF")
        prov = FakeProvider()
        v = VoiceRow("v1", "Thái Sơn", "voices/v1/ref.wav")

        # clone path: first call denoises + caches
        k1 = synthesize_with_voice("Xin chào", v, storage, provider=prov, out_key="jobs/a.wav")
        assert storage.get(k1) == ("AUDIO-CLONE:Xin chào").encode("utf-8")
        assert storage.exists("voices/v1/ref_clean.wav")
        assert prov.denoise_calls == 1 and prov.clone_calls == 1

        # second call reuses the cached clean ref (no re-denoise)
        k2 = synthesize_with_voice("Lần hai", v, storage, provider=prov, out_key="jobs/b.wav")
        assert prov.denoise_calls == 1 and prov.clone_calls == 2

        # preset path
        k3 = synthesize_with_voice("Preset", VoiceRow(None, "Hải Đăng", None),
                                   storage, provider=prov, out_key="jobs/c.wav")
        assert storage.get(k3) == ("AUDIO-PRESET:Hải Đăng").encode("utf-8")
        assert prov.preset_calls == 1

    print("clone path + clean-ref cache .. OK")
    print("preset path ................... OK")
    print("D4 LOGIC SELFTEST PASSED")


if __name__ == "__main__":
    _selftest()
