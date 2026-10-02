"""A2 guards — chọn điểm cắt tại điểm yên tĩnh (split_points).

Run:  cd backend && PYTHONPATH=. python tests/test_split_points.py
"""
from __future__ import annotations

import os
import pathlib
import subprocess
import sys
import tempfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from app.pipelines.split_points import (  # noqa: E402
    MIN_SEGMENT_DURATION, clip, ffprobe_duration, get_quietest_time_point,
    get_split_points)

sp = subprocess.run(["ffmpeg", "-version"], capture_output=True)
HAS_FFMPEG = sp.returncode == 0

if not HAS_FFMPEG:
    print("SKIP: không có ffmpeg")
else:
    with tempfile.TemporaryDirectory() as td:
        # 40s: 10s có tiếng — 6s IM TỊCH [10,16] — 24s có tiếng
        path = os.path.join(td, "a.wav")
        expr = ("if(lt(t,10), 0.8*sin(600*2*PI*t), "
                "if(lt(t,16), 0, 0.8*sin(600*2*PI*t)))")
        subprocess.run(["ffmpeg", "-y", "-f", "lavfi",
                        "-i", f"aevalsrc='{expr}':d=40:s=8000", path],
                       check=True, capture_output=True)
        assert abs(ffprobe_duration(path) - 40.0) < 0.5

        # điểm yên nhất quanh mốc 20s phải rơi vào quãng lặng
        p = get_quietest_time_point(path, 12.0, 28.0)
        assert 10.0 <= p <= 16.0, p
        print("1. điểm yên nhất trong quãng lặng ........... OK")

        # chia 40s tại mốc 20s → điểm cắt dời vào quãng lặng
        pts = get_split_points(path, 20, duration=40.0)
        assert pts == [pts[0] for _ in pts] or (len(pts) == 3), pts
        assert 12.0 <= pts[1] <= 16.0, pts
        # audio ngắn hơn mốc → 1 đoạn duy nhất
        assert get_split_points(path, 60, duration=40.0) == [0.0, 40.0]
        # đuôi ngắn < 10s bị gộp (duration 24, điểm nội dời ~15 → đuôi ~9s)
        assert get_split_points(path, 22.5, duration=24.0) == [0.0, 24.0]
        print("2. split points + gộp đuôi ngắn ............. OK")

        # guard: segment_duration quá nhỏ bị từ chối
        try:
            get_split_points(path, MIN_SEGMENT_DURATION - 1, duration=40.0)
            raise AssertionError("phải từ chối")
        except ValueError:
            pass
        try:
            get_quietest_time_point(path, -1.0, 5.0)
            raise AssertionError("phải từ chối")
        except ValueError:
            pass
        print("3. guard tham số ............................ OK")

        # clip: cắt đúng độ dài
        c = os.path.join(td, "c.wav")
        clip(path, 10.0, 16.0, c)
        assert abs(ffprobe_duration(c) - 6.0) < 0.5, ffprobe_duration(c)
        print("4. clip đúng độ dài ......................... OK")

    print("SPLIT POINTS GUARDS PASSED")
