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
| POST | /v1/keys | Tạo key `vv_...` — hiện 1 lần |
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
`VOICEVIBE_INLINE=1` (mặc định dev/máy cá nhân): chạy trong tiến trình API, không cần Redis.
`VOICEVIBE_INLINE=0`: Celery qua Redis, worker GPU 1 job/lúc (prefetch=1, acks_late).
Job types: `tts` ✅ · `stt` ✅ · `dub` ✅ · `translate` ✅ · `subtitle` ✅ (hết stub).

## Bổ sung (hardening pass 27/09)
| Method | Path | Mô tả |
|---|---|---|
| POST | /v1/auth/signup | `{email}` → 201 `{user_id, key}` — rate limit 5/phút/IP; trùng email → 409 |
| GET | /v1/pricing | Bảng credits/job từ Settings (admin sửa được) |

- POST /v1/jobs `type=subtitle` → **202**, pipeline thật (STT + tách người nói →
  SRT/VTT/ASS). Tham số riêng: `format` (`srt`|`vtt`|`ass`), `bilingual` (bool),
  `show_speaker` (bool). Cấu hình thiếu/sai bị chặn **422 TRƯỚC khi trừ credit**
  (thiếu `media_url`; `format` lạ; `bilingual` mà không có `target_lang`).
- **API key lưu SHA-256 hash** (cột `key`), cột `prefix` để hiển thị masked; DELETE /v1/keys/{raw}.
- **Refund**: job failed hoàn 100% credits (ledger `refund:job:<type>`); `_set_failed(job, exc, db)`.
- Webhook kèm `X-VoiceVibe-Signature` = HMAC-SHA256(`webhook.secret`, body) khi secret được set trong Settings.
- `_run_tts` kiểm tra ownership voice profile (chống IDOR).
- Storage: `S3_ENDPOINT` set → S3/MinIO (S3Storage); không → LocalStorage `MEDIA_ROOT` (mặc định `./media`).
- Celery: `task_default_queue="media"` khớp worker `-Q media`.

## Phase 2 — xác thực & phân quyền

**Hai đường, một chữ ký:** cookie phiên `vv_session` (trình duyệt) HOẶC `X-API-Key`
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

## Settings Hub — hồ sơ / phiên / audit / config (30/09)

Router riêng `app/settings_api.py` (mount trong `main.py`). CSRF tự bao phủ qua
`auth_optional` (`_check_csrf`); KHÔNG cần code thêm. Sai mật khẩu hiện tại trả
**403, KHÔNG 401** — `client.js` coi 401 là hết phiên (đá ra /login giữa lúc gõ).

Cá nhân (`Depends(auth)`):
- `PATCH /v1/me` `{name 1..120}` — tên hiển thị lưu `users.name` (nullable).
- `POST /v1/me/password` `{current_password, new_password}` — rate 5/phút; sai
  current → 403; yếu → 422 (`password_problem`); đổi xong thu hồi mọi phiên
  KHÁC (giữ phiên hiện tại) → `{ok, sessions_revoked}`.
- `GET /v1/me/sessions` — list `{token_hash, current, ip, user_agent…}`.
- `DELETE /v1/me/sessions/{hash}` — khác chủ → **404**; `DELETE /v1/me/sessions` —
  thu hồi mọi thiết bị khác.

Hệ thống (`Depends(current_admin)`):
- `GET /v1/admin/audit` `q/action/user_id/limit≤200/offset` + total (enrich user_email).
- `GET /v1/admin/overview` — jobs by_type/by_status toàn hệ + users/voices/api_keys/providers/models.
- `GET /v1/admin/system` — db/queue/storage/python/password_min_length. KHÔNG giá trị secret.
  `storage.root` lấy từ ENV (`get_storage`) — setting DB `media_root` chỉ hiển thị.
- `GET /v1/admin/config/export` — settings non-secret (source=db) + stub `{key, secret:true}`
  cho secret; providers KHÔNG api_key; stages; prompts.
- `POST /v1/admin/config/import` — shape xấu → 422; upsert idempotent (provider theo
  name, stage theo stage+order); phần thiếu → `warnings`, không chết cả file.

