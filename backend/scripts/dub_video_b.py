"""Stage B — dịch + lồng tiếng video mẫu ra tiếng Việt.

Chạy: cd /workspace/voicevibe && source .venv/bin/activate && cd backend
      PYTHONPATH=. VOICEVIBE_INLINE=1 python scripts/dub_video_b.py --lang <src>
Env bắt buộc: HF_TOKEN; src ngoài vi/en cần TRANSLATE_BASE_URL/API_KEY/MODEL.
"""
from __future__ import annotations
import argparse
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

ap = argparse.ArgumentParser()
ap.add_argument("--lang", required=True, help="ngôn ngữ nguồn (zh/en/vi/...)")
ap.add_argument("--speakers", default="SPEAKER_00=Hải Đăng")
ap.add_argument("--bg", default="source_low", help="silence | source_low")
ap.add_argument("--src", default="/workspace/samples/short_xianxia.mp4")
args = ap.parse_args()

voices = {}
for kv in args.speakers.split(","):
    if kv.strip():
        k, v = kv.split("=", 1)
        voices[k.strip()] = v.strip()

from app.pipelines.dub_pipeline import _has_video, dub_audio  # noqa: E402
from app.storage import get_storage  # noqa: E402

assert _has_video(args.src), "source video khong co video stream"
storage = get_storage()
key, plan = dub_audio(args.src, args.lang, "vi", voices, storage,
                      background_mode=args.bg)
out = storage.get_to_temp(key)
out_path = "/workspace/samples/short_xianxia_dub_vi.mp4"
subprocess.run(["cp", out, out_path], check=True)
probe = subprocess.run(["ffprobe", "-v", "error", "-show_entries",
                        "format=duration", "-of",
                        "default=noprint_wrappers=1:nokey=1", out_path],
                       capture_output=True, text=True)
print(f"OUT: {out_path}")
print(f"DURATION: {probe.stdout.strip()}s")
print(f"segments dubbed: {len(plan)}")
for s in plan[:40]:
    print(f"  [{s.start:6.2f}-{s.end:6.2f}] {s.speaker} {s.text}")
