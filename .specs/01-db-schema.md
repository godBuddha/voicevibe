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
| key | String(64) PK | `yv_` + 32 hex |
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