Audit (`app/audit.py`): `log_action()` best-effort (SessionLocal riêng, try/except —
không bao giờ gãy request); bảng `audit_logs` **không FK users** (nhật ký sống sót
khi user bị xoá); CHỈ GHI hành động, GET không sinh dòng. Danh sách action:
`app.audit.ACTIONS` (auth.*, me.*, user.*, provider.*, stage.*, model.toggle,
setting.*, key.*, prompt.*, job.*, config.import).

## Lồng tiếng tái tục + dịch batch (Giai đoạn A — port OpenCreator/KrillinAI, 02/10)

### Sổ tay công đoạn (A1) — `app/pipelines/manifest.py`
- Workdir bền: `MEDIA_ROOT/jobs/{job_id}/work/` (container read_only → chỉ volume
  media ghi bền được; cùng tiền tố kết quả nên xóa job dọn một phát). MEDIA_ROOT
  không ghi được → rơi tmpdir (mất resume, không chết job).
- `manifest.json` (schema v=1): `job_id/params_fp/stages{name:{ok,error,updated_at}}/
  outputs{...}/warnings[]`. Ghi NGUYÊN TỬ (temp→fsync→os.replace→fsync dir).
  "Xong" = cờ ok VÀ file output tồn tại size>0 (worker bị revoke kill thì
  `finally` không chạy — không tin cờ một mình).
- `params_fingerprint` = sha256 các tham số ảnh hưởng kết quả (ngôn ngữ, giọng,
  background_mode, max_speed, batch, prompt, media_url, backend_tag). Lệch →
  đổi tên `manifest.json.stale` + chạy lại sạch (không trộn hai cấu hình).
- Stage dub: `prepare → stt → translate → tts → fit → mix → mux`. TTS checkpoint
  TỪNG segment (`tts_progress.json`); STT chia đoạn checkpoint TỪNG đoạn
  (`stt_progress.json`); dịch checkpoint TỪNG batch (`translation.json`).
- A2 `split_points.py`: audio >300s chia tại điểm YÊN TĨNH nhất ±8s quanh mốc
  (PCM 3kHz, cửa sổ năng lượng 1.5s, tâm cửa sổ; đuôi <10s gộp; guard ≥20s).
- `JobCancelled` (raise từ dub_audio qua `abort_check`) → `_run_dub` ép
  status=cancelled (chống race requeue set running lại) + error lời nhắc
  "Chạy lại". `_abort_probe(job_id)` đọc DB cache 2s — không dập DB.
- A5 `estimator.py`: ước lượng đọc theo ngôn ngữ TRƯỚC khi TTS (profile `vi`
  16 ký tự/s + phạt dấu câu/số/viết tắt; các ngôn ngữ khác theo bảng gốc
  KrillinAI) → đoạn chắc chắn vượt `slot + GAP_TOLERANCE(1.5)` xin bản ngắn
  hơn TRƯỚC; hiệu chuẩn EMA 0.7/0.3 kẹp [0.5,1.5] học từ thời lượng đo thật
  giữa job. `plan_timing` thêm `warning` theo ngưỡng 1.15/1.30 (trần vẫn 1.35).

### Dịch batch (A3) — `app/pipelines/translate_batch.py`
- `BatchTranslator.translate_all(origins)` — 12 câu/lượt (job params
  `batch_size` > `StageModel.params.batch_size` của công đoạn translate >
  setting `translate.batch_size`) + ngữ cảnh ±2 câu (`context_sentences`,
  tương tự) đánh máy "KHÔNG dịch". Trả JSON `{"translations":[{index,text}]}` —
  xác thực nghiêm (đủ số/index 1..n không trùng/không rỗng).
- Fail → bisect chia đôi đệ quy; đáy 1 câu → `tr.translate` (chain đầy đủ);
  hỏng nốt → giữ nguyên văn + warning vào manifest. Checkpoint sau mỗi batch
  (chỉ dịch phần còn `null` khi resume; fingerprint origins — lệch văn bản →
  dịch lại từ đầu).
- `_extract_json_object`: trích JSON khỏi fence markdown/prose/phẩy thừa
  (quét ngoặc tôn trọng chuỗi). KHÔNG dùng `json_mode` provider (endpoint lạ
  trả 400 cho response_format).
- Prompt mới `translate_batch` trong `DEFAULT_PROMPTS` (system message); override
  Thư viện Prompt = system, danh sách câu + JSON contract = user message.
