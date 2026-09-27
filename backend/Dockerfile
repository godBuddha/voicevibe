# Multi-stage: `api` (light, no AI deps) and `worker` (GPU stack).
# Build:   docker build --target api    -t yupvox-api    ./backend
#          docker build --target worker -t yupvox-worker ./backend
# compose sets the target per service.
FROM python:3.12-slim AS base
RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg ca-certificates \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /srv

FROM base AS api
COPY requirements-api.txt .
RUN pip install --no-cache-dir -r requirements-api.txt
COPY app ./app
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

FROM base AS worker
# torch cu128 wheels run on driver >= CUDA 12.0 (verified on RTX 3060, driver 550).
# pyannote>=4 REQUIRES torch>=2.8 — do not downgrade (see requirements-worker.txt).
COPY requirements-worker.txt .
RUN pip install --no-cache-dir torch==2.8.0 torchaudio==2.8.0 \
        --index-url https://download.pytorch.org/whl/cu128 \
    && pip install --no-cache-dir -r requirements-worker.txt
COPY app ./app
ENV HF_HOME=/models/hf
CMD ["celery", "-A", "app.tasks.celery_app", "worker", "-l", "info", "-Q", "media", "-c", "1"]
