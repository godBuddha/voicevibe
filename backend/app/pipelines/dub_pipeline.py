"""Day 5: full dubbing pipeline — the heart of the product.

STT+diarize (D3) -> translate (D5) -> TTS per speaker (D4)
  -> timing-fit (D1) -> ffmpeg mix -> storage.

MVP notes:
  - Background bed = silence (speech/background separation with Demucs is a
    D7 stretch goal — music preservation).
  - Segments flagged `needs_shorter_text` by the timing engine are synthesized
    at max_speed and may slightly overrun — the re-translate-with-length-
    constraint loop is D6 polish.

Offline selftest (no models — plan building + ffmpeg command construction):
  PYTHONPATH=. python -m app.pipelines.dub_pipeline --selftest
"""
from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import wave

from ..providers.local import LocalVieneuTTSProvider
from .dub import Segment, build_mix_cmd, plan_timing
from .stt import diarize, merge, transcribe
from .translate import build_translator


def _ffprobe_duration(path: str) -> float:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", path],
        capture_output=True, text=True, check=True)
    return float(out.stdout.strip())


def _wav_duration(path: str) -> float:
    with wave.open(path) as w:
        return w.getnframes() / w.getframerate()


def _extract_wav(media_path: str, out_path: str, sr: int = 16000) -> None:
    subprocess.run(["ffmpeg", "-y", "-i", media_path, "-ac", "1", "-ar", str(sr),
                    out_path], check=True, capture_output=True)


def _silence_bed(duration: float, path: str, sr: int = 48000) -> None:
    subprocess.run(["ffmpeg", "-y", "-f", "lavfi",
                    "-i", f"anullsrc=r={sr}:cl=mono",
                    "-t", f"{duration:.3f}", "-q:a", "0", path],
                   check=True, capture_output=True)


def _has_video(path: str) -> bool:
    """True only for REAL video streams (ignore mp3 cover art etc.)."""
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v",
         "-show_entries", "stream=codec_name", "-of", "csv=p=0", path],
        capture_output=True, text=True)
    codecs = [c.strip() for c in out.stdout.strip().splitlines() if c.strip()]
    return any(c not in ("mjpeg", "png", "bmp", "gif") for c in codecs)


def _make_bed(source_path: str, duration: float, mode: str, path: str,
              sr: int = 48000) -> None:
    """background_mode: silence (clean dub) | source_low (karaoke-style backing)."""
    if mode == "source_low":
        subprocess.run(["ffmpeg", "-y", "-i", source_path, "-ac", "1", "-ar", str(sr),
                        "-af", "volume=0.12", "-t", f"{duration:.3f}", path],
                       check=True, capture_output=True)
    else:
        _silence_bed(duration, path, sr)


def build_plan(attributed, texts, gen_durations, max_speed: float = 1.35):
    """Timing plan from attributed segments + translations + measured durations."""
    plan_segs = [
        Segment(idx=i, start=s.start, end=s.end, speaker=s.speaker or "",
                text=t, gen_duration=d)
        for i, (s, t, d) in enumerate(zip(attributed, texts, gen_durations))
    ]
    plan_timing(plan_segs, max_speed=max_speed)
    return plan_segs


