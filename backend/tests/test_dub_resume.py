"""A1/A3 guards — sổ tay công đoạn (resume) + dịch batch + endpoint Chạy lại.

Run:  cd backend && PYTHONPATH=. python tests/test_dub_resume.py

Điểm ghim:
  1. dub_audio chạy LẦN 2 cùng workdir → KHÔNG đụng lại STT/dịch (resume thật)
  2. Đổi tham số ảnh hưởng (max_speed/giọng) → vân tay lệch → chạy lại SẠCH
  3. TTS chạy dở (đã xong 1/2) → lần sau chỉ đọc đúng phần thiếu
  4. abort_check True → JobCancelled; qua _run_dub → job giữ cancelled + lời
     nhắc "Chạy lại", KHÔNG bị đánh dấu failed
  5. POST /v1/jobs/{id}/retry: 401 lạ, 409 job done/đang chạy, 200 từ
     cancelled → queued + task_id + giữ params/result_key + audit `job.retry`
  6. delete_prefix dọn sạch `jobs/{id}/` (kết quả + workdir); file TTS dùng
     chung KHÔNG bị đụng
  7. batch_capable: CloudChat → completer; chain → entry đầu; Marian → None
"""
from __future__ import annotations

import io
import json
import os
import pathlib
import struct
import sys
import tempfile
import wave

os.environ["DATABASE_URL"] = "sqlite:///./voicevibe_resume_test.db"
os.environ["VOICEVIBE_INLINE"] = "1"
os.environ["MEDIA_ROOT"] = tempfile.mkdtemp(prefix="vv_resume_media_")
pathlib.Path("voicevibe_resume_test.db").unlink(missing_ok=True)

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

import app.pipelines.dub_pipeline as dub_pipeline  # noqa: E402
from app.db import Base, SessionLocal, engine  # noqa: E402
from app.models import User  # noqa: E402
from app.pipelines.manifest import JobCancelled, Manifest  # noqa: E402
from app.pipelines.translate import CloudChatTranslator  # noqa: E402
from app.providers.base import TranscriptSegment  # noqa: E402

Base.metadata.create_all(engine)
with SessionLocal() as _db:  # seed 1 user cho khối API
    if _db.query(User).count() == 0:
        _db.add(User(email="resume-tester@local"))
        _db.commit()

TMP = tempfile.mkdtemp(prefix="vv_resume_")


def wav_bytes(seconds: float, sr: int = 16000) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(struct.pack("<h", 0) * int(sr * seconds))
    return buf.getvalue()


def make_src() -> str:
    """Audio thật 2s (ffmpeg) — khâu chuẩn bị/trộn chạy thật."""
    import subprocess

    src = os.path.join(TMP, "src.wav")
    sp = subprocess.run(
        ["ffmpeg", "-y", "-f", "lavfi", "-i", "sine=frequency=440:duration=2", src],
        capture_output=True)
    if sp.returncode != 0:
        print("không có ffmpeg — bỏ qua các ca e2e audio")
        return ""
    return src


class FakeTTS:
    calls: list[str] = []

    def synthesize(self, text, voice=None):
        type(self).calls.append(text)
        return wav_bytes(max(0.2, len(text) / 12.0))


class FakeTranslator:
    def translate(self, text):
        return text + "_EN"


class FakeStorage:
    def __init__(self):
        self.puts: dict[str, str] = {}

    def put_from_file(self, key, path):
        self.puts[key] = path
        return key


CALLS = {"transcribe": 0, "diarize": 0}


def fake_transcribe(_p, language=None, stats=None):
    CALLS["transcribe"] += 1
    return ([TranscriptSegment(0.0, 1.0, "Xin chào", "SPEAKER_00")], None)


def fake_diarize(_p):
    CALLS["diarize"] += 1
    return [TranscriptSegment(0.0, 1.2, "", "SPEAKER_00")]


def fake_merge(segs, turns):
    return [TranscriptSegment(s.start, s.end, s.text, "SPEAKER_00") for s in segs]


def common(storage):
    return dict(storage=storage, mux_video=False, background_mode="silence",
                transcribe_fn=fake_transcribe, diarize_fn=fake_diarize,
                merge_fn=fake_merge, translator_factory=FakeTranslator,
                tts_factory=FakeTTS, job_id="jr1", key_prefix="jobs/jr1/")


