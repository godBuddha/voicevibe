"""Celery worker entrypoint + pipeline dispatch.

GPU worker runs ONE task at a time (prefetch=1, acks_late) — the models are
large; parallel tasks on one GPU just thrash VRAM.

Inline mode (VOICEVIBE_INLINE=1): run pipelines in-process against SQLite +
local storage — dev/GPU-box mode without Redis/Postgres/MinIO.
"""
from __future__ import annotations

import os

from celery import Celery

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

# Worker là tiến trình RIÊNG: nó không đi qua app.main nên không được hưởng
# `ensure_schema` ở đó. Gọi tại đây để worker cũng tự migrate trước khi nhận job —
# nếu không, worker sẽ chết ở query đầu tiên trên DB chưa nâng cấp.
from .db import engine as _engine  # noqa: E402
from .migrations import ensure_schema as _ensure_schema  # noqa: E402

_ensure_schema(_engine)

celery_app = Celery("voicevibe", broker=REDIS_URL, backend=REDIS_URL)
celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    task_acks_late=True,
    worker_prefetch_multiplier=1,  # one GPU job at a time
    task_track_started=True,
    # compose worker runs `celery worker -Q media` — send_task without a queue
    # would land on the default "celery" queue and NEVER be consumed.
    task_default_queue="media",
)

# Real implementations land on:
#   tts       -> D4  (VieNeu preset + zero-shot clone)  [DONE]
#   stt       -> D3  (faster-whisper + pyannote)        [DONE]
#   translate -> D5  (cloud OpenAI-compatible / local Marian)  [DONE]
#   dub       -> D5  (stt + translate + tts + timing-fit engine)  [DONE]
#   subtitle  -> D3+ (stt + diarize -> SRT/VTT/ASS, tuỳ chọn song ngữ)  [DONE]
PIPELINES: dict[str, str] = {
    "tts": "done", "stt": "done", "translate": "done", "dub": "done",
    "subtitle": "done", "download": "done", "render": "done",
}


def _set_failed(job, exc: Exception, db) -> None:
    """Mark failed — job miễn phí (self-host), không trừ, không hoàn credit."""
    from .models import JobStatus

    if job.status == JobStatus.cancelled:
        # Đã hủy — không ghi đè thành failed.
        return
    job.status = JobStatus.failed
    job.error = str(exc)[:500]
    job.progress = 100


def _notify(url: str | None, payload: dict) -> None:
    """Fire-and-forget webhook — failures must never fail the job.

    When `webhook.secret` is set (Settings UI → security), the body is signed:
    receiver verifies X-VoiceVibe-Signature = HMAC-SHA256(secret, raw_body).
    """
    if not url:
        return
    try:
        import hashlib
        import hmac
        import json

        import httpx

        headers: dict[str, str] = {}
        secret = get_setting_safe("webhook.secret")
        if secret:
            body = json.dumps(payload, separators=(",", ":")).encode()
            sig = hmac.new(str(secret).encode(), body, hashlib.sha256).hexdigest()
            headers["X-VoiceVibe-Signature"] = sig
        httpx.post(url, json=payload, headers=headers, timeout=10.0)
    except Exception:  # noqa: BLE001
        pass


def get_setting_safe(key: str):
    try:
        from .settings_service import get_setting

        return get_setting(key)
    except Exception:  # noqa: BLE001 — settings DB down must not break jobs
        return None


def _resolve_media(media_url: str, storage) -> str:
    """Local absolute path (dev) or storage key -> usable file path."""
    if os.path.exists(media_url):
        return media_url
    if storage.exists(media_url):
        return storage.get_to_temp(media_url)
    raise FileNotFoundError(f"media not found: {media_url}")


