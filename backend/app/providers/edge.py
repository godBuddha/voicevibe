"""B5 — edge-tts engine (Microsoft Edge đọc giọng miễn phí qua mạng).

Vì sao thêm: VieNeu local cần GPU (RTF 0.02 GPU / 0.5 CPU) — trên máy KHÔNG
GPU, giọng edge-tts qua mạng nhanh hơn nhiều và miễn phí, có sẵn giọng tiếng
Việt (vi-VN-HoaiMyNeural, vi-VN-NamMinhNeural...). Mặc định hệ vẫn dùng VieNeu
local — edge là LỰA CHỌN THÊM, không phải thay thế.

Kỹ thuật:
- Worker Celery là SYNC — bọc asyncio.run() quanh `edge_tts.Communicate`
  (async) là an toàn, KHÔNG tạo event loop nền (loop nền trên worker dễ đụng
  thư viện khác).
- edge-tts trả MP3 24kHz → CONVERT 48kHz mono wav bằng ffmpeg để NHẤT QUÁN
  với LocalVieneuTTSProvider (mix pipeline của dub đòi 48k mono — đổi định dạng
  ở đây là chỗ duy nhất, sau đó mọi khâu như cũ).
- Retry 3 lần backoff 2s*lần — port `pkg/localtts/edgetts.go:68-98`.
- list_voices() gọi API async MỘT LẦN rồi cache module-level 24h: vắng mạng →
  trả cache cũ (nếu có) hoặc rỗng, KHÔNG raise — listing giọng không được giết
  job (đề phòng rủi ro số 7 của kế hoạch: edge rate-limit).
- KHÔNG fallback chéo provider (quy tắc repo: hỏng là failed, không lặng lẽ
  đổi đường) — edge lỗi sẽ bong lên job failed với message rõ.
"""
from __future__ import annotations

import asyncio
import io
import os
import subprocess
import tempfile
import time
import wave

from .base import TTSOptions, TTSVoice

_RETRY_ATTEMPTS = 3
_VOICES_CACHE: tuple[float, list[TTSVoice]] | None = None
_VOICES_TTL = 24 * 3600


def _mp3_to_wav_48k(mp3: bytes) -> bytes:
    """MP3 24k stereo → WAV 48kHz mono 16-bit (ffmpeg — nhất quán VieNeu)."""
    src = os.path.join(tempfile.gettempdir(), f"edge_{os.urandom(4).hex()}.mp3")
    dst = src[:-4] + ".wav"
    with open(src, "wb") as f:
        f.write(mp3)
    try:
        res = subprocess.run(
            ["ffmpeg", "-y", "-i", src, "-ar", "48000", "-ac", "1",
             "-sample_fmt", "s16", dst],
            capture_output=True, timeout=120)
        if res.returncode != 0:
            raise RuntimeError("ffmpeg convert edge-tts audio thất bại: "
                               + res.stderr.decode()[-200:])
        with open(dst, "rb") as f:
            return f.read()
    finally:
        for p in (src, dst):
            try:
                os.unlink(p)
            except OSError:
                pass


class EdgeTTSEngine:
    """edge-tts (GPL-3.0 as pip dependency — tương thích AGPL-3.0 project).

    Implement cả 2 tầng: synthesize (tầng 1 — mọi pipeline dùng được) +
    synthesize_ex / list_voices (tầng 2 — port TTSProvider của OpenCreator).
    """

    def __init__(self):
        try:
            import edge_tts  # noqa: F401
        except ImportError as exc:
            raise RuntimeError(
                "edge-tts not installed — pip install edge-tts (worker image)"
            ) from exc

    # ------------------------------------------------------------- tầng 2
    def synthesize_ex(self, opts: TTSOptions) -> bytes:
        speed = max(0.5, min(2.0, opts.speed or 1.0))
        rate = f"{int((speed - 1.0) * 100):+d}%"
        return self._run(opts.text, voice=opts.voice, rate=rate)

    def list_voices(self) -> list[TTSVoice]:
        global _VOICES_CACHE
        now = time.time()
        if _VOICES_CACHE and now - _VOICES_CACHE[0] < _VOICES_TTL:
            return list(_VOICES_CACHE[1])
        try:
            import edge_tts

            raw = asyncio.run(edge_tts.voices())
        except Exception:  # noqa: BLE001 — vắng mạng/rate-limit: trả cache cũ
            raw = None
        voices = [
            TTSVoice(code=v["ShortName"], name=v.get("FriendlyName") or v["ShortName"],
                     language=v.get("Locale", ""), gender=v.get("Gender", "").lower(),
                     provider="edge", kind="preset")
            for v in (raw or [])
        ]
        if voices:  # chỉ cache khi lấy được — cache rỗng là bám lỗi vĩnh viễn
            _VOICES_CACHE = (now, voices)
        return list((_VOICES_CACHE or (0, []))[1])

    # ------------------------------------------------------------- tầng 1
    def synthesize(self, text: str, voice: str | None = None) -> bytes:
        return self._run(text, voice=voice, rate="+0%")

    # ------------------------------------------------------------------ run
    def _run(self, text: str, *, voice: str | None, rate: str) -> bytes:
        """Gọi edge-tts, retry 3× backoff — port `pkg/localtts/edgetts.go`.

        Blocking: giao tiếp qua tempfile + edge_tts.Communicate.save() — không
        dựng event loop riêng cho từng chunk.
        """
        import edge_tts

        last_exc: Exception | None = None
        for attempt in range(_RETRY_ATTEMPTS):
            try:
                out = os.path.join(tempfile.gettempdir(),
                                   f"vv_edge_{os.urandom(4).hex()}.mp3")
                com = edge_tts.Communicate(text, voice=voice or "vi-VN-HoaiMyNeural",
                                           rate=rate)
                asyncio.run(com.save(out))
                with open(out, "rb") as f:
                    mp3 = f.read()
                os.unlink(out)
                return _mp3_to_wav_48k(mp3)
            except Exception as exc:  # noqa: BLE001 — retry cả mạng + rate-limit
                last_exc = exc
                time.sleep(min(2 * (attempt + 1), 6))
        raise RuntimeError(f"edge-tts thất bại sau {_RETRY_ATTEMPTS} lần: "
                           f"{str(last_exc)[:200]}") from last_exc


def _wav_probe(b: bytes) -> tuple[int, int]:  # helper cho test
    buf = io.BytesIO(b)
    with wave.open(buf) as w:
        return w.getframerate(), w.getnchannels()
