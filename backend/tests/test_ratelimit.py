"""Guard cho rate limiter — đặc biệt là đường Redis (chia sẻ giữa nhiều tiến trình).

Vì sao có test này: rate limiter bản cũ chỉ nằm trong bộ nhớ một tiến trình. Với
`uvicorn --workers 4`, hạn mức `login:ip` 10/phút thành 40/phút — vẫn chặn được
kẻ tấn công rất chậm, nhưng đúng loại lỗi im lặng: `limit=10` trong code mà thực
tế là 10×số-tiến-trình.

Test chạy được cả khi KHÔNG có Redis (in-memory) lẫn khi có (đặt REDIS_URL).
Phần Redis tự bỏ qua nếu không kết nối được, nhưng khi CÓ thì khẳng định đúng
hành vi chia sẻ — cụ thể là hai "tiến trình" khác nhau (hai module import riêng
biệt) dùng chung một bộ đếm.

Run:  cd backend && python tests/test_ratelimit.py
      REDIS_URL=redis://localhost:6379/0 python tests/test_ratelimit.py   # có Redis
"""
from __future__ import annotations

import importlib
import os
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from app import ratelimit as RL  # noqa: E402

print(f"ratelimit — backend: {RL.backend()}")

# ----------------------------------------------------------- 1. hành vi cơ bản
RL.reset()
assert RL.check_rate("a", 3) is True
assert RL.check_rate("a", 3) is True
assert RL.check_rate("a", 3) is True
assert RL.check_rate("a", 3) is False, "phải chặn ở lần thứ 4"
assert RL.check_rate("a", 3) is False
print("chặn đúng hạn mức .................... OK")

# các ident độc lập nhau
assert RL.check_rate("b", 3) is True, "ident khác không được bị ảnh hưởng"
print("các ident độc lập .................... OK")

# ------------------------------------------------- 2. lần gọi bị chặn KHÔNG ghi nhận
# Nếu lần bị chặn cũng được ghi vào cửa sổ, người dùng đang trong hạn mức gõ thêm
# vài lần sẽ tự đẩy mình ra ngoài lâu hơn — "tự khoá" chính mình.
RL.reset()
for _ in range(3):
    RL.check_rate("c", 3, window=60)
for _ in range(5):                      # 5 lần bị chặn
    assert RL.check_rate("c", 3, window=60) is False
# nếu lần bị chặn không ghi nhận, cửa sổ vẫn chỉ có 3 mốc -> vẫn đang đầy
assert RL.check_rate("c", 3, window=60) is False
print("lần bị chặn không ghi vào cửa sổ .... OK")

# ------------------------------------------------------------- 3. cửa sổ trượt
RL.reset()
assert RL.check_rate("d", 2, window=0.4) is True
assert RL.check_rate("d", 2, window=0.4) is True
assert RL.check_rate("d", 2, window=0.4) is False
import time  # noqa: E402

time.sleep(0.45)
assert RL.check_rate("d", 2, window=0.4) is True, "hết cửa sổ phải cho qua lại"
print("cửa sổ trượt hết hạn ............... OK")

# ------------------------------------- 4. nhiều "tiến trình" dùng CHUNG bộ đếm
# Đây là điểm mấu chốt của bản sửa. Phải nạp module HAI LẦN thành hai đối tượng
# độc lập để có hai bộ `globals()` riêng — mô phỏng hai tiến trình.
#
# KHÔNG dùng `importlib.reload`: nó chạy lại mã trong CÙNG một đối tượng module,
# nên hai tên vẫn trỏ về một dict `_RATE` — test sẽ "xanh" một cách vô nghĩa.
# (Đã viết sai đúng như vậy ở lần đầu: nó báo cho qua 3/6 trong khi không hề có
# Redis, tức là kết luận "đã chia sẻ" trong khi thực tế không.)
import importlib.util  # noqa: E402

RATELIMIT_PATH = pathlib.Path(__file__).resolve().parents[1] / "app" / "ratelimit.py"


