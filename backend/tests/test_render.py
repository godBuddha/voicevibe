"""B3+B4 + GE1 — Guard job `render`: burn phụ đề ASS 2 style + dựng khung
(7 tỉ lệ: 9:16/4:5/1:1/4:3/16:9/21:9/original) + banner mọi tỉ lệ.

Vì sao có test riêng (selftest đã kiểm thuật toán thuần):
- ĐƯỜNG HTTP THẬT: validate create_job (≥1 lựa chọn; burn cần nguồn; key XOR
  job id; aspect sai giá trị/mâu thuẫn vertical), worker _run_render thật
  (monkeypatch run_render), ownership job phụ đề (job của người khác → lỗi
  rõ), đuôi file phụ đề sai → lỗi.
- GUARD NGƯỢC (nguyên tắc verification): đổi banner/vertical/burn/aspect
  PHẢI đổi vân tay render (render_fingerprint soi TOÀN BỘ material — bẫy
  fingerprint số 3; params_fingerprint của dub bỏ qua key lạ là bẫy thật).
- BYTE-COMPAT (GE1): 9:16 ra đúng filter cũ; job cũ KHÔNG aspect giữ
  fingerprint nguyên vẹn; banner-only giờ CÓ tác dụng (bug cũ: bị bỏ qua
  âm thầm khi vertical=False).

Bootstrap khớp pattern repo. Chạy:
    cd backend && PYTHONPATH=. python tests/test_render.py
"""
from __future__ import annotations

import os
import pathlib
import sys
import tempfile

WORK = pathlib.Path(tempfile.mkdtemp(prefix="vv_render_"))
os.environ["DATABASE_URL"] = f"sqlite:///{WORK}/render.db"
os.environ["MEDIA_ROOT"] = str(WORK / "media")
os.environ["VOICEVIBE_INLINE"] = "1"
os.environ.pop("VOICEVIBE_API_KEYS", None)
os.environ.pop("VOICEVIBE_ADMIN_KEY", None)

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient  # noqa: E402

from app import ratelimit as RL  # noqa: E402
from app.main import app  # noqa: E402
from app.pipelines import render as RND  # noqa: E402
from app.pipelines.manifest import params_fingerprint  # noqa: E402

c = TestClient(app)
RL.reset()
assert c.post("/v1/auth/setup",
              json={"email": "admin@local", "password": "matkhau123"}).status_code == 201

# --------------------------------------------- 1. validate create_job 422
FAKE_MEDIA = str(WORK / "src.mp4")
with open(FAKE_MEDIA, "wb") as f:
    f.write(b"MP4")
for bad, why in [
    ({"type": "render", "media_url": FAKE_MEDIA}, "không toggle nào"),
    ({"type": "render", "media_url": FAKE_MEDIA, "burn_subtitles": True},
     "burn nhưng không nguồn phụ đề"),
    ({"type": "render", "media_url": FAKE_MEDIA, "burn_subtitles": True,
      "subtitle_key": "jobs/x.srt", "subtitle_job_id": "abc"},
     "cả hai nguồn phụ đề"),
    ({"type": "render", "media_url": FAKE_MEDIA, "subtitle_key": "jobs/x.srt"},
     "chỉ có nguồn phụ đề mà không bật burn"),
]:
    r = c.post("/v1/jobs", json=bad)
    assert r.status_code == 422, f"{why}: {r.text}"
# banner-only là hợp lệ (có toggle)
r = c.post("/v1/jobs", json={"type": "render", "media_url": FAKE_MEDIA,
                             "vertical": True, "banner": {"major": "T", "minor": "P"}})
assert r.status_code in (200, 202), r.text
RL.reset()
print("1. validate render 422 + banner-only hợp lệ ..... OK")

# --------------------------------------------- 2. render_fingerprint soi đủ
m1 = {"media_url": "x", "burn_subtitles": True, "vertical": False,
      "banner": {"major": "A", "minor": "B"}, "cues_fingerprint": "h"}
m2 = {**m1, "banner": {"major": "A", "minor": "X"}}
m3 = {**m1, "vertical": True}
m4 = {**m1, "cues_fingerprint": "g"}
assert RND.render_fingerprint(m1) != RND.render_fingerprint(m2), "đổi banner phải đổi vân tay"
assert RND.render_fingerprint(m1) != RND.render_fingerprint(m3), "đổi vertical phải đổi vân tay"
assert RND.render_fingerprint(m1) != RND.render_fingerprint(m4), "đổi phụ đề phải đổi vân tay"
# guard NGƯỢC: params_fingerprint của dub là bộ khác — không dùng nhầm
assert params_fingerprint({"media_url": "x"}, "render") != RND.render_fingerprint(m1)
print("2. render_fingerprint soi toàn bộ material ........ OK")

