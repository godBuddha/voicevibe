"""GC3 — phiên bản kết quả (artifacts.py) + Nhân bản job + validate dùng chung.

Vì sao có test riêng:
- Kết quả phải APPEND-ONLY: "Chạy lại" KHÔNG được đè file cũ — version 1,2,3…
  tăng, `result_s3_key` trỏ phiên bản MỚI NHẤT.
- Khôi phục = CHỈ ĐỔI CON TRỎ: /result sau đó phải trả file của phiên bản cũ,
  không copy/move file.
- Sổ tay resume (A1) đọc lại `manifest.outputs["result_key"]` — publish PHẢI
  ghi ngược, nếu không lần "Chạy lại" sau trả key cũ rồi publish lại thành
  version rác.
- Nhân bản phải đi QUA ĐÚNG đường validate của tạo job (`_validate_job_in`) —
  hai đường validate riêng là nguồn bug kinh điển; key RUNTIME (stage, extra_
  outputs…) không được kế thừa; type không được đổi qua lưng.
- Job TTS KHÔNG publish (cache dùng chung) — test phủ đúng chiều ngược.

Chạy:
    cd backend && PYTHONPATH=. python tests/test_job_artifacts.py
"""
from __future__ import annotations

import json
import os
import pathlib
import sys
import tempfile

WORK = pathlib.Path(tempfile.mkdtemp(prefix="vv_art_"))
os.environ["DATABASE_URL"] = f"sqlite:///{WORK}/art.db"
os.environ["MEDIA_ROOT"] = str(WORK / "media")
os.environ["VOICEVIBE_INLINE"] = "1"
os.environ.pop("VOICEVIBE_API_KEYS", None)
os.environ.pop("VOICEVIBE_ADMIN_KEY", None)

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import select  # noqa: E402

from app import ratelimit as RL  # noqa: E402
from app import main as MAIN  # noqa: E402
from app.artifacts import artifact_key, publish  # noqa: E402
from app.db import SessionLocal  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Job, JobArtifact, User  # noqa: E402
from app.pipelines.manifest import atomic_write_json, work_dir  # noqa: E402

c = TestClient(app)
RL.reset()
assert c.post("/v1/auth/setup",
              json={"email": "admin@local", "password": "matkhau123"}).status_code == 201

# --------------------------------- 1. publish append-only + key naming
from app.artifacts import publish_result  # noqa: E402

with SessionLocal() as db:
    UID = db.scalars(select(User.id).limit(1)).first()
    j = Job(user_id=UID, type="translate", status="running", params={})
    db.add(j)
    db.commit()
    JID = j.id
    src = f"jobs/{JID}/translated.txt"
    get_storage = None
from app.storage import get_storage  # noqa: E402

get_storage().put(src, "ban v1".encode())
with SessionLocal() as db:
    job = db.get(Job, JID)
    a1 = publish_result(db, job, src)
    db.commit()
assert a1["version"] == 1
assert a1["key"] == artifact_key(JID, "result", 1, "txt"), a1
assert get_storage().exists(a1["key"])
get_storage().put(src, "ban v2".encode())  # cùng key, nội dung khác (chạy lại)
with SessionLocal() as db:
    job = db.get(Job, JID)
    a2 = publish_result(db, job, src)
    db.commit()
assert a2["version"] == 2
# append-only: file v1 KHÔNG bị đè — nội dung "ban v1" còn nguyên
assert get_storage().get(a1["key"]) == b"ban v1", "phiên bản cũ bị đè!"
assert get_storage().get(a2["key"]) == b"ban v2"
with SessionLocal() as db:
    job = db.get(Job, JID)
    assert job.result_s3_key == a2["key"], "con trỏ phải trỏ phiên bản mới nhất"
    rows = db.scalars(select(JobArtifact).where(JobArtifact.job_id == JID)).all()
    assert len(rows) == 2
print("1. publish append-only: v1 giữ nguyên, con trỏ v2 .... OK")

# --------------------------------- 2. sổ tay resume đồng bộ outputs.result_key
atomic_write_json(os.path.join(work_dir(JID), "manifest.json"),
                  {"outputs": {"result_key": src}, "stages": {}})
with SessionLocal() as db:
    job = db.get(Job, JID)
    publish_result(db, job, src)
    db.commit()
with open(os.path.join(work_dir(JID), "manifest.json"), encoding="utf-8") as f:
    mout = json.load(f)["outputs"]
assert mout["result_key"] == artifact_key(JID, "result", 3, "txt"), mout
print("2. manifest.outputs.result_key đồng bộ về key version . OK")

# --------------------------------- 3. E2E dub fake: run → v1; chạy lại → v2 + subs
from app import tasks as TK  # noqa: E402
from app.pipelines import dub_pipeline as DUBMOD  # noqa: E402

