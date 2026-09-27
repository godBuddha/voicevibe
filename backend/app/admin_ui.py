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
  select { background:var(--input); border:1px solid var(--line); color:var(--fg);
           border-radius:8px; padding:8px 10px; }
  .topbar { display:flex; justify-content:space-between; align-items:flex-start; gap:16px; flex-wrap:wrap; }
  .theme-btn { background:var(--card); border:1px solid var(--line); color:var(--fg);
               border-radius:99px; padding:8px 14px; cursor:pointer; font-size:13px; }
  .theme-btn:hover { border-color:var(--acc); }
  .tabs { display:flex; gap:8px; margin:22px 0 16px; flex-wrap:wrap; }
  .tabs button { background:var(--card); border:1px solid var(--line); color:var(--mut);
                 border-radius:99px; padding:8px 18px; cursor:pointer; font-size:13.5px; }
  .tabs button.on { border-color:var(--acc); color:var(--fg); font-weight:600; }
  table.users { width:100%; border-collapse:collapse; font-size:13.5px; }
  table.users th, table.users td { text-align:left; padding:9px 8px; border-bottom:1px solid var(--line); }
  table.users th { color:var(--mut); font-weight:500; font-size:12.5px; }
  .badge { font-size:11px; padding:2px 9px; border-radius:99px; border:1px solid var(--line); }
  .badge.admin { border-color:var(--acc); color:var(--acc); }
  .badge.off { border-color:var(--err); color:var(--err); }
  .row-actions { display:flex; gap:6px; flex-wrap:wrap; }
  .row-actions button { padding:5px 10px; font-size:12.5px; }
  #toast { position:fixed; bottom:22px; left:50%; transform:translateX(-50%);
           background:var(--card); border:1px solid var(--line); border-radius:12px;
           padding:12px 20px; font-size:13.5px; z-index:100; display:none; }
  #toast.on { display:block; }
  #toast.ok { border-color:var(--ok); color:var(--ok); }
  #toast.err { border-color:var(--err); color:var(--err); }
</style>
</head>
<body>
<div id="app">
  <div class="topbar">
    <div>
      <h1>⚙️ YupVox-Clone — Quản trị</h1>
      <p class="sub">Mọi cấu hình lưu DB (secret mã hóa at rest) — không hardcode .env <span id="saved" class="ok"></span></p>
    </div>
    <div class="row-actions">
      <button class="theme-btn" data-theme-label onclick="yvToggleTheme()">🌙 Chế độ tối</button>
      <a href="/"><button class="ghost">← Về ứng dụng</button></a>
      <button class="ghost" onclick="logout()">Đăng xuất</button>
    </div>
  </div>
  <div class="tabs">
    <button id="tab-settings" class="on" onclick="showTab('settings')">Cấu hình hệ thống</button>
    <button id="tab-users" onclick="showTab('users')">Người dùng</button>
  </div>
  <div id="pane-settings"><div id="content"></div></div>
  <div id="pane-users" style="display:none"><div id="users"></div></div>
</div>
<div id="toast"></div>
<script>
__THEME_JS__
const $ = (id) => document.getElementById(id);

async function api(path, opts = {}) {
  // Xác thực bằng COOKIE PHIÊN (server đã chặn nếu không phải Admin).
  // KHÔNG gửi header X-Admin-Key: gửi chuỗi rỗng sẽ bị coi là key sai và trả 401.
  const r = await fetch(path, { ...opts, credentials: "same-origin",
    headers: { "Content-Type": "application/json", ...(opts.headers || {}) } });
  if (r.status === 401 || r.status === 403) {
    flash("✗ phiên hết hạn hoặc không đủ quyền", "err");
    setTimeout(() => { location.href = "/login?next=/admin"; }, 1200);
    throw new Error("unauth");
  }
  return r;
}
function flash(msg, cls) { const el = $("toast");
  el.className = "on " + (cls || "ok"); el.textContent = msg;
  clearTimeout(window._t); window._t = setTimeout(() => { el.className = ""; }, 2500); }
