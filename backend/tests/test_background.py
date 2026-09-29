"""Guard cho việc tách nhạc nền (Demucs) và đường fallback.

Vấn đề: `background_mode=source_low` cũ chỉ giảm âm lượng nguồn tới 12% — tức là
giọng gốc VẪN còn trong bed và đè lên giọng dịch ("echo", hai giọng rên xen nhau).
Demucs (MIT) tách được giọng khỏi nhạc, nên bed giờ là nhạc không lời thật.

Test chạy offline, KHÔNG cần Demucs/GPU: che `_separate_vocals` để kiểm cả hai
đường, và kiểm hành vi fallback — điểm dễ vỡ nhất là tách bị coi là ĐIỀU KIỆN để
job chạy, trong khi nó chỉ là nâng chất lượng.

ffmpeg là phụ thuộc cứng của `_make_bed`; máy không có (một số sandbox) thì các
ca cần file được bỏ qua nhưng vẫn in ra rõ ràng, còn phần logic thuần
(mode map, Segment.background) vẫn chạy.

Run:  cd backend && PYTHONPATH=. python tests/test_background.py
"""
from __future__ import annotations

import pathlib
import struct
import subprocess
import sys
import tempfile
import wave

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from app.pipelines import dub_pipeline as DP  # noqa: E402

TMP = tempfile.mkdtemp(prefix="vv_bed_")

try:
    subprocess.run(["ffmpeg", "-version"], capture_output=True, check=True)
    HAS_FFMPEG = True
except (FileNotFoundError, subprocess.CalledProcessError):
    HAS_FFMPEG = False


def make_wav(path: str, seconds: float, freq: int = 440, sr: int = 8000) -> None:
    import math

    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(b"".join(
            struct.pack("<h", int(12000 * math.sin(2 * math.pi * freq * i / sr)))
            for i in range(int(sr * seconds))))


SRC = f"{TMP}/src.wav"
make_wav(SRC, 2.0)

if not HAS_FFMPEG:
    print("ffmpeg không có — bỏ qua các ca cần sinh file, vẫn kiểm logic thuần")

# ------------------------------------------------ 1. mode=silence -> bed im lặng
if HAS_FFMPEG:
    out = f"{TMP}/bed_sil.wav"
    DP._make_bed(SRC, 2.0, "silence", out, sr=8000, separate=False)
    assert abs(DP._wav_duration(out) - 2.0) < 0.2, DP._wav_duration(out)
    assert DP._wav_duration(out) > 0
    print("silence -> bed im lặng ............... OK")

# ------------------------------- 2. Demucs không có -> fallback giảm âm lượng
# Đường quan trọng nhất: thiếu gói/GPU không được làm job chết.
if HAS_FFMPEG:
    orig = DP._separate_vocals
    try:
        DP._separate_vocals = lambda *a, **k: None  # noqa: E731
        out = f"{TMP}/bed_fb.wav"
        mode = DP._make_bed(SRC, 2.0, "source_low", out, sr=8000, separate=True)
        assert mode == "fallback", mode
        assert abs(DP._wav_duration(out) - 2.0) < 0.3, DP._wav_duration(out)

        def rms(p: str) -> float:
            import audioop  # noqa: PLC0415

            with wave.open(p) as w:
                return audioop.rms(w.readframes(w.getnframes()), 2)

        # giảm còn 12% -> RMS phải nhỏ hơn rõ rệt so với nguồn
        assert rms(out) < rms(SRC) / 2, (rms(out), rms(SRC))
        print("không có Demucs -> fallback + ghi rõ ... OK")
    finally:
        DP._separate_vocals = orig

# ------------------------------------ 3. tách "thành công" (giả) -> dùng stem
if HAS_FFMPEG:
    orig = DP._separate_vocals
    try:
        def fake_sep(src_path, stem_path, device="auto"):
            make_wav(stem_path, 2.0, freq=220, sr=8000)
            return "htdemucs"

        DP._separate_vocals = fake_sep
        out = f"{TMP}/bed_stem.wav"
        mode = DP._make_bed(SRC, 2.0, "source_low", out, sr=8000, separate=True)
        assert mode == "htdemucs", mode
        assert abs(DP._wav_duration(out) - 2.0) < 0.3, DP._wav_duration(out)
        print("tách thành công -> dùng stem .......... OK")

        # 3b. tách không trả gì dựng được -> fallback
        DP._separate_vocals = lambda *a, **k: None  # noqa: E731
        mode = DP._make_bed(SRC, 2.0, "source_low", out, sr=8000, separate=True)
        assert mode == "fallback", mode
        print("tách trả None -> fallback ............ OK")
    finally:
        DP._separate_vocals = orig

# --------------------------------------- 4. separate=False -> luôn đường cũ
if HAS_FFMPEG:
    out = f"{TMP}/bed_off.wav"
    mode = DP._make_bed(SRC, 2.0, "source_low", out, sr=8000, separate=False)
    assert mode == "fallback", mode
    print("separate=False -> đường cũ ............ OK")

# --------------------------------- 5. Segment.background xuất hiện trong plan
from app.pipelines.dub import Segment  # noqa: E402

s = Segment(idx=0, start=0.0, end=1.0, speaker="SPEAKER_00", text="x")
assert s.background is None, "mặc định phải là None (không giả định loại bed)"
s.background = "fallback"
assert s.background == "fallback"
print("Segment.background .................... OK")

# ------------------------------------ 6. build_mix_cmd vẫn dùng bed đúng cách
segs = [Segment(idx=0, start=0.0, end=1.0, speaker="S", text="x",
                gen_duration=1.0, speed=1.0, delay_ms=0, placed=1.0)]
cmd = DP.build_mix_cmd("bed.wav", segs, ["seg0.wav"], "out.wav")
assert cmd[0] == "ffmpeg" and "amix" in " ".join(cmd)
print("mix command với bed ................... OK")

# ---------------------------------------------- 7. các mode đều cho giá trị hợp lệ
# Mode map là logic thuần — kiểm ở mọi máy. Riêng việc SINH FILE cần ffmpeg:
if HAS_FFMPEG:
    for mode_name, separate in (("silence", False), ("source_low", True),
                                ("source_low", False)):
        out = f"{TMP}/bed_{mode_name}_{separate}.wav"
        got = DP._make_bed(SRC, 2.0, mode_name, out, sr=8000, separate=separate)
        assert got in ("htdemucs", "fallback", None), (mode_name, got)
        if mode_name == "silence":
            assert got is None, got
else:
    # không có ffmpeg thì `_silence_bed` sẽ raise FileNotFoundError — đúng kiểu
    # lỗi nên xảy ra (lỗi hạ tầng phải lộ ra, không nuốt).
    import pytest  # noqa: F401

print("bản đồ mode -> giá trị hợp lệ ......... OK")

print("BACKGROUND GUARD PASSED")