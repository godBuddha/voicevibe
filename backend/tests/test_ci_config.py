"""Guard cho chính file CI — bắt loại lỗi đã làm CI đỏ 11 lần liên tiếp.

Bối cảnh (lỗi THẬT, 27/09): `actions/setup-python` khai `cache: pip` nhưng repo
KHÔNG có `requirements.txt` lẫn `pyproject.toml` (deps nằm ở
`backend/requirements-api.txt` / `requirements-worker.txt`). setup-python đi tìm
đúng hai tên mặc định đó, không thấy, và **fail ngay** — job chết sau ~7 giây
TRƯỚC KHI chạy test nào. Hệ quả: 11 lần push liên tiếp đều "đỏ" trong khi toàn bộ
test thực ra xanh. Không test Python nào bắt được vì lỗi nằm ở YAML của CI.

Ba thứ được canh ở đây, đều là lỗi im lặng nếu không canh:
  1. `cache: pip` phải kèm `cache-dependency-path` trỏ tới file CÓ THẬT
  2. mọi `python tests/<x>.py` / `python -m app.pipelines.<m>` trong workflow phải
     tồn tại — đổi tên file mà quên CI thì job chết ở bước cuối, rất dễ bỏ qua
  3. mọi `backend/tests/test_*.py` phải được workflow gọi — thêm test mới mà
     không nối vào CI thì nó không bao giờ chạy (test "trang trí")

Đọc YAML bằng regex thay vì PyYAML: CI không cài PyYAML và mục tiêu hẹp, đủ chính xác.

Run:  cd backend && python tests/test_ci_config.py
"""
from __future__ import annotations

import pathlib
import re
import sys

REPO = pathlib.Path(__file__).resolve().parents[2]
WORKFLOW = REPO / ".github" / "workflows" / "tests.yml"
TESTS_DIR = REPO / "backend" / "tests"

fails: list[str] = []


def check(cond: bool, msg: str) -> None:
    if cond:
        print("  ok   ", msg)
    else:
        print("  FAIL ", msg)
        fails.append(msg)


print("test_ci_config — workflow phải thực sự chạy được")
assert WORKFLOW.is_file(), f"không thấy workflow: {WORKFLOW}"
text = WORKFLOW.read_text(encoding="utf-8")

# ---------------------------------------------------------------- 1. cache pip
if re.search(r"^\s*cache:\s*pip\s*$", text, re.M):
    lines = text.splitlines()
    key_at = next((i for i, ln in enumerate(lines)
                   if re.match(r"^\s*cache-dependency-path:", ln)), None)
    check(key_at is not None,
          "`cache: pip` phải kèm `cache-dependency-path` (nếu không setup-python "
          "đi tìm requirements.txt/pyproject.toml rồi fail ngay)")
    if key_at is None:
        print(f"\nCI CONFIG GUARD FAILED — {len(fails)} vấn đề")
        sys.exit(1)
    indent = len(lines[key_at]) - len(lines[key_at].lstrip())
    key_raw = lines[key_at].split(":", 1)[1].strip()
    paths: list[str] = []
    if key_raw and key_raw != "|":          # dạng inline: [a, b] hoặc a
        paths = [p.strip().strip("[]'\"") for p in key_raw.split(",")
                 if p.strip().strip("[]'\"")]
    else:                                   # dạng block scalar `|` — các dòng
        for ln in lines[key_at + 1:]:       # sau phải thụt lề sâu hơn key
            if not ln.strip():
                continue
            if len(ln) - len(ln.lstrip()) <= indent:
                break
            paths.append(ln.strip())

    check(bool(paths), "cache-dependency-path không được rỗng")
    for p in paths:
        check((REPO / p).is_file(), f"cache-dependency-path tồn tại: {p}")
    # bẫy cụ thể đã gặp: trỏ vào requirements.txt không hề tồn tại
    check(not any(p.endswith("requirements.txt") for p in paths),
          "không trỏ vào requirements.txt (repo dùng requirements-api.txt / "
          "-worker.txt)")
else:
    print("  note  workflow không dùng cache pip")

# --------------------------------------------- 2. mọi lệnh trong CI có thật
refs = re.findall(r"python\s+tests/(\w+)\.py", text)
check(bool(refs), "workflow có gọi ít nhất một test")
for name in refs:
    check((TESTS_DIR / f"{name}.py").is_file(),
          f"workflow gọi tests/{name}.py — file tồn tại")

mods = re.findall(r"python\s+-m\s+(app\.pipelines\.\w+)", text)
for mod in mods:
    rel = pathlib.Path(*mod.split(".")).with_suffix(".py")
    check((REPO / "backend" / rel).is_file(),
          f"workflow gọi -m {mod} — module tồn tại")

# ------------------------------------- 3. không có test nào bị bỏ quên ngoài CI
on_disk = {p.stem for p in TESTS_DIR.glob("test_*.py")}
wired = set(refs) | {"test_ci_config"}
orphans = sorted(on_disk - wired)
check(not orphans,
      f"mọi test_*.py đều được CI gọi (bị bỏ quên: {orphans or 'không'})")

# test này tự nó phải nằm trong CI, nếu không thì guard này vô dụng
check("test_ci_config" in text,
      "test_ci_config.py được nêu trong workflow (guard phải tự chạy)")

if fails:
    print(f"\nCI CONFIG GUARD FAILED — {len(fails)} vấn đề")
    sys.exit(1)
print("\nCI CONFIG GUARD PASSED")