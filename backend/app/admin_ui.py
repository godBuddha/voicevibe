"""Day 6: admin Settings UI — single page, vanilla JS, no build step.

Served at GET /admin. The page asks for the admin API key and calls
/admin/settings (JSON) with the X-Admin-Key header. Secrets are masked on
read; saving a secret writes an encrypted row (Fernet, at rest).

Màu sắc lấy từ app/theme.py — cùng bảng token với UI người dùng, nên admin
cũng có chế độ sáng/tối và không hardcode hex.
"""
from __future__ import annotations

from .theme import THEME_BOOT, THEME_CSS, THEME_JS

ADMIN_HTML = """<!DOCTYPE html>
<html lang="vi">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>YupVox-Clone — Settings</title>
__THEME_BOOT__
<style>
__THEME_CSS__
  body { background:var(--bg); color:var(--fg); font:15px/1.5 system-ui,sans-serif; margin:0; padding:32px; }
  h1 { font-size:22px; margin:0 0 6px; } .sub { color:var(--mut); margin-bottom:24px; }
  .card { background:var(--card); border:1px solid var(--line); border-radius:12px; padding:18px 20px; margin-bottom:18px; }
  .card h2 { font-size:14px; margin:0 0 12px; color:var(--acc); text-transform:uppercase; letter-spacing:.08em; }
  .row { display:flex; gap:10px; align-items:center; padding:8px 0; border-bottom:1px solid var(--line); flex-wrap:wrap; }
  .row:last-child { border-bottom:none; }
  .k { width:250px; min-width:200px; } .k b { display:block; } .k span { color:var(--mut); font-size:12px; }
  input { background:var(--input); border:1px solid var(--line); color:var(--fg); border-radius:8px; padding:8px 10px; flex:1; min-width:200px; }
  button { background:var(--acc); border:none; color:var(--on-acc); border-radius:8px; padding:8px 14px; cursor:pointer; }
  button.ghost { background:transparent; border:1px solid var(--line); color:var(--mut); }
  .tag { font-size:11px; padding:2px 8px; border-radius:99px; border:1px solid var(--line); color:var(--mut); }
  .ok { color:var(--ok); } .err { color:var(--err); }
  #login { max-width:420px; margin:80px auto; text-align:center; }
  #login input { width:100%; margin:12px 0; }
  .topbar { display:flex; justify-content:space-between; align-items:flex-start; gap:16px; flex-wrap:wrap; }
  .theme-btn { background:var(--card); border:1px solid var(--line); color:var(--fg);
               border-radius:99px; padding:8px 14px; cursor:pointer; font-size:13px; }
  .theme-btn:hover { border-color:var(--acc); }
</style>
</head>
<body>
<div id="login" class="card">
  <h1>⚙️ YupVox-Clone Settings</h1>
  <p class="sub">Nhập Admin API key để quản lý cấu hình hệ thống</p>
  <input id="akey" type="password" placeholder="X-Admin-Key" onkeydown="if(event.key==='Enter')load()">
  <button onclick="load()">Đăng nhập</button>
  <p id="lmsg" class="err"></p>
</div>
<div id="app" style="display:none">
  <div class="topbar">
    <div>
      <h1>⚙️ YupVox-Clone — Settings</h1>
      <p class="sub">Mọi cấu hình lưu DB (secret mã hóa at rest) — không hardcode .env <span id="saved" class="ok"></span></p>
    </div>
    <button class="theme-btn" data-theme-label onclick="yvToggleTheme()">🌙 Chế độ tối</button>
  </div>
  <div id="content"></div>
</div>
<script>
__THEME_JS__
let AKEY = "";
const $ = (id) => document.getElementById(id);

async function api(path, opts = {}) {
  const r = await fetch(path, { ...opts,
    headers: { "X-Admin-Key": AKEY, "Content-Type": "application/json", ...(opts.headers || {}) } });
  if (r.status === 401) { showLogin("Admin key không hợp lệ"); throw new Error("unauth"); }
  return r;
}
function showLogin(msg) { $("login").style.display = ""; $("app").style.display = "none"; $("lmsg").textContent = msg || ""; }
function flash(msg) { $("saved").textContent = "  " + msg; setTimeout(() => { $("saved").textContent = ""; }, 2500); }
function esc(s) { const d = document.createElement("div"); d.textContent = s == null ? "" : String(s); return d.innerHTML.replace(/"/g, "&quot;"); }

async function load() {
  AKEY = $("akey").value;
  try {
    const r = await api("/admin/settings");
    const data = await r.json();
    $("login").style.display = "none";
    $("app").style.display = "";
    render(data.settings);
  } catch (e) { /* showLogin already handled 401 */ }
}

function render(settings) {
  const by = {};
  for (const s of settings) (by[s.category] = by[s.category] || []).push(s);
  let html = "";
  for (const cat of Object.keys(by).sort()) {
    html += `<div class="card"><h2>${esc(cat)}</h2>`;
    for (const s of by[cat]) {
      const val = s.value == null ? "" : s.value;
      html += `<div class="row">
        <div class="k"><b>${esc(s.label)}</b><span>${esc(s.key)}</span></div>
        <input id="in-${esc(s.key)}" type="${s.is_secret ? "password" : "text"}" value="${esc(val)}">
        <span class="tag">${esc(s.source)}</span>
        <button onclick="save('${esc(s.key)}', ${s.is_secret})">Lưu</button>
        ${s.set_in_db ? `<button class="ghost" onclick="del('${esc(s.key)}')">Xóa</button>` : ""}
      </div>`;
    }
    html += "</div>";
  }
  html += `<div class="card"><h2>custom key</h2><div class="row">
    <div class="k"><b>Key mới</b><span>key tuỳ ý, ví dụ provider.custom.url</span></div>
    <input id="new-key" placeholder="key"><input id="new-val" placeholder="value">
    <button onclick="addCustom()">Thêm</button></div></div>`;
  $("content").innerHTML = html;
}

async function save(key, isSecret) {
  const value = $("in-" + key).value;
  const r = await api("/admin/settings/" + encodeURIComponent(key),
                      { method: "PUT", body: JSON.stringify({ value, is_secret: isSecret }) });
  flash(r.ok ? "✔ đã lưu " + key : "✗ lỗi " + r.status);
  if (r.ok) load();
}
async function del(key) {
  if (!confirm("Xóa " + key + "? (sẽ fallback về env/default)")) return;
  const r = await api("/admin/settings/" + encodeURIComponent(key), { method: "DELETE" });
  flash(r.ok ? "✔ đã xóa" : "✗ lỗi");
  load();
}
async function addCustom() {
  const k = $("new-key").value.trim(), v = $("new-val").value;
  if (!k) return;
  const r = await api("/admin/settings/" + encodeURIComponent(k),
                      { method: "PUT", body: JSON.stringify({ value: v, is_secret: false }) });
  flash(r.ok ? "✔ thêm " + k : "✗ lỗi");
  load();
}

yvThemeChanged();  // đồng bộ nhãn nút sáng/tối với theme đã áp ở <head>
</script>
</body></html>"""

# Nội suy token theme (không dùng f-string: CSS/JS đầy dấu ngoặc nhọn).
ADMIN_HTML = (ADMIN_HTML
              .replace("__THEME_BOOT__", THEME_BOOT)
              .replace("__THEME_CSS__", THEME_CSS)
              .replace("__THEME_JS__", THEME_JS))
