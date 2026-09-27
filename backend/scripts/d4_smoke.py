"""Day 4 real-GPU smoke: voice cloning end-to-end (the core YupVox feature).

1. Simulate a user clip: generate ~5s with a Vieneu preset ("Thái Sơn", Southern)
2. Register voice profile (storage voices/{id}/ref.wav + DB row)
3. TTS job through the REAL dispatch path (inline mode) with the cloned voice
4. Round-trip verify: faster-whisper transcribes the cloned audio —
   it must contain the target words (TTS -> ASR loop closes)

Run on the GPU box:
  cd /workspace/yupvox-clone && source .venv/bin/activate
  cd backend && PYTHONPATH=. python scripts/d4_smoke.py
"""
from __future__ import annotations

import os
import sys
import wave

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ.setdefault("MEDIA_ROOT", "/workspace/media")
os.environ.setdefault("DATABASE_URL", "sqlite:////workspace/yupvox-clone/backend/yupvox.db")
os.environ.setdefault("YUPVOX_INLINE", "1")

from app.db import Base, SessionLocal, engine  # noqa: E402
from app.models import Job, User, Voice  # noqa: E402
from app.pipelines.stt import transcribe  # noqa: E402
from app.storage import get_storage  # noqa: E402
from app.tasks import dispatch  # noqa: E402

Base.metadata.create_all(engine)

REF_TEXT = ("Xin chào, tôi là Thái Sơn, giọng nam miền Nam. "
            "Đoạn ghi âm này dùng làm mẫu để nhân bản giọng nói.")
CLONE_TEXT = ("Đây là giọng được nhân bản tức thì. "
              "Hệ thống clone giọng nói đang hoạt động thật trên GPU.")
REF_KEY = "voices/smoke_thaison/ref.wav"
CLONE_WORDS = set(CLONE_TEXT.split())


def ensure_ref_clip() -> None:
    storage = get_storage()
    if storage.exists(REF_KEY):
        print(f"[ref] exists: {REF_KEY}")
        return
    from vieneu import Vieneu

    tts = Vieneu()
    print("[ref] generating reference clip (Thái Sơn)...")
    audio = tts.infer(REF_TEXT, voice="Thái Sơn")
    sr = 48000
    tmp = "/workspace/samples/d4_ref.wav"
    os.makedirs(os.path.dirname(tmp), exist_ok=True)
    with wave.open(tmp, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes((np.clip(audio, -1.0, 1.0) * 32767).astype("<i2").tobytes())
    storage.put_from_file(REF_KEY, tmp)
    print(f"[ref] saved {REF_KEY} ({len(audio) / sr:.1f}s)")


def ensure_voice_row() -> str:
    with SessionLocal() as db:
        user = db.query(User).filter_by(email="smoke@local").first()
        if user is None:
            user = User(email="smoke@local")
            db.add(user)
            db.commit()
            db.refresh(user)
        voice = db.query(Voice).filter_by(name="Thái Sơn (smoke)", user_id=user.id).first()
        if voice is None:
            voice = Voice(user_id=user.id, name="Thái Sơn (smoke)", lang="vi",
                          engine="vieneu", ref_s3_key=REF_KEY)
            db.add(voice)
            db.commit()
            db.refresh(voice)
        return voice.id


def roundtrip_score(heard: str, target_words: set[str]) -> float:
    return len(set(heard.split()) & target_words) / max(1, len(target_words))


def main() -> None:
    ensure_ref_clip()
    vid = ensure_voice_row()
    print(f"[voice] profile id={vid}")

    # real job path: DB row -> dispatch (inline) -> storage key
    with SessionLocal() as db:
        uid = db.query(User).filter_by(email="smoke@local").first().id
        job = Job(user_id=uid, type="tts",
                  params={"type": "tts", "text": CLONE_TEXT, "voice_id": vid})
        db.add(job)
        db.commit()
        db.refresh(job)
        jid = job.id

    mode = dispatch(jid, {"type": "tts", "text": CLONE_TEXT, "voice_id": vid})
    with SessionLocal() as db:
        job = db.get(Job, jid)
        print(f"[job] {jid} status={job.status.value} dispatch={mode} key={job.result_s3_key}")
        assert job.status.value == "done", f"job failed: {job.error}"
        out_key = job.result_s3_key

    storage = get_storage()
    out_path = storage.get_to_temp(out_key)
    with wave.open(out_path) as w:
        dur = w.getnframes() / w.getframerate()
    print(f"[clone] synthesized {dur:.1f}s -> {out_key}")

    print("[verify] faster-whisper round-trip on CLONED audio...")
    segs, _info = transcribe(out_path, language="vi")
    heard = " ".join(s.text for s in segs).strip()
    score = roundtrip_score(heard, CLONE_WORDS)
    print(f"[verify] heard: {heard}")
    print(f"[verify] word overlap with target: {score:.0%}")

    ok = score >= 0.5 and dur > 2
    print(f"\nD4 SMOKE: {'PASS' if ok else 'CHECK'} "
          f"(clone {dur:.1f}s, round-trip {score:.0%})")


if __name__ == "__main__":
    main()