def _download_source(job_id: str, params: dict, storage) -> str:
    """B1 — job dán link: tải về thư mục làm việc bền TRƯỚC khi pipeline chạy.

    Quyết định kiến trúc D1 (kế hoạch B): download KHÔNG là công đoạn của
    manifest — job subtitle chạy inline không manifest, translate-audio tạo
    2 job nối; nếu mỗi pipeline một cơ chế resume cho cùng việc tải file là
    hai code path làm một việc. File tải về có TÊN CỐ ĐỊNH (source.{ext}) —
    đổi link mà không đổi vân tay là tái dùng nhầm sổ tay của video khác,
    vì vậy source_url/quality PHẢI nằm trong material fingerprint (dub_audio).
    """
    url = params.get("source_url")
    if not url:
        return _resolve_media(params["media_url"], storage)
    from .pipelines.download import ensure_downloaded
    from .pipelines.manifest import work_dir

    marker = ensure_downloaded(
        url, work_dir(job_id), params.get("quality") or "1080",
        progress_cb=lambda pct, msg: _record_progress(job_id, pct, msg),
        abort_check=_abort_probe(job_id),
        cookies_file=get_setting_safe("download.cookies_file") or None,
        proxy=get_setting_safe("download.proxy") or None,
    )
    return os.path.join(work_dir(job_id), f"source.{marker.get('ext') or 'mp4'}")


def _youtube_transcript(job_id: str, params: dict):
    """B2 — phụ đề YouTube sẵn có khi job dán link. Trả (segments|None, note).

    `sub_source=auto` (mặc định): video có caption phù hợp thì lấy, không thì
    rơi về Whisper (rất tốt hơn OpenCreator — họ fail ngay). `sub_source=
    youtube`: người dùng CHỌN phụ đề YouTube → không có là lỗi rõ ràng, không
    rơi Whisper (đỡ treo GPU một giờ chỉ vì hiểu nhầm). Whisper luôn chạy khi
    `sub_source=whisper` hoặc không dán link.
    """
    sub_source = params.get("sub_source") or "auto"
    url = params.get("source_url")
    if not url or sub_source == "whisper":
        return None, None
    try:
        from .pipelines.youtube_subs import fetch_captions

        segs = fetch_captions(url, params.get("source_lang"))
    except Exception as exc:  # noqa: BLE001 — mạng hỏng phải rơi về Whisper
        if sub_source == "youtube":
            raise RuntimeError(
                f"lấy phụ đề YouTube thất bại: {str(exc)[:200]}") from exc
        _record_progress(job_id, 12, "lấy phụ đề YouTube lỗi — chuyển sang nghe lại")
        return None, None
    if not segs:
        if sub_source == "youtube":
            raise ValueError(
                "video không có phụ đề YouTube phù hợp — bỏ chọn "
                "«Phụ đề YouTube» để hệ tự nghe lại")
        return None, None
    _record_progress(job_id, 12, "đã lấy phụ đề YouTube — bỏ qua nghe lại")
    return segs, "youtube-captions"


def _record_stt_stats(job_id: str, stats: dict) -> None:
    """Lưu số đoạn bị loại vì hallucination vào `job.params`.

    Cố ý đưa ra API thay vì chỉ ghi log: bỏ nội dung là quyết định ảnh hưởng tới
    kết quả cuối, nên người dùng phải KIỂM TRA ĐƯỢC nó. Lỗi ở đây không được làm
    chết job — đây là thông tin phụ, không phải kết quả.
    """
    dropped = stats.get("dropped") or []
    if not dropped:
        return
    try:
        from .db import SessionLocal
        from .models import Job

        with SessionLocal() as db:
            job = db.get(Job, job_id)
            if job is not None:
                job.params = {**(job.params or {}),
                              "stt_dropped": len(dropped),
                              "stt_dropped_detail": dropped[:10]}
                db.commit()
    except Exception:  # noqa: BLE001
        pass


def _abort_probe(job_id: str, ttl: float = 2.0):
    """Probe trả True khi job ĐÃ bị hủy — đọc DB có cache `ttl` giây.

    Cắm vào `dub_audio(abort_check=...)` để hủy cắm được GIỮA ĐƯỜNG (giữa các
    khâu / giữa các câu đọc), không phải chờ khâu xong. Cache 2s: probe được
    gọi mỗi câu dịch/đọc — không cache là vài chục query/giây trên SQLite vô ích.
    """
    import time as _time

    cache = {"t": 0.0, "aborted": False}

    def probe() -> bool:
        now = _time.monotonic()
        if now - cache["t"] >= ttl:
            cache["t"] = now
            try:
                from .db import SessionLocal
                from .models import Job, JobStatus

                with SessionLocal() as db:
                    job = db.get(Job, job_id)
                    cache["aborted"] = bool(job is not None
                                            and job.status == JobStatus.cancelled)
            except Exception:  # noqa: BLE001 — DB hụt một nhịp không đáng chết job
                pass
        return cache["aborted"]

    return probe


