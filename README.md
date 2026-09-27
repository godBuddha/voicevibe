# YupVox-Clone — 7-day challenge (mục tiêu: 100% open source)

Clone của một SaaS AI voice/dubbing (TTS, STT, dubbing video/audio, dịch phụ đề,
tách & clone nhiều người nói, API developer) — dựng bằng stack open-source.

## Kiến trúc

```
Client / Web UI ──► FastAPI (api) ──► Celery queue (Redis) ──► AI Worker (GPU)
                        │                                           │
                        ├── Postgres: users, jobs, credits, api_keys│
                        └── MinIO (S3): media in/out ◄──────────────┘

AI Worker pipeline (dub):
  ffmpeg demux ─► faster-whisper (STT) ─► pyannote (diarization)
AI Worker pipeline (dub) — mỗi stage là provider hoán đổi được (app/providers/):
  stt        : local faster-whisper  | OpenAI-compatible /v1/audio/transcriptions
  diarize    : local pyannote        | (chuẩn OpenAI KHÔNG có speaker labels)
  translate  : local vLLM Qwen int4  | OpenAI-compatible /v1/chat/completions
  tts        : local VieNeu (clone)  | OpenAI-compatible /v1/audio/speech (preset)
  sync + mix : timing-fit engine + ffmpeg — local, core IP
```

## Provider layer — local-first, cloud-optional

Mỗi stage là một interface; local engine và endpoint cloud chuẩn OpenAI cài cùng
interface, hoán đổi qua config + fallback chain (lazy init — engine nặng chỉ nạp
khi được gọi, engine thiếu = fallback event thay vì boot failure).
Selftest: `PYTHONPATH=. python tests/test_providers.py`

| Stage | Chuẩn OpenAI? | Cloud | Local | Ghi chú |
|---|---|---|---|---|
| STT | ✅ /v1/audio/transcriptions | OpenAI, Groq… | faster-whisper | cloud cho spike, local cho batch |
| Diarization | ❌ | adapter riêng | pyannote | speaker labels không có trong chuẩn |
| Translate | ✅ /v1/chat/completions | OpenAI, DeepSeek, Groq, vLLM… | Qwen int4 | local mặc định, cloud fallback/quality |
| TTS preset | ✅ /v1/audio/speech | OpenAI, VieNeu server | VieNeu, Chatterbox | preset voices only |
| Voice cloning | ❌ | VieNeu API (proprietary), ElevenLabs (adapter) | VieNeu, Chatterbox | feature cốt lõi — bắt buộc local |
| Sync + mix | ❌ | — | ffmpeg + timing engine | core IP |

→ Hai tính năng định vị sản phẩm (clone giọng + tách người nói) KHÔNG có trong
chuẩn OpenAI: một clone "thuần cloud API" không thể tái tạo YupVox. Kiến trúc
local-first là bắt buộc; cloud chỉ tùy chọn cho các stage hàng hóa.

```yaml
# providers.yaml (ví dụ)
translation:
  - {provider: openai_chat, base_url: "https://api.deepseek.com/v1",
     api_key_env: DEEPSEEK_API_KEY, model: deepseek-chat}
  - {provider: openai_chat, base_url: "http://vllm:8000/v1",
     api_key: EMPTY, model: Qwen/Qwen3-4B-Instruct-2507}   # fallback local
tts_vi:
  - {provider: local_vieneu}                               # clone — local
  - {provider: openai_tts, base_url: "https://api.openai.com/v1",
     api_key_env: OPENAI_API_KEY, model: tts-1}            # fallback preset
```

Hybrid VRAM (gói 12GB): nếu dịch chạy cloud → trả lại ~4GB → all-resident
(whisper int8 + pyannote + VieNeu) ≈ 7GB, thoải mái.

## Stack & license (quyết định cuối — 26/09/2026)