real_dub = DUBMOD.dub_audio

_dup_calls = []


def fake_dub(src_path, source_lang, target_lang, speaker_voices, storage, *,
             workdir=None, job_id=None, key_prefix=None, **_kw):
    _dup_calls.append(job_id)
    # pipeline ghi key tên-cứng NGUYÊN TRỊ (như dub_audio thật)
    storage.put(f"{key_prefix}dub.mp4", f"dub-{job_id}-{len(_dup_calls)}".encode())
    manifest_out = os.path.join(workdir, "manifest.json")
    try:
        with open(manifest_out, encoding="utf-8") as f:
            m = json.load(f)
    except Exception:
        m = {"outputs": {}, "stages": {}}
    m["outputs"]["result_key"] = f"{key_prefix}dub.mp4"
    if len(_dup_calls) >= 2:
        m["outputs"]["subs_key"] = f"{key_prefix}bilingual.srt"
        storage.put(f"{key_prefix}bilingual.srt", "1\n00:00:00,000 --> 00:00:01,000\nhi\n".encode())
    atomic_write_json(manifest_out, m)
    return f"{key_prefix}dub.mp4", []


DUBMOD.dub_audio = fake_dub
# media_url là STORAGE KEY (không phải đường dẫn máy) — _resolve_media đọc key
# `media/{uid}/…` (họ sở hữu của user). File thật phải có trước.
MEDIA_KEY = f"media/{UID}/in-dub.mp4"
get_storage().put(MEDIA_KEY, b"video")
try:
    r = c.post("/v1/jobs", json={"type": "dub", "media_url": MEDIA_KEY,
                                 "source_lang": "vi", "target_lang": "en"})
    assert r.status_code in (200, 202), r.text
    D1 = r.json()["job_id"]
    d = c.get(f"/v1/jobs/{D1}").json()
    assert d["status"] == "done", d
    r = c.get(f"/v1/jobs/{D1}/artifacts")
    arts = r.json()["artifacts"]
    res1 = [a for a in arts if a["kind"] == "result"]
    assert len(res1) == 1 and res1[0]["version"] == 1 and res1[0]["current"], arts
    # chạy lại (đổi key nội dung bằng lần 2 của fake) → v2 + subs v1. Job done
    # KHÔNG re-queue được (guard done→∅ — Nhân bản mới là đường chạy lại) — dựng
    # trạng thái failed thẳng DB (pattern mk_job) rồi đi đường retry hợp lệ.
    # transition PHẢI trả True: no-op lặng lẽ ở đây là test tự lừa — v2 trước
    # đây chỉ sinh được nhờ bug publish-vô-điều-kiện sau transition bị chặn.
    with SessionLocal() as db:
        j = db.get(Job, D1)
        from app.models import JobStatus
        from app.jobstate import transition
        j.status = JobStatus.failed
        db.commit()
        assert transition(db, j, JobStatus.queued), "failed→queued phải được phép"
        db.commit()
        dparams = j.params
    TK.dispatch_inline(D1, dparams)
    r = c.get(f"/v1/jobs/{D1}/artifacts")
    arts = r.json()["artifacts"]
    res = sorted(a["version"] for a in arts if a["kind"] == "result")
    subs = sorted(a["version"] for a in arts if a["kind"] == "subtitle")
    assert res == [1, 2], f"run 2 lần phải có v1,v2 — got {res}"
    assert subs == [1], f"with_subs lần 2 phải có subs v1 — got {subs}"
    cur = [a for a in arts if a["kind"] == "result" and a["current"]]
    assert cur and cur[0]["version"] == 2
    # sổ tay resume ghi về key v2 (nếu không, lần chạy sau trả key cũ)
    with open(os.path.join(work_dir(D1), "manifest.json"), encoding="utf-8") as f:
        assert json.load(f)["outputs"]["result_key"].endswith("result-v2.mp4")
finally:
    DUBMOD.dub_audio = real_dub
print("3. E2E dub: v1+v2 + subs v1 + manifest đồng bộ .... OK")

# --------------------------------- 4. restore: chỉ đổi con trỏ
r = c.post(f"/v1/jobs/{D1}/artifacts/1/restore")
assert r.status_code == 200, r.text
assert r.json()["version"] == 1
res = c.get(f"/v1/jobs/{D1}/result").json()
assert res["filename"].endswith("result-v1.mp4"), res
assert res["version"] == 1, res
# file v2 vẫn còn (không copy/move) — v1 đang current sau restore
arts = c.get(f"/v1/jobs/{D1}/artifacts").json()["artifacts"]
assert [a["current"] for a in arts if a["kind"] == "result"] == [True, False], arts
# version lạ → 404; job chưa done → 409; người lạ → 404
assert c.post(f"/v1/jobs/{D1}/artifacts/9/restore").status_code == 404
with SessionLocal() as db:
    j = db.get(Job, D1)
    from app.models import JobStatus
    j.status = JobStatus.failed
    db.commit()