- `batch_capable(tr)`: CloudChat → `_chat`; ChainTranslator → completer entry
  đầu; Marian local → None (dịch từng câu như cũ).

### Endpoint mới
- `POST /v1/jobs/{id}/retry` — chủ job hoặc admin; chỉ failed/cancelled
  (queued/running/done → 409). Reset queued/progress 0/error None, GIỮ params +
  result_key (kết quả cũ tải được tới khi lần mới xong), dispatch lại + lưu
  task_id. Audit `job.retry`.
- `DELETE /v1/jobs/{id}` nay dọn `delete_prefix("jobs/{id}/")` (kết quả +
  workdir); key legacy `jobs/dub/<hash>` (dub cũ) dọn riêng CHỈ khi type=dub —
  file TTS dùng chung `jobs/tts/…` không bao giờ đụng.
- `Storage.delete_prefix(prefix)`: Local = rmtree (qua guard traversal); S3 =
  list + remove_objects batch 1000 (generator LỜI — phải duyệt hết kết quả lỗi,
  không duyệt là KHÔNG xoá gì).
- `JobIn`: `prompt_id` chấp nhận cho type `translate` **và `dub`** (422 còn lại).
- GET jobs vẫn cùng shape; thêm `params.stage` (msg công đoạn, 80 ký tự) +
  `params.stt_dropped*` như cũ. adaptJob SPA pass-through — không phá.

## Giai đoạn B — tính năng mới (port OpenCreator/youwee, 03/10)

### B1 — nhập từ URL (yt-dlp)
- `pipelines/download.py`: CLI subprocess `python -m yt_dlp` với
  `start_new_session=True` + `os.killpg` khi hủy (yt-dlp mồ côi = rác .part).
  FORMAT_LADDER (port youwee format.rs): 1080/720/480 mp4-m4a, audio mp3.
  ERROR_MAP ~20 substring → message tiếng Việt có gợi ý. `ensure_downloaded`
  ghi marker `download.json` (url+quality+cookies+file size>0) trong workdir
  bền — retry KHÔNG tải lại; **đổi chế độ cookies giữa chừng → tải lại**
  (marker ẩn danh không được reuse thành "đã có bản cookies"; marker cũ
  trước GB8 không có khoá `cookies` — coi như ẩn danh, nâng cấp không phá
  resume). Gate duration ≤ 7200s kiểm bằng Python SAU probe
  (match_filter chỉ "skip" + exit 0 — job tưởng thành công). URL validate
  http(s), từ chối `-`. Cookie chỉ nhận khi dòng đầu đúng `# Netscape HTTP
  Cookie File` (port youtube_cookies.go).
- Endpoint: `POST /v1/download/preview` (auth, rate 20/phút, timeout 60s) —
  `{url, use_cookies}` → `{title, duration, thumbnail, uploader, webpage_url,
  ext}`; `use_cookies=true` mà chưa cấu hình cookies → 422.
- Settings: `download.cookies_file` (path Netscape, không secret),
  `download.proxy` (secret).
- JobIn mới (khai tường minh — bài học pydantic nuốt âm thầm): `source_url`,
  `quality`, **`use_cookies` (GB8: mặc định FALSE — tải ẨN DANH; TRUE thì
  dùng cookies file đã cấu hình, chưa cấu hình → 422 lúc tạo job)**,
  `sub_source` (auto|youtube|whisper), `tts_backend`
  (local|edge|cloud), `subtitle_key`, `subtitle_job_id`, `burn_subtitles`,
  `vertical`, `banner{major,minor}`, `with_subs`.
- `_download_source(job_id, params, storage)` — chung cho
  dub/stt/subtitle/render/summary khi dán link; cookies CHỈ truyền khi
  `params.use_cookies` (mặc định ẩn danh — an toàn tài khoản Google, khó
  bị YouTube flag IP); file tải về tên cố định
  `work/source.{ext}` → source_url/quality PHẢI trong vân tay
  (`params_fingerprint` += source_url/quality/sub_source/tts_backend;
  `use_cookies` CỐ Ý KHÔNG nằm trong vân tay — retry reuse file đã tải).

