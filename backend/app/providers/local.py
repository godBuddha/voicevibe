"""Local engine providers — guarded imports so light containers (API, tests)
can import this module; heavy engines load only when actually constructed.
"""
from __future__ import annotations

import io
import wave

from .base import TranscriptSegment


class LocalVieneuTTSProvider:
    """VieNeu-TTS v3 Turbo (Apache-2.0) — 48kHz, zero-shot clone from 3-8s clip.

    ONNX/CPU (torch-free, RTF ~0.5) or PyTorch/CUDA (RTF ~0.02 batched).
    This is the CLONING path — OpenAI-standard TTS cannot replace it.
    """

    def __init__(self, mode: str = "v3turbo"):
        try:
            from vieneu import Vieneu  # heavy import — worker image only
        except ImportError as exc:
            raise RuntimeError(
                "vieneu not installed — pip install vieneu (worker image only)"
            ) from exc
        self._tts = Vieneu(mode=mode)

    def _to_wav_bytes(self, audio) -> bytes:
        import numpy as np

        buf = io.BytesIO()
        with wave.open(buf, "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(48000)
            w.writeframes((np.clip(audio, -1.0, 1.0) * 32767).astype("<i2").tobytes())
        return buf.getvalue()

    def synthesize(self, text: str, voice: str | None = None,
                   ref_audio: str | None = None, denoise: bool = True) -> bytes:
        """Preset path (voice=name) or clone path (ref_audio=clip path)."""
        if ref_audio is not None:
            audio = self._tts.infer(text, ref_audio=ref_audio, denoise=denoise)
        else:
            audio = self._tts.infer(text, voice=voice)
        return self._to_wav_bytes(audio)

    def denoise_to(self, src: str, dst: str) -> None:
        """Clean a reference clip once; result is cached in storage."""
        self._tts.denoise(src, out_path=dst)


class LocalWhisperSTTProvider:
    """faster-whisper (MIT) — large-v3. int8 on 12GB GPUs, fp16 on 24GB."""

    def __init__(self, model_size: str = "large-v3", compute_type: str = "int8",
                 device: str = "auto"):
        try:
            from faster_whisper import WhisperModel  # heavy import
        except ImportError as exc:
            raise RuntimeError(
                "faster-whisper not installed — pip install faster-whisper (worker image)"
            ) from exc
        self._model = WhisperModel(model_size, device=device, compute_type=compute_type)

    def transcribe(self, audio_path: str, language: str | None = None) -> list[TranscriptSegment]:
        segments, _info = self._model.transcribe(audio_path, language=language, vad_filter=True)
        return [TranscriptSegment(start=s.start, end=s.end, text=s.text.strip())
                for s in segments]