def dub_audio(source_path: str, source_lang: str, target_lang: str,
              speaker_voices: dict[str, str | None], storage,
              out_key: str | None = None, max_speed: float = 1.35,
              keep_temp: bool = False, background_mode: str = "silence",
              mux_video: bool = True) -> tuple[str, list[Segment]]:
    """Dub an audio OR video file. speaker_voices: SPEAKER_xx -> preset name.

    Video in -> MP4 out (video stream copied, dubbed audio as AAC).
    background_mode: silence | source_low (original ducked to 12%).
    Returns (storage_key, planned_segments).
    """
    tmpdir = tempfile.mkdtemp(prefix="dub_")
    try:
        work_wav = os.path.join(tmpdir, "src16k.wav")
        _extract_wav(source_path, work_wav)

        # 1) STT + diarize + speaker attribution
        segs, _info = transcribe(work_wav, language=source_lang)
        turns = diarize(work_wav)
        attributed = merge(segs, turns)
        if not attributed:
            raise RuntimeError("no speech detected in source")

        # 2) translate each segment
        tr = build_translator(source_lang, target_lang)
        texts = [tr.translate(s.text) for s in attributed]

        # 3) synthesize per segment; auto-assign presets to unseen speakers
        tts = LocalVieneuTTSProvider()
        preset_rotation = ["Hải Đăng", "Mai Anh", "Quang Sơn", "Thùy Dung",
                           "Thái Sơn", "Trúc Ly", "Ngọc Huyền", "Thanh Bình"]
        auto_idx: dict[str, int] = {}
        gen_durations, seg_wavs = [], []
        for i, text_t in enumerate(texts):
            spk = attributed[i].speaker or ""
            voice = speaker_voices.get(spk) or ""
            if not voice:
                idx = auto_idx.setdefault(spk, len(auto_idx))
                voice = preset_rotation[idx % len(preset_rotation)]
            audio = tts.synthesize(text_t, voice=voice or None)
            wav_path = os.path.join(tmpdir, f"seg{i}.wav")
            with open(wav_path, "wb") as f:
                f.write(audio)
            gen_durations.append(_wav_duration(wav_path))
            seg_wavs.append(wav_path)

        # 4) timing fit
        plan_segs = build_plan(attributed, texts, gen_durations, max_speed=max_speed)

        # 5) mix over the background bed
        src_dur = _ffprobe_duration(source_path)
        bed = os.path.join(tmpdir, "bed.wav")
        _make_bed(source_path, src_dur + 0.5, background_mode, bed)
        mixed_wav = os.path.join(tmpdir, "dubbed.wav")
        cmd = build_mix_cmd(bed, plan_segs, seg_wavs, mixed_wav)
        subprocess.run(cmd, check=True, capture_output=True)

        # 6) mux video when the source has a real video stream
        if mux_video and _has_video(source_path):
            out_path = os.path.join(tmpdir, "dubbed.mp4")
            subprocess.run(["ffmpeg", "-y", "-i", source_path, "-i", mixed_wav,
                            "-map", "0:v:0", "-map", "1:a:0",
                            "-c:v", "copy", "-c:a", "aac", "-shortest", out_path],
                           check=True, capture_output=True)
            key = out_key or f"jobs/dub/{os.urandom(6).hex()}.mp4"
        else:
            out_path = mixed_wav
            key = out_key or f"jobs/dub/{os.urandom(6).hex()}.wav"

        storage.put_from_file(key, out_path)
        return key, plan_segs
    finally:
        if not keep_temp:
            shutil.rmtree(tmpdir, ignore_errors=True)


def _selftest() -> None:
    from ..providers.base import TranscriptSegment

    attributed = [
        TranscriptSegment(0.0, 4.2, "Xin chào các bạn, mình là Long.", "SPEAKER_00"),
        TranscriptSegment(4.5, 9.0, "Chào Long, mình là Mai Anh.", "SPEAKER_01"),
    ]
    texts = ["Hello everyone, I am Long.", "Hi Long, I am Mai Anh."]
    durations = [3.9, 5.2]  # seg0 fits; seg1 needs mild speedup via overrun budget

    plan = build_plan(attributed, texts, durations)
    assert plan[0].speed == 1.0 and plan[0].delay_ms == 0
    # last segment: budget = end + MAX_OVERRUN - start = 4.9s
    assert abs(plan[1].speed - 5.2 / 4.9) < 1e-6, plan[1].speed
    assert plan[1].delay_ms == 4500

    # hopeless segment -> flagged for shorter re-translate (D6 loop)
    plan2 = build_plan(attributed[:1], ["A very very long english sentence " * 5], [9.0])
    assert plan2[0].needs_shorter_text is True

    # ffmpeg command shape
    cmd = build_mix_cmd("bed.wav", plan, ["s0.wav", "s1.wav"], "out.wav")
    assert cmd[0] == "ffmpeg" and "-filter_complex" in cmd
    joined = " ".join(cmd)
    assert "atempo" in joined and "adelay" in joined and "amix" in joined

    print("plan speeds/delays ........ OK")
    print("needs_shorter_text flag ... OK")
    print("ffmpeg mix command ........ OK")
    # video detection + bed modes (ffmpeg present in sandbox and on GPU box)
    _sp = subprocess.run(
        ["ffmpeg", "-y", "-f", "lavfi", "-i", "testsrc=duration=1:size=128x72:rate=10",
         "-f", "lavfi", "-i", "sine=frequency=440:duration=1",
         "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac",
         "-shortest", "/tmp/d7t.mp4"], capture_output=True)
    if _sp.returncode == 0:  # libx264 available
        assert _has_video("/tmp/d7t.mp4") is True
        subprocess.run(["ffmpeg", "-y", "-f", "lavfi",
                        "-i", "sine=frequency=440:duration=1", "/tmp/d7t.wav"],
                       capture_output=True, check=True)
        assert _has_video("/tmp/d7t.wav") is False
        _make_bed("/tmp/d7t.wav", 1.0, "silence", "/tmp/d7bed_s.wav")
        _make_bed("/tmp/d7t.wav", 1.0, "source_low", "/tmp/d7bed_l.wav")
        assert _wav_duration("/tmp/d7bed_s.wav") > 0.9
        assert _wav_duration("/tmp/d7bed_l.wav") > 0.9
        print("video detect + bed modes .. OK")
    else:
        print("video detect skipped (no libx264)")

    print("DUB PIPELINE SELFTEST PASSED")


if __name__ == "__main__":
    _selftest()
