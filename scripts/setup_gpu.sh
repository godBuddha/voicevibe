#!/usr/bin/env bash
# Bootstrap VoiceVibe trên instance GPU thuê (Ubuntu 24.04, driver 550 / CUDA 12.4).
# Chạy: bash setup_gpu.sh   (tại thư mục gốc repo)
set -euo pipefail

SUDO=""
[ "$(id -u)" -ne 0 ] && SUDO="sudo"

echo "== [1/5] GPU check =="
nvidia-smi

echo "== [2/5] System deps (ffmpeg, git, venv) =="
export DEBIAN_FRONTEND=noninteractive
$SUDO apt-get update -qq
$SUDO apt-get install -y -qq ffmpeg git curl python3-venv python3-pip

if [ -z "${HF_TOKEN:-}" ]; then
  echo "WARN: HF_TOKEN chưa set — pyannote (gated) sẽ fail ở Day 3. Export trước khi chạy."
fi

echo "== [3/5] Python env + deps =="
python3 -m venv .venv
# shellcheck disable=SC1091
source .venv/bin/activate
pip install -q -U pip
# Driver >= 550 chạy được wheel cu128 (CUDA minor-version compatibility).
# PIN torch==2.8 — pyannote>=4 yêu cầu torch>=2.8; KHÔNG để pip kéo bản mới hơn
# (từng bị kéo 2.14+cu130 -> kernel fail trên driver cũ).
pip install -q torch==2.8.0 torchaudio==2.8.0 --index-url https://download.pytorch.org/whl/cu128
pip install -q -r backend/requirements-api.txt
# Core AI deps (bắt buộc cho D3-D5): soundfile = nạp in-memory cho pyannote
# (bypass torchcodec); sentencepiece = tokenizer opus-mt (translate local).
pip install -q faster-whisper pyannote.audio vieneu srt soundfile sentencepiece numpy
# NOTE: chatterbox-tts KHÔNG cài vào venv này — nó pin torch==2.6 (xung đột
# pyannote>=2.8). Cần TTS đa ngôn ngữ non-vi thì tạo venv riêng.

echo "== [4/5] Offline selftests (không cần GPU) =="
cd backend
PYTHONPATH=. python tests/test_providers.py
PYTHONPATH=. python tests/test_day2.py
python -m app.pipelines.dub --selftest

echo "== [5/5] GPU smoke: CUDA + faster-whisper small/int8 =="
python - <<'PY'
import torch
print("CUDA:", torch.cuda.is_available(),
      "|", torch.cuda.get_device_name(0) if torch.cuda.is_available() else "no GPU")
from faster_whisper import WhisperModel
WhisperModel("small", device="auto", compute_type="int8")
print("faster-whisper loaded OK (small/int8)")
PY

echo "BOOTSTRAP DONE — sẵn sàng Day 3"