# --------------------------------------------- 3. worker _run_render thật
_calls: list[dict] = []
KEY = "jobs/ZZ/render.mp4"


def fake_run_render(src, *, burn_subtitles=False, vertical=False, aspect=None,
                    banner=None, cues_text=None, cues_ext="", workdir="",
                    job_id="", key_prefix="", storage=None, abort_check=None,
                    progress_cb=None):
    _calls.append({"src": src, "burn": burn_subtitles, "vert": vertical,
                   "aspect": aspect, "banner": banner, "cues_ext": cues_ext,
                   "cues_text": cues_text,
                   "cues_len": len(cues_text or "")})
    if progress_cb:
        progress_cb(70, "in phụ đề")
    return f"{key_prefix}render.mp4"


real_run_render = RND.run_render
RND.run_render = fake_run_render
try:
    r = c.post("/v1/jobs", json={"type": "render", "media_url": FAKE_MEDIA,
                                 "burn_subtitles": True, "vertical": True,
                                 "banner": {"major": "T", "minor": "P"},
                                 "subtitle_key": "jobs/sub.srt"})
    assert r.status_code in (200, 202), r.text
    J = r.json()["job_id"]
    d = c.get(f"/v1/jobs/{J}").json()
    # subtitle_key "jobs/sub.srt" chưa có trong storage → job FAILED (lỗi rõ),
    # KHÔNG 500 — đây là hành vi mong đợi ở bước chưa đặt file
    if d["status"] == "failed":
        assert "media not found" in (d.get("error") or "") or "không tồn tại" in \
            (d.get("error") or ""), d
        # đặt file phụ đề rồi chạy lại
        from app.storage import get_storage
        get_storage().put("jobs/sub.srt",
                          b"1\n00:00:00,000 --> 00:00:01,000\nXin ch\xc3\xa0o\n")
        r = c.post(f"/v1/jobs/{J}/retry")
        assert r.status_code in (200, 202), r.text
        d = c.get(f"/v1/jobs/{J}").json()
    assert d["status"] == "done", d
    call = _calls[-1]
    assert call["burn"] and call["vert"] and call["cues_ext"] == "srt", call
    assert call["banner"] == {"major": "T", "minor": "P"}, call
    # bug thật E2E GE1 bắt được: get_to_temp trả PATH — nếu worker truyền path
    # thay NỘI DUNG thì cues_text là "/tmp/..." và parse ra 0 cue. Khẳng định
    # worker phải trao NỘI DUNG phụ đề cho pipeline.
    assert "Xin chào" in call["cues_text"], call["cues_text"][:80]
    res = c.get(f"/v1/jobs/{J}/result").json()
    assert res["kind"] == "video" and res["filename"].endswith(".mp4"), res
finally:
    RND.run_render = real_run_render
print("3. _run_render thật: key + nguồn phụ đề srt ....... OK")

# --------------------------------------------- 4. subtitle_job_id + ownership
from app.db import SessionLocal  # noqa: E402
from app.models import Job as JobRow  # noqa: E402
from app.models import User  # noqa: E402
from app.security import hash_password  # noqa: E402

with SessionLocal() as db:
    db.add(User(email="other@local", role="user",
                password_hash=hash_password("matkhau456")))
    db.commit()
co = TestClient(app)
RL.reset()
assert co.post("/v1/auth/login",
               json={"email": "other@local", "password": "matkhau456"}).status_code == 200

with SessionLocal() as db:
    me = c.get("/v1/auth/me").json()
    sub = JobRow(user_id=me["user_id"], type="subtitle", status="done",
                 params={"type": "subtitle"}, result_s3_key="jobs/s1/subtitle.srt")
    db.add(sub)
    db.commit()
    SUB_ID = sub.id
# GE1: file phụ đề giờ được ĐỌC THẬT (bug get_to_temp-path đã sửa) — job
# sample phải có file trong kho, không chỉ key trên giấy.
from app.storage import get_storage  # noqa: E402
get_storage().put("jobs/s1/subtitle.srt",
                  "1\n00:00:00,000 --> 00:00:01,000\nChào bạn\n".encode())
