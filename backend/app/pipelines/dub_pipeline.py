"""Full dubbing pipeline — the heart of the product.

STT+diarize (D3) -> translate (D5) -> TTS per speaker (D4)
  -> timing-fit (D1) -> ffmpeg mix -> storage.

A1 — Sổ tay công đoạn (manifest resume): mỗi khâu xong ghi vào
  `workdir/manifest.json` (file nguyên tử, xem app/pipelines/manifest.py).
  Job hỏng / bị hủy giữa đường thì lần "Chạy lại" sau bỏ qua khâu đã xong:
  STT của video 60 phút không phải nghe lại, bản dịch không phải dịch lại.
  Cờ ok luôn được kiểm chứng bằng FILE THẬT (cờ có thể ghi trước khi worker
  bị kill kịp ghi file — chỉ tin khi file tồn tại và rỗng).

A2 — Cắt audio dài tại điểm yên tĩnh (split_points.py): audio > 5 phút được
  chia đoạn để STT từng phần, mỗi đoạn xong ghi checkpoint — worker chết giữa
  chừng chỉ mất đúng đoạn đang nghe.

A3 — Dịch LOẠT 12 câu + ngữ cảnh ±2 + bisect + checkpoint (translate_batch.py)
  cho translator LLM; Marian local vẫn dịch từng câu như cũ.

A5 — Estimator ước lượng thời lượng đọc TRƯỚC khi gọi TTS: đoạn chắc chắn
  vượt ngân sách thì xin bản ngắn hơn TRƯỚC, đỡ tổng hợp rồi vứt (mỗi lần đọc
  là một lượt GPU). Hiệu chuẩn EMA học từ thời lượng đo thật giữa job.

Bắt buộc giữ nguyên (contract của test_retranslate.py + smoke scripts):
  - `build_plan` / `_retranslate_pass` hoạt động ở mức SEGMENT với chữ ký như cũ.
  - Signature `dub_audio` chỉ THÊM tham số keyword có mặc định — 3 smoke script
    gọi positional vẫn chạy đúng.

Offline selftest (no models — plan building + ffmpeg command construction + a
fake-provider end-to-end with manifest resume):
  PYTHONPATH=. python -m app.pipelines.dub_pipeline --selftest
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import wave
from typing import Callable

from ..providers.base import TranscriptSegment
from ..providers.tts_catalog import build_tts, rotate_preset
from .dub import GAP_TOLERANCE, Segment, build_mix_cmd, plan_timing
from .estimator import StatisticalEstimator
from .manifest import (JobCancelled, Manifest, atomic_write_json,
                       params_fingerprint)
from .split_points import clip, get_split_points
from .stt import diarize, merge, transcribe
from .translate import batch_capable, build_translator
from .translate_batch import BatchConfig, BatchTranslator

# A2: audio dài hơn NGƯỜNG này (giây) mới đáng chia đoạn để STT tái tục.
# KrillinAI dùng 5 phút — giữ nguyên: ngắn hơn thì cả video thường chỉ có 1 đoạn,
# chia để làm gì. Job phụ đề song song vẫn để faster-whisper tự xử cả file.
SPLIT_SEGMENT_SECONDS = 300

# B5: xoay giọng đa người nói đổi theo backend — hằng cũ giữ lại chỉ làm THAM
# CHIẾU (catalog thật ở providers/tts_catalog.PRESET_VOICES["local"]).
PRESET_ROTATION = ["Hải Đăng", "Mai Anh", "Quang Sơn", "Thùy Dung",
                   "Thái Sơn", "Trúc Ly", "Ngọc Huyền", "Thanh Bình"]


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


def _separate_vocals(source_path: str, stem_path: str,
                     device: str = "auto") -> str | None:
    """Tách giọng hát khỏi nhạc bằng Demucs (MIT) — ghi accompaniment vào stem_path.

    `background_mode=source_low` cũ chỉ giảm âm lượng NGUỒN: giọng gốc vẫn còn
    trong bed ở mức 12%, đè lên giọng dịch → hai giọng rên xen nhau ("echo").
    Tách stem thật thì bed là **nhạc không lời**, không còn giọng gốc để đè.

    Trả về tên model nếu thành công, None nếu không tách được (thiếu gói /
    model chưa tải / không có torch). Tách là NÂNG CHẤT, không phải điều kiện để
    job chạy — rơi về đường giảm âm lượng cũ, job vẫn hoàn thành. Nhưng fallback
    cần được NHÌN THẤY: caller ghi vào kế hoạch.

    `htdemucs` trả **4 stem** (`drums`, `bass`, `other`, `vocals`) — KHÔNG có stem
    `no_vocals` (đã kiểm thật: `separate_audio_file` trả đúng bốn tên đó; tài liệu
    không có, phải đoán theo trí nhớ là sai). Nhạc không lời = tổng 3 stem phi
    giọng, qua `save_audio` để lo đúng samplerate/channels.
    """
    try:
        from demucs import api
    except ImportError:
        return None
    try:
        separator = api.Separator(model="htdemucs", device=device, shifts=0,
                                  progress=False)
        _orig, stems = separator.separate_audio_file(source_path)
        parts = [stems[k] for k in ("drums", "bass", "other") if k in stems]
        if not parts:  # dạng model khác — không dựng được accompaniment
            return None
        accompaniment = parts[0]
        for t in parts[1:]:
            accompaniment = accompaniment + t
        # CHÚ Ý THỨ TỰ: `save_audio(wav_tensor, path, …)` — tensor TRƯỚC, đường
        # dẫn SAU. Truyền ngược lại thì traceback chỉ nói "'str' object has no
        # attribute 'dtype'" (đã gặp thật) — và broad except biến nó thành None.
        api.save_audio(accompaniment, stem_path,
                       samplerate=separator.samplerate, clip="clamp")
        return "htdemucs"
    except Exception:  # noqa: BLE001 — mọi lỗi tách đều rơi về đường cũ
        return None


def _has_video(path: str) -> bool:
    """True only for REAL video streams (ignore mp3 cover art etc.)."""
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v",
         "-show_entries", "stream=codec_name", "-of", "csv=p=0", path],
        capture_output=True, text=True)
    codecs = [c.strip() for c in out.stdout.strip().splitlines() if c.strip()]
    return any(c not in ("mjpeg", "png", "bmp", "gif") for c in codecs)


def _retranslate_pass(tr, plan, texts, gen_durations, seg_wavs, seg_voices,
                      tts, tmpdir: str, round_no: int) -> int:
    """Gọi lại translator cho các đoạn vượt thời lượng, đo trên AUDIO thật.

    Vì sao cần: `plan_timing` chỉ GẮN CỜ `needs_shorter_text`; cách duy nhất để
    khớp là ép `atempo` tới `max_speed` (1.35), và ở tốc độ đó giọng bị méo rõ.
    Bản dịch ngắn hơn thì nghe tự nhiên hơn hẳn — prompt `retranslate_timing` đã
    có sẵn trong bảng `prompts` cho đúng việc này.

    Ba điều quyết định tính đúng đắn:
      1. **Ngân sách ký tự tính từ tốc độ nói THẬT** của chính bản dịch hiện tại
         (ký tự/giây đo từ audio đã tổng hợp), không phải một con số chung. Cùng
         một câu, người nói nhanh/chậm cho ra ngân sách khác nhau.
      2. **Đo trên audio tổng hợp, không tin độ dài chuỗi.** Model hoàn toàn có
         thể trả về chuỗi ngắn hơn mà nói ra dài hơn (viết tắt, số, từ dài). Chỉ
         nhận khi `gen_duration` thật sự giảm.
      3. **Một lượt, không lặp vô hạn**: trả về số đoạn đã cải thiện; vòng ngoài
         dừng khi không còn đoạn nào cờ, hoặc khi lượt này không cải thiện được gì
         (translator không hỗ trợ / model trả về dài hơn) — tránh gọi LLM mãi không
         tiến triển.

    Trả về số đoạn đã được thay bằng bản ngắn hơn.
    """
    improved = 0
    for s in plan:
        if not s.needs_shorter_text:
            continue
        i = s.idx
        cur = texts[i]
        dur = gen_durations[i]
        slot = s.end - s.start
        if dur <= 0 or not cur.strip() or slot <= 0:
            continue

        chars_per_sec = len(cur) / dur
        # 0.95: chừa biên, vì tốc độ nói không hoàn toàn tuyến tính theo ký tự
        max_chars = max(8, int(chars_per_sec * slot * 0.95))
        if max_chars >= len(cur):
            continue  # bản dịch đã ngắn hơn cả ngân sách -> ép tốc độ là đủ

        shorter_fn = getattr(tr, "retranslate_shorter", None)
        if shorter_fn is None:
            # Local Marian không có đường này (dịch lại ngắn hơn cần LLM). Không
            # phải lỗi — giữ nguyên và để timing engine ép tốc độ như trước.
            continue
        try:
            shorter = (shorter_fn(cur, max_chars) or "").strip()
        except Exception:  # noqa: BLE001 — lỗi mạng/LLM không được giết cả job
            continue
        if not shorter or len(shorter) >= len(cur):
            continue

        voice = seg_voices[i]
        try:
            audio = tts.synthesize(shorter, voice=voice or None)
        except Exception:  # noqa: BLE001
            continue
        path = os.path.join(tmpdir, f"seg{i}r{round_no}.wav")
        with open(path, "wb") as f:
            f.write(audio)
        new_dur = _wav_duration(path)
        if new_dur >= dur:
            continue  # chuỗi ngắn hơn nhưng nói RA dài hơn -> không nhận

        texts[i] = shorter
        gen_durations[i] = new_dur
        seg_wavs[i] = path
        improved += 1
    return improved


def _make_bed(source_path: str, duration: float, mode: str, path: str,
              sr: int = 48000, separate: bool = True) -> str | None:
    """background_mode: silence (lồng tiếng sạch) | source_low (nhạc nền kiểu karaoke).

    Khi `separate` bật (mặc định) và Demucs khả dụng, `source_low` dùng
    **nhạc không lời tách được** thay vì nguồn giảm âm lượng → không còn giọng
    gốc đè lên giọng dịch. Trả về `"htdemucs"` (đã tách), `"fallback"` (đã dùng
    đường giảm âm lượng cũ) hoặc None (bed im lặng).
    """
    if mode == "source_low":
        if separate:
            got = _separate_vocals(source_path, path)
            if got:
                # stem trả ở samplerate/channels của model; quy về mono @sr của mix
                subprocess.run(
                    ["ffmpeg", "-y", "-i", path, "-ac", "1", "-ar", str(sr),
                     "-t", f"{duration:.3f}", path + ".n.wav"],
                    check=True, capture_output=True)
                os.replace(path + ".n.wav", path)
                return got
        subprocess.run(["ffmpeg", "-y", "-i", source_path, "-ac", "1", "-ar", str(sr),
                        "-af", "volume=0.12", "-t", f"{duration:.3f}", path],
                       check=True, capture_output=True)
        return "fallback"
    _silence_bed(duration, path, sr)
    return None


def build_plan(attributed, texts, gen_durations, max_speed: float = 1.35):
    """Timing plan from attributed segments + translations + measured durations."""
    plan_segs = [
        Segment(idx=i, start=s.start, end=s.end, speaker=s.speaker or "",
                text=t, gen_duration=d)
        for i, (s, t, d) in enumerate(zip(attributed, texts, gen_durations))
    ]
    plan_timing(plan_segs, max_speed=max_speed)
    return plan_segs


def _translator_tag(tr) -> str:
    """Nhận diện bộ dịch cho vân tay tham số: đổi model/provider giữa hai lần
    chạy → bản dịch cũ là của mô hình khác → sổ tay phải bị coi là lỗi thời."""
    chat = getattr(tr, "_chat", None)
    model = getattr(chat, "model", "") if chat else ""
    return f"{type(tr).__name__}:{model or 'marian'}"


def _voice_plan(attributed, speaker_voices: dict, manifest: Manifest,
                tts_backend: str = "local") -> list[str]:
    """Gán giọng cho từng segment — GHI SỔ TRƯỚC khi đọc (A1).

    Tự xoay preset cho người nói lạ là hàm thuần của transcript: cùng transcript
    (đã lưu) thì cùng thứ tự gán — nên có thể tính MỘT LẦN rồi persist. Resume
    đọc lại từ manifest: không bao giờ xảy ra "lần trước giọng A, lần sau giọng
    B" cho cùng một người nói.
    """
    got = manifest.outputs.get("voices")
    if isinstance(got, list) and len(got) == len(attributed):
        return got
    auto_idx: dict[str, int] = {}
    plan: list[str] = []
    for s in attributed:
        spk = s.speaker or ""
        # "*" = "áp cho MỌI người nói" — UI không biết trước id speaker
        # (SPEAKER_00…) vì diarization chạy sau, nên map-all phải có phím tắt.
        voice = speaker_voices.get(spk) or speaker_voices.get("*") or ""
        if not voice:
            idx = auto_idx.setdefault(spk, len(auto_idx))
            voice = rotate_preset(tts_backend, idx)
        plan.append(voice)
    manifest.outputs["voices"] = plan
    manifest.save()
    return plan


def _read_json(path: str) -> dict | None:
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else None
    except (OSError, ValueError):
        return None


def dub_audio(source_path: str, source_lang: str, target_lang: str,
              speaker_voices: dict[str, str | None], storage,
              out_key: str | None = None, max_speed: float = 1.35,
              keep_temp: bool = False, background_mode: str = "silence",
              mux_video: bool = True, retranslate_rounds: int = 2,
              *, workdir: str | None = None, job_id: str | None = None,
              abort_check: Callable[[], bool] | None = None,
              progress_cb: Callable[[int, str], None] | None = None,
              key_prefix: str | None = None,
              system_prompt: str | None = None,
              batch_size: int = 12, context_sentences: int = 2,
              source_url: str | None = None, quality: str | None = None,
              sub_source: str | None = None, captions=None,
              tts_backend: str = "local",
              transcribe_fn=None, diarize_fn=None, merge_fn=None,
              translator_factory=None, tts_factory=None,
              ) -> tuple[str, list[Segment]]:
    """Dub an audio OR video file. speaker_voices: SPEAKER_xx -> preset name.

    Video in -> MP4 out (video stream copied, dubbed audio as AAC).
    background_mode: silence | source_low (original ducked to 12%).
    retranslate_rounds: số lượt xin bản dịch ngắn hơn cho đoạn vượt thời lượng
        (0 = tắt; chỉ có tác dụng với translator dạng LLM, xem `_retranslate_pass`).

    A1 tham số mới (mặc định None/giữ hành vi cũ):
        workdir        thư mục làm việc BỀN (media/jobs/{id}/work) — bật resume;
                       None = tmpdir dùng một lần như trước.
        job_id         ghi vào manifest (định danh, không ảnh hưởng thuật toán).
        abort_check    fn() -> bool; True giữa đường → raise JobCancelled.
        progress_cb    fn(percent:int, msg:str) — phơi tiến độ từng khâu.
        key_prefix     tiền tố key kết quả (vd "jobs/{id}/") — cùng tiền tố với
                       workdir nên xóa job dọn sạch; None = hành vi cũ.
        system_prompt  override Thư viện Prompt cho bộ dịch.
        batch_size / context_sentences  núm dịch batch (A3).
        source_url / quality / sub_source  B1-B2: các tham số NHẬP TỪ LINK — chỉ
                       dùng cho VÂN TAY (không tác động thuật toán ở đây): file
                       tải về luôn có tên cố định (source.{ext}), đổi link mà
                       không vào vân tay là tái dùng nhầm sổ tay của video khác.
        captions       B2: phụ đề YouTube sẵn có (list[TranscriptSegment]) — có
                       mặt thì BỎ WHISPER (vẫn diarize để gán người nói).
        tts_backend    B5: "local" (VieNeu, mặc định) | "edge" | "cloud" — đổi
                       backend là ĐỔI CHẤT LƯỢNG GIỌNG, phải nằm trong vân tay.
        *_fn / *_factory  điểm cắm giả cho test (mặc định dùng engine thật).
    Returns (storage_key, planned_segments).
    """
    own_tmp = workdir is None
    if own_tmp:
        workdir = tempfile.mkdtemp(prefix="dub_")
    os.makedirs(workdir, exist_ok=True)
    job_id = job_id or os.path.basename(os.path.dirname(os.path.abspath(workdir)))

    def _abort() -> None:
        if abort_check is not None and abort_check():
            manifest.note("bị hủy giữa đường — Chạy lại sẽ tiếp tục từ công đoạn đã xong")
            raise JobCancelled("job bị hủy giữa đường")

    def _report(pct: int, msg: str) -> None:
        if progress_cb is not None:
            progress_cb(int(pct), msg)

    # 0) Bộ dịch dựng TRƯỚC (fail fast: cặp ngôn ngữ không hỗ trợ thì chết ngay,
    #    đỡ tốn cả khâu STT rồi mới biết không dịch được) → vân tay → sổ tay.
    tr = (translator_factory() if translator_factory
          else build_translator(source_lang, target_lang, system_prompt=system_prompt))
    fp = params_fingerprint(
        {"source_lang": source_lang, "target_lang": target_lang,
         "speaker_voices": speaker_voices, "background_mode": background_mode,
         "max_speed": max_speed, "retranslate_rounds": retranslate_rounds,
         "mux_video": mux_video, "batch_size": batch_size,
         "context_sentences": context_sentences,
         "prompt_id": None, "media_url": source_path,
         "source_url": source_url, "quality": quality, "sub_source": sub_source,
         "tts_backend": tts_backend},
        _translator_tag(tr))
    manifest = Manifest.load_or_none(workdir, fp) or Manifest.create(workdir, job_id, fp)
    if manifest.stage_ok("mux"):
        resumed_all = " (resume: mọi công đoạn đã xong)"
    else:
        resumed_all = ""

    # 1) CHUẨN BỊ — trích 16kHz + (audio dài) chia đoạn tại điểm yên tĩnh (A2)
    src16k = os.path.join(workdir, "src16k.wav")
    if not manifest.stage_ok("prepare", "src16k.wav"):
        _abort()
        _report(12, "chuẩn bị âm thanh")
        _extract_wav(source_path, src16k)
        dur = _ffprobe_duration(source_path)
        manifest.outputs["duration"] = dur
        chunks = []
        if dur > SPLIT_SEGMENT_SECONDS:
            pts = get_split_points(src16k, SPLIT_SEGMENT_SECONDS, duration=dur)
            for k in range(len(pts) - 1):
                f = f"chunk_{k:03d}.wav"
                clip(src16k, pts[k], pts[k + 1], os.path.join(workdir, f))
                chunks.append({"start": pts[k], "end": pts[k + 1], "file": f})
            manifest.note(f"audio dài {dur:.0f}s — chia {len(chunks)} đoạn tại điểm "
                          "yên tĩnh để nghe từng phần có thể tái tục")
        manifest.outputs["chunks"] = chunks
        manifest.mark("prepare")
    src_dur = manifest.outputs.get("duration") or _ffprobe_duration(source_path)
    chunks: list[dict] = manifest.outputs.get("chunks") or []

    # 2) NGHE — STT + diarize + gán người nói; ghi transcript.json (A1)
    #    Audio đã chia đoạn → nghe TỪNG ĐOẠN, mỗi đoạn xong ghi checkpoint (A2)
    #    — chết giữa chừng chỉ mất đúng đoạn đang nghe.
    transcript_file = os.path.join(workdir, "transcript.json")
    rows: list[dict] = []
    if manifest.stage_ok("stt", "transcript.json"):
        rows = (_read_json(transcript_file) or {}).get("segments") or []
        if not rows:
            # Cờ ok nhưng file hỏng (bị xoá tay / ghi nửa vời từ kill cũ) — tự
            # chữa như khâu dịch: coi khâu nghe là chưa xong, nghe lại từ đầu.
            manifest.note("transcript.json hỏng — nghe lại từ đầu")
    if rows:
        attributed = [TranscriptSegment(start=d["start"], end=d["end"],
                                        text=d["text"], speaker=d["speaker"])
                      for d in rows]
    elif captions is not None:
        # B2 — phụ đề YouTube SẴN CÓ: bỏ WHISPER (tiết kiệm GPU cả giờ cho video
        # dài), vẫn DIARIZE để gán người nói cho từng câu.
        _abort()
        diarize_fn = diarize_fn or diarize
        merge_fn = merge_fn or merge
        _report(20, "dùng phụ đề YouTube sẵn có — bỏ qua nghe lại")
        turns = diarize_fn(src16k)
        attributed = merge_fn(list(captions), turns)
        if not attributed:
            manifest.mark("stt", error="phụ đề YouTube rỗng sau khi gán người nói")
            raise RuntimeError("no speech detected in source (captions empty)")
        atomic_write_json(transcript_file, {
            "segments": [{"start": s.start, "end": s.end, "text": s.text,
                          "speaker": s.speaker} for s in attributed]})
        manifest.outputs["transcript"] = "transcript.json"
        manifest.outputs["stt_source"] = "youtube-captions"
        manifest.note("nghe bằng PHỤ ĐỀ YOUTUBE sẵn có — bỏ qua Whisper")
        manifest.mark("stt")
    else:
        _abort()
        transcribe_fn = transcribe_fn or (lambda p, language=None, stats=None:
                                          transcribe(p, language=language, stats=stats))
        diarize_fn = diarize_fn or diarize
        merge_fn = merge_fn or merge
        stt_stats: dict = {}
        raw_dicts: list[dict] = []
        if chunks:
            prog_path = os.path.join(workdir, "stt_progress.json")
            prog = _read_json(prog_path) or {"chunks": {}}
            for idx, ch in enumerate(chunks):
                got = prog["chunks"].get(str(idx))
                if got is None:
                    _abort()
                    _report(15 + 10 * idx / len(chunks),
                            f"nghe đoạn {idx + 1}/{len(chunks)}")
                    segs_c, _info = transcribe_fn(
                        os.path.join(workdir, ch["file"]),
                        language=source_lang, stats=stt_stats)
                    got = [{"start": s.start + ch["start"], "end": s.end + ch["start"],
                            "text": s.text, "speaker": None} for s in segs_c]
                    prog["chunks"][str(idx)] = got
                    atomic_write_json(prog_path, prog)
                raw_dicts.extend(got)
            raw_segments = [TranscriptSegment(start=d["start"], end=d["end"],
                                              text=d["text"]) for d in raw_dicts]
        else:
            segs, _info = transcribe_fn(src16k, language=source_lang, stats=stt_stats)
            raw_segments = segs
        turns = diarize_fn(src16k)
        attributed = merge_fn(raw_segments, turns)
        if not attributed:
            manifest.mark("stt", error="không phát hiện tiếng nói trong nguồn")
            raise RuntimeError("no speech detected in source")
        atomic_write_json(transcript_file, {
            "segments": [{"start": s.start, "end": s.end, "text": s.text,
                          "speaker": s.speaker} for s in attributed]})
        manifest.outputs["transcript"] = "transcript.json"
        manifest.mark("stt")
    _report(30, "nghe xong" + resumed_all)

    # 3) DỊCH — batch + ngữ cảnh + checkpoint (A3); Marian local từng câu như cũ
    origins = [s.text for s in attributed]
    translation_file = os.path.join(workdir, "translation.json")
    texts: list[str] | None = None
    if manifest.stage_ok("translate", "translation.json"):
        saved = _read_json(translation_file)
        if saved and isinstance(saved.get("translated"), list):
            texts = saved["translated"]
    if texts is None or len(texts) != len(origins):
        _abort()
        chat = batch_capable(tr)
        if chat is not None:
            bt = BatchTranslator(chat, source_lang, target_lang, fallback=tr,
                                 system_prompt=system_prompt,
                                 config=BatchConfig(batch_size=batch_size,
                                                    context_sentences=context_sentences),
                                 checkpoint_path=translation_file,
                                 progress_cb=lambda pct, msg: _report(
                                     30 + int(pct * 0.3), msg),
                                 abort_check=_abort)
            texts = bt.translate_all(origins)
            for w in bt.warnings:
                manifest.note(w)
        else:
            texts = [tr.translate(t) for t in origins]
            atomic_write_json(translation_file, {"origins": origins, "translated": texts})
        manifest.mark("translate")
    _report(60, "dịch xong" + resumed_all)

    # 3b) A5 — ƯỚC LƯỢNG TRƯỚC KHI ĐỌC: đoạn chắc chắn vượt ngân sách thì xin
    # bản ngắn hơn TRƯỚC, đỡ tổng hợp rồi vứt (mỗi lần đọc là một lượt GPU).
    # Chạy trong khâu TTS (không phải công đoạn riêng) vì nó là phần chuẩn bị
    # của TTS. `estimates` đọc lại từ sổ tay khi resume — vòng hiệu chuẩn còn
    # số liệu để so; `est` luôn có mặt vì hiệu chuẩn TTS ở dưới dùng nó.
    estimates: list[float] = list(manifest.outputs.get("estimates") or [])
    est = StatisticalEstimator()
    if not manifest.stage_ok("fit"):
        estimates = []
        shorter_fn = getattr(tr, "retranslate_shorter", None)
        for i, t in enumerate(texts):
            e, _conf = est.estimate(t, target_lang)
            estimates.append(e)
            slot = attributed[i].end - attributed[i].start
            available = slot + GAP_TOLERANCE
            if e > available and slot > 0 and shorter_fn is not None and t.strip():
                max_chars = max(8, int(len(t) * available / e * 0.95))
                if max_chars < len(t):
                    try:
                        shorter = (shorter_fn(t, max_chars) or "").strip()
                    except Exception:  # noqa: BLE001 — LLM lỗi không giết job
                        continue
                    if shorter and len(shorter) < len(t):
                        texts[i] = shorter
                        estimates[i] = est.estimate(shorter, target_lang)[0]
        atomic_write_json(translation_file, {"origins": origins, "translated": texts})

    # 4) ĐỌC (TTS) — từng segment; MỖI segment xong ghi tts_progress.json (A1)
    #    nên chết giữa chừng chỉ mất đúng đoạn đang đọc. B5: backend giọng đọc
    #    đổi được (local VieNeu | edge | cloud) — factory của test thắng.
    tts = tts_factory() if tts_factory else build_tts(tts_backend)
    voices = _voice_plan(attributed, speaker_voices, manifest, tts_backend)
    tts_progress_file = os.path.join(workdir, "tts_progress.json")
    tts_state = (_read_json(tts_progress_file) or {}).get("segments", {})
    gen_durations: list[float] = []
    seg_wavs: list[str] = []
    for i, text_t in enumerate(texts):
        rec = tts_state.get(str(i))
        wav_path = os.path.join(workdir, f"seg{i}.wav")
        if rec and os.path.isfile(wav_path) and os.path.getsize(wav_path) > 0:
            gen_durations.append(float(rec["duration"]))
        else:
            _abort()
            _report(60 + 18 * i / max(1, len(texts)), f"đọc {i + 1}/{len(texts)}")
            audio = tts.synthesize(text_t, voice=voices[i] or None)
            with open(wav_path, "wb") as f:
                f.write(audio)
            actual = _wav_duration(wav_path)
            tts_state[str(i)] = {"duration": actual, "voice": voices[i]}
            atomic_write_json(tts_progress_file, {"segments": tts_state})
            gen_durations.append(actual)
            # hiệu chuẩn sống (A5): đo thật giữa job — các đoạn sau ước lượng sát hơn
            if i < len(estimates) and estimates[i] > 0:
                est.calibrate(target_lang, estimates[i], actual)
        seg_wavs.append(wav_path)  # cả hai nhánh đều cần file cho khâu trộn
    if manifest.outputs.get("estimates") != estimates:
        manifest.outputs["estimates"] = estimates
        manifest.save()
    manifest.mark("tts")
    _report(80, "đọc xong" + resumed_all)

    # 5) CĂN THỜI LƯỢNG + vòng xin bản dịch ngắn hơn (giữ nguyên contract cũ)
    if not manifest.stage_ok("fit"):
        _abort()
        _report(82, "căn thời lượng")
        plan_segs = build_plan(attributed, texts, gen_durations, max_speed=max_speed)
        for round_no in range(1, retranslate_rounds + 1):
            if not any(s.needs_shorter_text for s in plan_segs):
                break
            n = _retranslate_pass(tr, plan_segs, texts, gen_durations, seg_wavs,
                                  voices, tts, workdir, round_no)
            plan_segs = build_plan(attributed, texts, gen_durations,
                                   max_speed=max_speed)
            # lưu bản dịch sau vòng xin — resume giữa vòng chỉ lặp lại đúng vòng dở
            atomic_write_json(translation_file, {"origins": origins, "translated": texts})
            if n == 0:
                break
        manifest.mark("fit")
    else:
        plan_segs = build_plan(attributed, texts, gen_durations, max_speed=max_speed)

    # 6) TRỘN — bed nhạc nền + amix
    mixed_wav = os.path.join(workdir, "dubbed.wav")
    if not manifest.stage_ok("mix", "dubbed.wav"):
        _abort()
        _report(88, "trộn nhạc nền")
        bed = os.path.join(workdir, "bed.wav")
        # bed_mode cho biết bed được tách thật ("htdemucs"), rơi về giảm âm
        # lượng ("fallback") hay là im lặng (None). Giá trị trả về có trong
        # kế hoạch để người dùng thấy bed là loại nào — không im lặng.
        bed_mode = _make_bed(source_path, src_dur + 0.5, background_mode, bed)
        for s in plan_segs:
            s.background = bed_mode
        cmd = build_mix_cmd(bed, plan_segs, seg_wavs, mixed_wav)
        subprocess.run(cmd, check=True, capture_output=True)
        manifest.outputs["bed_mode"] = bed_mode
        manifest.mark("mix")

    # 7) ĐÓNG GÓI — mux video (nếu có) + đẩy lên storage
    if mux_video and _has_video(source_path):
        out_path = os.path.join(workdir, "dubbed.mp4")
        ext = "mp4"
    else:
        out_path = mixed_wav
        ext = "wav"
    if not manifest.stage_ok("mux"):
        _abort()
        _report(94, "đóng gói")
        if ext == "mp4" and not os.path.isfile(out_path):
            subprocess.run(["ffmpeg", "-y", "-i", source_path, "-i", mixed_wav,
                            "-map", "0:v:0", "-map", "1:a:0",
                            "-c:v", "copy", "-c:a", "aac", "-shortest", out_path],
                           check=True, capture_output=True)
        if key_prefix:
            key = f"{key_prefix}dub.{ext}"
        else:
            key = out_key or f"jobs/dub/{os.urandom(6).hex()}.{ext}"
        storage.put_from_file(key, out_path)
        manifest.outputs["result_key"] = key
        manifest.mark("mux")
    else:
        key = manifest.outputs["result_key"]
    _report(100, "xong")
    return key, plan_segs


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

    # --- A1 e2e nhỏ với giả lập: resume phải BỎ QUA khâu STT (transcribe 1 lần)
    # Cần file audio THẬT cho khâu chuẩn bị/trộn (ffmpeg thật) — sinh 2s sóng
    # bằng lavfi. Engine nhận diện/dịch/đọc là giả lập.
    import io
    import struct

    src_path = "/tmp/dub_selftest_src.wav"
    gen = subprocess.run(
        ["ffmpeg", "-y", "-f", "lavfi", "-i", "sine=frequency=440:duration=2",
         src_path], capture_output=True)
    if gen.returncode != 0:
        print("e2e resume skipped (no ffmpeg)")
    else:
        def wav_bytes(seconds: float, sr: int = 16000) -> bytes:
            buf = io.BytesIO()
            with wave.open(buf, "wb") as w:
                w.setnchannels(1)
                w.setsampwidth(2)
                w.setframerate(sr)
                w.writeframes(struct.pack("<h", 0) * int(sr * seconds))
            return buf.getvalue()

        class FakeTTS:
            def synthesize(self, text, voice=None):
                return wav_bytes(max(0.2, len(text) / 12.0))

        class FakeTranslator:
            def translate(self, text):
                return text + "_EN"

        class FakeStorage:
            def __init__(self):
                self.puts = []

            def put_from_file(self, key, path):
                self.puts.append(key)
                return key

        calls = {"transcribe": 0, "diarize": 0}

        def fake_transcribe(_p, language=None, stats=None):
            calls["transcribe"] += 1
            return ([TranscriptSegment(0.0, 1.0, "Xin chào", "SPEAKER_00")], None)

        def fake_diarize(_p):
            calls["diarize"] += 1
            return [TranscriptSegment(0.0, 1.2, "", "SPEAKER_00")]

        def fake_merge(segs, turns):
            return [TranscriptSegment(s.start, s.end, s.text, "SPEAKER_00")
                    for s in segs]

        import tempfile

        with tempfile.TemporaryDirectory() as wd:
            storage = FakeStorage()
            common = dict(storage=storage, mux_video=False, background_mode="silence",
                          transcribe_fn=fake_transcribe, diarize_fn=fake_diarize,
                          merge_fn=fake_merge, translator_factory=FakeTranslator,
                          tts_factory=FakeTTS, job_id="jt1",
                          key_prefix="jobs/jt1/")
            key1, _plan1 = dub_audio(src_path, "vi", "en", {}, workdir=wd, **common)
            assert calls == {"transcribe": 1, "diarize": 1}, calls
            assert key1 == "jobs/jt1/dub.wav", key1
            assert _plan1 and _plan1[0].idx == 0

            # lần 2 cùng workdir: mọi khâu đã xong -> KHÔNG đụng engine nào
            key2, _plan2 = dub_audio(src_path, "vi", "en", {}, workdir=wd, **common)
            assert calls == {"transcribe": 1, "diarize": 1}, calls  # không tăng!
            assert key2 == key1

            # đổi tham số ảnh hưởng (max_speed) -> vân tay lệch -> chạy lại sạch
            calls_before = calls["transcribe"]
            dub_audio(src_path, "vi", "en", {}, max_speed=1.2, workdir=wd, **common)
            assert calls["transcribe"] == calls_before + 1, calls
            assert os.path.isfile(os.path.join(wd, "manifest.json.stale"))

            # hủy ngay từ đầu -> JobCancelled nổi lên (không bị nuốt thành failed)
            mf = os.path.join(wd, "manifest.json")
            os.remove(mf)
            stale = mf + ".stale"
            if os.path.exists(stale):
                os.remove(stale)
            try:
                dub_audio(src_path, "vi", "en", {}, workdir=wd,
                          abort_check=lambda: True, **common)
                raise AssertionError("phải JobCancelled")
            except JobCancelled:
                pass

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

    print("resume: skip STT + vân tay + hủy ... OK")
    print("DUB PIPELINE SELFTEST PASSED")


if __name__ == "__main__":
    _selftest()
