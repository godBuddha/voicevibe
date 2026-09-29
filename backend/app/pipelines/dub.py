"""
Timing-fit engine — the hardest 20% of a dubbing SaaS.

Problem: after STT + diarization you get speech slots (start, end, speaker).
You translate each slot and synthesize new speech with a cloned voice.
The generated audio almost never matches the slot length. This module
decides, per segment, how to place generated speech:

  1. fits in slot            -> play as-is at slot start
  2. needs mild speedup      -> ffmpeg `atempo` (pitch-preserving time-stretch)
  3. may bleed into silence  -> allowed overrun into the gap before next speaker
  4. hopeless                -> flag for re-translation with a length constraint

Pure stdlib + ffmpeg subprocess. No torch needed — testable anywhere.
Run self-test:  python -m app.pipelines.dub --selftest
"""
from __future__ import annotations

import argparse
import subprocess
from dataclasses import dataclass

MIN_ATEMPO = 0.5   # per-instance range of ffmpeg `atempo`
MAX_ATEMPO = 2.0
MAX_SPEED = 1.35   # beyond this, dubbed speech sounds rushed
MAX_OVERRUN = 0.40  # seconds a segment may bleed past its slot into silence


@dataclass
class Segment:
    idx: int
    start: float          # seconds, from diarization
    end: float
    speaker: str
    text: str             # translated text sent to TTS
    gen_duration: float = 0.0   # duration of synthesized audio (s)
    speed: float = 1.0
    delay_ms: int = 0
    placed: float = 0.0         # actual occupied duration after tempo change
    needs_shorter_text: bool = False
    # bed thực tế đã dùng: "htdemucs" (tách nhạc không lời), "fallback" (nguồn
    # giảm âm lượng — giọng gốc vẫn còn 12%), hoặc None (im lặng). Ghi vào kế
    # hoạch để người dùng thấy chất lượng bed, không phải phán đoán ngầm.
    background: str | None = None


def plan_timing(segments: list[Segment], max_speed: float = MAX_SPEED,
                max_overrun: float = MAX_OVERRUN) -> list[Segment]:
    """Assign speed / delay / flags for every segment."""
    for i, s in enumerate(segments):
        slot = s.end - s.start
        if slot <= 0:
            raise ValueError(f"segment {s.idx}: non-positive slot ({slot:.3f}s)")

        # Budget: own slot, plus silence gap up to the next speaker's start,
        # capped at max_overrun of bleed.
        next_start = segments[i + 1].start if i + 1 < len(segments) else float("inf")
        budget = min(next_start, s.end + max_overrun) - s.start

        if s.gen_duration <= slot:
            s.speed, s.delay_ms, s.placed = 1.0, round(s.start * 1000), s.gen_duration
            s.needs_shorter_text = False
        else:
            speed_needed = s.gen_duration / budget
            if speed_needed <= max_speed:
                s.speed = speed_needed
                s.needs_shorter_text = False
            else:
                # Even at max tempo with full bleed it doesn't fit.
                # Re-translate with "shorter" instruction, then re-synthesize.
                s.speed = max_speed
                s.needs_shorter_text = True
            s.delay_ms = round(s.start * 1000)
            s.placed = s.gen_duration / s.speed
    return segments


def atempo_chain(speed: float) -> list[float]:
    """ffmpeg atempo accepts 0.5..2.0 per instance; chain for anything else."""
    if abs(speed - 1.0) < 1e-9:
        return []
    factors: list[float] = []
    f = speed
    while f > MAX_ATEMPO + 1e-9:
        factors.append(MAX_ATEMPO)
        f /= MAX_ATEMPO
    while f < MIN_ATEMPO - 1e-9:
        factors.append(MIN_ATEMPO)
        f /= MIN_ATEMPO
    factors.append(round(f, 4))
    return factors


def build_mix_cmd(bg_path: str, segments: list[Segment], seg_wavs: list[str],
                  out_path: str) -> list[str]:
    """Mix synthesized segments over the (ducked) original background track."""
    cmd = ["ffmpeg", "-y", "-i", bg_path]
    for w in seg_wavs:
        cmd += ["-i", w]
    chains, labels = [], ["[0:a]"]
    for i, s in enumerate(segments, start=1):
        f = atempo_chain(s.speed)
        tempo = ",".join(f"atempo={x}" for x in f) or "anull"
        chains.append(f"[{i}]{tempo},adelay={s.delay_ms}|{s.delay_ms}[a{i}]")
        labels.append(f"[a{i}]")
    n = len(segments) + 1
    chains.append(f"{''.join(labels)}amix=inputs={n}:duration=first:normalize=0[out]")
    cmd += ["-filter_complex", ";".join(chains), "-map", "[out]", out_path]
    return cmd


def _selftest() -> None:
    segs = [
        Segment(0, 0.0, 4.2, "SPK1", "Xin chào thế giới", gen_duration=5.10),
        Segment(1, 4.5, 9.0, "SPK2", "Dịch nhanh với AI", gen_duration=6.80),
        Segment(2, 9.6, 12.0, "SPK1", "Câu này quá dài", gen_duration=7.50),
    ]
    plan_timing(segs)

    # Invariants
    for s in segs:
        prod = 1.0
        for f in atempo_chain(s.speed):
            prod *= f
        assert abs(prod - s.speed) < 0.01, f"atempo chain mismatch: {prod} != {s.speed}"
        assert s.delay_ms >= 0
        if not s.needs_shorter_text:
            assert s.placed <= (s.end - s.start) + MAX_OVERRUN + 1e-6

    print("== TIMING PLAN ==")
    for s in segs:
        flag = "  <-- RE-TRANSLATE (shorter)" if s.needs_shorter_text else ""
        print(f"#{s.idx} {s.speaker} slot={s.end - s.start:5.2f}s gen={s.gen_duration:5.2f}s "
              f"speed={s.speed:4.2f} delay={s.delay_ms:6d}ms placed={s.placed:5.2f}s{flag}")

    wavs = [f"seg{s.idx}.wav" for s in segs]
    print("\n== FFMPEG MIX ==")
    print(" ".join(build_mix_cmd("background.wav", segs, wavs, "dubbed.m4a")))
    print("\n== SELFTEST PASSED ==")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()
    if args.selftest:
        _selftest()
