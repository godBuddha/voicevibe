"""B6 — Guard job `summary` (AI tóm tắt map-reduce + chống injection).

Vì sao có test riêng (selftest đã kiểm thuật toán):
- ĐƯỜNG HTTP THẬT: tạo job qua POST /v1/jobs (422 thiếu nguồn, 422 thiếu
  model chat là FAIL RÕ KHÔNG 500), worker _run_summary thật (monkeypatch
  chat), transcript CHECKPOINT qua manifest (chạy lại KHÔNG nghe lại —
  lãng phí GPU lớn nhất của job này), result summary.md phải là kind "text"
  (thiếu "md" trong get_result là bug chắc chắn — xếp loại audio).
- Prompt seed: 3 prompt mới phải vừa cột (guard test_prompt_library tự bắn
  khi boot — nhưng suite này kiểm sớm không phụ thuộc thứ tự).
- Ownership prompt_id cho summary.

Bootstrap khớp pattern repo. Chạy:
    cd backend && PYTHONPATH=. python tests/test_summary.py
"""
from __future__ import annotations

import os
import pathlib
import sys
import tempfile

WORK = pathlib.Path(tempfile.mkdtemp(prefix="vv_sum_"))
os.environ["DATABASE_URL"] = f"sqlite:///{WORK}/sum.db"
os.environ["MEDIA_ROOT"] = str(WORK / "media")
os.environ["VOICEVIBE_INLINE"] = "1"
os.environ.pop("VOICEVIBE_API_KEYS", None)
os.environ.pop("VOICEVIBE_ADMIN_KEY", None)

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient  # noqa: E402

from app import ratelimit as RL  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Job as JobRow  # noqa: E402
from app.db import SessionLocal  # noqa: E402

c = TestClient(app)
RL.reset()
assert c.post("/v1/auth/setup",
              json={"email": "admin@local", "password": "matkhau123"}).status_code == 201

# ------------------------------------- 1. prompt seed mới vừa cột + guard 401
from app.prompts import DEFAULT_PROMPTS  # noqa: E402

for key in ("summarize", "summarize_map", "summarize_compose"):
    assert key in DEFAULT_PROMPTS, key
    assert len(DEFAULT_PROMPTS[key]["description"]) <= 255, \
        f"{key}: description {len(DEFAULT_PROMPTS[key]['description'])} > 255"
anon = TestClient(app)
RL.reset()
r = anon.post("/v1/jobs", json={"type": "summary", "text": "x"})
assert r.status_code == 401, r.status_code
print("1. 3 prompt seed vừa cột + anon 401 .............. OK")

# --------------------------------------------- 2. validate tạo job 422
r = c.post("/v1/jobs", json={"type": "summary"})
assert r.status_code == 422, r.text  # không text, không media, không link
r = c.post("/v1/jobs", json={"type": "summary", "media_url": "https://x.test/v.mp4"})
assert r.status_code in (200, 202), r.text  # media (sẽ failed vì file không có)
print("2. validate summary 422 / media được nhận ......... OK")

# ------------------------------- 3. worker thật với text: route qua fake chat
_calls: list[dict] = []
FAKE_OUT = "# Tóm tắt cuối cùng bằng tiếng việt"


class FakeChat:
    def complete(self, system, user, *, json_mode=False, max_tokens=2048,
                 temperature=0.2):
        _calls.append({"system": system, "user": user, "temperature": temperature})
        return FAKE_OUT


import app.pipelines.summary as SMOD  # noqa: E402

real_build_chat = SMOD.build_chat
SMOD.build_chat = lambda: FakeChat()
try:
    r = c.post("/v1/jobs", json={"type": "summary",
                                 "text": "[00:00:01] Đây là nội dung video thử. " * 20})
    assert r.status_code in (200, 202), r.text
    J = r.json()["job_id"]
    d = c.get(f"/v1/jobs/{J}").json()
    assert d["status"] == "done", d
    assert _calls and _calls[0]["temperature"] == 0.7, _calls[0]
    assert _calls[0]["system"].startswith("Security rule:"), \
        "security rule phải ở ĐẦU system prompt"
    assert "<video_transcript>" in _calls[0]["user"]
    res = c.get(f"/v1/jobs/{J}/result").json()
    assert res["kind"] == "text", res  # THIẾU "md" trong get_result = bug audio
    assert res["filename"].endswith(".md"), res
    assert res.get("content", "").startswith("# Tóm tắt"), res.get("content", "")
finally:
    SMOD.build_chat = real_build_chat
print("3. summary text: fake chat + result md text ....... OK")

# ------------------------------------------------- 4. checkpoint transcript
_transcribe_calls: list[str] = []