| Layer | Model / tool | License | Ghi chú |
|---|---|---|---|
| TTS tiếng Việt + clone | **VieNeu-TTS v3 Turbo** | Apache-2.0 | 48kHz, clone từ clip 3–8s, 25 giọng preset 3 miền, streaming OpenAI-compatible |
| TTS đa ngôn ngữ (non-vi) | Chatterbox | MIT | 23+ ngôn ngữ, không có tiếng Việt |
| TTS đa ngôn ngữ (thay thế) | CosyVoice | Apache-2.0 | 9 ngôn ngữ |
| STT | faster-whisper (large-v3) | MIT | Whisper gốc MIT |
| Diarization | pyannote 3.1 | MIT code | HF gated — accept 4 repo: speaker-diarization-3.1, segmentation-3.0, wespeaker-voxceleb-resnet34-LM, speaker-diarization-community-1 |
| Translation | Qwen LLM local | Apache-2.0 | **Không dùng NLLB** (CC-BY-NC) |
| Loại trừ | F5-TTS (checkpoint CC-BY-NC), XTTS-v2 (CPML), NLLB (CC-BY-NC) | ❌ | không đạt chuẩn OSS thương mại |

⚠️ VieNeu **v4 là proprietary** (không open-source, chỉ qua API vieneu.io) — dùng v3 Turbo,
bản open-source mới nhất. Tính năng Dubbing/Lecture/TikTok của VieNeu chỉ có trong app
chính thức; repo chỉ cung cấp core SDK → pipeline dub (D5) là phần chúng ta tự viết.

## Lộ trình 7 ngày

- [x] **D1** Skeleton: docker-compose (postgres/redis/minio/api/worker), API shape,
      timing-fit engine + selftest
- [x] **D2** Postgres schema (users, jobs, credits, api_keys, voices) + Celery dispatch
      + credit metering — selftest: `PYTHONPATH=. python tests/test_day2.py`
- [x] **D2.5** Provider layer: local ↔ OpenAI-compatible cloud + fallback chain
      — selftest: `PYTHONPATH=. python tests/test_providers.py`
- [x] **D3** STT pipeline: faster-whisper large-v3 + pyannote diarization → SRT có speaker
      — PASS trên RTX 3060: 4 segments, 2 speakers tách đúng, SRT xuất chuẩn
- [x] **D4** TTS + voice cloning: **VieNeu v3 Turbo** (vi) + Chatterbox (multilingual);
      voice profiles từ reference clip 3–8s
      — PASS trên RTX 3060: clone từ clip 6.6s → nói văn bản mới, round-trip ASR 89%
- [x] **D5** Full dub pipeline: dịch → TTS per segment → timing-fit → ffmpeg mix;
      UI upload + preview (Next.js)
      — PASS trên RTX 3060: dub vi→en 13.4s→13.9s, 2 speakers giữ đúng giọng,
      round-trip ASR tiếng Anh p=1.00 (34 từ)
- [x] **D6** Developer API hoàn chỉnh: API keys, rate limit, webhook, credit metering
      + **Settings UI** (`/admin`): mọi cấu hình (HF token, cloud translation, pricing)
      quản lý qua giao diện, lưu DB — secret mã hóa Fernet at rest, KHÔNG hardcode .env
      — PASS trên GPU box: PUT/GET settings, secret masked `••••oken`, job qua API
      đọc pricing từ Settings (credits_charged=5), keys create/revoke
- [x] **D7** Deploy + polish: supervisor service (auto-restart) + portal Caddy (token auth),
      video dubbing (MP4 in/out), background mode (silence/source_low)
      — PASS: video dub vi→en MP4 13.3s, ASR round-trip en p=1.00, external URL sống

## Kết quả challenge (26/09 – 03/10/2026) — 7/7 ngày ✅

| Tính năng YupVox | Clone | Verify trên RTX 3060 |
|---|---|---|
| Chuyển văn bản thành giọng nói (TTS) | ✅ VieNeu v3 Turbo (Apache-2.0) | preset + streaming OK |
| Chuyển giọng nói thành văn bản (STT) | ✅ faster-whisper large-v3 (MIT) | vi p=1.00 |
| Dịch video (dubbing) | ✅ full pipeline | MP4 vi→en 13.3s, ASR p=1.00 |
| Tự nhận diện nhiều người nói | ✅ pyannote 3.1 | 2 speakers tách đúng |
| Clone & giữ đúng voice từng nhân vật | ✅ zero-shot 3–8s clip | round-trip 89% |
| Đồng bộ voice với timing | ✅ timing-fit engine | speed 1.34 auto-fit |
| Xử lý cloud | ✅ API + jobs + storage | supervisor + portal URL |
| API cho developer | ✅ keys/rate-limit/webhook | admin UI live |
| **Settings UI (yêu cầu riêng)** | ✅ DB-backed, Fernet at rest | `/admin` live external |

