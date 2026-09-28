# Multi-stage: `api` (light, no AI deps) and `worker` (GPU stack).
# Build:   docker build --target api    -t yupvox-api    ./backend
#          docker build --target worker -t yupvox-worker ./backend
# compose sets the target per service.
FROM python:3.12-slim AS base

# ffmpeg: dub pipeline mix/encode. ca-certificates: outbound HTTPS to providers/HF.
RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Non-root. Both containers used to run as root, which turns any RCE in the app
# into root inside the container and, with a mounted volume, into whatever else
# that mount reaches.
#
# uid/gid are fixed (10001) so volume ownership is predictable. The directories
# are created here, BEFORE the volumes are mounted, because Docker initialises a
# fresh named volume with the ownership of the image path it mounts over — do
# this the other way round and the volume lands root-owned and the app cannot
# write to it (silent failure: jobs complete, files never appear).
RUN groupadd -g 10001 yupvox \
    && useradd -u 10001 -g yupvox -M -s /usr/sbin/nologin yupvox

WORKDIR /srv

FROM base AS api
COPY requirements-api.txt .
RUN pip install --no-cache-dir -r requirements-api.txt
COPY app ./app
RUN mkdir -p /media && chown -R yupvox:yupvox /media
USER yupvox
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

FROM base AS worker
# torch cu128 wheels run on driver >= CUDA 12.0 (verified RTX 3060, driver 550).
# pyannote>=4 REQUIRES torch>=2.8 — do not downgrade (see requirements-worker.txt).
#
# torch cài TRƯỚC và ở LỚP RIÊNG, cố ý:
#   * trước, vì nếu để pip tự giải quyết sau đó nó sẽ kéo torch bản CPU từ PyPI
#     và ghi đè bản cu128 (pyannote>=4 đòi torch>=2.8);
#   * lớp riêng, vì bánh xe torch+cu128 nặng ~890MB. Gộp chung một RUN với
#     requirements-worker.txt thì MỖI lần sửa danh sách phụ thuộc là tải lại 890MB.
#     Tách ra thì chỉ lớp nhỏ bên dưới phải chạy lại.
RUN pip install --no-cache-dir torch==2.8.0 torchaudio==2.8.0 \
        --index-url https://download.pytorch.org/whl/cu128

COPY requirements-worker.txt .
RUN pip install --no-cache-dir -r requirements-worker.txt

COPY app ./app
# Model cache volume must be writable by uid 10001 too (HF downloads land here).
RUN mkdir -p /media /models/hf && chown -R yupvox:yupvox /media /models/hf
ENV HF_HOME=/models/hf
USER yupvox
CMD ["celery", "-A", "app.tasks.celery_app", "worker", "-l", "info", "-Q", "media", "-c", "1"]