# 01 — Database Schema

Engine: SQLAlchemy 2.0 (Postgres prod / SQLite dev — tự tạo bảng lúc startup, idempotent).

## Bảng

### users
| Cột | Kiểu | Ghi chú |
|---|---|---|
| id | String(12) PK | uuid hex rút gọn |
| email | String(255) UNIQUE, INDEX | |
| credits | Integer | mặc định 50_000 (free credits) |
| created_at | BigInteger | unix seconds |

### api_keys
| Cột | Kiểu | Ghi chú |
|---|---|---|
| key | String(64) PK | `vv_` + 32 hex |
| user_id | FK users.id, INDEX | |
| active | Boolean | |
| rate_limit_per_min | Integer | mặc định 60, enforce ở auth |

### voices
| Cột | Kiểu | Ghi chú |
|---|---|---|
| id | String(12) PK | |
| user_id | FK users.id | |
| name / lang / engine | String | engine mặc định `vieneu` |
| ref_s3_key | String(512) | storage key clip tham chiếu 3–8s |

### jobs
| Cột | Kiểu | Ghi chú |
|---|---|---|
| id | String(12) PK | |
| user_id | FK users.id, INDEX | |
| type | String(16) | tts \| stt \| translate \| dub \| subtitle |
| status | Enum | queued → running → done \| failed |
| progress | Integer | 0–100 |
| params | JSON | tham số job |
| result_s3_key | String(512) NULL | storage key kết quả |
| error | Text NULL | |
| credits_charged | Integer | ghi nhận lúc tạo job |

### credit_ledger (append-only)
| Cột | Kiểu | Ghi chú |
|---|---|---|
| user_id | FK, INDEX | |
| delta | Integer | âm = tiêu |
| reason / job_id | | truy vết |

### settings (Day 6)
| Cột | Kiểu | Ghi chú |
|---|---|---|
| key | String(128) PK | |
| value | Text | JSON thường, hoặc Fernet token nếu is_secret |
| is_secret | Boolean | mã hóa at rest bằng SETTINGS_MASTER_KEY |
| category | String(32) | nhóm hiển thị trên UI |

## Quan hệ & quy tắc
- users 1-n api_keys, 1-n voices, 1-n jobs, 1-n credit_ledger.
- `users.credits` KHÔNG BAO GIỜ đổi mà không có dòng credit_ledger tương ứng.
- Bảng `settings` thay thế .env cho cấu hình nghiệp vụ (quy tắc phân loại cứng).

## Phase 2 — tài khoản, phiên, sở hữu media

### users (cột thêm)
| Cột | Kiểu | Ghi chú |
|---|---|---|
| password_hash | String(255) NULL | `scrypt$N$r$p$salt$hash`; NULL = user cũ chưa có mật khẩu |
| role | String(16) | `user` \| `admin` — String chứ không SAEnum (tránh ALTER kiểu enum của Postgres) |
| is_active | Boolean | khoá tài khoản: chặn đăng nhập, thu hồi phiên + API key |
| last_login_at | BigInteger NULL | |
| updated_at | BigInteger | |

### sessions
`token_hash` String(64) PK (**SHA-256 của token thô** — token thô chỉ nằm trong cookie),
`user_id` FK, `created_at`/`expires_at`(index)/`last_seen_at`, `ip`, `user_agent`.

### system_flags
`key` PK, `value`, `updated_at`. Dùng `setup.completed` làm **chốt nguyên tử** cho `/setup`
(khoá chính unique ⇒ hai request đồng thời không thể cùng thắng).

### media_objects
`key` String(512) PK, `user_id` FK index, `created_at`. Sổ chủ sở hữu media upload;
`/media/{key}` tra bảng này, `jobs.result_s3_key`, `voices.ref_s3_key`.

### api_keys (bổ sung)
`prefix` String(16) — hiển thị masked; `key` lưu SHA-256 (đã có từ hardening trước).

### Migration
`app/migrations.py::ensure_schema(engine)` — `create_all` (bảng thiếu) + `ALTER TABLE ADD
COLUMN` cho cột thiếu (**luôn nullable, không DEFAULT inline**: SQLite từ chối
`ADD COLUMN … NOT NULL` không default trên bảng có dữ liệu) + backfill theo default của model
(callable `_now` → mốc thời gian hiện tại) + tạo index thiếu. Idempotent. Postgres siết
`SET NOT NULL` sau backfill. **Không dùng Alembic.**

## Phase 3 — cấu hình AI

### ai_providers
`id` PK · `name` · `kind` (`openai` \| `ollama`) · `base_url` · `api_key_enc` (**Fernet**,
dùng lại `_fernet()` của settings_service) · `api_key_hint` (4 ký tự cuối) · `prefix_id` ·
`enabled` · `created_at`/`updated_at`.

### stage_models
`id` PK autoincrement · `stage` (index) · `provider_id` FK NULL · `model` · `params` JSON ·
`order` (0 = chính, >0 = dự phòng). Xoá provider thì gỡ luôn các gán trỏ tới nó.

### prompts
`task_key` PK · `content` · `description` · `variables` JSON · `is_default` · `updated_at`.
Prompt **mặc định nằm trong code** (`app/prompts.py::DEFAULT_PROMPTS`) — đó là nguồn sự thật
để nút "Khôi phục mặc định" luôn có đích; `is_default` cho biết row đang lệch khỏi bản gốc.
Seed lúc khởi động (`seed_prompts()`, idempotent).