def _record_progress(job_id: str, pct: int, msg: str) -> None:
    """Phơi tiến độ pipeline vào job (progress + params.stage) — pattern
    `_record_stt_stats`: thông tin phụ, lỗi không được giết job."""
    try:
        from .db import SessionLocal
        from .models import Job

        with SessionLocal() as db:
            job = db.get(Job, job_id)
            if job is not None:
                job.progress = max(int(job.progress or 0), int(pct))
                job.params = {**(job.params or {}), "stage": str(msg)[:80]}
                db.commit()
    except Exception:  # noqa: BLE001
        pass


def _resolve_prompt_override(job_id: str, owner_id: str, prompt_id: str | None,
                             source: str, target: str):
    """Prompt cá nhân (Thư viện Prompt) của CHỦ job → chuỗi override (đã điền
    biến {source}/{target}); None nếu không chọn / prompt đã xoá. Đường dùng
    chung cho `_run_translate` và dub.

    Prompt bị xoá/đổi chủ giữa lúc tạo job và lúc chạy → ghi chú fallback vào
    DB (pattern `_record_stt_stats`) — không im lặng."""
    if not prompt_id:
        return None
    from .prompt_library import resolve_prompt_override

    override = resolve_prompt_override(prompt_id, owner_id)
    if override is None:
        try:
            from .db import SessionLocal
            from .models import Job

            with SessionLocal() as db:
                job = db.get(Job, job_id)
                if job is not None:
                    job.params = {**(job.params or {}), "prompt_fallback": "not found"}
                    db.commit()
        except Exception:  # noqa: BLE001 — thông tin phụ
            pass
        return None
    from .prompts import render_template

    # Biến {source}/{target} phải điền TẠI ĐÂY (đúng như đường cũ của
    # _run_translate) — trả template trần là prompt user gửi model nguyên chữ
    # "{source}" (test_prompt_library bắt đúng ca này).
    return render_template(override, source=source, target=target)


