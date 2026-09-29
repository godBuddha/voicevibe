"""Kiểm tra cấu hình triển khai — bắt loại lỗi mà `docker compose config -q` bỏ qua.

Vì sao cần: `docker compose config -q` chỉ xác nhận YAML hợp lệ. Nó KHÔNG biết
image có tồn tại hay không, container có healthcheck hay không, hay container có
đang chạy bằng root. Bản self-host trước đây trỏ vào `minio/minio:latest` — image
đã bị xoá khỏi Docker Hub — nên `config -q` vẫn xanh trong khi stack **không pull
nổi một image nào**.

Script này chạy offline và tất định (không hỏi registry — Docker Hub giới hạn
request ẩn danh, kiểm tra qua mạng sẽ thành flaky trong CI).

Kiểm tra:
  1. Không image nào dùng tag trôi nổi (`:latest`) hoặc biến chưa phân giải
  2. Không dùng image đã biết là KHÔNG CÒN TỒN TẠI
  3. `api` và `worker` phải có: healthcheck, read_only, cap_drop, no-new-privileges
  4. Dockerfile phải chuyển sang user KHÔNG phải root
  5. `api` mặc định bind loopback (không phơi ra Internet khi chưa có TLS)
  6. File compose phụ (GPU override, proxy) phải có thật và khai đúng thứ cần
  7. Caddyfile tồn tại và chuyển tiếp X-Forwarded-Proto (cookie phiên cần nó)

Run:  python scripts/check_deploy.py
"""
from __future__ import annotations

import pathlib
import re
import sys

REPO = pathlib.Path(__file__).resolve().parents[1]
COMPOSE = REPO / "docker-compose.yml"
GPU_OVERRIDE = REPO / "docker-compose.gpu.yml"
CADDYFILE = REPO / "Caddyfile"
DOCKERFILE = REPO / "backend" / "Dockerfile"

fails: list[str] = []


def check(cond: bool, msg: str) -> None:
    print(("  ok   " if cond else "  FAIL ") + msg)
    if not cond:
        fails.append(msg)


# Image đã biết là KHÔNG CÒN dùng được. MinIO xoá toàn bộ ảnh community khỏi
# Docker Hub; giữ tên cũ ở đây để nếu ai dán lại thì CI chặn ngay kèm lý do.
DEAD_IMAGES = {
    "minio/minio": "ảnh đã bị xoá khỏi Docker Hub — dùng S3 ngoài hoặc volume nội bộ",
    "minio/mc": "ảnh đã bị xoá khỏi Docker Hub (đi cùng minio/minio)",
}

print("check_deploy — cấu hình triển khai phải chạy được thật")
for p in (COMPOSE, GPU_OVERRIDE, CADDYFILE, DOCKERFILE):
    assert p.is_file(), f"thiếu file: {p}"

yaml = COMPOSE.read_text(encoding="utf-8")
lines = yaml.splitlines()

# Bỏ comment trước khi soi chuỗi. Chính các ghi chú giải thích hai cái bẫy
# APP_DOMAIN có chứa `APP_DOMAIN:?` và `APP_DOMAIN:-` — nếu quét cả comment thì
# guard tự tố cáo chính tài liệu của nó (đã gặp thật ngay lần chạy đầu).
code = "\n".join(ln for ln in lines if not ln.lstrip().startswith("#"))


def service_block(name: str, text: str) -> str:
    """Cắt phần của một service trong compose (theo thụt lề)."""
    out: list[str] = []
    inside = False
    for ln in text.splitlines():
        if re.match(rf"^  {re.escape(name)}:\s*$", ln):
            inside = True
            continue
        if inside:
            if ln.strip() and not ln.startswith("    "):
                break
            out.append(ln)
    return "\n".join(out)


# ---------------------------------------------------- 1. tag trôi nổi / chết
images: list[str] = []
for ln in lines:
    m = re.match(r"\s*image:\s*(\S+)\s*$", ln)
    if m:
        images.append(m.group(1))

check(bool(images), f"tìm thấy image trong compose ({len(images)})")
for img in images:
    check(":latest" not in img, f"không dùng tag trôi nổi: {img}")
    check(not img.endswith(":") and "${" not in img,
          f"image phân giải được thành tag cụ thể: {img}")
    repo = img.split(":")[0]
    check(repo not in DEAD_IMAGES,
          f"image còn tồn tại: {img}"
          + (f" — {DEAD_IMAGES[repo]}" if repo in DEAD_IMAGES else ""))

