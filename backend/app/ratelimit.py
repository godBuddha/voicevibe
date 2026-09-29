"""Rate limiting — cửa sổ trượt, dùng Redis khi có, in-memory khi không.

Vì sao cần Redis: cửa sổ in-memory nằm trong dict của TIẾN TRÌNH, nên khi chạy
nhiều uvicorn worker (`--workers 4`) hoặc nhiều replica, mỗi tiến trình giữ một
bộ đếm riêng — hạn mức thực tế bị nhân lên theo số tiến trình, và mất sạch khi
restart. Với giới hạn chống dò mật khẩu (`login:ip` 10/phút) thì đó là lỗ hổng
thật, không phải chuyện hiệu năng.

Cách chọn backend: có `REDIS_URL` **và** kết nối được -> Redis. Còn lại -> in-memory.
Redis chết giữa chừng cũng rơi về in-memory chứ không làm request gãy: thà mất
tính chia sẻ còn hơn chặn hết người dùng thật (đánh đổi có ý thức — xem `_redis_check`).

Vì sao dùng Lua: `ZREMRANGEBYSCORE` + `ZCARD` + `ZADD` phải là MỘT thao tác
nguyên tử. Nếu tách ra, hai request đồng thời cùng đọc thấy `count = limit - 1`
rồi cùng thêm -> vượt hạn mức. Đúng loại lỗi mà rate limiter sinh ra để chặn.

Tách khỏi main.py để cả main.py (job + signup) lẫn auth.py (login/setup) dùng chung
một nguồn, thay vì mỗi nơi giữ một dict riêng.
"""
from __future__ import annotations

import logging
import os
import threading
import time
import uuid

log = logging.getLogger("voicevibe.ratelimit")

# ident -> danh sách timestamp (giây). Dùng khi KHÔNG có Redis.
_RATE: dict[str, list[float]] = {}

# Khoá cho đường in-memory. Không thừa: FastAPI chạy endpoint `def` (đồng bộ)
# trong threadpool, nên NHIỀU LUỒNG thật sự gọi vào đây cùng lúc. Đường in-memory
# là đọc-sửa-ghi (`_RATE.get` -> lọc -> append -> gán lại), nên hai luồng có thể
# cùng đọc thấy `count = limit - 1` rồi cùng cho qua: luồng sau ghi đè danh sách
# của luồng trước, và số lần đã ghi bị hụt. Kết quả là vượt hạn mức.
# Chạy 200 luồng thì bản không khoá *thường* vẫn ra đúng nhờ GIL, nhưng đó là
# may mắn về thời điểm chứ không phải bảo đảm — nên khoá cho chắc.
_mem_lock = threading.Lock()

_PRUNE_EVERY = 512  # số lần gọi giữa hai lần dọn rác
_calls_since_prune = 0

# Client Redis dựng muộn, chỉ một lần. None = chưa thử; _redis_broken = đã thử, hỏng.
_redis = None
_redis_broken = False

# Cửa sổ trượt nguyên tử: trả 1 nếu cho qua (và ghi nhận), 0 nếu đã vượt hạn mức.
# KEYS[1]=khoá; ARGV=[now_ms, window_ms, limit, member]
_LUA = """
local key = KEYS[1]
local now = tonumber(ARGV[1])
local window = tonumber(ARGV[2])
local limit = tonumber(ARGV[3])
redis.call('ZREMRANGEBYSCORE', key, 0, now - window)
local n = redis.call('ZCARD', key)
if n >= limit then
  return 0
end
redis.call('ZADD', key, now, ARGV[4])
redis.call('PEXPIRE', key, window)
return 1
"""


def _get_redis():
    """Client Redis dùng chung, hoặc None nếu không cấu hình / không kết nối được."""
    global _redis, _redis_broken
    if _redis_broken or not os.getenv("REDIS_URL"):
        return None
    if _redis is not None:
        return _redis
    try:
        import redis  # có sẵn qua celery[redis]

        client = redis.Redis.from_url(
            os.environ["REDIS_URL"], socket_connect_timeout=2,
            socket_timeout=2, decode_responses=True)
        client.ping()
        _redis = client
        log.info("rate limit: dùng Redis (hạn mức chia sẻ giữa các tiến trình)")
        return _redis
    except Exception as exc:  # noqa: BLE001
        _redis_broken = True
        log.warning("rate limit: Redis không dùng được (%s) — rơi về in-memory; "
                    "hạn mức sẽ KHÔNG chia sẻ giữa các tiến trình", exc)
        return None


def _redis_check(ident: str, limit: int, window: float) -> bool | None:
    """True/False theo Redis, hoặc None nếu không dùng được Redis.

    Cố ý KHÔNG ném lỗi ra ngoài. Redis chết giữa chừng thì rơi về in-memory (tức
    cho qua rộng hơn đáng lẽ) thay vì chặn toàn bộ người dùng thật — sự cố hạ tầng
    không nên biến thành "không ai đăng nhập được". Đánh đổi này chỉ có nghĩa khi
    Redis chết; lúc đó giới hạn vẫn còn ở mức một-tiến-trình.
    """
    client = _get_redis()
    if client is None:
        return None
    try:
        now_ms = int(time.time() * 1000)
        # member phải DUY NHẤT: hai lần gọi trong cùng một milli-giây mà trùng
        # member thì ZSET ghi đè nhau -> đếm thiếu -> thủng hạn mức.
        member = f"{now_ms}-{uuid.uuid4().hex[:8]}"
        ok = client.eval(_LUA, 1, f"rl:{ident}", now_ms,
                         int(window * 1000), limit, member)
        return bool(ok)
    except Exception as exc:  # noqa: BLE001
        global _redis_broken
        _redis_broken = True
        log.warning("rate limit: Redis lỗi giữa chừng (%s) — rơi về in-memory", exc)
        return None


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


def _memory_check(ident: str, limit: int, window: float) -> bool:
    """Ghi nhận lần gọi khi và chỉ khi nó được phép — để không "tự khoá" người
    dùng đang trong hạn mức.

    Cả phần đọc lẫn phần ghi nằm trong một khoá: đọc-sửa-ghi mà không khoá thì hai
    luồng cùng lọt qua khi cửa sổ chỉ còn một chỗ.
    """
    with _mem_lock:
        now = time.time()
        _prune(now, max(window, 60.0))
        lst = [t for t in _RATE.get(ident, []) if now - t < window]
        if len(lst) >= limit:
            _RATE[ident] = lst
            return False
        lst.append(now)
        _RATE[ident] = lst
        return True


def check_rate(ident: str, limit: int, window: float = 60.0) -> bool:
    """True nếu còn trong hạn mức; False nếu đã vượt (caller trả 429)."""
    via_redis = _redis_check(ident, limit, window)
    if via_redis is not None:
        return via_redis
    return _memory_check(ident, limit, window)


def backend() -> str:
    """Backend đang thực sự dùng — để /admin hiển thị và để test khẳng định."""
    return "redis" if _get_redis() is not None else "memory"


def reset() -> None:
    """Xoá sạch trạng thái — dùng cho test.

    Xoá cả khoá `rl:*` trên Redis (chỉ của mình) để test không phụ thuộc thứ tự.
    """
    global _calls_since_prune
    _RATE.clear()
    _calls_since_prune = 0
    client = _get_redis()
    if client is None:
        return
    try:
        keys = list(client.scan_iter(match="rl:*", count=500))
        if keys:
            client.delete(*keys)
    except Exception:  # noqa: BLE001
        pass