def _run_dub(job_id: str, params: dict) -> dict:
    """Real D5/D7 pipeline: media -> STT -> translate -> TTS -> mix -> storage.

    A1: chạy trong thư mục làm việc bền `media/jobs/{job_id}/work/` + sổ tay
    công đoạn — job hỏng/hủy thì "Chạy lại" tiếp tục từ khâu đã xong (xem
    pipelines/manifest.py). Kết quả cũng nằm dưới `jobs/{job_id}/` (key_prefix)
    để xóa job dọn sạch một phát.
    """
    from .db import SessionLocal
    from .models import Job, JobStatus
    from .pipelines.dub_pipeline import dub_audio
    from .pipelines.manifest import JobCancelled, work_dir
    from .pipelines.translate import stage_translate_params
    from .settings_service import get_setting
    from .storage import get_storage

    with SessionLocal() as db:
        job = db.get(Job, job_id)
        if job is None:
            return {"ok": False, "error": "job not found"}
        if _aborted(db, job_id):
            return {"ok": False, "error": "cancelled"}
        job.status = JobStatus.running
        job.progress = 10
        owner_id = job.user_id
        db.commit()
    try:
        storage = get_storage()
        src = _download_source(job_id, params, storage)
        yt_segs, _note = _youtube_transcript(job_id, params)
        # Prompt cá nhân (nếu job chọn) — thay system prompt của bộ dịch.
        override = _resolve_prompt_override(
            job_id, owner_id, params.get("prompt_id"),
            params.get("source_lang") or "vi", params.get("target_lang") or "en")
        # Núm dịch batch: job params > công đoạn translate (Model Hub, params
        # JSON của StageModel — cổng có sẵn trước đây không ai đọc) > setting.
        sp = stage_translate_params()
        bs = int(params.get("batch_size") or sp.get("batch_size")
                 or get_setting("translate.batch_size", 12) or 12)
        ctx = int(params.get("context_sentences") or sp.get("context_sentences")
                  or get_setting("translate.context_sentences", 2) or 2)
        key, _plan = dub_audio(
            src,
            params.get("source_lang") or "vi",
            params.get("target_lang") or "en",
            params.get("speaker_voices") or {},
            storage,
            max_speed=float(get_setting("max_speed", 1.35)),
            background_mode=params.get("background_mode") or "silence",
            workdir=work_dir(job_id),
            job_id=job_id,
            abort_check=_abort_probe(job_id),
            progress_cb=lambda pct, msg: _record_progress(job_id, pct, msg),
            key_prefix=f"jobs/{job_id}/",
            system_prompt=override,
            batch_size=bs,
            context_sentences=ctx,
            source_url=params.get("source_url"),
            quality=params.get("quality"),
            sub_source=params.get("sub_source"),
            captions=yt_segs,
            tts_backend=params.get("tts_backend") or "local",
            with_subs=bool(params.get("with_subs")),
        )
        # B4b — phụ đề song ngữ là OUTPUT PHỤ: đọc từ sổ tay (accessor nhẹ),
        # ghi vào params để /v1/jobs + render job tái dùng được.
        try:
            from .pipelines.manifest import read_outputs

            subs_key = read_outputs(work_dir(job_id)).get("subs_key")
        except Exception:  # noqa: BLE001 — thông tin phụ, không giết job
            subs_key = None
        if subs_key:
            _record_progress(job_id, 100, "phụ đề song ngữ: " + subs_key)
        with SessionLocal() as db:
            job = db.get(Job, job_id)
            job.status = JobStatus.done
            job.progress = 100
            job.result_s3_key = key
            job.error = None
            if subs_key:
                job.params = {**(job.params or {}),
                              "extra_outputs": [{"kind": "subtitle",
                                                 "key": subs_key,
                                                 "filename": "bilingual.srt"}]}
            db.commit()
        _notify(params.get("webhook_url"),
                {"job_id": job_id, "status": "done", "result_key": key})
        return {"ok": True, "key": key}
    except JobCancelled:
        with SessionLocal() as db:
            job = db.get(Job, job_id)
            if job is not None:
                # Ép cancelled: hủy đã đặt cờ trên DB TRƯỚC rồi worker mới thấy,
                # nhưng task requeue/race có thể vừa set running lại — guard này
                # không cho trạng thái sống sót. Kèm lời nhắc để nút Chạy lại có
                # ngữ nghĩa "tiếp tục từ công đoạn đã xong".
                if job.status != JobStatus.cancelled:
                    job.status = JobStatus.cancelled
                job.error = ("Đã hủy giữa đường — bấm Chạy lại để tiếp tục "
                             "từ công đoạn đã xong")
                db.commit()
        return {"ok": False, "error": "cancelled"}
    except Exception as exc:  # noqa: BLE001
        with SessionLocal() as db:
            job = db.get(Job, job_id)
            if job is not None:
                _set_failed(job, exc, db)
                db.commit()
        return {"ok": False, "error": str(exc)[:200]}


def _run_download(job_id: str, params: dict) -> dict:
    """B1 — job "Tải video" riêng: URL -> file trong storage.

    Kết quả `jobs/{id}/video.{ext}` dùng lại được cho job khác (media_url =
    key này — `_resolve_media` đọc được key, `_owns_media` phủ tiền tố jobs/).
    Marker resume nằm trong workdir bền — nút Chạy lại KHÔNG tải lại video.
    """
    from .db import SessionLocal
    from .models import Job, JobStatus
    from .pipelines.download import ensure_downloaded
    from .pipelines.manifest import JobCancelled, work_dir
    from .settings_service import get_setting
    from .storage import get_storage

    url = params.get("source_url") or ""
    quality = params.get("quality") or "1080"
    with SessionLocal() as db:
        job = db.get(Job, job_id)
        if job is None:
            return {"ok": False, "error": "job not found"}
        if _aborted(db, job_id):
            return {"ok": False, "error": "cancelled"}
        job.status = JobStatus.running
        job.progress = 5
        db.commit()
    try:
        storage = get_storage()
        marker = ensure_downloaded(
            url, work_dir(job_id), quality,
            progress_cb=lambda pct, msg: _record_progress(job_id, pct, msg),
            abort_check=_abort_probe(job_id),
            cookies_file=get_setting("download.cookies_file") or None,
            proxy=get_setting("download.proxy") or None,
        )
        ext = marker.get("ext") or "mp4"
        name = "audio.mp3" if quality == "audio" else f"video.{ext}"
        key = f"jobs/{job_id}/{name}"
        storage.put_from_file(key, os.path.join(work_dir(job_id),
                                                f"source.{ext}"))
        with SessionLocal() as db:
            job = db.get(Job, job_id)
            job.status = JobStatus.done
            job.progress = 100
            job.result_s3_key = key
            job.error = None
            # metadata cho /v1/jobs + trang Jobs hiển thị title/duration
            job.params = {**(job.params or {}),
                          "download_title": marker.get("title") or "",
                          "download_duration": marker.get("duration"),
                          "download_uploader": marker.get("uploader") or ""}
            db.commit()
        _notify(params.get("webhook_url"),
                {"job_id": job_id, "status": "done", "result_key": key})
        return {"ok": True, "key": key}
    except JobCancelled:
        with SessionLocal() as db:
            job = db.get(Job, job_id)
            if job is not None:
                if job.status != JobStatus.cancelled:
                    job.status = JobStatus.cancelled
                job.error = "Đã hủy trong lúc tải — bấm Chạy lại để tải lại"
                db.commit()
        return {"ok": False, "error": "cancelled"}
    except Exception as exc:  # noqa: BLE001
        with SessionLocal() as db:
            job = db.get(Job, job_id)
            if job is not None:
                _set_failed(job, exc, db)
                db.commit()
        return {"ok": False, "error": str(exc)[:200]}


