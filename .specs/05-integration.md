# 05 — Integration (Data Flow)

## Luồng Job (dub为例 — các type tương tự)
```
UI (fetch, X-API-Key)
  → POST /v1/media/upload        → storage key (Local FS hoặc S3/MinIO)
  → POST /v1/jobs {type:dub,...} → trừ credits + ledger → Job(queued)
  → dispatch():
      YUPVOX_INLINE=1 → dispatch_inline()  (cùng tiến trình, dev/máy cá nhân)
      else            → Celery "pipeline.run" → GPU worker (prod, 1 job/lúc)
  → _run_dub:
      _resolve_media (path | storage key)
      → dub_audio: ffmpeg extract → faster-whisper (STT) → pyannote (diarize)
        → merge speakers → translate (Settings-driven: cloud OpenAI-compatible
        hoặc opus-mt local) → VieNeu TTS per speaker (auto-assign preset)
        → timing-fit (max_speed từ Settings) → ffmpeg amix → mux MP4 nếu video
      → Job(done) + result_s3_key → webhook (nếu có)
  → UI poll GET /v1/jobs → GET /media/{key}?api_key= (player inline)
```

## State management
- Server: Postgres/SQLite là source of truth (jobs, credits, settings).
- UI: không state library — localStorage chỉ giữ API key; mọi dữ liệu fetch theo tab.

## Auth flow
- User: X-API-Key (DB `api_keys` hoặc dev fallback env) → rate limit 60/phút per key.
- Admin: X-Admin-Key (settings `admin.api_key`, bootstrap từ env).
- Media serving: query param `api_key` (browser media tag giới hạn).

## Settings flow (không restart)
`set_setting` → ghi DB (Fernet nếu secret) → `_CACHE_TS = 0` →
lần đọc kế tiếp (TTL 5s) reload → pipeline đọc qua `get_setting` →
**cấu hình mới có hiệu lực ≤5s mà không cần khởi động lại**.

## Env var contract (duy nhất được phép)
`DATABASE_URL` · `SETTINGS_MASTER_KEY` — bootstrap secrets.
Mọi biến khác (HF_TOKEN, TRANSLATE_*, YUPVOX_ADMIN_KEY, YUPVOX_API_KEYS,
MEDIA_ROOT) chỉ là DEV FALLBACK khi DB chưa có entry.

## Phase 2 — luồng xác thực

```
Lần đầu:  GET / ─(chưa có admin)─► /setup ─POST /v1/auth/setup─► tạo admin + cookie ─► /
Sau đó:   GET / ─(chưa đăng nhập)─► /login ─POST /v1/auth/login─► cookie ─► /  (admin ─► /admin)
Máy gọi:  X-API-Key: yv_…  ──► user_from_api_key (kiểm active + rate limit)
Media:    <img|audio|video> tự gửi cookie  ──► _owns_media ──► 200 | 404
```

Env mới (đều là bootstrap/ops, không phải cấu hình nghiệp vụ):
`YUPVOX_SECURE_COOKIES` (ép cookie Secure khi proxy thiếu `X-Forwarded-Proto`),
`YUPVOX_ENABLE_DOCS` (mở `/docs`).

**Đã bỏ mặc định:** `YUPVOX_ADMIN_KEY` (rỗng = tắt đường key) và `YUPVOX_API_KEYS`
(rỗng = không dev key) — trước đây là `admin-dev-key` / `dev-key-1`, tức backdoor luôn mở.

## Phase 3 — luồng cấu hình AI

```
/admin (tab AI) ──► POST /v1/admin/providers        (key mã hóa Fernet)
                ──► POST …/{id}/test                 backend gọi {base}/models | /api/version
                ──► GET  …/{id}/models               danh sách model
                ──► POST …/{id}/pull                 proxy stream NDJSON → thanh tiến trình
                ──► PUT  /v1/admin/stages/{stage}    gán công đoạn → model
                ──► PUT  /v1/admin/prompts/{key}     sửa prompt hệ thống

Pipeline dịch: build_translator()
  stage_translator()  ← stage_models (provider+model, key giải mã tại chỗ)
    └─ None → _pick_backend() → translate.* settings → LocalMarianTranslator
  prompt: prompts.get_prompt('translate')  (DB → mặc định trong code)
```