### B2 — phụ đề YouTube sẵn có
- `pipelines/youtube_subs.py` (port youtube_subtitle.go): chọn track
  auto`-orig` → manual → auto; LOẠI track đã bị dịch (`tlang=` trong URL
  caption); canonical lang iw→he, zh-hans→zh. Parser VTT tự viết (pysubs2 rối
  với word-timestamp inline — cue đầu dòng `<ts>` bị missed-start); word-level
  ghép câu + khử từ lặp cue rolling. `_youtube_transcript`: auto = lấy nếu có
  không thì rơi Whisper; youtube = fail rõ; whisper = luôn nghe lại.
  Captions vào dub → BỎ WHISPER, vẫn diarize.

### B3+B4 — job `render`
- `pipelines/render.py`: stage `prepare→subtitles→vertical→burn` (manifest
  job_type="render", stage tắt KHÔNG mark). ASS 2 style 1 Dialogue
  (`{\rMajor}…\N{\rMinor}`, port srt_embed.go:767-778), không ghi PlayResX/Y
  (384×288 mặc định); wrap theo rune-width (port bảng hệ số) + MỞ RỘNG wrap
  latin THEO TỪ. Vertical trước burn (phụ đề đo bề rộng theo frame dọc
  720×1280). Banner Pillow→PNG→`overlay` qua `-filter_complex` (overlay là
  filter 2 input — không nhét `-vf` được, gặp thật). crf 20 thay bitrate.
  `render_fingerprint` SOI TOÀN BỘ material (params_fingerprint của dub bỏ
  qua key lạ — bẫy thật).
- Nguồn phụ đề: `subtitle_key` XOR `subtitle_job_id` (422 khi cả hai; job
  phải done + cùng chủ + ext srt/vtt/ass).

### B4b — dub with_subs + quyền đọc output phụ
- dub kwarg `with_subs` → `bilingual.srt` sau mux (stage "subs"); KHÔNG nằm
  trong vân tay (hàm thuần của translations — bật/tắt chỉ chạy thêm khâu).
  `manifest.read_outputs(workdir)` accessor.
- `_owns_media` THÊM HỌ KHOÁ `jobs/{job_id}/…` đối chiếu CHỦ JOB (output phụ
  không là result_key của job nào — 404 trước đây với chính chủ). Test 2 chiều.

### B5 — đa TTS provider 2 tầng
- `providers/base.py`: `TTSOptions`/`TTSVoice`/`TTSEngine` (tầng 2 tùy chọn);
  tầng 1 `TTSProvider.synthesize(text, voice)` giữ nguyên.
- `providers/edge.py`: EdgeTTSEngine (asyncio.run bọc; mp3 24k → ffmpeg
  48kHz mono wav; retry 3× backoff; list_voices cache 24h, vắng mạng KHÔNG
  raise). `providers/tts_catalog.py`: PRESET_VOICES 3 backend + build_tts +
  parse_voice_ref (LEGACY không dấu `:` = local — job cũ/giọng clone không vỡ)
  + rotate_preset. Dub `tts_backend` + vân tay; `synthesize_with_voice(backend)`;
  endpoint `GET /v1/tts/presets?lang=vi`.

### B6 — job `summary`
- `pipelines/summary.py` (port youwee ai.rs): ≤32k single-shot temp 0.7
  truncate 8000; >32k chunk `\n\n`→câu→hard-cut → map tuần tự kèm
  `<previous_part_summary>` temp 0.3 → reduce batch 8000 → compose. Chống
  injection 3 lớp (Security rule ghim ĐẦU system prompt ở CODE; tag untrusted;
  title tách riêng). `models.STAGES += "summarize"` +
  `STAGE_FEATURES["summarize"]="text_generation"`. Prompt 3 key
  summarize/summarize_map/summarize_compose. Checkpoint transcript.json —
  retry không nghe lại. `get_result` ext "md" → kind text. prompt_id cho
  summary (override single-shot; map/reduce giữ vai trò riêng).
- `OpenAIChatProvider.complete(..., temperature=0.2)` kwarg mới — default
  không đổi.

### Endpoint + settings tổng hợp Giai đoạn B
| Method | Path | Mô tả |
|---|---|---|
| POST | /v1/download/preview | Metadata link trước khi tải (title/duration/thumbnail) |
| GET | /v1/tts/presets | Catalog giọng theo backend local/edge/cloud |