def _run_render(job_id: str, params: dict) -> dict:
    """B3+B4 — job `render`: burn phụ đề song ngữ 2 style + cắt dọc 9:16 + banner.

    Manifest riêng (stage prepare→subtitles→vertical→burn) — encode video dài
    chết giữa đường thì nút Chạy lại tiếp đúng stage, không encode lại từ đầu
    (rủi ro số 8 của kế hoạch).
    """
    from .db import SessionLocal
    from .models import Job, JobStatus
    from .pipelines.manifest import JobCancelled, work_dir
    from .pipelines.render import load_cues_from_text, run_render
    from .storage import get_storage

    with SessionLocal() as db:
        job = db.get(Job, job_id)
        if job is None:
            return {"ok": False, "error": "job not found"}
        if _aborted(db, job_id):
            return {"ok": False, "error": "cancelled"}
        job.status = JobStatus.running
        job.progress = 5
        owner_id = job.user_id
        db.commit()
    try:
        storage = get_storage()
        src = _download_source(job_id, params, storage)

        # Nguồn phụ đề: key XOR job id (đã validate ở create_job)
        cues_text, cues_ext = None, ""
        sub_key = params.get("subtitle_key")
        if not sub_key and params.get("subtitle_job_id"):
            with SessionLocal() as db:
                sub_job = db.get(Job, params["subtitle_job_id"])
            if sub_job is None or sub_job.user_id != owner_id:
                raise ValueError("job phụ đề không tồn tại hoặc không thuộc về bạn")
            if sub_job.status != JobStatus.done or not sub_job.result_s3_key:
                raise ValueError("job phụ đề chưa hoàn thành — chưa có file để in")
            sub_key = sub_job.result_s3_key
        if sub_key:
            ext = sub_key.rsplit(".", 1)[-1].lower()
            if ext not in ("srt", "vtt", "ass"):
                raise ValueError(
                    f"phụ đề phải là .srt/.vtt/.ass — nhận .{ext}")
            cues_text = storage.get_to_temp(sub_key)
            cues_ext = ext

        key = run_render(
            src,
            burn_subtitles=bool(params.get("burn_subtitles")),
            vertical=bool(params.get("vertical")),
            banner=params.get("banner") or None,
            cues_text=cues_text, cues_ext=cues_ext,
            workdir=work_dir(job_id), job_id=job_id,
            key_prefix=f"jobs/{job_id}/", storage=storage,
            abort_check=_abort_probe(job_id),
            progress_cb=lambda pct, msg: _record_progress(job_id, pct, msg),
        )
        with SessionLocal() as db:
            job = db.get(Job, job_id)
            job.status = JobStatus.done
            job.progress = 100
            job.result_s3_key = key
            job.error = None
            db.commit()
        _notify(params.get("webhook_url"),
                {"job_id": job_id, "status": "done", "result_key": key})
        return {"ok": True, "key": key}
    except JobCancelled:
        with SessionLocal() as db:
            job = db.get(Job, job_id)
            if job is not None:
                if job.status != JobStatus.cancelled:
                    job.status = JobStatus.cancelled
                job.error = ("Đã hủy giữa đường — bấm Chạy lại để tiếp tục "
                             "từ công đoạn đã xong")
                db.commit()
        return {"ok": False, "error": "cancelled"}
    except Exception as exc:  # noqa: BLE001
        with SessionLocal() as db:
            job = db.get(Job, job_id)
            if job is not None:
                _set_failed(job, exc, db)
                db.commit()
        return {"ok": False, "error": str(exc)[:200]}


