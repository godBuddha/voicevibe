# 02 — Backend API

Base: FastAPI. Auth: header `X-API-Key` (DB key hoặc dev key). Admin: `X-Admin-Key`.
Lỗi chuẩn HTTP: 401 (key sai) · 402 (thiếu credits) · 404 · 409 (job chưa done) · 413 (file quá lớn) · 422 (payload sai) · 429 (rate limit).

## Jobs
| Method | Path | Mô tả |
|---|---|---|
| POST | /v1/jobs | Tạo job. Body: `{type, media_url?, text?, source_lang?, target_lang?, voice_id?, background_mode?, webhook_url?}` → 202 `{job_id, status, credits_charged, dispatch}` |
| GET | /v1/jobs?limit=20 | List jobs của user (mới nhất trước) |
| GET | /v1/jobs/{id} | Trạng thái: `{status, progress, error, credits_charged}` |
| GET | /v1/jobs/{id}/result | `{download_url}` — chỉ khi done, else 409 |

## Media
| Method | Path | Mô tả |
|---|---|---|
| POST | /v1/media/upload | Multipart `file` → 201 `{media_key, size}` (max 200MB) |
| GET | /media/{key:path}?api_key=... | Serve kết quả (auth qua query param — media tag không gửi header được) |

## Voices
| Method | Path | Mô tả |
|---|---|---|
| POST | /v1/voices | Đăng ký profile (JSON: name, lang, engine, ref_s3_key) |
| POST | /v1/voices/upload | Multipart `file` + `name` → 201 `{voice_id}` (clip 3–8s) |
| GET | /v1/me | `{user_id, credits, voices[]}` |

## API keys
| Method | Path | Mô tả |
|---|---|---|
| POST | /v1/keys | Tạo key `yv_...` — hiện 1 lần |
| GET | /v1/keys | List (masked `••••xxxx`) |
| DELETE | /v1/keys/{key} | Revoke |

## Admin (X-Admin-Key)
| Method | Path | Mô tả |
|---|---|---|
| GET | /admin | Settings UI (HTML) |
| GET | / | App UI (Dub/TTS/Voices/Jobs) |
| GET | /admin/settings | List cấu hình (secret masked `••••xxxx`, kèm `source: db/env/default`) |
| PUT | /admin/settings/{key} | `{value, is_secret?}` — secret mã hóa Fernet at rest |
| DELETE | /admin/settings/{key} | Xóa → fallback env/default |

## Pipeline dispatch
`YUPVOX_INLINE=1` (mặc định dev/máy cá nhân): chạy trong tiến trình API, không cần Redis.
`YUPVOX_INLINE=0`: Celery qua Redis, worker GPU 1 job/lúc (prefetch=1, acks_late).
Job types: `tts` ✅ · `stt` ✅ · `dub` ✅ · `translate`/`subtitle` → stub (D8+).

## Bổ sung (hardening pass 27/09)
| Method | Path | Mô tả |
|---|---|---|
| POST | /v1/auth/signup | `{email}` → 201 `{user_id, key}` — rate limit 5/phút/IP; trùng email → 409 |
| GET | /v1/pricing | Bảng credits/job từ Settings (admin sửa được) |
| GET | /v2/ | Frontend redesign (StaticFiles, song song với UI inline ở /) |

- POST /v1/jobs `type=subtitle` → **501, KHÔNG trừ credits** (pipeline chưa có).
- **API key lưu SHA-256 hash** (cột `key`), cột `prefix` để hiển thị masked; DELETE /v1/keys/{raw}.
- **Refund**: job failed hoàn 100% credits (ledger `refund:job:<type>`); `_set_failed(job, exc, db)`.
- Webhook kèm `X-YupVox-Signature` = HMAC-SHA256(`webhook.secret`, body) khi secret được set trong Settings.
- `_run_tts` kiểm tra ownership voice profile (chống IDOR).
- Storage: `S3_ENDPOINT` set → S3/MinIO (S3Storage); không → LocalStorage `MEDIA_ROOT` (mặc định `./media`).
- Celery: `task_default_queue="media"` khớp worker `-Q media`.