RND.run_render = fake_run_render
try:
    r = c.post("/v1/jobs", json={"type": "render", "media_url": FAKE_MEDIA,
                                 "burn_subtitles": True,
                                 "subtitle_job_id": SUB_ID})
    assert r.status_code in (200, 202), r.text
    J2 = r.json()["job_id"]
    d = c.get(f"/v1/jobs/{J2}").json()
    assert d["status"] == "done", d
    call = _calls[-1]
    assert call["cues_ext"] == "srt", call

    # job phụ đề của NGƯỜI KHÁC → job render failed với lỗi rõ (không lộ file)
    with SessionLocal() as db:
        other = db.get(User, me["user_id"])
    r = co.post("/v1/jobs", json={"type": "render", "media_url": FAKE_MEDIA,
                                  "burn_subtitles": True,
                                  "subtitle_job_id": SUB_ID})
    assert r.status_code in (200, 202), r.text
    J3 = r.json()["job_id"]
    d = co.get(f"/v1/jobs/{J3}").json()
    assert d["status"] == "failed", d
    assert "không thuộc về bạn" in (d.get("error") or ""), d
finally:
    RND.run_render = real_run_render
print("4. subtitle_job_id: của mình OK, người khác fail .. OK")

# --------------------------------------------- 5. đuôi file phụ đề sai
RND.run_render = fake_run_render
try:
    r = c.post("/v1/jobs", json={"type": "render", "media_url": FAKE_MEDIA,
                                 "burn_subtitles": True,
                                 "subtitle_key": "jobs/x.pdf"})
    assert r.status_code in (200, 202), r.text
    J5 = r.json()["job_id"]
    d = c.get(f"/v1/jobs/{J5}").json()
    assert d["status"] == "failed" and ".pdf" in (d.get("error") or ""), d
finally:
    RND.run_render = real_run_render
print("5. đuôi phụ đề sai → failed rõ ràng ............... OK")

# --------------------------------------------- 6. aspect validate (GE1)
RND.run_render = fake_run_render
try:
    for bad, why in [
        ({"type": "render", "media_url": FAKE_MEDIA, "aspect": "3:2"},
         "aspect sai giá trị"),
        ({"type": "render", "media_url": FAKE_MEDIA, "aspect": "16:9",
          "vertical": True}, "vertical legacy mâu thuẫn 16:9"),
        ({"type": "render", "media_url": FAKE_MEDIA, "aspect": "original"},
         "original đơn lẻ — không làm gì cả"),
    ]:
        r = c.post("/v1/jobs", json=bad)
        assert r.status_code == 422, f"{why}: {r.text}"
    # hợp lệ: 9:16 đi cùng vertical legacy (cùng nghĩa); 16:9 đơn lẻ (job chỉ
    # dựng khung); banner-only KHÔNG vertical/aspect → GE1 sửa bug "banner bị
    # bỏ qua âm thầm" (trước đây banner chỉ có tác dụng khi vertical=True)
    for good, why in [
        ({"type": "render", "media_url": FAKE_MEDIA, "aspect": "9:16",
          "vertical": True}, "9:16 + legacy cùng nghĩa"),
        ({"type": "render", "media_url": FAKE_MEDIA, "aspect": "16:9"},
         "16:9 đơn lẻ"),
        ({"type": "render", "media_url": FAKE_MEDIA,
          "banner": {"major": "T", "minor": "P"}}, "banner-only (bug fix)"),
    ]:
        RL.reset()
        r = c.post("/v1/jobs", json=good)
        assert r.status_code in (200, 202), f"{why}: {r.text}"
finally:
    RND.run_render = real_run_render
RL.reset()
print("6. aspect validate 422/202 + banner-only fix ...... OK")

# --------------------------------------------- 7. resolve khung + _strip_h
for a, dims in RND.ASPECT_TARGETS.items():
    tw, th, strip, scale, label = RND._resolve_frame(a, False, 320, 180, None)
    assert (tw, th) == dims and strip == RND._strip_h(th) and scale is None, a
    assert label == a, a
# legacy: không aspect + vertical=True → đúng bộ 9:16 cũ
assert RND._resolve_frame(None, True, 320, 180, None) == \
    (720, 1280, 250, None, "9:16"), "legacy phải là 9:16 nguyên bản"
# legacy: không aspect + không vertical → không dựng khung
assert RND._resolve_frame(None, False, 320, 180, None) == \
    (None, None, None, None, "9:16"), "legacy không vertical = giữ nguyên"
