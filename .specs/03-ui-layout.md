# 03 — UI Layout

Hai giao diện single-page (vanilla JS, KHÔNG build step — self-host chỉ cần Python):
- `/` → App UI (app/app_ui.py → APP_HTML)
- `/admin` → Settings UI (app/admin_ui.py → ADMIN_HTML)

## App UI `/`
Header: brand + API key (masked) + credits + nút đổi key (localStorage `yv_api_key`).
Tabs dọc theo chiều ngang:

1. **Dub video/audio**: file input (audio/video) → source_lang/target_lang select →
   background_mode (silence | source_low) → submit → toast job_id → tự chuyển tab Jobs.
2. **Text → Speech**: textarea + voice select (từ /v1/me) → submit.
3. **Giọng của tôi**: upload clip 3–8s + tên → POST /v1/voices/upload; list voices.
4. **Jobs**: poll GET /v1/jobs mỗi 6s; job done render player inline
   (audio/video qua `/media/{key}?api_key=`) hoặc link tải SRT.

Trạng thái job: pill màu (queued xám / running vàng + % / done xanh / failed đỏ).

## Admin UI `/admin`
Gate: input admin key → GET /admin/settings.
Render: card theo category, mỗi setting một row
(label + key · input [password nếu secret] · tag nguồn db/env/default · Lưu · Xóa nếu set_in_db).
Cuối trang: form thêm custom key.

## Quy ước
- **Hai chế độ màu: sáng (mặc định) và tối**, cùng một bộ token trong `backend/app/theme.py`
  (`:root` = sáng, `html[data-theme="dark"]` = tối). Không được hardcode màu hex ngoài hai
  khối đó — `tests/test_theme.py` cưỡng chế. Nút lật nằm ở topbar, ghi nhớ ở
  `localStorage['yv_theme']`; `THEME_BOOT` phải chèn TRƯỚC stylesheet để không nhấp nháy màu.
- Viền mảnh phân tách khối, không shadow dày.
- Emoji chỉ làm marker tab/tiêu đề (tradeoff cố ý: không build step).
- Mọi fetch gắn header auth tương ứng; lỗi 401 → về gate.

## Phase 2 — trang & đăng nhập

- `/setup` — *Thiết lập lần đầu* → form **Tạo tài khoản quản trị** (email, mật khẩu, nhập lại).
- `/login` — **Đăng nhập**; lỗi chung *Email hoặc mật khẩu không đúng*.
- `/` — topbar hiện email + vai trò + *Đăng xuất*; **không còn gate API key ở client**
  (localStorage `yv_api_key` đã bỏ), mọi fetch dùng `credentials:"same-origin"`.
- `/admin` — hai tab: *Cấu hình hệ thống* (như cũ) và **Người dùng** (form tạo, bảng
  user với badge vai trò/trạng thái, nút Đặt lại mật khẩu · Cấp credits · Vô hiệu hóa).
- Thông báo dùng **toast dùng chung** (`#toast`) — trước đây `flash()` ghi vào phần tử
  `.status` có thể không tồn tại ở panel hiện tại.
