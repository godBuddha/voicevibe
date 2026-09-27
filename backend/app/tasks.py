"""Celery worker entrypoint + pipeline dispatch.

GPU worker runs ONE task at a time (prefetch=1, acks_late) — the models are
large; parallel tasks on one GPU just thrash VRAM.

Inline mode (YUPVOX_INLINE=1): run pipelines in-process against SQLite +
local storage — dev/GPU-box mode without Redis/Postgres/MinIO.
"""
from __future__ import annotations

import os

from celery import Celery

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

celery_app = Celery("yupvox", broker=REDIS_URL, backend=REDIS_URL)
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
#   subtitle  -> NOT WIRED (API returns 501, no credits charged)
PIPELINES: dict[str, str] = {
    "tts": "done", "stt": "done", "translate": "done", "dub": "done",
    "subtitle": "not implemented",
}


def _set_failed(job, exc: Exception, db) -> None:
    """Mark failed + REFUND charged credits — failed jobs are free.

    Job.credits_charged is zeroed (history stays in the ledger rows); the
    refund is a positive ledger row with reason `refund:job:<type>`.
    """
    from .models import CreditLedger, JobStatus, User

    job.status = JobStatus.failed
    job.error = str(exc)[:500]
    job.progress = 100
    charged = job.credits_charged or 0
    if charged:
        user = db.get(User, job.user_id)
        if user is not None:
            user.credits += charged
            db.add(CreditLedger(user_id=user.id, delta=charged,
                                reason=f"refund:job:{job.type}", job_id=job.id))
            job.credits_charged = 0


def _notify(url: str | None, payload: dict) -> None:
    """Fire-and-forget webhook — failures must never fail the job.

    When `webhook.secret` is set (Settings UI → security), the body is signed:
    receiver verifies X-YupVox-Signature = HMAC-SHA256(secret, raw_body).
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
            headers["X-YupVox-Signature"] = sig
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


def _run_dub(job_id: str, params: dict) -> dict:
    """Real D5/D7 pipeline: media -> STT -> translate -> TTS -> mix -> storage."""
    from .db import SessionLocal
    from .models import Job, JobStatus
    from .pipelines.dub_pipeline import dub_audio
    from .settings_service import get_setting
    from .storage import get_storage

    with SessionLocal() as db:
        job = db.get(Job, job_id)
        if job is None:
            return {"ok": False, "error": "job not found"}
        job.status = JobStatus.running
        job.progress = 10
        db.commit()
    try:
        storage = get_storage()
        src = _resolve_media(params["media_url"], storage)
        key, _plan = dub_audio(
            src,
            params.get("source_lang") or "vi",
            params.get("target_lang") or "en",
            params.get("speaker_voices") or {},
            storage,
            max_speed=float(get_setting("max_speed", 1.35)),
            background_mode=params.get("background_mode") or "silence",
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
        job.status = JobStatus.running
        job.progress = 10
        db.commit()
    try:
        storage = get_storage()
        src = _resolve_media(params["media_url"], storage)
        segs, _info = transcribe(src, language=params.get("source_lang"))
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
        job.status = JobStatus.running
        job.progress = 10
        db.commit()
        try:
            voice = db.get(Voice, params["voice_id"]) if params.get("voice_id") else None
            if voice is not None and voice.user_id != job.user_id:
                # Ownership check — a key must not synthesize with another
                # user's cloned voice profile (IDOR).
                raise PermissionError("voice profile does not belong to you")
            out_key = synthesize_with_voice(params["text"], voice, get_storage())
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
        job.status = JobStatus.running
        job.progress = 10
        db.commit()
    try:
        source = params.get("source_lang") or "vi"
        target = params.get("target_lang") or "en"
        text = params.get("text") or ""
        if not text.strip():
            raise ValueError("text is required for translate jobs")
        tr = build_translator(source, target)
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
    return _run_stub(job_id, params)


def dispatch(job_id: str, params: dict) -> str:
    """Send to Celery; inline fallback when YUPVOX_INLINE=1 (dev, no Redis)."""
    if os.getenv("YUPVOX_INLINE") == "1":
        dispatch_inline(job_id, params)
        return "inline"
    try:
        celery_app.send_task("pipeline.run", args=[job_id, params])
        return "celery"
    except Exception as exc:  # broker down — job stays queued, logged for ops
        return f"no-broker:{exc.__class__.__name__}"
