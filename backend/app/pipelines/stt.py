"""Day 3: STT + diarization + speaker merge + SRT export.

Stage functions mirror the provider contracts (app/providers/base.py):
  transcribe() -> transcript segments   (faster-whisper, MIT)
  diarize()    -> speaker turns         (pyannote 3.1, gated models -> HF_TOKEN)
  merge()      -> speaker-attributed transcript (max time overlap)
  to_srt()     -> SRT string with [SPEAKER] tags

Note on pyannote 4.x: file-path decoding goes through torchcodec, which needs a
CUDA runtime matching its build. We sidestep that entirely by feeding the
pipeline an in-memory {'waveform', 'sample_rate'} dict (the officially
recommended fallback). Non-wav inputs are converted via ffmpeg first.

Offline selftest (no GPU, no model downloads):
  PYTHONPATH=. python -m app.pipelines.stt --selftest
"""
from __future__ import annotations

import argparse
import os
import subprocess
import tempfile
from dataclasses import replace

from ..providers.base import TranscriptSegment

DIA_MODEL = "pyannote/speaker-diarization-3.1"


def transcribe(audio_path: str, model_size: str = "large-v3",
               compute_type: str = "int8", language: str | None = None,
               device: str = "auto"):
    """faster-whisper transcription -> (segments, info)."""
    from faster_whisper import WhisperModel

    model = WhisperModel(model_size, device=device, compute_type=compute_type)
    segments, info = model.transcribe(audio_path, language=language, vad_filter=True)
    out = [TranscriptSegment(start=s.start, end=s.end, text=s.text.strip())
           for s in segments]
    return out, info


def _audio_dict(audio_path: str) -> dict:
    """Load audio in-memory for pyannote (bypasses torchcodec file decoding)."""
    import soundfile as sf
    import torch

    path = audio_path
    tmp_name = None
    if not audio_path.lower().endswith(".wav"):
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            tmp_name = tmp.name
        subprocess.run(
            ["ffmpeg", "-y", "-i", audio_path, "-ac", "1", "-ar", "16000", tmp_name],
            check=True, capture_output=True,
        )
        path = tmp_name
    try:
        data, sr = sf.read(path, dtype="float32", always_2d=True)  # (time, ch)
    finally:
        if tmp_name:
            os.unlink(tmp_name)
    waveform = torch.from_numpy(data.T.copy())  # (ch, time)
    return {"waveform": waveform, "sample_rate": int(sr)}


def diarize(audio_path: str, hf_token: str | None = None) -> list[TranscriptSegment]:
    """pyannote speaker-diarization -> speaker turns (text empty)."""
    from pyannote.audio import Pipeline

    token = hf_token or os.getenv("HF_TOKEN")
    if not token:
        raise RuntimeError("HF_TOKEN not set — pyannote models are gated on Hugging Face")
    # huggingface_hub reads HF_TOKEN from the environment natively — this works
    # across pyannote 3.x (no `token` kwarg) and 4.x (no `use_auth_token` kwarg).
    os.environ["HF_TOKEN"] = token
    pipe = Pipeline.from_pretrained(DIA_MODEL)
    result = pipe(_audio_dict(audio_path))
    # pyannote 3.x -> Annotation; 4.x -> DiarizeOutput wrapping an Annotation
    ann = result if hasattr(result, "itertracks") else None
    if ann is None:
        ann = getattr(result, "speaker_diarization", None)
    if ann is None:
        from pyannote.core import Annotation

        for v in vars(result).values():
            if isinstance(v, Annotation):
                ann = v
                break
    if ann is None:
        raise RuntimeError(f"no Annotation in diarization output: {type(result)}")
    return [TranscriptSegment(start=float(t.start), end=float(t.end),
                              text="", speaker=str(spk))
            for t, _, spk in ann.itertracks(yield_label=True)]


def merge(transcript: list[TranscriptSegment],
          diarization: list[TranscriptSegment]) -> list[TranscriptSegment]:
    """Assign each transcript segment the speaker with max time overlap."""
    out: list[TranscriptSegment] = []
    for seg in transcript:
        best, best_ov = None, 0.0
        for d in diarization:
            ov = min(seg.end, d.end) - max(seg.start, d.start)
            if ov > best_ov:
                best, best_ov = d.speaker, ov
        out.append(replace(seg, speaker=best))
    return out


def _ts(seconds: float) -> str:
    ms = max(0, int(round(seconds * 1000)))
    h, ms = divmod(ms, 3_600_000)
    m, ms = divmod(ms, 60_000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def to_srt(segments: list[TranscriptSegment]) -> str:
    lines: list[str] = []
    for i, seg in enumerate(segments, 1):
        who = f" [{seg.speaker}]" if seg.speaker else ""
        lines += [str(i), f"{_ts(seg.start)} --> {_ts(seg.end)}", f"{seg.text}{who}", ""]
    return "\n".join(lines)


def _selftest() -> None:
    transcript = [
        TranscriptSegment(0.0, 4.2, "Xin chào các bạn"),
        TranscriptSegment(4.5, 9.0, "Hôm nay thử nghiệm diarization"),
    ]
    dia = [
        TranscriptSegment(0.0, 4.4, "", speaker="SPEAKER_00"),
        TranscriptSegment(4.5, 9.2, "", speaker="SPEAKER_01"),
    ]
    merged = merge(transcript, dia)
    assert merged[0].speaker == "SPEAKER_00", merged[0]
    assert merged[1].speaker == "SPEAKER_01", merged[1]

    inner = merge([TranscriptSegment(5.0, 6.0, "đoạn giữa")], dia)
    assert inner[0].speaker == "SPEAKER_01"

    solo = merge(transcript, [])
    assert all(s.speaker is None for s in solo)

    srt = to_srt(merged)
    assert srt.splitlines()[1] == "00:00:00,000 --> 00:00:04,200", srt
    assert "[SPEAKER_00]" in srt and "[SPEAKER_01]" in srt

    print("merge overlap assignment .. OK")
    print("SRT format ................ OK")
    print("D3 LOGIC SELFTEST PASSED")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()
    if args.selftest:
        _selftest()
