"""Stage A — nghe thoại video mẫu: phát hiện ngôn ngữ + số người nói.

Chạy: cd /workspace/voicevibe && source .venv/bin/activate && cd backend
      PYTHONPATH=. VOICEVIBE_INLINE=1 python scripts/dub_video_a.py
"""
from __future__ import annotations
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("MEDIA_ROOT", "/workspace/media")
os.environ.setdefault("DATABASE_URL", "sqlite:////workspace/voicevibe/backend/voicevibe.db")

# Đọc .env repo (HF_TOKEN...) — env set từ ngoài vẫn ưu tiên, không ghi đè.
_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if os.path.exists(_root + "/.env"):
    with open(_root + "/.env") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())

from app.pipelines.stt import transcribe, diarize

SRC = "/workspace/samples/short_xianxia.mp4"
wav = "/tmp/xianxia_16k.wav"
subprocess.run(["ffmpeg", "-y", "-i", SRC, "-ac", "1", "-ar", "16000", wav],
               check=True, capture_output=True)

segs, info = transcribe(wav)
print(f"LANG: {info.language} (p={info.language_probability:.2f})")
print(f"segments: {len(segs)}")
for s in segs:
    print(f"  [{s.start:6.2f}-{s.end:6.2f}] {s.text}")

print("\n--- diarize ---")
turns = diarize(wav)
spk = sorted({t.speaker for t in turns})
print(f"speakers: {len(spk)} -> {spk}")
for t in turns[:30]:
    print(f"  [{t.start:6.2f}-{t.end:6.2f}] {t.speaker} {t.text[:60]}")
