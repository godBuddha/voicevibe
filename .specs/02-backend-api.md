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

- POST /v1/jobs `type=subtitle` → **501, KHÔNG trừ credits** (pipeline chưa có).
- **API key lưu SHA-256 hash** (cột `key`), cột `prefix` để hiển thị masked; DELETE /v1/keys/{raw}.
- **Refund**: job failed hoàn 100% credits (ledger `refund:job:<type>`); `_set_failed(job, exc, db)`.
- Webhook kèm `X-YupVox-Signature` = HMAC-SHA256(`webhook.secret`, body) khi secret được set trong Settings.
- `_run_tts` kiểm tra ownership voice profile (chống IDOR).
- Storage: `S3_ENDPOINT` set → S3/MinIO (S3Storage); không → LocalStorage `MEDIA_ROOT` (mặc định `./media`).
- Celery: `task_default_queue="media"` khớp worker `-Q media`.

## Phase 2 — xác thực & phân quyền

**Hai đường, một chữ ký:** cookie phiên `yv_session` (trình duyệt) HOẶC `X-API-Key`
(máy gọi). Cả hai trả về cùng `User` ⇒ 13 endpoint `Depends(auth)` cũ không phải sửa.
Header phải khai `Header(None, …)` và coi chuỗi rỗng như không có.

| Method | Path | Ghi chú |
|---|---|---|
| GET | /setup | Chưa có admin → form tạo Admin; đã có → 302 `/login` |
| GET | /login | Chưa có admin → 302 `/setup`; đã đăng nhập → 302 `/` |
| POST | /v1/auth/setup | 201 + cookie. Chốt `system_flags('setup.completed')`; đã setup → **409**; rate 5/phút/IP |
| POST | /v1/auth/login | 401 thông báo chung; rate 10/phút/IP + 20/15 phút/tài khoản |
| POST | /v1/auth/logout | Xoá phiên + cookie |
| GET | /v1/auth/me | Danh tính hiện tại (401 nếu chưa đăng nhập) |
| GET | /v1/admin/users | (admin) danh sách |
| POST | /v1/admin/users | (admin) tạo user; 409 nếu trùng email |
| POST | /v1/admin/users/{id}/reset-password | (admin) đổi mật khẩu + **thu hồi mọi phiên** của user |
| POST | /v1/admin/users/{id}/credits | (admin) cấp/trừ credit, luôn ghi `credit_ledger` |
| POST | /v1/admin/users/{id}/deactivate · /activate | (admin) khoá/mở; khoá ⇒ tắt phiên + API key. **Chặn khoá admin cuối** (409) |

Cổng vào HTML ở **server**: `/`, `/admin`, `/setup`, `/login` đều redirect theo trạng thái
(trước đây chỉ có gate ở client). `/docs` mặc định tắt.

### Quyền sở hữu media (`/media/{key}`)
Xác thực qua `user_from_api_key` (**có** kiểm `ApiKey.active`) hoặc cookie phiên, rồi
`_owns_media`: admin → qua; `media/{user_id}/…` khớp user → qua; còn lại tra
`media_objects` → `jobs.result_s3_key` → `voices.ref_s3_key`. **Thất bại trả 404**, không 404/403
phân biệt — không xác nhận sự tồn tại của file cho người không có quyền.

### Bảo vệ bổ sung
- Mật khẩu: `hashlib.scrypt` (N=2^14, r=8, p=1, dklen=64) — **không thêm dependency nào**.
- CSRF: `SameSite=Lax` + lớp hai — request xác thực bằng **cookie** mà `Origin` khác host → 403.
- `create_job` kiểm tra quyền sở hữu `voice_id` **trước `_charge`** (trước đây chỉ worker
  kiểm tra, tức đã trừ credit rồi mới fail).
- Rate limiter: **Redis** khi có `REDIS_URL` (cửa sổ trượt bằng ZSET + script Lua
  nguyên tử → hạn mức chia sẻ giữa mọi worker/replica); không có Redis thì rơi về
  in-memory **một tiến trình** (hạn mức bị nhân theo số worker). Redis chết giữa
  chừng cũng rơi về in-memory chứ không làm request gãy — đánh đổi có ý thức.
  Dùng `ratelimit.backend()` để biết đang ở backend nào.

## Phase 3 — quản trị AI (đều `Depends(current_admin)`)

| Method | Path | Ghi chú |
|---|---|---|
| GET/POST | /v1/admin/providers | list (**không bao giờ trả key thật**) · tạo |
| PATCH | /v1/admin/providers/{id} | `api_key`: vắng = giữ nguyên · `""` = xoá · có giá trị = thay |
| DELETE | /v1/admin/providers/{id} | gỡ luôn gán công đoạn trỏ tới nó |
| POST | /v1/admin/providers/{id}/test | OpenAI `GET {base}/models` · Ollama `GET {base}/api/version`; lỗi trả `ok:false` (không 500) |
| GET | /v1/admin/providers/{id}/models | OpenAI `data[].id` · Ollama `models[]` (+`parameter_size`, `quantization`) |
| POST | /v1/admin/providers/{id}/pull | proxy `POST /api/pull` → **StreamingResponse NDJSON** (tiến trình) |
| DELETE | /v1/admin/providers/{id}/models/{name} | `DELETE /api/delete`; kind≠ollama → 422 |
| GET/PUT/DELETE | /v1/admin/stages[/{stage}] | gán/bỏ gán công đoạn; trả `summary` đọc được |
| GET/PUT | /v1/admin/prompts[/{task_key}] | prompt hệ thống |
| POST | /v1/admin/prompts/{task_key}/reset | khôi phục mặc định trong code |

**Mọi lời gọi ra nhà cung cấp phát xuất từ BACKEND** — key không đi qua trình duyệt.

### Thứ tự ưu tiên khi pipeline chạy
`stage_models` (công đoạn) → setting `translate.*` (đường cũ) → engine local mặc định.
`build_translator()` dùng `stage_translator()` trước; hàm này bọc try/except nên DB chưa
migrate KHÔNG làm chết pipeline — cứ rơi về đường cũ.

### Ghi chú vận hành
Worker là tiến trình riêng, không đi qua `app.main` → `app/tasks.py` cũng gọi
`ensure_schema` để tự migrate trước khi nhận job.
