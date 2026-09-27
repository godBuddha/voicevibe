"""Trang Đăng nhập và Thiết lập lần đầu — inline, không build step.

Dùng chung bộ token màu với UI chính (app/theme.py) nên hai trang này tự có chế độ
sáng/tối. Không hardcode hex — tests/test_theme.py cưỡng chế.
"""
from __future__ import annotations

from .theme import THEME_BOOT, THEME_CSS, THEME_JS

_AUTH_CSS = """
  body { background:var(--bg); color:var(--fg);
         font:14.5px/1.55 system-ui,-apple-system,sans-serif; margin:0;
         min-height:100vh; display:flex; align-items:center; justify-content:center;
         padding:24px; }
  .card { background:var(--card); border:1px solid var(--line); border-radius:18px;
          padding:30px; width:100%; max-width:430px; }
  .mark { width:46px; height:46px; border-radius:14px;
          background:linear-gradient(135deg,var(--acc),var(--acc2));
          display:flex; align-items:center; justify-content:center; font-size:23px;
          margin-bottom:14px; }
  h1 { font-size:21px; margin:0 0 6px; }
  .sub { color:var(--mut); font-size:13px; margin:0 0 22px; }
  label { display:block; color:var(--mut); font-size:12.5px; margin:14px 0 5px; }
  input { background:var(--input); border:1px solid var(--line); color:var(--fg);
          border-radius:10px; padding:11px 13px; width:100%; font:inherit; }
  input:focus { outline:2px solid var(--acc); outline-offset:1px; }
  button.go { background:linear-gradient(90deg,var(--acc),var(--acc2)); border:none;
              color:var(--on-acc); border-radius:11px; padding:12px 22px;
              font-weight:700; cursor:pointer; width:100%; margin-top:22px; font-size:15px; }
  button.go[disabled] { opacity:.6; cursor:default; }
  .msg { margin-top:14px; font-size:13.5px; min-height:20px; }
  .err { color:var(--err); } .ok { color:var(--ok); }
  .note { color:var(--mut); font-size:12.5px; margin-top:18px;
          border-top:1px solid var(--line); padding-top:14px; }
  .theme-btn { position:fixed; top:18px; right:18px; background:var(--card);
               border:1px solid var(--line); color:var(--fg); border-radius:99px;
               padding:8px 14px; cursor:pointer; font-size:13px; }
  .theme-btn:hover { border-color:var(--acc); }
"""

_AUTH_JS = """
const $ = (id) => document.getElementById(id);
function setMsg(text, cls) { const el = $("msg"); el.className = "msg " + (cls || ""); el.textContent = text; }
function busy(on) { $("submit").disabled = !!on; }
async function post(path, payload) {
  const r = await fetch(path, {
    method: "POST", credentials: "same-origin",
    headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload),
  });
  let data = {};
  try { data = await r.json(); } catch (e) {}
  if (!r.ok) throw new Error(data.detail || ("HTTP " + r.status));
  return data;
}
"""

# ---------------------------------------------------------------- Đăng nhập
LOGIN_HTML = """<!DOCTYPE html>
<html lang="vi">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Đăng nhập — YupVox-Clone</title>
__THEME_BOOT__
<style>
__THEME_CSS__
__AUTH_CSS__
</style>
</head>
<body>
<button class="theme-btn" data-theme-label onclick="yvToggleTheme()">🌙 Chế độ tối</button>
<div class="card">
  <div class="mark">🎙️</div>
  <h1>Đăng nhập</h1>
  <p class="sub">YupVox-Clone — AI Voice cho một thế giới mới</p>
  <label for="email">Email</label>
  <input id="email" type="email" autocomplete="username" autofocus
         onkeydown="if(event.key==='Enter')submitLogin()">
  <label for="password">Mật khẩu</label>
  <input id="password" type="password" autocomplete="current-password"
         onkeydown="if(event.key==='Enter')submitLogin()">
  <button class="go" id="submit" onclick="submitLogin()">Đăng nhập</button>
  <div id="msg" class="msg"></div>
  <p class="note">Chưa có tài khoản? Liên hệ quản trị viên để được cấp.</p>
</div>
<script>
__THEME_JS__
__AUTH_JS__
async function submitLogin() {
  const email = $("email").value.trim(), password = $("password").value;
  if (!email || !password) { setMsg("Nhập email và mật khẩu", "err"); return; }
  busy(true); setMsg("Đang kiểm tra…");
  try {
    const d = await post("/v1/auth/login", { email: email, password: password });
    setMsg("Đăng nhập thành công, đang chuyển…", "ok");
    location.href = new URLSearchParams(location.search).get("next") || d.redirect || "/";
  } catch (e) { setMsg(e.message, "err"); busy(false); }
}
yvThemeChanged();
</script>
</body></html>"""

