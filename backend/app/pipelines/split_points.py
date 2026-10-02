"""A2 — Chọn điểm cắt audio tại chỗ YÊN TĨNH nhất quanh mốc chia.

Vấn đề: cắt audio dài thành đoạn để nhận diện song song/checkpoint thì điểm cắt
trời định (5 phút một nhát) hay rơi NGANG CÂU — Whisper nhận đoạn nửa câu thì
nền giờ hỏng câu đó, và khi ghép lại phụ đề bị lệch.

Giải pháp (port từ KrillinAI `internal/service/split_audio.go`, Apache-2.0):
mốc chia 5 phút chỉ là TÂM ĐIỂM TÌM KIẾM — thật sự cắt tại chỗ năng lượng thấp
nhất trong ±8 giây quanh mốc. Cách làm: ffmpeg xuất PCM 3kHz lọc chỉ giữ dải
giọng nói (300–3000Hz) → cửa sổ trượt 1.5 giây cộng dồn năng lượng → lấy cửa sổ
yên nhất. Giống như cắt đoạn phim: đừng cắt giữa lời thoại, hãy cắt ở cảnh
không ai nói.

Hằng số giữ nguyên từ bản gốc (đã được kiểm chứng qua thực chiến):
  SAMPLE_RATE=3000 — 3kHz đủ nghe ra "im hay ồn", tiết kiệm 53× so 44.1kHz
  ENERGY_WINDOW_DURATION=1.5 — cửa sổ 1.5s, đủ phủ một quãng lặng ngắn
  TOLERANCE_DURATION=8 — tìm trong ±8s quanh mốc
  MIN_DURATION=10 — đoạn cuối ngắn hơn 10s thì gộp vào đoạn trước
  MIN_SEGMENT_DURATION=20 — đoạn ngắn hơn 20s không đáng chia (8+8=16 < 20 bảo
  đảm hai mốc kế tiếp không bao giờ tràn vào nhau)

Tự chạy thử (chỉ cần ffmpeg, không cần model):
  PYTHONPATH=. python -m app.pipelines.split_points --selftest
"""
from __future__ import annotations

import argparse
import math
import subprocess
from array import array
from collections import deque

SAMPLE_RATE = 3000
ENERGY_WINDOW_DURATION = 1.5
TOLERANCE_DURATION = 8
MIN_DURATION = 10
MIN_SEGMENT_DURATION = 20

_WINDOW = int(SAMPLE_RATE * ENERGY_WINDOW_DURATION)  # 4500 mẫu = 1.5s
_HALF = _WINDOW // 2


def ffprobe_duration(path: str) -> float:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", path],
        capture_output=True, text=True, check=True)
    return float(out.stdout.strip())


def get_quietest_time_point(input_path: str, start: float, end: float) -> float:
    """Thời điểm YÊN nhất trong khoảng [start, end].

    ffmpeg xuất PCM s16le mono 3kHz (lọc 300–3000Hz — dải giọng nói, nhạc bass
    và rít ngoài dải không làm nhiễu phép đo) → mỗi mẫu một năng lượng bình
    phương → cửa sổ trượt 1.5s cộng dồn → cửa sổ có tổng năng lượng nhỏ nhất,
    trả về TÂM cửa sổ (không phải mép — cắt ở giữa quãng lặng an toàn hơn cắt
    sát mép). Hòa điểm (nhiều cửa sổ yên như nhau) thì chọn cửa sổ SAU — bản
    gốc Go dùng `<=`, giữ nguyên để hai hệ ra cùng quyết định.
    """
    if start < 0 or end <= start:
        raise ValueError(f"khoảng tìm kiếm vô lý: [{start}, {end}]")
    cmd = ["ffmpeg", "-y", "-ss", f"{start:.3f}", "-to", f"{end:.3f}",
           "-i", input_path, "-f", "s16le", "-ar", str(SAMPLE_RATE), "-ac", "1",
           "-af", "lowpass=f=3000,highpass=f=300", "pipe:1"]
    out = subprocess.run(cmd, capture_output=True)
    if out.returncode != 0:
        raise RuntimeError(f"ffmpeg trích PCM lỗi: {out.stderr[-300:].decode('utf-8', 'replace')}")

    samples = array("h")
    samples.frombytes(out.stdout)
    window: deque = deque(maxlen=_WINDOW)
    energy = 0.0
    min_energy = float("inf")
    min_index = 0
    filled = False
    for index, s in enumerate(samples):
        e = float(s) * float(s)
        if len(window) == _WINDOW:
            energy -= window[0]
            filled = True
        window.append(e)
        energy += e
        if filled and energy <= min_energy:
            min_energy = energy
            min_index = index - _HALF  # tâm cửa sổ, không phải mép
    if not filled:
        return start  # khoảng ngắn hơn 1.5s — không đủ dữ liệu, trả mép trái
    return start + min_index / SAMPLE_RATE