Chi phí GPU toàn bộ challenge: **~$2.5** (RTX 3060).

---

# 🏠 Self-host trong 5 phút

Mã nguồn mở 100% (Apache-2.0). Không bắt buộc GPU — chạy được trên máy cá nhân.

## Bước 0 — Yêu cầu chung

```bash
git clone <repo-url> && cd yupvox-clone
cp .env.example .env
# Sinh master key (BẮT BUỘC — mã hóa secret settings):
openssl rand -hex 32   # dán vào SETTINGS_MASTER_KEY trong .env
```

**HF token (cho pyannote diarization):** tạo token read tại
`huggingface.co/settings/tokens`, rồi accept điều khoản ở 4 repo:
`pyannote/speaker-diarization-3.1` · `pyannote/segmentation-3.0` ·
`pyannote/wespeaker-voxceleb-resnet34-LM` · `pyannote/speaker-diarization-community-1`.
Token dán vào `.env` HOẶC set sau qua `/admin/settings` (khuyến nghị).

## Lựa chọn A — Máy cá nhân KHÔNG GPU (CPU-only)

Toàn bộ pipeline chạy CPU: VieNeu ONNX torch-free (RTF ~0.5),
faster-whisper int8, pyannote CPU (chậm hơn nhưng chạy được), opus-mt CPU.

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r backend/requirements-api.txt
pip install faster-whisper pyannote.audio vieneu srt soundfile sentencepiece numpy cryptography
sudo apt install -y ffmpeg   # hoặc brew install ffmpeg (macOS)
cd backend
YUPVOX_INLINE=1 MEDIA_ROOT=./media uvicorn app.main:app --port 8000
# Mở http://localhost:8000 → nhập API key dev-key-1
```

## Lựa chọn B — Máy có GPU (NVIDIA)

```bash
# như A, nhưng thêm:
pip install torch==2.8.0 torchaudio==2.8.0 --index-url https://download.pytorch.org/whl/cu128
# GPU tự nhận: whisper ~10× nhanh, dub 13s audio xong trong ~20s
```

## Lựa chọn C — VPS / Docker Compose

```bash
docker compose up -d --build   # postgres + redis + minio + api + worker
# Worker GPU: bỏ comment phần deploy.resources trong docker-compose.yml
# + cài nvidia-container-toolkit trên host
```

## Sau khi chạy

1. Mở `http://<host>:8000/admin` → đăng nhập `admin-dev-key`
   → **ĐỔI NGAY `admin.api_key`** (category security).
2. Set `hf_token` trong UI (credentials) nếu chưa có trong .env.
3. (Tùy chọn) Cấu hình cloud translation trong UI: `translate.base_url` +
   `translate.api_key` + `translate.model` — hoạt động với **bất kỳ backend
   chuẩn OpenAI**: vLLM · SGLang · LMDeploy · TGI · Ollama · llama.cpp-server ·
   LiteLLM · DeepSeek · OpenAI · Groq. Không cấu hình = dùng opus-mt local
   (Apache-2.0, ~300MB, đủ dùng cho subtitle).
4. Mở `/` → upload video/audio → Dub.

## ⚖️ Trách nhiệm khi dùng voice cloning

Clone giọng nói công nghệ nhạy cảm: CHỈ clone giọng CỦA BẠN hoặc khi có
SỰ ĐỒNG Ý rõ ràng của chủ giọng. Không dùng để mạo danh người khác.
Người tự-host chịu trách nhiệm tuân thủ pháp luật địa phương về quyền
chân dung và dữ liệu cá nhân.

