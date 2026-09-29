"""Day 5 real-GPU smoke: full dubbing pipeline vi -> en on the D3 sample.

Source: /workspace/samples/d3_2spk.wav (13.4s, Vietnamese, 2 speakers)
Steps: STT+diarize -> translate (opus-mt vi->en) -> TTS per speaker (VieNeu)
       -> timing-fit -> ffmpeg mix -> duration check + round-trip ASR (en).

Run on the GPU box:
  cd /workspace/voicevibe && source .venv/bin/activate
  cd backend && PYTHONPATH=. python scripts/d5_smoke.py
"""
from __future__ import annotations

import os
import sys
import wave

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ.setdefault("MEDIA_ROOT", "/workspace/media")
os.environ.setdefault("DATABASE_URL", "sqlite:////workspace/voicevibe/backend/voicevibe.db")

from app.pipelines.dub_pipeline import dub_audio  # noqa: E402
from app.pipelines.stt import transcribe  # noqa: E402
from app.storage import get_storage  # noqa: E402

SRC = "/workspace/samples/d3_2spk.wav"
VOICES = {"SPEAKER_00": "Hải Đăng", "SPEAKER_01": "Mai Anh"}


def wav_dur(path: str) -> float:
    with wave.open(path) as w:
        return w.getnframes() / w.getframerate()


def main() -> None:
    storage = get_storage()
    src_dur = wav_dur(SRC)
    print(f"[src] {SRC} ({src_dur:.1f}s, vi, 2 speakers)")

    key, plan = dub_audio(SRC, "vi", "en", VOICES, storage)
    out_path = storage.get_to_temp(key)
    out_dur = wav_dur(out_path)
    print(f"[dub] saved {key} ({out_dur:.1f}s vs src {src_dur:.1f}s)")
    print("[plan] per-segment timing:")
    for s in plan:
        flag = "  <-- RE-TRANSLATE" if s.needs_shorter_text else ""
        print(f"  #{s.idx} {s.speaker} slot={s.end - s.start:5.2f}s "
              f"gen={s.gen_duration:5.2f}s speed={s.speed:4.2f} "
              f"delay={s.delay_ms:6d}ms{flag}")

    assert 0.6 * src_dur <= out_dur <= 1.8 * src_dur, \
        f"output duration out of range: {out_dur:.1f}s"

    print("[verify] faster-whisper round-trip on DUBBED audio (en)...")
    segs, info = transcribe(out_path, language="en")
    heard = " ".join(s.text for s in segs).strip()
    words = len(heard.split())
    print(f"[verify] heard: {heard}")
    print(f"[verify] {words} words | lang={info.language} p={info.language_probability:.2f}")

    ok = info.language == "en" and words >= 8
    print(f"\nD5 SMOKE: {'PASS' if ok else 'CHECK'} "
          f"(dub {out_dur:.1f}s, heard {words} en words)")


if __name__ == "__main__":
    main()
