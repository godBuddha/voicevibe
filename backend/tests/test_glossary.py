"""GD2 — Thuật ngữ bắt buộc (glossary) + khung phụ đề dễ đọc.

Vì sao có test riêng:
- Glossary là RÀNG BUỘC CỨNG chèn CUỐI system prompt: override Thư viện
  Prompt không được xoá nhầm danh sách — sai chỗ này user mất quyền kiểm soát
  tên riêng mà không hay biết.
- Vi phạm CHỈ CẢNH BÁO (không fail job): LLM không tôn trọng ràng buộc là
  chuyện đã kiểm chứng — assert cứng trên đầu ra LLM là job chết oan. Test
  neo đúng hợp đồng này: warnings vào `params["glossary_warnings"]`, job vẫn
  `done`.
- Sai format glossary phải chặn LÚC TẠO JOB (422 kèm số dòng), không để
  worker chết giữa đường sau khi user chờ STT xong.

Chạy:
    cd backend && PYTHONPATH=. python tests/test_glossary.py
"""
from __future__ import annotations

import os
import pathlib
import sys
import tempfile

WORK = pathlib.Path(tempfile.mkdtemp(prefix="vv_glossary_"))
os.environ["DATABASE_URL"] = f"sqlite:///{WORK}/glossary.db"
os.environ["MEDIA_ROOT"] = str(WORK / "media")
os.environ["VOICEVIBE_INLINE"] = "1"
os.environ.pop("VOICEVIBE_API_KEYS", None)
os.environ.pop("VOICEVIBE_ADMIN_KEY", None)

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient  # noqa: E402

from app import ratelimit as RL  # noqa: E402
from app.main import app  # noqa: E402
from app.pipelines import stt as STTMOD  # noqa: E402
from app.pipelines import translate as TRMOD  # noqa: E402
from app.pipelines.glossary import (  # noqa: E402
    check_translations, glossary_block, parse_glossary)
from app.pipelines.subtitle import Cue, enforce_limits  # noqa: E402
from app.settings_service import set_setting  # noqa: E402

c = TestClient(app)
RL.reset()
assert c.post("/v1/auth/setup",
              json={"email": "admin@local", "password": "matkhau123"}).status_code == 201

# --------------------------------------------- 1. parse + block + check (unit)
pairs = parse_glossary("# ghi chú\nOpenAI=OpenAI (công ty)\n\nGióng=Thánh Gióng\n")
assert pairs == [("OpenAI", "OpenAI (công ty)"), ("Gióng", "Thánh Gióng")], pairs
try:
    parse_glossary("dòng 1 đúng=a\nsai định dạng")
except ValueError as exc:
    assert "dòng 2" in str(exc), exc
else:
    raise AssertionError("sai format phải ValueError kèm số dòng")
block = glossary_block(pairs)
assert "BỘ THUẬT NGỮ BẮT BUỘC" in block and "Thánh Gióng" in block, block
warn = check_translations(["Nhờ OpenAI nhé."], ["Nhờ OpenAI (công ty)."], pairs)
assert warn == ["câu 1: vẫn giữ «OpenAI» trong bản dịch"], warn
# biên từ: "cat" KHÔNG khớp trong "category"
assert check_translations(["category"], ["category"], [("cat", "mèo")]) == []
# câu gốc không chứa thuật ngữ → không cảnh báo dù bản dịch chứa
assert check_translations(["chào"], ["chào OpenAI"], pairs) == []
print("1. parse/block/check_translations ................ OK")

# --------------------------------------------- 2. validate chặn lúc tạo job
from app import main as MAIN  # noqa: E402

real_dispatch = MAIN.dispatch
MAIN.dispatch = lambda *a, **k: ("inline", None)
try:
    RL.reset()
    r = c.post("/v1/jobs", json={"type": "subtitle", "source_url": "https://x.test/v",
                                 "glossary": "dòng thiếu dấu bằng"})
    assert r.status_code == 422 and "dòng 1" in r.text, (r.status_code, r.text)
    RL.reset()
    r = c.post("/v1/jobs", json={"type": "tts", "text": "x", "glossary": "a=b"})
    assert r.status_code == 422 and "translate, dub" in r.text, r.text
    RL.reset()
    r = c.post("/v1/jobs", json={"type": "subtitle", "source_url": "https://x.test/v",
                                 "glossary": "# ok\na=b"})
    assert r.status_code in (200, 202), r.text
finally:
    MAIN.dispatch = real_dispatch
    RL.reset()
print("2. validate glossary: 422 sai format / sai type .... OK")

# --------------------------------------------- 3. BatchTranslator: block cuối + warnings
from app.pipelines.translate_batch import BatchConfig, BatchTranslator  # noqa: E402