function esc(s) { const d = document.createElement("div"); d.textContent = s == null ? "" : String(s); return d.innerHTML.replace(/"/g, "&quot;"); }

function showTab(name) {
  $("pane-settings").style.display = name === "settings" ? "" : "none";
  $("pane-users").style.display = name === "users" ? "" : "none";
  $("tab-settings").classList.toggle("on", name === "settings");
  $("tab-users").classList.toggle("on", name === "users");
  if (name === "users") loadUsers();
}

async function load() {
  try {
    const r = await api("/admin/settings");
    render((await r.json()).settings);
  } catch (e) { /* api() đã điều hướng khi 401/403 */ }
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

// ------------------------------------------------------------ quản lý người dùng
async function loadUsers() {
  const r = await api("/v1/admin/users");
  if (!r.ok) return;
  renderUsers((await r.json()).users);
}

function renderUsers(users) {
  const rows = users.map(u => `<tr>
    <td><b>${esc(u.email)}</b>${u.has_password ? "" : ' <span class="mut">(chưa có mật khẩu)</span>'}</td>
    <td>${u.role === "admin" ? '<span class="badge admin">Quản trị</span>' : '<span class="badge">Người dùng</span>'}</td>
    <td>${u.is_active ? '<span class="badge">Hoạt động</span>' : '<span class="badge off">Đã khoá</span>'}</td>
    <td>${u.credits.toLocaleString("vi-VN")}</td>
    <td class="mut">${u.last_login_at ? new Date(u.last_login_at * 1000).toLocaleString("vi-VN") : "—"}</td>
    <td><div class="row-actions">
      <button class="ghost" onclick="resetPw('${esc(u.user_id)}', '${esc(u.email)}')">Đặt lại mật khẩu</button>
      <button class="ghost" onclick="grantCredits('${esc(u.user_id)}')">Cấp credits</button>
      ${u.is_active
        ? `<button class="ghost" onclick="toggleActive('${esc(u.user_id)}', false)">Vô hiệu hóa</button>`
        : `<button class="ghost" onclick="toggleActive('${esc(u.user_id)}', true)">Kích hoạt</button>`}
    </div></td></tr>`).join("");

  $("users").innerHTML = `
    <div class="card"><h2>Tạo người dùng</h2>
      <div class="row"><div class="k"><b>Email</b><span>bắt buộc</span></div>
        <input id="nu-email" placeholder="email@example.com"></div>
      <div class="row"><div class="k"><b>Mật khẩu</b><span>tối thiểu 8 ký tự</span></div>
        <input id="nu-pass" type="password" placeholder="••••••••"></div>
      <div class="row"><div class="k"><b>Vai trò</b><span>quản trị / người dùng</span></div>
        <select id="nu-role"><option value="user">Người dùng</option>
          <option value="admin">Quản trị</option></select>
        <button onclick="createUser()">Tạo người dùng</button></div>
    </div>
    <div class="card"><h2>Người dùng (${users.length})</h2>
      <table class="users"><thead><tr><th>Email</th><th>Vai trò</th><th>Trạng thái</th>
        <th>Credits</th><th>Đăng nhập gần nhất</th><th></th></tr></thead>
        <tbody>${rows}</tbody></table>
      <p class="sub" style="margin-top:14px">Đăng ký công khai ${users.length ? "" : ""}do Admin bật/tắt
        ở Cấu hình hệ thống → <code>auth.allow_signup</code>.</p>
    </div>`;
}

async function createUser() {
  const body = { email: $("nu-email").value.trim(), password: $("nu-pass").value,
                 role: $("nu-role").value };
  const r = await api("/v1/admin/users", { method: "POST", body: JSON.stringify(body) });
  const d = await r.json();
  if (!r.ok) { flash("✗ " + (d.detail || r.status), "err"); return; }
  flash("✔ đã tạo " + d.email);
  loadUsers();
}
async function resetPw(id, email) {
  const pw = prompt("Mật khẩu mới cho " + email + " (tối thiểu 8 ký tự):");
  if (!pw) return;
  const r = await api(`/v1/admin/users/${id}/reset-password`,
                      { method: "POST", body: JSON.stringify({ password: pw }) });
  const d = await r.json();
  flash(r.ok ? `✔ đã đổi mật khẩu (${d.sessions_revoked} phiên bị đăng xuất)` : "✗ " + (d.detail || r.status),
        r.ok ? "ok" : "err");
  loadUsers();
}
async function grantCredits(id) {
  const v = prompt("Số credits muốn cấp thêm (dùng số âm để trừ):", "1000");
  if (!v) return;
  const r = await api(`/v1/admin/users/${id}/credits`,
                      { method: "POST", body: JSON.stringify({ delta: parseInt(v, 10) || 0 }) });
  const d = await r.json();
  flash(r.ok ? `✔ số dư mới: ${d.credits}` : "✗ " + (d.detail || r.status), r.ok ? "ok" : "err");
  loadUsers();
}
async function toggleActive(id, active) {
  const path = active ? "activate" : "deactivate";
  if (!active && !confirm("Vô hiệu hóa người dùng này? Mọi phiên đăng nhập và API key sẽ bị khoá.")) return;
  const r = await api(`/v1/admin/users/${id}/${path}`, { method: "POST" });
  const d = await r.json();
  flash(r.ok ? (active ? "✔ đã kích hoạt" : "✔ đã vô hiệu hóa") : "✗ " + (d.detail || r.status),
        r.ok ? "ok" : "err");
  loadUsers();
}
async function logout() {
  try { await fetch("/v1/auth/logout", { method: "POST", credentials: "same-origin" }); } catch (e) {}
  location.href = "/login";
}

load();               // trang chỉ được server trả khi đã là Admin
yvThemeChanged();     // đồng bộ nhãn nút sáng/tối với theme đã áp ở <head>
</script>
</body></html>"""

# Nội suy token theme (không dùng f-string: CSS/JS đầy dấu ngoặc nhọn).
ADMIN_HTML = (ADMIN_HTML
              .replace("__THEME_BOOT__", THEME_BOOT)
              .replace("__THEME_CSS__", THEME_CSS)
              .replace("__THEME_JS__", THEME_JS))