def _run_stt(job_id: str, params: dict) -> dict:
    """Real D3 pipeline: media -> transcript with speakers -> SRT in storage."""
    from .db import SessionLocal
    from .models import Job, JobStatus
    from .pipelines.stt import diarize, merge, to_srt, transcribe
    from .storage import get_storage

    with SessionLocal() as db:
        job = db.get(Job, job_id)
        if job is None:
            return {"ok": False, "error": "job not found"}
        if _aborted(db, job_id):
            return {"ok": False, "error": "cancelled"}
        job.status = JobStatus.running
        job.progress = 10
        db.commit()
    try:
        storage = get_storage()
        src = _download_source(job_id, params, storage)
        # B2 — phụ đề YouTube sẵn có khi dán link (auto: lấy nếu có, rơi Whisper)
        yt_segs, _note = _youtube_transcript(job_id, params)
        stt_stats: dict = {}
        if yt_segs is not None:
            segs = yt_segs  # caption chất lượng cao nhất đã chọn ở youtube_subs
        else:
            segs, _info = transcribe(src, language=params.get("source_lang"),
                                     stats=stt_stats)
        # Bỏ hallucination là quyết định ảnh hưởng nội dung -> phải nhìn thấy được.
        _record_stt_stats(job_id, stt_stats)
        turns = diarize(src)
        attributed = merge(segs, turns)
        srt = to_srt(attributed)
        key = f"jobs/{job_id}/transcript.srt"
        storage.put(key, srt.encode("utf-8"))
        with SessionLocal() as db:
            job = db.get(Job, job_id)
            job.status = JobStatus.done
            job.progress = 100
            job.result_s3_key = key
            job.error = None
            db.commit()
        _notify(params.get("webhook_url"),
                {"job_id": job_id, "status": "done", "result_key": key})
        return {"ok": True, "key": key}
    except Exception as exc:  # noqa: BLE001
        with SessionLocal() as db:
            job = db.get(Job, job_id)
            if job is not None:
                _set_failed(job, exc, db)
                db.commit()
        return {"ok": False, "error": str(exc)[:200]}