# ------------------------------------------------- 3. hardening api + worker
for svc in ("api", "worker"):
    blk = service_block(svc, yaml)
    check(bool(blk), f"tìm thấy service `{svc}`")
    if not blk:
        continue
    check("healthcheck:" in blk, f"`{svc}` có healthcheck")
    check("read_only: true" in blk, f"`{svc}` filesystem read-only")
    check("cap_drop:" in blk and "ALL" in blk, f"`{svc}` bỏ toàn bộ capability")
    check("no-new-privileges" in blk, f"`{svc}` chặn leo thang đặc quyền")

# worker phải chờ Redis/Postgres sẵn sàng, nếu không job đầu tiên rơi mất
wblk = service_block("worker", yaml)
check("condition: service_healthy" in wblk, "`worker` chờ postgres/redis healthy")
# healthcheck của worker phải kiểm CÓ worker trả lời, không chỉ chạy được lệnh
check("grep -q pong" in wblk, "healthcheck `worker` xác nhận worker thật trả lời")

# ------------------------------------------------------ 4. Dockerfile non-root
df = DOCKERFILE.read_text(encoding="utf-8")
check("USER voicevibe" in df, "Dockerfile chạy bằng user không phải root")
check(df.count("USER voicevibe") == 2, "CẢ HAI stage (api + worker) đều non-root")
check("useradd" in df and "10001" in df,
      "uid cố định (volume giữ được quyền sở hữu qua các lần deploy)")

# Runtime của từng image phải có lệnh nó khai ở CMD. Ảnh worker khai
# `celery -A app.tasks.celery_app worker` trong khi `requirements-worker.txt`
# KHÔNG có celery -> container không start nổi ("exec: celery: executable file
# not found in $PATH"). Đây là lỗi có thật, chỉ lộ ra khi chạy `up`.
# Cách kiểm: mỗi lệnh ở CMD phải xuất hiện trong requirements tương ứng.
import json as _json  # noqa: E402

REQ = REPO / "backend" / "requirements-api.txt"
REQ_W = REPO / "backend" / "requirements-worker.txt"


def requirements_code(path: pathlib.Path) -> str:
    """Bỏ dòng comment trước khi soi.

    Bắt buộc: chính ghi chú giải thích trong requirements-worker.txt có chứa chữ
    "celery", nên quét cả comment thì guard báo PASS dù package đã bị gỡ — đúng
    loại bẫy vừa gặp ở phần APP_DOMAIN.
    """
    return "\n".join(
        ln.split("#", 1)[0]
        for ln in path.read_text(encoding="utf-8").splitlines())


req_api = requirements_code(REQ)
req_worker = requirements_code(REQ_W)

# CMD của mỗi stage (giữa `FROM base AS <tên>` và FROM kế tiếp)
stages = re.split(r"^FROM .*? AS (\w+)\s*$", df, flags=re.M)
stage_body = {stages[i]: stages[i + 1] for i in range(1, len(stages), 2)}


def cmd_first_word(body: str) -> str:
    m = re.search(r'^CMD \["([^"]+)"', body, re.M)
    return m.group(1) if m else ""


# Lệnh nào do pip cài thì phải có trong requirements tương ứng
for stage, req, req_name in (("api", req_api, "requirements-api.txt"),
                             ("worker", req_worker, "requirements-worker.txt")):
    body = stage_body.get(stage, "")
    prog = cmd_first_word(body)
    check(bool(prog), f"stage `{stage}` có CMD")
    # `uvicorn`/`celery` là entry point do pip cài -> phải có package tương ứng
    pip_provides = {"celery": "celery", "uvicorn": "uvicorn"}
    if prog in pip_provides and prog != "uvicorn":
        check(pip_provides[prog] in req,
              f"`{prog}` (CMD của stage `{stage}`) có trong {req_name}")
    if prog not in pip_provides:
        check(False, f"CMD của `{stage}` dùng chương trình lạ: {prog!r}")

check("celery" in req_worker,
      "requirements-worker.txt có celery (worker CHẠY celery, không chỉ import)")