class FakeChat:
    """Trả bản dịch CỐ ĐỊNH — không đọc prompt. `system_seen` để khẳng định
    glossary block được nối vào system prompt."""

    def __init__(self, text: str) -> None:
        self.text = text
        self.system_seen = ""

    def complete(self, system, user, *, json_mode=False, max_tokens=2048, **kw):
        self.system_seen = system
        return f'{{"translations":[{{"index":1,"text":"{self.text}"}}]}}'


VIOLATING = "Xin chào các bạn"      # giữ từ gốc «Xin chào»
CLEAN = "Hello everyone"
GLOSS = "Xin chào=Hello"

chat = FakeChat(VIOLATING)
bt = BatchTranslator(chat, "vi", "en", config=BatchConfig(), glossary=GLOSS)
assert "BỘ THUẬT NGỮ BẮT BUỘC" in bt.system, "glossary phải nối vào system"
assert bt.system.endswith("KHÔNG giữ lại từ gốc trong bản dịch."), \
    "glossary phải là phần CUỐI (override không xoá được)"
out = bt.translate_all(["Xin chào các bạn"])
assert out == [VIOLATING], out
assert bt.warnings == ["câu 1: vẫn giữ «Xin chào» trong bản dịch"], bt.warnings

chat2 = FakeChat(CLEAN)
bt2 = BatchTranslator(chat2, "vi", "en", config=BatchConfig(), glossary=GLOSS)
out2 = bt2.translate_all(["Xin chào các bạn"])
assert out2 == [CLEAN] and bt2.warnings == [], (out2, bt2.warnings)

# không glossary → system nguyên vẹn, không warning
bt3 = BatchTranslator(FakeChat(CLEAN), "vi", "en", config=BatchConfig())
bt3.translate_all(["Xin chào các bạn"])
assert bt3.warnings == [] and "BỘ THUẬT NGỮ" not in bt3.system, bt3.system
# override Prompt Library + glossary: override thay base, glossary NỐI SAU CÙNG
bt4 = BatchTranslator(FakeChat(CLEAN), "vi", "en", config=BatchConfig(),
                      system_prompt="PROMPT CÁ NHÂN", glossary=GLOSS)
sys4 = bt4.system
assert sys4.startswith("PROMPT CÁ NHÂN") and "BỘ THUẬT NGỮ" in sys4, sys4
print("3. BatchTranslator: block cuối + warnings ......... OK")

# --------------------------------------------- 4. E2E translate text (inline)
class FakeTrSingle:
    def __init__(self) -> None:
        self.system_seen = ""
        self.called = 0

    def translate(self, text):
        self.called += 1
        return f"{text} OpenAI"   # cố tình giữ từ gốc → phải có cảnh báo

    def translate_batch(self, texts, source=None, target=None, system=None):
        self.system_seen = system or ""
        return [f"{t} OpenAI" for t in texts]


fake_tr = FakeTrSingle()
real_build_tr = TRMOD.build_translator


def _fake_build_tr(*args, **kw):
    # build_translator nhận system_prompt (override + glossary) → chụp lại
    fake_tr.system_seen = kw.get("system_prompt")
    return fake_tr


TRMOD.build_translator = _fake_build_tr
try:
    RL.reset()
    r = c.post("/v1/jobs", json={"type": "translate", "text": "Dùng OpenAI nhé",
                                 "source_lang": "vi", "target_lang": "en",
                                 "glossary": "OpenAI=OpenAI (công ty)"})
    assert r.status_code in (200, 202), r.text
    JID = r.json()["job_id"]
    d = c.get(f"/v1/jobs/{JID}").json()
    assert d["status"] == "done", d
    assert d["params"].get("glossary_warnings"), d["params"]
    assert "OpenAI" in d["params"]["glossary_warnings"][0], d["params"]
    # prompt đã nhận block thuật ngữ (nối sau prompt base/override)
    assert "BỘ THUẬT NGỮ BẮT BUỘC" in fake_tr.system_seen, fake_tr.system_seen
finally:
    TRMOD.build_translator = real_build_tr
    RL.reset()
print("4. E2E translate: warnings vào job.params ......... OK")

# --------------------------------------------- 5. E2E subtitle bilingual + glossary
from app import tasks as TK  # noqa: E402
from app.providers.base import TranscriptSegment  # noqa: E402

_SEGS = [TranscriptSegment(0.0, 1.5, "Xin chào các bạn", "SPEAKER_00"),
         TranscriptSegment(1.5, 3.0, "Hôm nay học lập trình", "SPEAKER_01")]


