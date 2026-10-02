"""A5 — Ước lượng thời lượng đọc (estimator) để PHÂN ĐOẠN TRƯỚC khi gọi TTS.

Vấn đề: hiện pipeline chỉ phát hiện đoạn "không vừa thời lượng" SAU khi đã tổng
hợp audio (đo file wav). Nghĩa là mỗi đoạn vượt thời lượng tốn 2 lần TTS — lần
đầu đọc xong rồi vứt, xin bản ngắn hơn rồi đọc lại. Với model TTS local mỗi lần
đọc là một lượt GPU; với 50 đoạn dài là 50 lượt lãng phí.

Giải pháp (port từ KrillinAI `dubbing/estimator.go`, Apache-2.0): ước lượng
thời lượng đọc theo ngôn ngữ TRƯỚC khi gọi TTS — ký tự/giây của từng ngôn ngữ +
phạt dấu câu (nghỉ hơi) + phạt chữ số (đọc dài) + phạt từ viết tắt (đọc từng
chữ). Đoạn nào ước lượng vượt ngân sách thì XIN BẢN NGẮN HƠN TRƯỚC, chỉ đọc MỘT
lần.

Bảng profile giữ nguyên từ bản gốc, BỔ SUNG `vi` (bản gốc không có — tiếng Việt
rơi vào heuristic tổng quát): tiếng Việt nói ~4.2 âm tiết/giây, trung bình mỗi
âm tiết ~3.8 ký tự (kể cả khoảng trắng) → ~16 ký tự/giây. Confidence 0.85 vì
chưa đo thực địa rộng — và đó là lý do có **hiệu chuẩn (calibration)**: sau mỗi
lần TTS đo được thời lượng THẬT, hệ số hiệu chỉnh ngôn ngữ được cập nhật theo
EMA — các đoạn sau trong cùng job ước lượng càng lúc càng sát. (Bản gốc Go có
viết `Calibrate` nhưng KHÔNG BAO GIỜ gọi — chết code; ở đây bật sống.)

Chạy thử: PYTHONPATH=. python -m app.pipelines.estimator --selftest
"""
from __future__ import annotations

import argparse

# ngôn ngữ -> (ký_tự/giây, confidence, phạt_dấu_phẩy, phạt_chữ_số, phạt_viết_tắt)
# 3 hệ số sau là TRỌNG SỐ nhân với mức phạt gốc: dấu phẩy 0.22s, chấm 0.28s,
# ba chấm 0.34s, mỗi chữ số 0.12s, mỗi chữ trong từ viết tắt 0.18s.
PROFILES: dict[str, tuple[float, float, float, float, float]] = {
    "vi": (16.0, 0.85, 0.24, 0.24, 0.20),
    "zh-CN": (4.2, 0.95, 0.30, 0.22, 0.12),
    "zh-TW": (4.1, 0.95, 0.30, 0.22, 0.12),
    "ja": (4.0, 0.94, 0.28, 0.20, 0.12),
    "ko": (4.3, 0.93, 0.28, 0.20, 0.12),
    "en": (13.5, 0.92, 0.24, 0.26, 0.32),
    "de": (11.8, 0.91, 0.24, 0.25, 0.28),
    "ru": (10.8, 0.90, 0.24, 0.24, 0.24),
    "tr": (12.0, 0.91, 0.24, 0.24, 0.26),
}

# mức phạt gốc (giây) — giữ nguyên từ bản gốc
PAUSE_SOFT = 0.22    # , 、 ; ； : ：
PAUSE_HARD = 0.28    # . 。 ! ！ ? ？
PAUSE_LONG = 0.34    # … — ～
NUMBER_PENALTY = 0.12
ACRONYM_PENALTY = 0.18

# heuristic tổng quát cho ngôn ngữ không có profile
HEURISTIC_PAUSE, HEURISTIC_NUMBER, HEURISTIC_ACRONYM = 0.18, 0.10, 0.10
HEURISTIC_RUNES_PER_SEC = 8.5

_PAUSE_SOFT = set(",、;；:：，")
_PAUSE_HARD = set(".。!!??！？")
_PAUSE_LONG = set("…—～")


def estimate_duration(text: str, language: str,
                      calibration: float = 1.0) -> tuple[float, float]:
    """(giây ước lượng, độ tin cậy 0..1). Giữ hàm thuần để test không cần class."""
    profile = PROFILES.get((language or "").strip().lower())
    if profile is None:
        return _heuristic(text, calibration)
    rps, confidence, w_pause, w_number, w_acronym = profile
    runes = [c for c in text if not c.isspace()]
    base = len(runes) / rps
    base += _punctuation_pause(text, w_pause)
    base += _number_penalty(text, w_number)
    base += _acronym_penalty(text, w_acronym)
    duration = base * calibration
    return (max(0.0, duration), confidence)


def _punctuation_pause(text: str, w_pause: float) -> float:
    total = 0.0
    for c in text:
        if c in _PAUSE_SOFT:
            total += PAUSE_SOFT * w_pause
        elif c in _PAUSE_HARD:
            total += PAUSE_HARD * w_pause
        elif c in _PAUSE_LONG:
            total += PAUSE_LONG * w_pause
    return total


def _number_penalty(text: str, w_number: float) -> float:
    return sum(1 for c in text if c.isdigit()) * NUMBER_PENALTY * w_number


def _acronym_penalty(text: str, w_acronym: float) -> float:
    """Từ viết tắt = chạy chữ HOA liền ≥2 ký tự (UN, AI, GPT...). Đọc từng chữ
    nên dài hơn viết. Chạy ở cuối chuỗi cũng tính ("...NASA")."""
    total, run = 0.0, 0
    for c in text + " ":  # chốt chuỗi để run cuối được tính
        if c.isalpha() and c.isupper():
            run += 1
        else:
            if run >= 2:
                total += run * ACRONYM_PENALTY * w_acronym
            run = 0
    return total


