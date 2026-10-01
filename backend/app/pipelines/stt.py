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

# --- Ngưỡng chống hallucination -------------------------------------------------
# Whisper "bịa" chữ ở đoạn im lặng, nhạc, hoặc tiếng ồn: nó vẫn phải sinh ra ký tự
# nào đó, nên nhả ra những câu không hề có trong audio. Với pipeline lồng tiếng,
# chuyện này nguy hiểm gấp đôi: câu bịa bị DỊCH rồi ĐỌC LÊN thành tiếng, tức là
# thêm nội dung không có trong bản gốc.
#
# Vì sao lọc theo XÁC SUẤT của model thay vì danh sách câu: danh sách câu bịa phụ
# thuộc ngôn ngữ, model và phiên bản — "Hãy subscribe cho kênh..." là câu bịa tiếng
# Việt nổi tiếng, nhưng hardcode nó sẽ hụt mọi biến thể khác và mọi ngôn ngữ khác.
# Ba tín hiệu dưới đây do chính model đưa ra, độc lập ngôn ngữ:
#
#   no_speech_prob  — model nghĩ đoạn này KHÔNG có tiếng nói
#   avg_logprob     — độ "tự tin" trung bình khi giải mã; rất thấp = đang đoán bừa
#   compression_ratio — mức nén của văn bản; cao bất thường = lặp lại cùng một câu
#
# Ngưỡng lấy theo mặc định của reference implementation (no_speech 0.6,
# logprob -1.0, compression 2.4), tức là cùng thang đo mà chính Whisper dùng để
# đánh dấu một đoạn là hỏng.
NO_SPEECH_MAX = 0.6        # > mức này: coi như không có tiếng nói
LOGPROB_MIN = -1.0         # < mức này: giải mã thiếu tự tin
LOGPROB_MIN_HARD = -1.5    # < mức này: bỏ bất kể các chỉ số khác
COMPRESSION_MAX = 2.4      # > mức này: văn bản lặp lại bất thường

# Đoạn chỉ có ký hiệu/dấu câu — Whisper sinh ra ở đoạn nhạc hoặc tiếng động.
# `\w` bắt cả chữ có dấu tiếng Việt nên so khớp này độc lập ngôn ngữ.
import re as _re

_ONLY_SYMBOLS = _re.compile(r"^[^\w]*$", _re.UNICODE)

# Whisper chèn nhãn phi-lời-nói trong ngoặc: `[Music]`, `[Applause]`, `[nhạc]`,
# `(tiếng cười)`. Với lồng tiếng, những nhãn này ĐẶC BIỆT tai hại: chúng bị dịch
# rồi đọc lên thành tiếng ("Music" đọc thành "Âm nhạc") — thêm hẳn một câu không
# ai nói. Nhận diện bằng hình dạng (cả chuỗi nằm trong một cặp ngoặc), không bằng
# danh sách từ — danh sách sẽ hụt ngay khi đổi ngôn ngữ.
_ANNOTATION = _re.compile(r"^[\[\(（【][^\[\]\(\)（）【】]*[\]\)）】]$", _re.UNICODE)


def segment_is_hallucination(seg) -> str | None:
    """Trả về LÝ DO nếu đoạn này là hallucination, hoặc None nếu giữ lại.

    Trả lý do (thay vì True/False) để chỗ gọi ghi log được VÌ SAO bỏ — nếu không,
    người vận hành chỉ thấy phụ đề thiếu câu mà không biết tại sao.
    """
    text = (getattr(seg, "text", "") or "").strip()
    if not text:
        return "empty"
    if _ONLY_SYMBOLS.match(text):
        return "chỉ có ký hiệu, không có chữ"
    if _ANNOTATION.match(text):
        return "nhãn phi-lời-nói (nhạc/tiếng động) — dịch rồi đọc lên là thêm câu không ai nói"

    logprob = getattr(seg, "avg_logprob", 0.0)
    if logprob is None:
        logprob = 0.0
    if logprob < LOGPROB_MIN_HARD:
        return f"avg_logprob {logprob:.2f} < {LOGPROB_MIN_HARD}"

    compression = getattr(seg, "compression_ratio", 0.0) or 0.0
    if compression > COMPRESSION_MAX:
        return f"compression_ratio {compression:.2f} > {COMPRESSION_MAX}"

    no_speech = getattr(seg, "no_speech_prob", 0.0)
    if no_speech is None:
        no_speech = 0.0
    # Cần CẢ HAI: no_speech cao mà logprob vẫn tốt là trường hợp bình thường với
    # đoạn nói ngắn/ngắt quãng (model phân vân nhưng vẫn giải mã đúng).
    if no_speech > NO_SPEECH_MAX and logprob < LOGPROB_MIN:
        return f"no_speech_prob {no_speech:.2f} > {NO_SPEECH_MAX} và avg_logprob {logprob:.2f}"
    return None


