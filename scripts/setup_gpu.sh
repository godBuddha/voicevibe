#!/usr/bin/env bash
# Bootstrap VoiceVibe trên instance GPU thuê (Ubuntu 24.04, driver 550 / CUDA 12.4+).
# Chạy: bash setup_gpu.sh   (tại thư mục gốc repo)
#
# Học từ lần dựng máy vast.ai 2x3090 (29/09/2026):
#   - Một số máy thuê bị CHẶN huggingface.co (DNS poisoning kiểu GFW — trả IP giả).
#     Nếu huggingface.co không truy cập được, script tự chuyển sang mirror
#     hf-mirror.com (HF_ENDPOINT). Cửa hàng thay thế y hệt, không cần can thiệp.
#   - setup cũ thiếu demucs/pysubs2/transformers — chết giữa chừng khi chạy dub.
#   - HF_TOKEN đọc từ .env (repo gốc) — script chỉ WARN nếu thiếu, không tự tạo.
set -euo pipefail

SUDO=""
[ "$(id -u)" -ne 0 ] && SUDO="sudo"

echo "== [1/5] GPU check =="
nvidia-smi

echo "== [2/5] System deps (ffmpeg, git, venv) =="
export DEBIAN_FRONTEND=noninteractive
$SUDO apt-get update -qq
$SUDO apt-get install -y -qq ffmpeg git curl python3-venv python3-pip

# HF_TOKEN: env trước, .env (repo gốc) sau — để nguyên nếu cả hai rỗng.
if [ -z "${HF_TOKEN:-}" ]; then
  if [ -f .env ] && grep -q '^HF_TOKEN=hf_' .env; then
    HF_TOKEN="$(grep -oP '(?<=^HF_TOKEN=).*' .env)"
    export HF_TOKEN
    echo "HF_TOKEN: đọc từ .env"
  else
    echo "WARN: HF_TOKEN chưa set — pyannote (gated) sẽ fail khi diarize."
    echo "      Điền HF_TOKEN=hf_... vào .env rồi chạy lại (không cần cài lại deps)."
  fi
fi

# Mirror: máy bị chặn huggingface.co -> mọi tải model đi qua hf-mirror.com.
# Máy truy cập bình thường thì giữ endpoint gốc (curl probe 10s).
if [ -z "${HF_ENDPOINT:-}" ]; then
  if curl -s -o /dev/null --max-time 10 https://huggingface.co; then
    echo "HF endpoint: huggingface.co OK"
  else
    export HF_ENDPOINT=https://hf-mirror.com
    echo "HF endpoint: huggingface.co KHÔNG truy cập được -> dùng mirror hf-mirror.com"
  fi
else
  echo "HF endpoint: giữ HF_ENDPOINT=${HF_ENDPOINT} (đã set từ env)"
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
# Core AI deps (bắt buộc cho D3-D7 + dub video): soundfile = nạp in-memory cho
# pyannote (bypass torchcodec); sentencepiece = tokenizer opus-mt (translate
# local); demucs = tách bed nhạc không-lời (DubTrans F0, htdemucs); pysubs2 =
# xuất phụ đề SRT/VTT/ASS; transformers PIN 4.57.6 = GPU path của vieneu
# (pin theo upstream README — thiếu thì import VieNeuTTS chết).
pip install -q faster-whisper pyannote.audio vieneu srt soundfile sentencepiece numpy \
  demucs pysubs2 "transformers==4.57.6"
# NOTE: chatterbox-tts KHÔNG cài vào venv này — nó pin torch==2.6 (xung đột
# pyannote>=2.8). Cần TTS đa ngôn ngữ non-vi thì tạo venv riêng.

# Warm cache pyannote: Pipeline 4.x kéo thêm checkpoint phụ community-1 khi
# CHẠY (không phải khi cài) — không warm trước thì run đầu tiên chết mạng.
echo "== [3.5/5] Warm cache pyannote community-1 (model phụ của 4.x) =="
python - <<'PY'
import os
from huggingface_hub import snapshot_download
token = os.getenv("HF_TOKEN")
try:
    snapshot_download("pyannote/speaker-diarization-community-1", token=token)
    print("pyannote community-1: cached")
except Exception as e:
    print(f"WARN: warm community-1 fail ({e.__class__.__name__}) — diarize sẽ thử lại lúc chạy")
PY

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
