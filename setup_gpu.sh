#!/usr/bin/env bash
# Bootstrap YupVox-Clone trên instance GPU thuê (Ubuntu 24.04, driver 550 / CUDA 12.4).
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
# Driver host là 550 (CUDA 12.4): wheel cu128 chạy được nhờ CUDA minor-version
# compatibility. Nếu smoke test cuối báo CUDA unavailable -> cài lại bằng cu126:
#   pip install torch torchaudio --index-url https://download.pytorch.org/whl/cu126
pip install -q torch torchaudio --index-url https://download.pytorch.org/whl/cu128
pip install -q -r backend/requirements-api.txt
# Core AI deps (bắt buộc cho D3-D5)
pip install -q faster-whisper pyannote.audio vieneu srt numpy
# Tùy chọn: engine clone đa ngôn ngữ (non-vi) — lỗi không chặn pipeline
pip install -q chatterbox-tts || echo "WARN: chatterbox-tts lỗi (tùy chọn, chỉ non-vi TTS) — bỏ qua"

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