## 📐 Specs cho contributor

Kiến trúc chi tiết trong `.specs/`:
`01-db-schema.md` · `02-backend-api.md` · `03-ui-layout.md` ·
`04-components.md` · `05-integration.md` — đọc file tương ứng trước khi
sửa tầng đó.

## Phần cứng

### VRAM (ước tính, chạy tuần tự trên 1 GPU)

| Thành phần | VRAM | Ghi chú |
|---|---|---|
| faster-whisper large-v3 | ~4.7 GB fp16 / ~3.1 GB int8 | int8 đủ cho SRT (ước tính) |
| pyannote diarization-3.1 | ~1.5–2 GB | model nhỏ; cần HF_TOKEN (gated) |
| Qwen3-4B-Instruct-2507 (int4) | ~3.5–4.5 GB | dịch phụ đề; cap context 8–16K |
| Qwen2.5-7B-Instruct-AWQ (int4) | ~5.5–6.5 GB | chất lượng cao hơn, hỗ trợ tiếng Việt chính thức |
| VieNeu v3 Turbo | ~1–3 GB | streaming 1.1GB peak @16 streams (đo trên RTX 3060) |
| LoRA finetune VieNeu (tùy chọn) | ~6 GB | 10–30 phút audio / giọng |

### Ngân sách 12GB — pipeline chạy theo PHA, không cần all-resident

| Pha | Model | VRAM ước tính |
|---|---|---|
| 1. STT + diarize | whisper int8 + pyannote | ~5 GB |
| 2. Dịch | Qwen3-4B int4 (hoặc 7B-AWQ) | ~4 GB (7B: ~6 GB) |
| 3. TTS + mix | VieNeu v3 Turbo | ~2–3 GB |
| **Peak** | | **~6 GB → 12GB dư dả** |

All-resident (whisper int8 + pyannote + 4B int4 + VieNeu) ≈ 11 GB — gần tràn,
chỉ dùng khi cần throughput. Mẹo: `PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True`
để giảm phân mảnh; với vLLM đặt `--max-model-len 8192` (KHÔNG để 262K mặc định của
Qwen3 — sẽ OOM trên 12GB).

### Thuê GPU cloud (giá kiểm chứng 26/09/2026 — biến động theo giờ/thị trường)

| GPU | VRAM | Vast.ai (from / median) | RunPod (Secure) | Đủ cho |
|---|---|---|---|---|
| RTX 3060 | 12 GB | $0.03 / $0.07 | — | toàn bộ pipeline D3–D5 |
| RTX 3090 | 24 GB | $0.11 / $0.17 | $0.50 | pipeline + headroom |
| RTX A5000 | 24 GB | $0.14 / $0.23 | $0.27 | pipeline + headroom |
| RTX 4090 | 24 GB | $0.14 / $0.49 | $0.74 | pipeline + dev nhanh |
| L4 | 24 GB | $0.16 / $0.32 | $0.49 | pipeline + headroom |
| L40S | 48 GB | $0.47 / $0.80 | $1.09 | overkill cho D3–D5 |

Chiến lược:
- **Dev D3–D5**: Vast.ai interruptible (rẻ hơn 50%+, có thể bị thu hồi — checkpoint
  thường xuyên) hoặc on-demand per-second. RTX 3090 median $0.17/hr là giá trị tốt nhất.
- **Demo/prod D7**: RunPod Secure Cloud (chuyên dụng, ổn định) hoặc RunPod Serverless
  (per-second; 3090/A5000/L4 $0.69/hr, 4090 $1.10/hr).
- **Storage**: RunPod $0.07–0.10/GB/tháng; cache model ~10GB → ~$1/tháng.

### Ngân sách ước tính D3–D5

~25–40 giờ GPU (dev + debug + test): RTX 3090 ≈ **$5–10**, RTX 4090 ≈ **$15–25**.
Không kể thời gian CPU-only (VieNeu chạy được CPU RTF ~0.5, torch-free).

## Chạy thử timing engine (không cần GPU)

```bash
cd backend && python -m app.pipelines.dub --selftest
```