def fake_ts(path, language=None, stats=None):
    _transcribe_calls.append("listen")
    return "[00:00:01] Đoạn một.\n[00:00:05] Đoạn hai."


real_ts = SMOD.transcript_with_timestamps
SMOD.transcript_with_timestamps = fake_ts
FAKE_MEDIA = str(WORK / "src.mp4")
with open(FAKE_MEDIA, "wb") as f:
    f.write(b"MP4")
SMOD.build_chat = lambda: FakeChat()
try:
    r = c.post("/v1/jobs", json={"type": "summary", "media_url": FAKE_MEDIA})
    assert r.status_code in (200, 202), r.text
    J2 = r.json()["job_id"]
    d = c.get(f"/v1/jobs/{J2}").json()
    assert d["status"] == "done", d
    assert len(_transcribe_calls) == 1, _transcribe_calls
    with SessionLocal() as db:
        row = db.get(JobRow, J2)
        assert row.params.get("stage"), row.params
    # retry thất bại giả → phải DÙNG checkpoint (không nghe lại)
    import app.pipelines.summary as _S

    def failing_map(*a, **kw):
        raise RuntimeError("LLM chết giữa đường")

    real_mr = _S.map_reduce
    _S.map_reduce = failing_map
    from app.tasks import _run_summary  # noqa: E402

    with SessionLocal() as db:
        row = db.get(JobRow, J2)
        row.status = "failed"
        db.commit()
    _S.transcript_with_timestamps = fake_ts  # vẫn fake — nếu gọi lại là fail assert
    _run_summary(J2, {"type": "summary", "media_url": FAKE_MEDIA})
    assert len(_transcribe_calls) == 1, \
        f"checkpoint phải giữ transcript (nghe {len(_transcribe_calls)} lần)"
    _S.map_reduce = real_mr
finally:
    SMOD.transcript_with_timestamps = real_ts
    SMOD.build_chat = real_build_chat
print("4. checkpoint transcript: retry không nghe lại .... OK")

# ------------------------------------------- 5. không có model chat → fail rõ
SMOD.build_chat = lambda: None
try:
    r = c.post("/v1/jobs", json={"type": "summary", "text": "nội dung thử"})
    assert r.status_code in (200, 202), r.text
    J3 = r.json()["job_id"]
    d = c.get(f"/v1/jobs/{J3}").json()
    assert d["status"] == "failed", d
    assert "model chat" in (d.get("error") or "") or "Model Hub" in (d.get("error") or ""), d
finally:
    SMOD.build_chat = real_build_chat
print("5. thiếu model chat → failed rõ (không 500) ....... OK")

# ------------------------------------------- 6. prompt_id ownership cho summary
r = c.post("/v1/prompts", json={"name": "tóm tắt của tôi",
                                "content": "Tóm tắt NGẮN, giọng vui vẻ."})
assert r.status_code == 201, r.text
PID = r.json()["id"]
SMOD.build_chat = lambda: FakeChat()
try:
    r = c.post("/v1/jobs", json={"type": "summary", "text": "nội dung",
                                 "prompt_id": PID})
    assert r.status_code in (200, 202), r.text
    J4 = r.json()["job_id"]
    d = c.get(f"/v1/jobs/{J4}").json()
    assert d["status"] == "done", d
    # override phải thay system prompt single-shot (giữ security rule đầu)
    sys_msgs = [x["system"] for x in _calls]
    assert any("Tóm tắt NGẮN" in s for s in sys_msgs), sys_msgs[-1]
    # prompt của user khác → 404
    other_email = "other-sum@local"
    from app.models import User  # noqa: E402
    from app.security import hash_password  # noqa: E402

    with SessionLocal() as db:
        db.add(User(email=other_email, role="user",
                    password_hash=hash_password("matkhau456")))
        db.commit()
    co = TestClient(app)
    RL.reset()
    assert co.post("/v1/auth/login",
                   json={"email": other_email, "password": "matkhau456"}).status_code == 200
    r = co.post("/v1/jobs", json={"type": "summary", "text": "x", "prompt_id": PID})
    assert r.status_code == 404, r.text
finally:
    SMOD.build_chat = real_build_chat
print("6. prompt_id summary: override đi ra + ownership .. OK")

# ------------------------------------------- 7. stage 'summarize' khả dụng
from app.capabilities import STAGE_FEATURES  # noqa: E402
from app.models import STAGES  # noqa: E402

assert "summarize" in STAGES and STAGE_FEATURES["summarize"] == "text_generation"
r = c.get("/v1/admin/stages")  # admin thấy công đoạn mới trong Model Hub
print("7. stage summarize trong Model Hub ................ OK")

print("SUMMARY SUITE PASSED")