class FakeBatchChat:
    """Đối với glossary: câu 1 giữ từ gốc (vi phạm), câu 2 sạch."""

    def __init__(self) -> None:
        self.system_seen = ""

    def complete(self, system, user, *, json_mode=False, max_tokens=2048, **kw):
        self.system_seen = system
        return ('{"translations":[{"index":1,"text":"Xin chào everyone"},'
                '{"index":2,"text":"Today we learn programming"}]}')


fake_dl = TK._download_source
fake_transcribe = STTMOD.transcribe
fake_diarize = STTMOD.diarize
fake_bc = TRMOD.batch_capable
fake_bt2 = TRMOD.build_translator
TK._download_source = lambda job_id, params, storage: "/tmp/fake.mp4"
STTMOD.transcribe = lambda src, language=None, stats=None, want_words=False: (_SEGS, {})
STTMOD.diarize = lambda src: []
chat_batch = FakeBatchChat()
TRMOD.batch_capable = lambda tr: chat_batch
TRMOD.build_translator = lambda *a, **kw: type("T", (), {"translate": lambda s, t: t})()
try:
    RL.reset()
    r = c.post("/v1/jobs", json={
        "type": "subtitle", "source_url": "https://x.test/v", "format": "srt",
        "bilingual": True, "target_lang": "en",
        "glossary": "Xin chào=Hello"})
    assert r.status_code in (200, 202), r.text
    SJID = r.json()["job_id"]
    d = c.get(f"/v1/jobs/{SJID}").json()
    assert d["status"] == "done", d
    ws = d["params"].get("glossary_warnings")
    assert ws and ws[0] == "câu 1: vẫn giữ «Xin chào» trong bản dịch", d["params"]
    assert "BỘ THUẬT NGỮ BẮT BUỘC" in chat_batch.system_seen, chat_batch.system_seen
    assert "glossary_warnings" in (c.get(f"/v1/jobs/{SJID}").json()["params"]), ""
finally:
    TK._download_source = fake_dl
    STTMOD.transcribe = fake_transcribe
    STTMOD.diarize = fake_diarize
    TRMOD.batch_capable = fake_bc
    TRMOD.build_translator = fake_bt2
    RL.reset()
print("5. E2E subtitle: block + warnings đúng câu 1 ...... OK")

# --------------------------------------------- 6. khung phụ đề: cps/dòng qua job thật
set_setting("subtitle.max_line_chars", 20)
set_setting("subtitle.max_cps", 21)
# KHÔNG để STT thật chạy trong job (nạp large-v3 ~4 phút rồi chết decode file
# giả — bẫy worker image đã ghi nhớ): fake STT/diarize cho cả section này.
TK._download_source = lambda job_id, params, storage: "/tmp/fake.mp4"
STTMOD.transcribe = lambda src, language=None, stats=None, want_words=False: (_SEGS, {})
STTMOD.diarize = lambda src: []
try:
    RL.reset()
    r = c.post("/v1/jobs", json={"type": "subtitle", "source_url": "https://x.test/v",
                                 "format": "srt"})
    assert r.status_code in (200, 202), r.text
    FJID = r.json()["job_id"]
    d = c.get(f"/v1/jobs/{FJID}").json()
    assert d["status"] == "done", d
    fit = d["params"].get("subtitle_fit_warnings")
    assert not fit, fit  # 2 cue ngắn đều đủ giờ → không cảnh báo (key không ghi)
finally:
    TK._download_source = fake_dl
    STTMOD.transcribe = fake_transcribe
    STTMOD.diarize = fake_diarize
    set_setting("subtitle.max_line_chars", 0)   # 0 = tắt
    set_setting("subtitle.max_cps", 0)
    RL.reset()
print("6. khung phụ đề đọc từ Settings, 0 = tắt .......... OK")

# --------------------------------------------- 7. enforce_limits: tách + mượn giờ
warns: list[str] = []
fast = enforce_limits([Cue(0.0, 2.0, ["a " * 50]), Cue(30.0, 31.0, ["x"])],
                      max_line_chars=42, max_cps=21, warnings=warns)
assert len(fast) == 3, fast
for cue in fast[:2]:
    chars = sum(len(ln) for ln in cue.lines)
    assert chars / (cue.end - cue.start) <= 21 + 1e-6, (chars, cue)
assert warns == [], warns
dense = enforce_limits([Cue(0.0, 2.0, ["a " * 50]), Cue(2.0, 3.0, ["x"])],
                       max_line_chars=42, max_cps=21)
assert dense[0].end <= 2.0, "không được đè lên cue kế"
print("7. enforce_limits: mượn giờ + tách + chặn biên .... OK")

print("GLOSSARY SUITE PASSED")