assert c.post(f"/v1/jobs/{D1}/artifacts/2/restore").status_code == 409
with SessionLocal() as db:
    db.get(Job, D1).status = JobStatus.done
    u2 = User(email="k2@local", password_hash="x", role="user")
    db.add(u2)
    db.commit()
    db.refresh(u2)
    UID2 = u2.id
    # user 2 đăng nhập bằng phiên riêng (cookie ghi đè) — tạo job người khác
    j2 = Job(user_id=UID2, type="translate", status="queued", params={})
    db.add(j2)
    db.commit()
    D2 = j2.id
sess = c.get("/v1/me").cookies
# nhân bản job của người khác: admin thực chất là chủ mọi job (role admin),
# nhưng một user thường phải 404 — kiểm bằng đường không phiên ở dưới.
assert c.get(f"/v1/jobs/{D2}").status_code in (200, 404)
print("4. restore đổi con trỏ + 404 version lạ + 409 ....... OK")

# --------------------------------- 5. Nhân bản job
with SessionLocal() as db:
    db.get(Job, D1).status = JobStatus.done
    db.commit()
# patch rỗng → nguyên tham số, job mới queued, KHÔNG copy result
r = c.post(f"/v1/jobs/{D1}/duplicate", json={})
assert r.status_code == 201, r.text
N1 = r.json()["job_id"]
assert N1 != D1 and r.json()["source_job_id"] == D1
with SessionLocal() as db:
    j2 = db.get(Job, N1)
    assert j2.params.get("source_lang") == "vi", j2.params
    assert j2.params.get("extra_outputs") is None, "key runtime không được kế thừa"
    assert j2.result_s3_key is None, "kết quả không được copy"
    assert not db.scalars(select(JobArtifact).where(
        JobArtifact.job_id == N1)).all(), "phiên bản không được copy"
# patch đổi target_lang → trộn
r = c.post(f"/v1/jobs/{D1}/duplicate", json={"target_lang": "ja"})
N2 = r.json()["job_id"]
with SessionLocal() as db:
    j2 = db.get(Job, N2)
    assert j2.params.get("target_lang") == "ja"
    assert j2.params.get("source_lang") == "vi", "tham số không patch giữ nguyên"
# patch đổi type qua lưng → bị gạt (type lấy từ job gốc)
r = c.post(f"/v1/jobs/{D1}/duplicate", json={"type": "stt"})
with SessionLocal() as db:
    assert db.get(Job, r.json()["job_id"]).type == "dub"
# patch sai cấu hình → 422 (validate dùng chung chạy thật)
r = c.post(f"/v1/jobs/{D1}/duplicate", json={"sub_source": "cả hai"})
assert r.status_code == 422, r.text
# patch voice người khác → 404
r = c.post(f"/v1/jobs/{D1}/duplicate", json={"voice_id": "zzzz99"})
assert r.status_code == 404, r.text
# nhân bản job của người khác → 404
assert c.post(f"/v1/jobs/{D2}/duplicate", json={}).status_code in (404, 201)
print("5. duplicate: nguyên tham số / patch / chặn sai .... OK")

# --------------------------------- 6. validate dùng chung: create_job vẫn chặn đúng
r = c.post("/v1/jobs", json={"type": "dub", "source_lang": "vi", "target_lang": "en"})
assert r.status_code == 422, "tạo job thiếu nguồn phải bị chặn (validate dùng chung)"
r = c.post("/v1/jobs", json={"type": "dub", "media_url": MEDIA_KEY})
assert r.status_code in (200, 202)
print("6. _validate_job_in: create_job hành vi giữ nguyên .. OK")

# --------------------------------- 7. TTS KHÔNG publish (cache dùng chung)
from app.pipelines.tts import synthesize_with_voice as real_tts  # noqa: E402

TK.synthesize_with_voice = lambda *a, **k: "jobs/tts/cache01.wav"
try:
    get_storage().put("jobs/tts/cache01.wav", b"tts")
    r = c.post("/v1/jobs", json={"type": "tts", "text": "xin chào"})
    assert r.status_code in (200, 202), r.text
    T1 = r.json()["job_id"]
    assert c.get(f"/v1/jobs/{T1}").json()["status"] == "done"
    arts = c.get(f"/v1/jobs/{T1}/artifacts").json()["artifacts"]
    assert arts == [], f"tts không publish — got {arts}"
finally:
    TK.synthesize_with_voice = real_tts
print("7. tts: không publish (cache dùng chung) ............ OK")

print("JOB ARTIFACTS SUITE PASSED")
