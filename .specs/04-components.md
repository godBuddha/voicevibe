# 04 — Components (vanilla JS, không framework)

Quy ước: mọi thành phần là hàm JS thuần + HTML template string. Không build step,
không node_modules — self-host chỉ cần `python -m uvicorn`.

## App UI (app_ui.py)
| Component | Trạng thái xử lý | Ghi chú |
|---|---|---|
| Gate (API key) | loading → ok / err 401 | localStorage `vv_api_key`, auto-enter nếu còn hạn |
| TabBar | active tab | 4 tab |
| CreditsBadge | GET /v1/me | refresh sau mỗi job |
| FileUploader | upload progress → media_key | dùng cho dub + voice clip |
| DubForm | submit → 202 job_id | validate file chọn trước |
| TTSForm | submit → 202 | voice select đồng bộ /v1/me |
| VoiceList | GET /v1/me | empty state "Chưa có giọng nào" |
| JobList | poll 6s | empty state; pill trạng thái |
| JobResult | done → player inline | wav → `<audio>`, mp4 → `<video>`, srt → link tải |
| Toast/Flash | success / err | timeout 2.5s |

## Admin UI (admin_ui.py)
| Component | Ghi chú |
|---|---|
| AdminGate | X-Admin-Key, 401 → hiện lại gate |
| SettingsGrid | card theo category; input password nếu secret |
| SettingRow | tag nguồn (db/env/default/unset); nút Lưu + Xóa (nếu set_in_db) |
| CustomKeyForm | thêm key ngoài registry |

## Quy tắc lỗi
Mọi fetch bọc try/catch → hiển thị message ngắn trên element trạng thái của tab,
không alert; 401 → reset về gate.

## Phase 2 — components mới

| Component | File | Ghi chú |
|---|---|---|
| SetupForm | `auth_ui.py::SETUP_HTML` | email + mật khẩu ×2, validate ≥8 ký tự phía client, server vẫn kiểm lại |
| LoginForm | `auth_ui.py::LOGIN_HTML` | hiển thị `?next=` sau khi đăng nhập |
| ThemeToggle | `theme.py::THEME_JS` | nút `[data-theme-label]`, nhãn tự đổi theo trạng thái |
| UserTable | `admin_ui.py` | tạo/đặt lại mật khẩu/cấp credits/khoá — gọi `/v1/admin/users/*` |
| Toast | `app_ui.py` + `admin_ui.py` | `#toast` dùng chung thay cho `.status` cục bộ |

Bỏ: **Gate (API key)** ở cả hai UI — thay bằng cổng server-side + phiên cookie.

## Phase 3 — components tab AI

| Component | Ghi chú |
|---|---|
| ProviderList | card/nhà cung cấp: chấm trạng thái, badge loại, hint key, nút Kiểm tra kết nối · Quản lý model (Ollama) · Sửa · Xoá |
| ProviderModal | Tên · Loại · Base URL (kèm helper "Sẽ gọi: {url}/chat/completions") · API key write-only · Prefix ID |
| OllamaModels | liệt kê model (dung lượng/số tham số/lượng tử) · ô tải model + **thanh tiến trình từ NDJSON** · nút Xoá |
| StageTable | mỗi công đoạn: select provider + input model + Lưu/Bỏ gán; dòng **tóm tắt đọc được** |
| PromptEditor | textarea + bảng biến + Lưu + Khôi phục mặc định; badge "đã sửa" khi `is_default=false` |
| Modal | `#modal-bg` dùng chung cho mọi hộp thoại của tab AI |
