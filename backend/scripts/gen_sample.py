"""Generate the 2-speaker Vietnamese sample used by d5/d7 smoke tests.

Creates /workspace/samples/d3_2spk.wav (~13s): line-by-line concat of VieNeu
preset voices (Hải Đăng = SPEAKER_00, Mai Anh = SPEAKER_01), tiny silence
gaps between turns — same shape as a real two-person conversation clip.

Run on the GPU box:
  cd /workspace/yupvox-clone && source .venv/bin/activate
  cd backend && PYTHONPATH=. python scripts/gen_sample.py
"""
from __future__ import annotations

import os
import sys
import wave

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

OUT_DIR = "/workspace/samples"
OUT_WAV = os.path.join(OUT_DIR, "d3_2spk.wav")
SR = 48000

LINES = [  # (voice, text) — turns alternate between the two speakers
    ("Hải Đăng", "Xin chào các bạn, mình là Long."),
    ("Hải Đăng", "Hôm nay chúng ta sẽ thử nghiệm hệ thống dịch và lồng tiếng tự động "
                 "do chính mình viết trong 7 ngày."),
    ("Mai Anh", "Chào Long, mình là Mai Anh đây."),
    ("Mai Anh", "Nghe nói công nghệ giọng nói AI đang thay đổi rất nhanh, đúng không nào?"),
]
GAP_S = 0.3  # silence between turns


def main() -> None:
    os.makedirs(OUT_DIR, exist_ok=True)
    from vieneu import Vieneu

    tts = Vieneu(mode="v3turbo")
    import numpy as np

    parts: list[np.ndarray] = []
    with wave.open(OUT_WAV, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        for voice, text in LINES:
            audio = np.asarray(tts.infer(text, voice=voice), dtype=np.float32)
            if audio.ndim > 1:
                audio = audio.mean(axis=0)
            pcm = (np.clip(audio, -1.0, 1.0) * 32767).astype("<i2")
            w.writeframes(pcm.tobytes())
            w.writeframes(b"\x00\x00" * int(SR * GAP_S))  # inter-turn silence
    with wave.open(OUT_WAV) as w:
        dur = w.getnframes() / w.getframerate()
    print(f"[sample] saved {OUT_WAV} ({dur:.1f}s, {len(LINES)} turns, "
          f"2 voices: {LINES[0][0]}/{LINES[-1][0]})")


if __name__ == "__main__":
    main()
