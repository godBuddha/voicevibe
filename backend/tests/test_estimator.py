"""A5 guards — estimator (ước lượng thời lượng đọc + hiệu chuẩn EMA).

Run:  cd backend && PYTHONPATH=. python tests/test_estimator.py
"""
from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from app.pipelines.dub import GAP_TOLERANCE, SPEED_ACCEPT, SPEED_WARN_MAX, Segment, plan_timing  # noqa: E402
from app.pipelines.estimator import (  # noqa: E402
    PROFILES, StatisticalEstimator, estimate_duration)

# --- 1. profile vi có mặt; câu tiếng Việt ước lượng trong biên hợp lý
assert "vi" in PROFILES
dur, conf = estimate_duration("Xin chào các bạn, mình là Long.", "vi")
assert 1.0 <= dur <= 4.5 and conf == 0.85, (dur, conf)
print("1. profile vi + biên ước lượng .............. OK")

# --- 2. phạt dấu câu / số / viết tắt đều LÀM TĂNG thời lượng
plain, _ = estimate_duration("abc def ghi jkl mno pqr stu", "vi")
assert estimate_duration("abc, def, ghi, jkl, mno, pqr, stu", "vi")[0] > plain
assert estimate_duration("Quãng 12345 mét", "vi")[0] > estimate_duration(
    "Quãng mét mét mét mét mét mét mét", "vi")[0] * 0.5
assert estimate_duration("HĐND TP phát biểu", "vi")[0] > estimate_duration(
    "hđnd tp phát biểu", "vi")[0]
print("2. phạt dấu câu/số/viết tắt ................. OK")

# --- 3. ngôn ngữ lạ → heuristic; chuỗi rỗng → 0
h, hc = estimate_duration("hi", "xx")
assert h >= 0.2 and hc == 0.5
assert estimate_duration("", "vi")[0] == 0.0
print("3. heuristic + chuỗi rỗng ................... OK")

# --- 4. hiệu chuẩn EMA: học "đọc chậm" → nới; học lại "đọc nhanh" → thu
est = StatisticalEstimator()
assert est.factor("vi") == 1.0
est.calibrate("vi", 1.0, 2.0)  # target 2.0 → kẹp 1.5
assert est.factor("vi") == 1.0 * 0.7 + 1.5 * 0.3
d_up, _ = est.estimate("Xin chào các bạn, mình là Long.", "vi")
assert d_up > dur, "hiệu chuẩn chậm phải nới ước lượng"
f2 = est.calibrate("vi", 1.0, 0.4)  # target 0.4 → kẹp 0.5
assert f2 == est.factor("vi") == 1.15 * 0.7 + 0.5 * 0.3
d_down, _ = est.estimate("Xin chào các bạn, mình là Long.", "vi")
assert d_down < d_up
assert est.factor("en") == 1.0, "hiệu chuẩn vi không được nhiễm en"
assert est.calibrate("vi", 0, 5) == est.factor("vi")
assert est.calibrate("vi", 5, 0) == est.factor("vi")
print("4. hiệu chuẩn EMA sống, cô lập ngôn ngữ ..... OK")

# --- 5. plan_timing: cảnh báo theo ngưỡng (không đổi trần 1.35)
# budget của seg cuối = slot + overrun = 1.0 + 0.4 = 1.4s
segs = [Segment(idx=0, start=0.0, end=1.0, speaker="S", text="a",
                gen_duration=1.13)]  # 1.13/1.4 ≈ 0.81 → vừa, không cảnh báo
plan_timing(segs)
assert segs[0].warning is None and abs(segs[0].speed - 1.13 / 1.4) < 1e-6
segs2 = [Segment(idx=0, start=0.0, end=1.0, speaker="S", text="a",
                 gen_duration=1.70)]  # 1.70/1.4 ≈ 1.21 → vượt 1.15, dưới 1.30
plan_timing(segs2)
assert segs2[0].warning and "1.15" in segs2[0].warning, segs2[0].warning
segs3 = [Segment(idx=0, start=0.0, end=1.0, speaker="S", text="a",
                 gen_duration=2.0)]  # 2.0/1.4 ≈ 1.43 → chạm trần 1.35 + cờ
plan_timing(segs3)
assert segs3[0].needs_shorter_text and abs(segs3[0].speed - 1.35) < 1e-9
assert segs3[0].warning is not None and "1.3" in segs3[0].warning
print("5. cảnh báo tốc độ 1.15/1.30 ................ OK")

# --- 6. GAP_TOLERANCE hợp lý (dùng chung cho estimator pre-check)
assert 0.5 <= GAP_TOLERANCE <= 3.0
print("6. GAP_TOLERANCE hợp lý ..................... OK")

print("ESTIMATOR GUARDS PASSED")