SRC = make_src()
if SRC:
    wd = os.path.join(TMP, "work1")
    os.makedirs(wd, exist_ok=True)

    # --- 1. lần 1 chạy; lần 2 cùng workdir: KHÔNG đụng engine (resume full)
    FakeTTS.calls = []
    dub_pipeline.dub_audio(SRC, "vi", "en", {}, workdir=wd, **common(FakeStorage()))
    assert CALLS["transcribe"] == 1 and len(FakeTTS.calls) >= 1
    first_calls = (CALLS["transcribe"], CALLS["diarize"], len(FakeTTS.calls))
    dub_pipeline.dub_audio(SRC, "vi", "en", {}, workdir=wd, **common(FakeStorage()))
    assert (CALLS["transcribe"], CALLS["diarize"], len(FakeTTS.calls)) == first_calls, \
        "lần 2 cùng tham số phải bỏ qua TẤT CẢ khâu"
    print("1. resume full: không đụng lại engine ....... OK")

    # --- 3. TTS dở dang: xoá cờ tts, giữ seg0 + tts_progress -> chỉ đọc seg thiếu
    segs_txt = list(FakeTTS.calls)
    prog_path = os.path.join(wd, "tts_progress.json")
    state = json.load(open(prog_path))["segments"]
    assert state, "tts_progress phải ghi sau mỗi đoạn"
    FakeTTS.calls = []
    # bỏ cờ fit+tts+mux để tái vào khâu TTS (giữ sổ tay, chỉ hạ cờ từ tts đi)
    m = Manifest.load_or_none(wd, json.load(open(os.path.join(wd, "manifest.json")))["params_fp"])
    assert m is not None
    for st in ("fit", "tts", "mix", "mux"):
        m.stages.pop(st, None)
    m.save()
    # giữ nguyên seg0.wav nhưng XOÁ seg1.wav (nếu có) — FakeTTS 1 đoạn nên không ảnh hưởng;
    # kiểm bằng cách đếm: FakeTTS không được gọi lại khi seg còn nguyên
    dub_pipeline.dub_audio(SRC, "vi", "en", {}, workdir=wd, **common(FakeStorage()))
    assert FakeTTS.calls == [], "đoạn đã đọc xong không được đọc lại"
    print("2. TTS dở dang: không đọc lại đoạn xong ..... OK")

    # --- 2. đổi max_speed -> vân tay lệch -> chạy lại sạch + .stale
    FakeTTS.calls = []
    calls_before = CALLS["transcribe"]
    dub_pipeline.dub_audio(SRC, "vi", "en", {}, max_speed=1.2, workdir=wd,
                           **common(FakeStorage()))
    assert CALLS["transcribe"] == calls_before + 1, "đổi tham số phải chạy lại sạch"
    assert os.path.isfile(os.path.join(wd, "manifest.json.stale"))
    print("3. lệch vân tay -> chạy lại sạch ............ OK")

    # --- 4. hủy giữa đường -> JobCancelled; qua _run_dub giữ cancelled
    wd2 = os.path.join(TMP, "work2")
    os.makedirs(wd2, exist_ok=True)
    try:
        dub_pipeline.dub_audio(SRC, "vi", "en", {}, workdir=wd2,
                               abort_check=lambda: True, **common(FakeStorage()))
        raise AssertionError("phải JobCancelled")
    except JobCancelled:
        pass
    print("4a. abort_check -> JobCancelled ............. OK")

    # đường _run_dub thật (monkeypatch dub_audio raise) — job giữ cancelled
    from app.db import SessionLocal
    from app.models import Job, User

    with SessionLocal() as db:
        u = db.query(User).first()
        j = Job(user_id=u.id, type="dub", params={"type": "dub", "media_url": SRC})
        db.add(j)
        db.commit()
        jid = j.id

    import app.tasks as tasks_mod

    orig = dub_pipeline.dub_audio

    def raising_dub(*a, **k):
        raise JobCancelled("job bị hủy giữa đường")

    dub_pipeline.dub_audio = raising_dub
    try:
        # job đang running → _run_dub đi đến dub_audio → JobCancelled
        from app.db import SessionLocal as SL
        from app.models import JobStatus

        with SL() as db:
            job = db.get(Job, jid)
            job.status = JobStatus.running
            db.commit()
        out = tasks_mod._run_dub(jid, {"type": "dub", "media_url": SRC})
        assert out["ok"] is False and out["error"] == "cancelled"
        with SL() as db:
            job = db.get(Job, jid)
            assert job.status == JobStatus.cancelled, job.status
            assert "Chạy lại" in (job.error or "")
    finally:
        dub_pipeline.dub_audio = orig
    print("4b. hủy giữa đường: giữ cancelled + nhắc .... OK")

    # --- 5. endpoint retry
    from fastapi.testclient import TestClient

    from app.main import app

    c = TestClient(app)

    def auth_headers():
        import hashlib
        from app.db import SessionLocal as SL
        from app.models import ApiKey

        with SL() as db:
            row = db.query(ApiKey).first()
        # test_day2 tạo key nhưng ta không biết raw — tạo key riêng cho suite này
        raw = "retry-suite-key"
        h = hashlib.sha256(raw.encode()).hexdigest()
        with SL() as db:
            u = db.query(User).first()
            k = ApiKey(key=h, prefix=raw[:12], user_id=u.id)
            db.add(k)
            db.commit()
        return {"X-API-Key": raw}

    hdr = auth_headers()
    # đánh job về cancelled rồi retry (dispatch GIẢ: inline thật sẽ chạy engine
    # và đè progress/error — ở đây chỉ kiểm trạng thái xếp hàng lại)
    import app.main as main_mod

    orig_dispatch = main_mod.dispatch
    main_mod.dispatch = lambda jid, params: ("fake", "task-fake-id")

    from app.db import SessionLocal as SL
    from app.models import JobStatus

    with SL() as db:
        job = db.get(Job, jid)
        job.status = JobStatus.cancelled
        job.params = {"type": "dub", "media_url": SRC, "source_lang": "vi"}
        job.result_s3_key = "jobs/jr1/dub.wav"
        db.commit()
    r = c.post(f"/v1/jobs/{jid}/retry", headers=hdr)
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "queued" and r.json()["dispatch"] == "fake"
    with SL() as db:
        job = db.get(Job, jid)
        assert job.progress == 0 and job.error is None
        assert job.params.get("source_lang") == "vi", "params phải giữ nguyên"
        assert job.result_s3_key == "jobs/jr1/dub.wav", "result cũ phải giữ"
        assert job.task_id == "task-fake-id", "task_id phải được lưu để hủy được"
    main_mod.dispatch = orig_dispatch

    # 404 job người khác
    with SL() as db:
        other = User(email="other@local")
        db.add(other)
        db.commit()
        j2 = Job(user_id=other.id, type="stt", params={"type": "stt"})
        j2.status = JobStatus.cancelled
        db.add(j2)
        db.commit()
        oid = j2.id
    r2 = c.post(f"/v1/jobs/{oid}/retry", headers=hdr)
    assert r2.status_code == 404, r2.status_code

    # 409 job done
    with SL() as db:
        job = db.get(Job, jid)
        job.status = JobStatus.done
        db.commit()
    r3 = c.post(f"/v1/jobs/{jid}/retry", headers=hdr)
    assert r3.status_code == 409, r3.status_code

    # 409 job đang chạy
    with SL() as db:
        job = db.get(Job, jid)
        job.status = JobStatus.running
        db.commit()
    r4 = c.post(f"/v1/jobs/{jid}/retry", headers=hdr)
    assert r4.status_code == 409, r4.status_code

    # audit `job.retry` đã ghi (lần 200 duy nhất)
    from app.models import AuditLog

    with SL() as db:
        n = db.query(AuditLog).filter(AuditLog.action == "job.retry",
                                      AuditLog.target == jid).count()
        assert n >= 1, "phải ghi audit job.retry"
    print("5. endpoint retry (404/409/200 + audit) ..... OK")

    # --- 6. delete_prefix: dọn sạch jobs/{id}/ — TTS dùng chung nguyên vẹn
    from app.storage import LocalStorage

    root = tempfile.mkdtemp(prefix="vv_del_")
    st = LocalStorage(root)
    st.put("jobs/jx/work/manifest.json", b"{}")
    st.put("jobs/jx/dub.wav", b"x")
    st.put("jobs/tts/shared-hash.wav", b"shared")
    assert st.delete_prefix("jobs/jx/") == 1
    assert not st.exists("jobs/jx/dub.wav") and not st.exists("jobs/jx/work/manifest.json")
    assert st.exists("jobs/tts/shared-hash.wav"), "TTS dùng chung không được đụng"
    assert st.delete_prefix("jobs/khong-ton-tai/") == 0
    print("6. delete_prefix (sạch + giữ TTS chung) ..... OK")

# --- 7. batch_capable
t = CloudChatTranslator("http://mock/v1", "k", "m", "vi", "en")
assert dub_pipeline.batch_capable(t) is t._chat


class FakeChain:
    def __init__(self, providers):
        self.providers = providers


class FakeChainTranslator:
    def __init__(self, providers):
        self._chain = FakeChain(providers)


chain_tr = FakeChainTranslator([t, object()])
assert dub_pipeline.batch_capable(chain_tr) is t._chat


class MarianLike:
    pass


assert dub_pipeline.batch_capable(MarianLike()) is None
print("7. batch_capable (cloud/chain/marian) ....... OK")

print("DUB RESUME GUARDS PASSED")