# --------------------------------- 4b. mỗi image phải mang đủ thứ nó CẦN LÚC CHẠY
# Lớp lỗi đã gặp thật, hai lần, cùng một dạng: image worker thiếu thứ nó cần.
#   - `celery`  -> "exec: celery: executable file not found in $PATH"
#   - `psycopg` -> "ModuleNotFoundError: No module named 'psycopg'" khi kết nối DB
# Cả hai chỉ lộ khi `docker compose up` thật. Không test Python nào thấy được, vì
# ở môi trường dev thì các gói đó có sẵn.
#
# Cách kiểm: đọc biến môi trường của từng service trong compose rồi suy ra gói cần.
svc_env: dict[str, str] = {}
cur = None
for ln in code.splitlines():
    m = re.match(r"^  (\w[\w-]*):\s*$", ln)
    if m:
        cur = m.group(1)
        continue
    m = re.match(r"^\s+([A-Z][A-Z0-9_]*):\s*(.*)$", ln)
    if m and cur:
        svc_env[f"{cur}.{m.group(1)}"] = m.group(2).strip()

# DATABASE_URL dạng postgresql+psycopg:// -> image đó phải có psycopg
for key, val in svc_env.items():
    svc = key.split(".")[0]
    if key.endswith(".DATABASE_URL") and "psycopg" in val:
        req = req_api if svc == "api" else (req_worker if svc == "worker" else None)
        if req is not None:
            check("psycopg" in req,
                  f"`{svc}` dùng DATABASE_URL postgres -> requirements có psycopg")
    # REDIS_URL -> cần redis client (celery[redis] kéo theo)
    if key.endswith(".REDIS_URL"):
        req = req_api if svc == "api" else (req_worker if svc == "worker" else None)
        if req is not None:
            check("redis" in req or "celery" in req,
                  f"`{svc}` dùng REDIS_URL -> requirements có redis/celery")

# -------------------------------------------------------- 5. api bind loopback
check("${API_BIND:-127.0.0.1}" in yaml,
      "`api` mặc định bind loopback (không phơi ra Internet khi chưa có TLS)")

# ---------------------------------------------------- 6. file compose phụ
gpu = GPU_OVERRIDE.read_text(encoding="utf-8")
check("capabilities: [gpu]" in gpu, "GPU override cấp capability gpu")
check("reservations:" in gpu and "driver: nvidia" in gpu,
      "GPU override khai đúng driver nvidia")
check("worker:" in gpu, "GPU override áp cho service worker")

# proxy nằm trong profile -> mặc định không dựng
cblk = service_block("web", yaml)
check("profiles: [proxy]" in cblk, "web (Caddy) nằm trong profile `proxy` (opt-in)")

# ------------------------------------------------------------ 7. Caddyfile
cf = CADDYFILE.read_text(encoding="utf-8")
check("reverse_proxy api:8000" in cf, "Caddyfile chuyển tiếp tới api:8000")
# auth.py đọc header này để bật cờ Secure cho cookie phiên. Caddy tự đặt, nhưng
# nếu ai thay bằng proxy khác mà không gửi thì cookie sẽ đi qua HTTP thường.
check("X-Forwarded-Proto" in cf, "Caddyfile nhắc tới X-Forwarded-Proto (cookie Secure)")

# ------------------------------------------- 8. hai cái bẫy APP_DOMAIN đã gặp thật
# (a) `:?` bắt buộc -> compose nội suy biến của MỌI service TRƯỚC khi lọc profile,
#     nên `docker compose build api` hỏng dù profile `proxy` đang tắt.
check("APP_DOMAIN:?" not in code,
      "APP_DOMAIN không dùng `:?` (sẽ chặn mọi lệnh compose khi tắt profile proxy)")
check("APP_DOMAIN:-" in code,
      "APP_DOMAIN có giá trị mặc định trong compose")
# (b) mặc định phải KHÁC RỖNG: Caddy chỉ áp dụng `{$VAR:default}` khi biến KHÔNG
#     được set; set-nhưng-rỗng làm địa chỉ site rỗng và Caddy hiểu nhầm khối sau
#     là global option ("unrecognized global option: encode").
m = re.search(r"APP_DOMAIN:-([^}\s]*)", code)
default_val = (m.group(1) if m else "")
check(bool(default_val),
      f"mặc định của APP_DOMAIN khác rỗng (đang là {default_val!r})")
check("{$APP_DOMAIN:localhost}" not in cf,
      "Caddyfile không dựa vào `:default` (vô hiệu khi biến set-nhưng-rỗng)")

if fails:
    print(f"\nDEPLOY CHECK FAILED — {len(fails)} vấn đề")
    sys.exit(1)
print("\nDEPLOY CHECK PASSED")