# ------------------------------------------------------- Thiết lập lần đầu
SETUP_HTML = """<!DOCTYPE html>
<html lang="vi">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Thiết lập lần đầu — YupVox-Clone</title>
__THEME_BOOT__
<style>
__THEME_CSS__
__AUTH_CSS__
</style>
</head>
<body>
<button class="theme-btn" data-theme-label onclick="yvToggleTheme()">🌙 Chế độ tối</button>
<div class="card">
  <div class="mark">🚀</div>
  <h1>Tạo tài khoản quản trị</h1>
  <p class="sub">Thiết lập lần đầu — chỉ hiển thị một lần duy nhất</p>
  <label for="email">Email quản trị</label>
  <input id="email" type="email" autocomplete="username" autofocus
         onkeydown="if(event.key==='Enter')submitSetup()">
  <label for="password">Mật khẩu</label>
  <input id="password" type="password" autocomplete="new-password"
         onkeydown="if(event.key==='Enter')submitSetup()">
  <label for="password2">Nhập lại mật khẩu</label>
  <input id="password2" type="password" autocomplete="new-password"
         onkeydown="if(event.key==='Enter')submitSetup()">
  <button class="go" id="submit" onclick="submitSetup()">Tạo tài khoản quản trị</button>
  <div id="msg" class="msg"></div>
  <p class="note">Sau bước này, hệ thống không cho đăng ký công khai nữa — chỉ quản trị
     viên tạo được tài khoản cho người khác, trong trang quản trị.</p>
</div>
<script>
__THEME_JS__
__AUTH_JS__
async function submitSetup() {
  const email = $("email").value.trim();
  const pw = $("password").value, pw2 = $("password2").value;
  if (!email || !pw) { setMsg("Nhập email và mật khẩu", "err"); return; }
  if (pw !== pw2) { setMsg("Mật khẩu nhập lại không khớp", "err"); return; }
  if (pw.length < 8) { setMsg("Mật khẩu phải có ít nhất 8 ký tự", "err"); return; }
  busy(true); setMsg("Đang tạo tài khoản quản trị…");
  try {
    const d = await post("/v1/auth/setup", { email: email, password: pw });
    setMsg("Đã tạo tài khoản quản trị, đang chuyển…", "ok");
    location.href = d.redirect || "/";
  } catch (e) { setMsg(e.message, "err"); busy(false); }
}
yvThemeChanged();
</script>
</body></html>"""

# Nội suy token theme (không dùng f-string: CSS/JS đầy dấu ngoặc nhọn).
def _render(page: str) -> str:
    return (page
            .replace("__THEME_BOOT__", THEME_BOOT)
            .replace("__THEME_CSS__", THEME_CSS)
            .replace("__THEME_JS__", THEME_JS)
            .replace("__AUTH_CSS__", _AUTH_CSS)
            .replace("__AUTH_JS__", _AUTH_JS))


LOGIN_HTML = _render(LOGIN_HTML)
SETUP_HTML = _render(SETUP_HTML)