def _heuristic(text: str, calibration: float) -> tuple[float, float]:
    runes = [c for c in text if not c.isspace()]
    duration = (len(runes) / HEURISTIC_RUNES_PER_SEC
                + 0.12 * len(text.split())
                + 0.08 * sum(1 for c in text if c.isdigit())
                + 0.01 * sum(1 for c in text if c.isalpha())
                + _punctuation_pause(text, HEURISTIC_PAUSE)
                + _number_penalty(text, HEURISTIC_NUMBER)
                + _acronym_penalty(text, HEURISTIC_ACRONYM))
    if duration < 0.2:
        duration = 0.2
    return (duration * calibration, 0.5)


class StatisticalEstimator:
    """Estimator có HIỆU CHUẨN SỐNG: đo thật → chỉnh hệ số ngôn ngữ theo EMA.

    Một instance dùng cho MỘT job (không chia sẻ giữa các job — mỗi job một
    văn phong, hiệu chuẩn của job này không nhất thiết đúng cho job khác).
    """

    def __init__(self) -> None:
        self._calibration: dict[str, float] = {}

    def factor(self, language: str) -> float:
        return self._calibration.get((language or "").strip().lower(), 1.0)

    def estimate(self, text: str, language: str) -> tuple[float, float]:
        return estimate_duration(text, language, self.factor(language))

    def calibrate(self, language: str, estimated: float, actual: float) -> float:
        """Học từ chênh lệch ước-tính vs THỰC-TE (EMA 0.7/0.3, kẹp [0.5, 1.5]).

        actual = thời lượng audio TTS đo được; estimated = số đã dùng để quyết
        định. Lệch >0 nghĩa là "model đọc chậm hơn tưởng" → hệ số tăng. Trả về
        hệ số mới để caller ghi log; dữ liệu lỗi (<=0) bỏ qua im lặng.
        """
        lang = (language or "").strip().lower()
        if not lang or estimated <= 0 or actual <= 0:
            return self._calibration.get(lang, 1.0)
        target = max(0.5, min(1.5, actual / estimated))
        current = self._calibration.get(lang, 1.0)
        new = current * 0.7 + target * 0.3
        self._calibration[lang] = new
        return new


def _selftest() -> None:
    # --- tiếng Việt: câu tiêu biểu ~40 ký tự hiệu dụng ≈ 2.5-3.5s
    dur, conf = estimate_duration("Xin chào các bạn, mình là Long.", "vi")
    assert 1.0 <= dur <= 4.5, dur
    assert conf == 0.85, conf

    # --- bản gốc Go: tiếng Anh nhanh hơn tiếng Trung nhiều
    en, _ = estimate_duration("Hello everyone, I am Long.", "en")
    zh, _ = estimate_duration("大家好，我是龙。", "zh-CN")
    assert en < zh * 2, (en, zh)

    # --- dấu câu làm chậm; câu nhiều dấu phẩy dài hơn câu trơn cùng độ dài
    plain, _ = estimate_duration("abc def ghi jkl mno pqr stu", "vi")
    dotted, _ = estimate_duration("abc, def, ghi, jkl, mno, pqr, stu", "vi")
    assert dotted > plain

    # --- chữ số đọc dài: "đường 128" chậm hơn "đường trăm hai mươi tám" ký tự ít
    with_num, _ = estimate_duration("Quãng 12345 mét", "vi")
    without, _ = estimate_duration("Quãng mét mét mét mét mét mét mét", "vi")
    assert with_num > without * 0.5

    # --- từ viết tắt bị phạt
    with_acr, _ = estimate_duration("HĐND TP phát biểu", "vi")
    assert with_acr > estimate_duration("hđnd tp phát biểu", "vi")[0]

    # --- ngôn ngữ lạ -> heuristic, min 0.2s
    h, hconf = estimate_duration("hi", "xx")
    assert h >= 0.2 and hconf == 0.5
    assert estimate_duration("", "vi")[0] == 0.0

    # --- hiệu chuẩn EMA: đo thật gấp đôi ước lượng -> hệ số tăng về ~1.2
    est = StatisticalEstimator()
    assert est.factor("vi") == 1.0
    est.calibrate("vi", estimated=1.0, actual=2.0)   # target = 2.0 -> kẹp 1.5
    assert est.factor("vi") == 1.0 * 0.7 + 1.5 * 0.3
    d_up, _ = est.estimate("Xin chào các bạn, mình là Long.", "vi")
    assert d_up > dur, (d_up, dur)  # "đọc chậm hơn tưởng" -> ước lượng nới ra
    f2 = est.calibrate("vi", estimated=1.0, actual=0.4)  # target = 0.4 -> kẹp 0.5
    assert f2 == est.factor("vi") == 1.15 * 0.7 + 0.5 * 0.3
    d_down, _ = est.estimate("Xin chào các bạn, mình là Long.", "vi")
    assert d_down < d_up, (d_down, d_up)  # học lại "đọc nhanh" -> ước lượng thu vào
    assert est.factor("en") == 1.0, "ngôn ngữ khác không bị nhiễm"
    # dữ liệu lỗi bỏ qua
    assert est.calibrate("vi", 0, 5) == est.factor("vi")
    assert est.calibrate("vi", 5, 0) == est.factor("vi")

    print("profile vi + bảng gốc ........... OK")
    print("phạt dấu câu / số / viết tắt ... OK")
    print("heuristic ngôn ngữ lạ .......... OK")
    print("hiệu chuẩn EMA sống, cô lập ... OK")
    print("ESTIMATOR SELFTEST PASSED")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        _selftest()