def drop_hallucinations(raw_segments: list) -> tuple[list, list[tuple[str, str]]]:
    """Lọc hallucination. Trả (giữ lại, [(text, lý do do bỏ)]).

    Không bao giờ trả về danh sách rỗng vì lọc quá tay: nếu bỏ hết thì giữ nguyên
    bản gốc và coi như không lọc — mất sạch nội dung là hỏng nặng hơn nhiễu.
    """
    kept, dropped = [], []
    for seg in raw_segments:
        reason = segment_is_hallucination(seg)
        if reason:
            dropped.append(((getattr(seg, "text", "") or "").strip(), reason))
        else:
            kept.append(seg)
    if raw_segments and not kept:
        return list(raw_segments), []
    return kept, dropped


def _cloud_stt() -> tuple[str, str, str] | None:
    """(base_url, api_key, model) của stage 'stt' khi admin đã gán model cloud —
    None nếu không cấu hình/lỗi DB.

    Đọc ở đây (không ở call sites) vì transcribe() là điểm đi qua duy nhất của
    3 đường (_run_stt, _run_subtitle, dub). Bọc try/except rộng: worker không
    được chết vì DB chưa migrate hay thiếu bảng — rơi về local là đúng.
    """
    try:
        from ..db import SessionLocal
        from ..providers_api import stage_entry

        with SessionLocal() as db:
            e = stage_entry("stt", db)
    except Exception:  # noqa: BLE001
        return None
    if not e:
        return None
    return e["base_url"], e["api_key"], e["model"]


def transcribe(audio_path: str, model_size: str = "large-v3",
               compute_type: str = "int8", language: str | None = None,
               device: str = "auto", filter_hallucinations: bool = True,
               stats: dict | None = None):
    """STT: stage 'stt' có model cloud → OpenAI-compatible /audio/transcriptions;
    không có → faster-whisper local. Trả (segments, info) — cloud không trả info
    whisper nên info=None.

    Quy tắc lỗi: cloud ĐÃ cấu hình mà gọi hỏng → raise (job failed) — KHÔNG
    lặng lẽ rơi về local: admin cấu hình cloud là ý định rõ ràng, tự chuyển
    engine là giấu lỗi (và hoá đơn/latency khác nhau). OpenAIBase._post đã
    retry 429/5xx trước khi buông.
    """
    cloud = _cloud_stt()
    if cloud is not None:
        from ..providers.openai_compat import OpenAISTTProvider
        base, api_key, model = cloud
        raw = list(OpenAISTTProvider(base, api_key, model)
                   .transcribe(audio_path, language=language))
        # Filter chữ (câu bịa rỗng/annotation) vẫn chạy — không phụ thuộc thống
        # kê; filter thống kê tự no-op vì segment cloud không có logprob
        # (getattr default 0.0, xem segment_is_hallucination).
        dropped: list[tuple[str, str]] = []
        if filter_hallucinations:
            raw, dropped = drop_hallucinations(raw)
        out = [TranscriptSegment(start=s.start, end=s.end, text=(s.text or "").strip())
               for s in raw]
        if stats is not None:
            stats["kept"] = len(out)
            stats["dropped"] = [{"text": t[:120], "reason": r} for t, r in dropped]
        return out, None

    from faster_whisper import WhisperModel

    model = WhisperModel(model_size, device=device, compute_type=compute_type)
    segments, info = model.transcribe(audio_path, language=language, vad_filter=True)
    raw = list(segments)

    dropped: list[tuple[str, str]] = []
    if filter_hallucinations:
        raw, dropped = drop_hallucinations(raw)

    out = [TranscriptSegment(start=s.start, end=s.end, text=s.text.strip())
           for s in raw]
    if stats is not None:
        stats["kept"] = len(out)
        stats["dropped"] = [{"text": t[:120], "reason": r} for t, r in dropped]
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


def _setting_hf_token() -> str | None:
    """`hf_token` set trong UI (/admin/settings). None nếu chưa set/lỗi đọc.

    Import bọc try: script chạy ngoài package (uv run scripts/…) không có
    settings_service — khi đó rơi về env như cũ, không phá pipeline.
    """
    try:
        from ..settings_service import get_setting
    except Exception:
        return None
    try:
        return get_setting("hf_token") or None
    except Exception:
        return None


def diarize(audio_path: str, hf_token: str | None = None) -> list[TranscriptSegment]:
    """pyannote speaker-diarization -> speaker turns (text empty)."""
    from pyannote.audio import Pipeline

    # Token ưu tiên: tham số → Settings (`hf_token`, admin set qua UI — trước
    # đây setting này chỉ để trang trí, pipeline chỉ đọc env, đã gặp thật) → env.
    token = hf_token or _setting_hf_token() or os.getenv("HF_TOKEN")
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