def get_split_points(input_path: str, segment_duration: float,
                     duration: float | None = None) -> list[float]:
    """Danh sách mốc chia [0, p1, …, pN-1, duration] — điểm cắt YÊN TĨNH NHẤT.

    `segment_duration` là TÂM TÌM KIẾM (mốc chia trời định), không phải điểm cắt
    cứng: mỗi mốc nội (không phải đầu/cuối) được dời về chỗ yên nhất ±8s. Cuối
    cùng: đoạn đuôi ngắn hơn MIN_DURATION gộp vào đoạn trước (mốc nội kế chót bị
    bỏ) — một đoạn 3s chẳng đáng một lượt nhận diện riêng.
    """
    segment_duration = float(segment_duration)
    if segment_duration < MIN_SEGMENT_DURATION:
        raise ValueError(f"segment_duration phải >= {MIN_SEGMENT_DURATION}s, "
                         f"nhận {segment_duration}")
    if duration is None:
        duration = ffprobe_duration(input_path)

    n = max(1, math.ceil(duration / segment_duration))
    points = [float(i * segment_duration) for i in range(n)]
    for i in range(1, n):
        points[i] = get_quietest_time_point(
            input_path, i * segment_duration - TOLERANCE_DURATION,
            i * segment_duration + TOLERANCE_DURATION)
    points.append(0.0)  # placeholder cho mốc cuối
    if n > 1 and duration - points[n - 1] < MIN_DURATION:
        points = points[:n]  # gộp đoạn đuôi ngắn vào đoạn trước
    points[-1] = duration
    return points


def clip(input_path: str, start: float, end: float, output_path: str) -> None:
    """Cắt [start, end] ra file riêng — dùng để tách đoạn cho STT từng phần."""
    subprocess.run(["ffmpeg", "-y", "-ss", f"{start:.3f}", "-to", f"{end:.3f}",
                    "-i", input_path, output_path],
                   check=True, capture_output=True)


def _selftest() -> None:
    import os
    import tempfile

    with tempfile.TemporaryDirectory() as td:
        # Audio 40s: 10s có tiếng (sóng 0.8) — 6s IM TỊCH — 24s có tiếng.
        # Biểu thức phải bọc NHÁY ĐƠN: dấu phẩy trong expr trùng ký tự phân cách
        # tùy chọn của bộ lọc (đã gặp thật — không nháy là ffmpeg trả exit 234).
        path = os.path.join(td, "a.wav")
        expr = ("if(lt(t,10), 0.8*sin(600*2*PI*t), "
                "if(lt(t,16), 0, 0.8*sin(600*2*PI*t)))")
        subprocess.run(["ffmpeg", "-y", "-f", "lavfi",
                        "-i", f"aevalsrc='{expr}':d=40:s=8000", path],
                       check=True, capture_output=True)
        assert abs(ffprobe_duration(path) - 40.0) < 0.5, ffprobe_duration(path)

        # Điểm yên nhất quanh 15s (tìm 7..23) phải nằm trong quãng lặng [10, 16]
        p = get_quietest_time_point(path, 7.0, 23.0)
        assert 10.0 <= p <= 16.0, f"điểm yên nhất lệch khỏi quãng lặng: {p}"

        # Chia 40s thành 2 đoạn (mốc 20s, tìm 12..28 — guard >= 20s): điểm cắt
        # phải rơi vào phần quãng lặng nằm trong khoảng tìm kiếm [12, 16]
        pts = get_split_points(path, 20, duration=40.0)
        assert len(pts) == 3 and pts[0] == 0.0 and pts[-1] == 40.0, pts
        assert 12.0 <= pts[1] <= 16.0, pts

        # audio ngắn hơn segment_duration -> 1 đoạn duy nhất [0, duration]
        assert get_split_points(path, 60, duration=40.0) == [0.0, 40.0]

        # đoạn đuôi < 10s bị gộp: điểm nội dời về chỗ yên (~15s, quãng lặng ∩
        # khoảng tìm kiếm), duration=24 -> đuôi 24-15≈9s < 10 -> mốc nội bị gỡ,
        # chỉ còn 1 đoạn [0, 24]
        assert get_split_points(path, 22.5, duration=24.0) == [0.0, 24.0]

        # segment_duration < 20 -> từ chối rõ ràng
        try:
            get_split_points(path, 19, duration=30.0)
            raise AssertionError("phải từ chối segment_duration < 20")
        except ValueError:
            pass

        # khoảng tìm kiếm vô lý -> ValueError
        for bad in ((-1.0, 5.0), (5.0, 5.0)):
            try:
                get_quietest_time_point(path, *bad)
                raise AssertionError(f"phải từ chối {bad}")
            except ValueError:
                pass

        # clip: cắt đúng độ dài
        c = os.path.join(td, "c.wav")
        clip(path, 10.0, 16.0, c)
        assert abs(ffprobe_duration(c) - 6.0) < 0.5, ffprobe_duration(c)

    print("điểm yên nhất trong quãng lặng . OK")
    print("split points + gộp đoạn đuôi ... OK")
    print("guard segment_duration >= 20 ... OK")
    print("clip đúng độ dài ............... OK")
    print("SPLIT_POINTS SELFTEST PASSED")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        _selftest()