def _run_subtitle(job_id: str, params: dict) -> dict:
    """STT + tách người nói -> phụ đề SRT/VTT/ASS, tuỳ chọn song ngữ.

    Dùng lại `_run_stt` ở phần đầu (transcribe + diarize + merge) thay vì viết lại:
    cùng một đường, cùng một cách kiểm lỗi. Khác ở bước xuất và ở chỗ có thể dịch.
    """
    from .db import SessionLocal
    from .models import Job, JobStatus
    from .pipelines.stt import diarize, merge, transcribe
    from .pipelines.subtitle import DEFAULT_FORMAT, extension, render
    from .storage import get_storage

    with SessionLocal() as db:
        job = db.get(Job, job_id)
        if job is None:
            return {"ok": False, "error": "job not found"}
        if _aborted(db, job_id):
            return {"ok": False, "error": "cancelled"}
        job.status = JobStatus.running
        job.progress = 10
        db.commit()
    try:
        storage = get_storage()
        src = _download_source(job_id, params, storage)
        yt_segs, _note = _youtube_transcript(job_id, params)

        stt_stats: dict = {}
        # want_words=True (A4): mốc giờ TỪNG TỪ cho tách cue phụ đề dài đúng
        # ranh giới từ — chỉ đường local Whisper có; cloud STT tự no-op (None).
        if yt_segs is not None:
            segs = yt_segs
        else:
            segs, _info = transcribe(src, language=params.get("source_lang"),
                                     stats=stt_stats, want_words=True)
        # Bỏ hallucination là việc PHẢI NHÌN THẤY ĐƯỢC: nếu im lặng, phụ đề
        # thiếu câu mà không ai biết vì sao. Ghi vào params để /v1/jobs đọc ra.
        _record_stt_stats(job_id, stt_stats)
        turns = diarize(src)
        attributed = merge(segs, turns)

        with SessionLocal() as db:
            job = db.get(Job, job_id)
            job.progress = 60
            db.commit()

        fmt = params.get("format") or DEFAULT_FORMAT
        bilingual = bool(params.get("bilingual"))
        show_speaker = params.get("show_speaker", True)

        translations = None
        if bilingual or params.get("target_lang"):
            from .pipelines.translate import batch_capable, build_translator
            from .pipelines.translate_batch import BatchConfig, BatchTranslator

            source = params.get("source_lang") or "auto"
            target = params.get("target_lang")
            if not target:
                raise ValueError("target_lang là bắt buộc khi cần dịch phụ đề")
            tr = build_translator(source, target)
            # A3 — dịch LOẠT (LLM) thay vì từng cue: giữ nguyên số lượng + thứ
            # tự, có ngữ cảnh ±2 câu nên bản dịch mạch lạc hơn hẳn; LLM hỏng
            # một lô thì bisect chia nhỏ, cùng đáy là dịch từng cue như cũ.
            # Marian local không batch được → giữ đường từng cue.
            chat = batch_capable(tr)
            if chat is not None:
                bt = BatchTranslator(chat, source, target, fallback=tr,
                                     config=BatchConfig())
                translations = bt.translate_all([s.text for s in attributed])
            else:
                # Dịch từng cue MỘT, giữ nguyên số lượng và thứ tự — ghép lại
                # theo chỉ số. Dịch gộp cả khối rồi tách lại sẽ lệch số dòng
                # không báo lỗi.
                translations = [tr.translate(s.text) if s.text.strip() else ""
                                for s in attributed]

        out = render(attributed, fmt, translations=translations,
                     bilingual=bilingual, show_speaker=show_speaker)
        key = f"jobs/{job_id}/subtitle.{extension(fmt)}"
        storage.put(key, out.encode("utf-8"))

        with SessionLocal() as db:
            job = db.get(Job, job_id)
            job.status = JobStatus.done
            job.progress = 100
            job.result_s3_key = key
            job.error = None
            db.commit()
        _notify(params.get("webhook_url"),
                {"job_id": job_id, "status": "done", "result_key": key})
        return {"ok": True, "key": key}
    except Exception as exc:  # noqa: BLE001
        with SessionLocal() as db:
            job = db.get(Job, job_id)
            if job is not None:
                _set_failed(job, exc, db)
                db.commit()
        return {"ok": False, "error": str(exc)[:200]}


def _run_tts(job_id: str, params: dict) -> dict:
    """Real D4 pipeline: text (+ voice profile) -> WAV in media storage."""
    from .db import SessionLocal
    from .models import Job, JobStatus, Voice
    from .pipelines.tts import synthesize_with_voice
    from .storage import get_storage

    with SessionLocal() as db:
        job = db.get(Job, job_id)
        if job is None:
            return {"ok": False, "error": "job not found"}
        if _aborted(db, job_id):
            return {"ok": False, "error": "cancelled"}
        job.status = JobStatus.running
        job.progress = 10
        db.commit()
        try:
            voice = db.get(Voice, params["voice_id"]) if params.get("voice_id") else None
            if voice is not None and voice.user_id != job.user_id:
                # Ownership check — a key must not synthesize with another
                # user's cloned voice profile (IDOR).
                raise PermissionError("voice profile does not belong to you")
            out_key = synthesize_with_voice(params["text"], voice, get_storage(),
                                            backend=params.get("tts_backend"))
            job.status = JobStatus.done
            job.progress = 100
            job.result_s3_key = out_key
            job.error = None
            db.commit()
            _notify(params.get("webhook_url"),
                    {"job_id": job_id, "status": "done", "result_key": out_key})
            return {"ok": True, "key": out_key}
        except Exception as exc:  # noqa: BLE001 — any failure -> job.failed
            _set_failed(job, exc, db)
            db.commit()
            return {"ok": False, "error": str(exc)[:200]}


