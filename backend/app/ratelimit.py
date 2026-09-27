"""Rate limiting — sliding window trong bộ nhớ (một tiến trình).

⚠️ GIỚI HẠN ĐÃ BIẾT: cửa sổ lưu trong dict của tiến trình, nên (a) không chia sẻ
giữa nhiều uvicorn worker / nhiều replica, (b) reset khi restart. Với self-host một
tiến trình thì đủ dùng — đủ để chặn dò mật khẩu và spam job. Bản nhiều tiến trình cần
Redis (đã nằm trong roadmap, xem README).

Tách khỏi main.py để cả main.py (job + signup) lẫn auth.py (login/setup) dùng chung
một nguồn, thay vì mỗi nơi giữ một dict riêng.
"""
from __future__ import annotations

import time

# ident -> danh sách timestamp (giây) của các lần gọi gần đây.
_RATE: dict[str, list[float]] = {}

_PRUNE_EVERY = 512  # số lần gọi giữa hai lần dọn rác
_calls_since_prune = 0


def _prune(now: float, max_window: float) -> None:
    """Bỏ các ident đã hết hạn — nếu không, dict phình mãi theo số IP/key từng thấy."""
    global _calls_since_prune
    _calls_since_prune += 1
    if _calls_since_prune < _PRUNE_EVERY:
        return
    _calls_since_prune = 0
    for ident in list(_RATE):
        fresh = [t for t in _RATE[ident] if now - t < max_window]
        if fresh:
            _RATE[ident] = fresh
        else:
            del _RATE[ident]


def check_rate(ident: str, limit: int, window: float = 60.0) -> bool:
    """True nếu còn trong hạn mức; False nếu đã vượt (caller trả 429).

    Ghi nhận lần gọi hiện tại khi và chỉ khi nó được phép — để không "tự khoá"
    người dùng đang trong hạn mức.
    """
    now = time.time()
    _prune(now, max(window, 60.0))
    lst = [t for t in _RATE.get(ident, []) if now - t < window]
    if len(lst) >= limit:
        _RATE[ident] = lst
        return False
    lst.append(now)
    _RATE[ident] = lst
    return True


def reset() -> None:
    """Xoá sạch trạng thái — dùng cho test."""
    _RATE.clear()