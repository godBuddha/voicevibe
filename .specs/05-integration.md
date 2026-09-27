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