def _run_translate(job_id: str, params: dict) -> dict:
    """Real D5 translate pipeline: text -> translated text (storage .txt)."""
    from .db import SessionLocal
    from .models import Job, JobStatus
    from .pipelines.translate import build_translator
    from .storage import get_storage

    with SessionLocal() as db:
        job = db.get(Job, job_id)
        if job is None:
            return {"ok": False, "error": "job not found"}
        if _aborted(db, job_id):
            return {"ok": False, "error": "cancelled"}
        owner_id = job.user_id   # chụp TRƯỚC session đóng — prompt override cần nó
        job.status = JobStatus.running
        job.progress = 10
        db.commit()
    try:
        source = params.get("source_lang") or "vi"
        target = params.get("target_lang") or "en"
        text = params.get("text") or ""
        if not text.strip():
            raise ValueError("text is required for translate jobs")
        # Thư viện prompt: params.prompt_id = prompt cá nhân của CHỦ job (đường
        # dùng chung `_resolve_prompt_override` — cả dub dùng).
        override = _resolve_prompt_override(job_id, owner_id, params.get("prompt_id"),
                                           source, target)
        tr = build_translator(source, target, system_prompt=override)
        out = tr.translate(text)
        key = f"jobs/{job_id}/translated.txt"
        get_storage().put(key, out.encode("utf-8"))
        with SessionLocal() as db:
            job = db.get(Job, job_id)
            job.status = JobStatus.done
            job.progress = 100
            job.result_s3_key = key
            job.error = None
            db.commit()
        _notify(params.get("webhook_url"),
                {"job_id": job_id, "status": "done", "result_key": key})
        return {"ok": True, "key": key}
    except Exception as exc:  # noqa: BLE001
        with SessionLocal() as db:
            job = db.get(Job, job_id)
            if job is not None:
                _set_failed(job, exc, db)
                db.commit()
        return {"ok": False, "error": str(exc)[:200]}


def _run_stub(job_id: str, params: dict) -> dict:
    """Placeholder for pipelines not implemented yet."""
    from .db import SessionLocal
    from .models import Job, JobStatus

    with SessionLocal() as db:
        job = db.get(Job, job_id)
        if job is None:
            return {"ok": False, "error": "job not found"}
        if _aborted(db, job_id):
            return {"ok": False, "error": "cancelled"}
        job.status = JobStatus.running
        job.progress = 10
        db.commit()
        job.status = JobStatus.done
        job.progress = 100
        job.result_s3_key = f"jobs/{job_id}/output"
        job.error = None
        db.commit()
    note = PIPELINES.get(params.get("type", ""), "D5")
    return {"ok": True, "note": f"stub — real pipeline lands {note}"}


@celery_app.task(name="pipeline.run", bind=True, max_retries=2, default_retry_delay=30)
def run_pipeline(self, job_id: str, params: dict) -> dict:
    return dispatch_inline(job_id, params)


def dispatch_inline(job_id: str, params: dict) -> dict:
    jtype = params.get("type", "")
    if jtype == "tts":
        return _run_tts(job_id, params)
    if jtype == "dub":
        return _run_dub(job_id, params)
    if jtype == "stt":
        return _run_stt(job_id, params)
    if jtype == "translate":
        return _run_translate(job_id, params)
    if jtype == "subtitle":
        return _run_subtitle(job_id, params)
    if jtype == "download":
        return _run_download(job_id, params)
    if jtype == "render":
        return _run_render(job_id, params)
    return _run_stub(job_id, params)


def dispatch(job_id: str, params: dict) -> tuple[str, str | None]:
    """Send to Celery; inline fallback when VOICEVIBE_INLINE=1 (dev, no Redis).

    Trả (mode, task_id) — task_id để HỦY được job sau này (revoke theo id).
    Không có id thì hủy chỉ có thể gạch trên DB, không ra lệnh được cho Celery.
    """
    if os.getenv("VOICEVIBE_INLINE") == "1":
        dispatch_inline(job_id, params)
        return "inline", None
    try:
        res = celery_app.send_task("pipeline.run", args=[job_id, params])
        return "celery", getattr(res, "id", None)
    except Exception as exc:  # broker down — job stays queued, logged for ops
        return f"no-broker:{exc.__class__.__name__}", None


def _aborted(db, job_id: str) -> bool:
    """Job đã bị HỦY thì pipeline phải DỪNG ĐÚNG Ở ĐÂU — không đụng model.

    Mỗi `_run_*` gọi ngay sau khi fetch job, TRƯỚC khi set status=running:
    nếu không có gate này, worker nhặt được task (requeue sau terminate, hoặc
    task đã vào hàng đợi trước lúc hủy) sẽ set running lại và ghi đè trạng thái
    `cancelled` (resurrect — đã gặp kiểu bug ngược chiều này ở code khác).
    Trả kết quả bỏ qua: message được ack, không lặp.
    """
    from .models import Job, JobStatus

    job = db.get(Job, job_id)
    if job is not None and job.status == JobStatus.cancelled:
        return True
    return False