def _load_isolated(name: str):
    """Nạp ratelimit.py thành một module RIÊNG (globals riêng)."""
    spec = importlib.util.spec_from_file_location(name, RATELIMIT_PATH)
    mod = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(mod)
    return mod


procA, procB = _load_isolated("rl_proc_a"), _load_isolated("rl_proc_b")
assert procA._RATE is not procB._RATE, "hai bản phải có dict riêng"

procA.reset()
procB.reset()
passed = 0
for _ in range(6):
    if procA.check_rate("shared", 3, window=60):
        passed += 1
    if procB.check_rate("shared", 3, window=60):
        passed += 1

if procA.backend() == "redis":
    assert passed == 3, (
        f"Redis phải chia sẻ hạn mức giữa các tiến trình: cho qua {passed} lần "
        f"(mong đợi 3)")
    print("chia sẻ hạn mức giữa 2 tiến trình ... OK (redis)")
else:
    # Không có Redis thì biết trước là KHÔNG chia sẻ — khẳng định đúng con số đó
    # để nó thành bằng chứng, chứ không phải lời hứa.
    assert passed == 6, passed
    print(f"KHÔNG có Redis -> hạn mức nhân lên (cho qua {passed}/6) — đúng như đã biết")

# ---------------------------------------------- 5. redis chết -> rơi về in-memory
# Không được ném lỗi ra ngoài; phải vẫn trả lời được (thà rộng còn hơn chặn hết).
RL.reset()
os.environ["REDIS_URL"] = "redis://127.0.0.1:1/0"   # cổng chắc chắn không có gì
sys.modules.pop("redis", None)
importlib.reload(RL)
try:
    ok = RL.check_rate("e1", 2)
    assert ok is True, "Redis hỏng phải rơi về in-memory, không được chặn"
    assert RL.backend() == "memory", RL.backend()
    print("Redis hỏng -> rơi về in-memory ..... OK")
finally:
    os.environ.pop("REDIS_URL", None)
    importlib.reload(RL)

# ------------------------------------------------------------- 6. đồng thời
# FastAPI chạy endpoint đồng bộ trong threadpool, nên ĐA LUỒNG là tình huống thật.
# Khẳng định: cả hai backend cho qua ĐÚNG BẰNG hạn mức, không hơn.
#
# NÓI THẲNG VỀ GIỚI HẠN CỦA CA NÀY: nó KHÔNG chứng minh được rằng khoá trong
# `_memory_check` là cần thiết. Đã thử gỡ khoá ra và chạy 40 lượt × 60 luồng —
# 0 lượt vượt hạn mức. GIL của CPython làm cửa sổ tranh chấp hẹp tới mức gần như
# không quan sát được bằng thực nghiệm. Khoá được giữ vì đúng theo thiết kế
# (đọc-sửa-ghi phải nguyên tử), KHÔNG phải vì test này bắt được lỗi.
# Ca này vẫn có ích: nó ghim bất biến "không bao giờ vượt hạn mức", và bắt được
# lỗi rõ ràng nếu ai đó viết lại thành logic không nguyên tử ở mức thô.
import threading  # noqa: E402

for mod, label in ((RL, "in-memory"), (_load_isolated("rl_conc"), "isolated")):
    mod.reset()
    LIMIT, N = 20, 200
    got: list[bool] = []
    g = threading.Lock()

    def worker():
        r = mod.check_rate("hot", LIMIT, window=60)
        with g:
            got.append(r)

    ts = [threading.Thread(target=worker) for _ in range(N)]
    for t in ts:
        t.start()
    for t in ts:
        t.join()
    n = sum(1 for x in got if x)
    assert n == LIMIT, f"[{label}] {n}/{N} lọt qua, hạn mức {LIMIT} — THỦNG hạn mức"
    print(f"đồng thời {N} luồng -> đúng {n}/{LIMIT} ... OK")

# ---------------------------------------------------------------- 7. dọn dẹp
RL.reset()
assert RL._RATE == {}, "reset() phải xoá sạch bộ nhớ"
print("reset() dọn sạch .................... OK")

print("RATELIMIT GUARD PASSED")