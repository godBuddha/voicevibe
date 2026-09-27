"""Day 3 real-GPU smoke test.

1. Generate a 2-speaker Vietnamese sample with VieNeu (early D4 validation too)
2. faster-whisper large-v3 (int8) transcription — first run downloads ~3GB
3. pyannote 3.1 diarization (needs HF_TOKEN in env)
4. merge -> SRT with speaker tags

Run on the GPU instance:
  cd /workspace/yupvox-clone && source .venv/bin/activate
  cd backend && PYTHONPATH=. python scripts/d3_smoke.py [--skip-gen]
"""
from __future__ import annotations

import argparse
import os
import sys
import wave

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.pipelines.stt import diarize, merge, to_srt, transcribe  # noqa: E402

SAMPLE = os.environ.get("D3_SAMPLE", "/workspace/samples/d3_2spk.wav")
SRT_PATH = SAMPLE.replace(".wav", ".srt")

LINE_1 = ("Xin chào các bạn, mình là Long. Hôm nay chúng ta sẽ thử nghiệm hệ thống "
          "dịch và lồng tiếng tự động do chính mình viết trong bảy ngày.")
LINE_2 = ("Chào Long! Mình là Mai Anh đây. Nghe nói công nghệ giọng nói AI đang "
          "thay đổi rất nhanh, đúng không nào?")


def generate_sample() -> None:
    from vieneu import Vieneu

    tts = Vieneu()  # v3 Turbo default
    print("[gen] loading VieNeu v3 Turbo...")
    a1 = tts.infer(LINE_1, voice="Hải Đăng")
    a2 = tts.infer(LINE_2, voice="Mai Anh")
    sr = 48000
    gap = np.zeros(int(0.4 * sr), dtype=np.float32)
    audio = np.concatenate([a1, gap, a2])
    os.makedirs(os.path.dirname(SAMPLE), exist_ok=True)
    with wave.open(SAMPLE, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes((np.clip(audio, -1.0, 1.0) * 32767).astype("<i2").tobytes())
    print(f"[gen] saved {SAMPLE} ({len(audio) / sr:.1f}s)")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--skip-gen", action="store_true",
                    help="reuse existing sample instead of generating")
    args = ap.parse_args()

    if os.path.exists(SAMPLE):
        print(f"[gen] sample exists, reuse: {SAMPLE} (delete to regenerate)")
    elif args.skip_gen:
        raise SystemExit(f"sample not found: {SAMPLE} (run without --skip-gen first)")
    else:
        generate_sample()

    print("[stt] faster-whisper large-v3 (int8)...")
    segs, info = transcribe(SAMPLE, language="vi")
    print(f"[stt] {info.duration:.1f}s audio | {len(segs)} segments | "
          f"lang={info.language} p={info.language_probability:.2f}")

    print("[dia] pyannote 3.1...")
    dia = diarize(SAMPLE)
    speakers = sorted({d.speaker for d in dia if d.speaker})
    print(f"[dia] {len(dia)} turns | speakers={speakers}")

    merged = merge(segs, dia)
    srt = to_srt(merged)
    with open(SRT_PATH, "w", encoding="utf-8") as f:
        f.write(srt)
    print(f"[srt] saved {SRT_PATH}\n")
    print(srt)

    ok = len(speakers) >= 2 and len(merged) >= 2
    print(f"\nD3 SMOKE: {'PASS' if ok else 'CHECK'} "
          f"({len(merged)} segments, {len(speakers)} speakers)")


if __name__ == "__main__":
    main()