# original: không banner → không dựng khung; có banner → khung nguồn + co nội dung
assert RND._resolve_frame("original", False, 320, 180, None)[0] is None
assert RND._resolve_frame("original", False, 320, 180, {"major": "A"}) == \
    (320, 180, 35, 145, "giữ nguyên khung"), "original + banner: strip 35, co 145"
# strip theo chiều cao khung (≈20%): 1280→250 legacy, 1080→211, 720→141
assert (RND._strip_h(1280), RND._strip_h(1080), RND._strip_h(720)) == (250, 211, 141)
# phòng thủ lớp 2: aspect lạ → ValueError
try:
    RND._resolve_frame("3:2", False, 320, 180, None)
    raise SystemExit("aspect lạ phải ValueError")
except ValueError:
    pass
print("7. _resolve_frame 6 tỉ lệ + legacy + original ..... OK")

# --------------------------------------------- 8. fingerprint: aspect có điều kiện
m5 = RND._fingerprint_material("x", True, True, {"major": "A", "minor": "B"},
                               "srt-cues", None)
assert set(m5) == {"media_url", "burn_subtitles", "vertical", "banner",
                   "cues_fingerprint"}, "job cũ KHÔNG được có key aspect"
m5a = RND._fingerprint_material("x", True, True, {"major": "A", "minor": "B"},
                                "srt-cues", "16:9")
assert m5a["aspect"] == "16:9", "aspect tường minh phải nằm trong material"
assert RND.render_fingerprint(m5) != RND.render_fingerprint(m5a), \
    "có/không aspect phải khác vân tay"
# hai aspect khác nhau phải khác nhau (16:9 vs 1:1 cùng material khác)
m5b = RND._fingerprint_material("x", True, True, {"major": "A", "minor": "B"},
                                "srt-cues", "1:1")
assert RND.render_fingerprint(m5a) != RND.render_fingerprint(m5b)
print("8. fingerprint aspect có điều kiện + guard ngược .. OK")

# --------------------------------------------- 9. banner scale + filter byte-compat
legacy = RND.frame_cmd("in.mp4", "out.mp4", 720, 1280, 250)
assert legacy[legacy.index("-vf") + 1] == (
    "scale=720:1280:force_original_aspect_ratio=decrease,"
    "pad=720:1280:(ow-iw)/2:250"), "9:16 phải ra đúng filter cũ byte-for-byte"
wide = RND.frame_cmd("in.mp4", "out.mp4", 1280, 720, 141)
assert wide[wide.index("-vf") + 1] == (
    "scale=1280:720:force_original_aspect_ratio=decrease,"
    "pad=1280:720:(ow-iw)/2:141"), "16:9: strip 141"
try:
    from PIL import Image  # noqa: F401
    png = os.path.join(str(WORK), "banner-ge1.png")
    RND.render_banner_png({"major": "Ngang", "minor": "YouTube"}, png,
                          width=1680, height=141)
    assert Image.open(png).size == (1680, 141)
    have_pillow = True
except ImportError:
    have_pillow = False
print("9. frame_cmd byte-compat + banner scale "
      + ("OK" if have_pillow else "(pillow bỏ qua)") + " . OK")

# --------------------------------------------- 10. worker truyền aspect xuống pipeline
RND.run_render = fake_run_render
try:
    RL.reset()
    r = c.post("/v1/jobs", json={"type": "render", "media_url": FAKE_MEDIA,
                                 "aspect": "21:9"})
    assert r.status_code in (200, 202), r.text
    J21 = r.json()["job_id"]
    d = c.get(f"/v1/jobs/{J21}").json()
    assert d["status"] == "done", d
    assert _calls[-1]["aspect"] == "21:9", _calls[-1]
    assert not _calls[-1]["vert"], "16:9-style job không gửi vertical"
    RL.reset()
    r = c.post("/v1/jobs", json={"type": "render", "media_url": FAKE_MEDIA,
                                 "burn_subtitles": True,
                                 "subtitle_key": "jobs/sub.srt"})
    assert r.status_code in (200, 202), r.text
    Jn = r.json()["job_id"]
    d = c.get(f"/v1/jobs/{Jn}").json()
    assert d["status"] == "done", d
    assert _calls[-1]["aspect"] is None, "không gửi aspect → None (legacy)"
finally:
    RND.run_render = real_run_render
print("10. worker truyền aspect xuống run_render ......... OK")

print("RENDER SUITE PASSED")
