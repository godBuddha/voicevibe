"""Day 7 real-GPU smoke: VIDEO dubbing end-to-end (the flagship demo).

1. Build a test video from the D3 sample audio (testsrc visuals + real speech)
2. dub_audio vi->en with background_mode=source_low -> MP4 out
3. Verify: MP4 keeps the video stream, duration preserved
4. Round-trip ASR on the dubbed MP4's audio track

Run on the GPU box:
  cd /workspace/voicevibe && source .venv/bin/activate
  cd backend && PYTHONPATH=. python scripts/d7_smoke.py
"""
from __future__ import annotations

import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ.setdefault("MEDIA_ROOT", "/workspace/media")
os.environ.setdefault("DATABASE_URL", "sqlite:////workspace/voicevibe/backend/voicevibe.db")

from app.pipelines.dub_pipeline import _has_video, dub_audio  # noqa: E402
from app.pipelines.stt import transcribe  # noqa: E402
from app.storage import get_storage  # noqa: E402

SRC_AUDIO = "/workspace/samples/d3_2spk.wav"
SRC_VIDEO = "/workspace/samples/d7_src.mp4"
VOICES = {"SPEAKER_00": "Hải Đăng", "SPEAKER_01": "Mai Anh"}


def build_test_video() -> None:
    if os.path.exists(SRC_VIDEO):
        print(f"[video] exists: {SRC_VIDEO}")
        return
    subprocess.run(
        ["ffmpeg", "-y", "-f", "lavfi", "-i",
         "testsrc=duration=14:size=320x180:rate=15",
         "-i", SRC_AUDIO,
         "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac",
         "-shortest", SRC_VIDEO],
        check=True, capture_output=True)
    print(f"[video] built {SRC_VIDEO}")


def main() -> None:
    build_test_video()
    assert _has_video(SRC_VIDEO), "source video has no video stream?!"
    storage = get_storage()

    key, plan = dub_audio(SRC_VIDEO, "vi", "en", VOICES, storage,
                          background_mode="source_low")
    out_path = storage.get_to_temp(key)
    print(f"[dub] saved {key}")
    assert key.endswith(".mp4"), "video source must produce MP4"
    assert _has_video(out_path), "output MP4 lost the video stream!"

    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries",
                          "format=duration", "-of",
                          "default=noprint_wrappers=1:nokey=1", out_path],
                         capture_output=True, text=True)
    dur = float(out.stdout.strip())
    print(f"[dub] duration {dur:.1f}s (src ~13.4s)")
    assert 0.6 * 13.4 <= dur <= 1.8 * 13.4, f"duration out of range: {dur:.1f}s"

    print("[verify] round-trip ASR on the dubbed MP4 audio track...")
    tmp_wav = "/tmp/d7_check.wav"
    subprocess.run(["ffmpeg", "-y", "-i", out_path, "-ac", "1", "-ar", "16000",
                    tmp_wav], check=True, capture_output=True)
    segs, info = transcribe(tmp_wav, language="en")
    heard = " ".join(s.text for s in segs).strip()
    print(f"[verify] heard: {heard}")
    print(f"[verify] lang={info.language} p={info.language_probability:.2f}")

    ok = info.language == "en" and len(heard.split()) >= 8
    print(f"\nD7 SMOKE: {'PASS' if ok else 'CHECK'} "
          f"(video dub MP4 {dur:.1f}s, {len(heard.split())} en words, "
          f"background=source_low)")


if __name__ == "__main__":
    main()
