"""Day 6: admin Settings UI — single page, vanilla JS, no build step.

Served at GET /admin. The page asks for the admin API key and calls
/admin/settings (JSON) with the X-Admin-Key header. Secrets are masked on
read; saving a secret writes an encrypted row (Fernet, at rest).

Màu sắc lấy từ app/theme.py — cùng bảng token với UI người dùng, nên admin
cũng có chế độ sáng/tối và không hardcode hex.
"""
from __future__ import annotations

from .theme import THEME_BOOT, THEME_CSS, THEME_JS

ADMIN_HTML = r"""<!DOCTYPE html>
<html lang="vi">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>VoiceVibe — Settings</title>
__THEME_BOOT__
<style>
__THEME_CSS__
  body { background:var(--bg); color:var(--fg); font:13.5px/1.5 system-ui,sans-serif; margin:0; padding:20px; }
  h1 { font-size:18px; margin:0 0 6px; } .sub { color:var(--mut); margin-bottom:14px; }
  .card { background:var(--card); border:1px solid var(--line); border-radius:10px; padding:14px 16px; margin-bottom:12px; }
  .card h2 { font-size:14px; margin:0 0 12px; color:var(--acc); text-transform:uppercase; letter-spacing:.08em; }
  .row { display:flex; gap:10px; align-items:center; padding:6px 0; border-bottom:1px solid var(--line); flex-wrap:wrap; }
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
  table.users th, table.users td { text-align:left; padding:7px 8px; border-bottom:1px solid var(--line); }
  table.users th { color:var(--mut); font-weight:500; font-size:12.5px; }
  .badge { font-size:11px; padding:2px 9px; border-radius:99px; border:1px solid var(--line); }
  .badge.admin { border-color:var(--acc); color:var(--acc); }
  .badge.off { border-color:var(--err); color:var(--err); }
  .row-actions { display:flex; gap:6px; flex-wrap:wrap; }
  .row-actions button { padding:5px 10px; font-size:12.5px; }
  /* --- tab AI --- */
  .prov { display:flex; justify-content:space-between; gap:14px; align-items:center;
          padding:12px 0; border-bottom:1px solid var(--line); flex-wrap:wrap; }
  .prov:last-child { border-bottom:none; }
  .prov .meta { min-width:240px; flex:1; }
  .prov .meta b { display:block; }
  .prov .meta code { font-size:12px; }
  .dot { display:inline-block; width:9px; height:9px; border-radius:50%;
         background:var(--mut); margin-right:6px; }
  .dot.ok { background:var(--ok); } .dot.bad { background:var(--err); }
  .grid2 { display:grid; grid-template-columns:repeat(auto-fit,minmax(320px,1fr)); gap:14px; }
  .hint { color:var(--mut); font-size:12px; margin-top:4px; }
  textarea { background:var(--input); border:1px solid var(--line); color:var(--fg);
             border-radius:8px; padding:10px; width:100%; min-height:110px;
             font:13px/1.5 ui-monospace,SFMono-Regular,Menlo,monospace; resize:vertical; }
  .vars { color:var(--mut); font-size:12px; margin:6px 0 0; }
  .vars code { margin-right:6px; }
  .progress { height:8px; border-radius:99px; background:var(--track); margin-top:8px;
              overflow:hidden; display:none; }
  .progress.on { display:block; }
  .progress i { display:block; height:100%; background:var(--acc); width:0; }
  .modal-bg { position:fixed; inset:0; background:rgba(0,0,0,.45); z-index:200;
              display:none; align-items:flex-start; justify-content:center; padding:40px 16px; }
  .modal-bg.on { display:flex; }
  .modal { background:var(--card); border:1px solid var(--line); border-radius:14px;
           padding:22px; width:100%; max-width:560px; max-height:85vh; overflow-y:auto; }
  .modal h2 { margin-top:0; }
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
      <h1>⚙️ VoiceVibe — Quản trị</h1>
      <p class="sub">Mọi cấu hình lưu DB (secret mã hóa at rest) — không hardcode .env <span id="saved" class="ok"></span></p>
    </div>
    <div class="row-actions">
      <button class="theme-btn" data-theme-label onclick="vvToggleTheme()">🌙 Chế độ tối</button>
      <a href="/"><button class="ghost">← Về ứng dụng</button></a>
      <button class="ghost" onclick="logout()">Đăng xuất</button>
    </div>
  </div>
  <div class="tabs">
    <button id="tab-ai" class="on" onclick="showTab('ai')">AI (nhà cung cấp &amp; model)</button>
    <button id="tab-settings" onclick="showTab('settings')">Cấu hình hệ thống</button>
    <button id="tab-users" onclick="showTab('users')">Người dùng</button>
    <button id="tab-audit" onclick="showTab('audit')">Nhật ký kiểm toán</button>
  </div>
  <div id="pane-ai"><div id="ai"></div></div>
  <div id="pane-settings" style="display:none"><div id="content"></div></div>
  <div id="pane-users" style="display:none"><div id="users"></div></div>
  <div id="pane-audit" style="display:none"><div id="audit"></div></div>
</div>
<div id="toast"></div>
<div id="modal-bg" class="modal-bg"><div class="modal" id="modal"></div></div>
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
  ["ai", "settings", "users", "audit"].forEach(n => {
    $("pane-" + n).style.display = n === name ? "" : "none";
    $("tab-" + n).classList.toggle("on", n === name);
  });
  if (name === "users") loadUsers();
  if (name === "settings") load();
  if (name === "ai") loadAi();
  if (name === "audit") loadAudit();
}

async function load() {
  try {
    const r = await api("/v1/admin/settings");
    render((await r.json()).settings);
  } catch (e) { /* api() đã điều hướng khi 401/403 */ }
  loadSystem();
}

// Card TÌNH TRẠNG HỆ THỐNG (read-only) — GET /v1/admin/system, KHÔNG chứa secret.
// Lưu ý thật: runtime đọc env MEDIA_ROOT; setting DB media_root chỉ hiển thị.
async function loadSystem() {
  try {
    const r = await api("/v1/admin/system");
    if (!r.ok) return;
    const d = await r.json();
    const el = $("sysinfo");
    if (!el) return;
    const fmtB = (n) => n == null ? "—" : (n > 1e9 ? (n / 1e9).toFixed(1) + " GB" : Math.round(n / 1e6) + " MB");
    el.innerHTML = `
      <div class="row"><div class="k"><b>Database</b><span>dialect + phiên bản</span></div>
        <span class="tag">${esc(d.db?.dialect || "—")}</span><span class="mut">${esc((d.db?.version || "").slice(0, 40))}</span></div>
      <div class="row"><div class="k"><b>Hàng đợi</b><span>chế độ chạy job</span></div>
        <span class="tag">${esc(d.queue?.mode)}</span><span class="mut">${esc(d.queue?.broker)}</span></div>
      <div class="row"><div class="k"><b>Lưu trữ media</b><span>runtime đọc env MEDIA_ROOT</span></div>
        <span class="tag">${esc(d.storage?.mode)}</span><span class="mut">${esc(d.storage?.root || "")} · trống ${esc(fmtB(d.storage?.free_bytes))}</span></div>
      <div class="row"><div class="k"><b>Job đang chạy</b><span>toàn hệ</span></div>
        <span class="tag">${esc(String(d.jobs_running ?? "—"))}</span><span class="mut">phiên hết hạn chưa dọn: ${esc(String(d.sessions_expired ?? "—"))}</span></div>`;
  } catch (e) { /* im lặng — card phụ không được phá trang settings */ }
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
  html += `<div class="card"><h2>Tình trạng hệ thống</h2><div id="sysinfo"><span class="mut">đang tải…</span></div></div>`;
  html += `<div class="card"><h2>custom key</h2><div class="row">
    <div class="k"><b>Key mới</b><span>key tuỳ ý, ví dụ provider.custom.url</span></div>
    <input id="new-key" placeholder="key"><input id="new-val" placeholder="value">
    <button onclick="addCustom()">Thêm</button></div></div>`;
  $("content").innerHTML = html;
}

async function save(key, isSecret) {
  const value = $("in-" + key).value;
  const r = await api("/v1/admin/settings/" + encodeURIComponent(key),
                      { method: "PUT", body: JSON.stringify({ value, is_secret: isSecret }) });
  flash(r.ok ? "✔ đã lưu " + key : "✗ lỗi " + r.status);
  if (r.ok) load();
}
async function del(key) {
  if (!confirm("Xóa " + key + "? (sẽ fallback về env/default)")) return;
  const r = await api("/v1/admin/settings/" + encodeURIComponent(key), { method: "DELETE" });
  flash(r.ok ? "✔ đã xóa" : "✗ lỗi");
  load();
}
async function addCustom() {
  const k = $("new-key").value.trim(), v = $("new-val").value;
  if (!k) return;
  const r = await api("/v1/admin/settings/" + encodeURIComponent(k),
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
    <td>${u.name ? '<b>' + esc(u.name) + '</b><br>' : ''}<span class="mut">${esc(u.email)}</span>${u.has_password ? "" : ' (chưa có mật khẩu)'}</td>
    <td>${u.role === "admin" ? '<span class="badge admin">Quản trị</span>' : '<span class="badge">Người dùng</span>'}</td>
    <td>${u.is_active ? '<span class="badge">Hoạt động</span>' : '<span class="badge off">Đã khoá</span>'}</td>
    <td class="mut">${u.last_login_at ? new Date(u.last_login_at * 1000).toLocaleString("vi-VN") : "—"}</td>
    <td><div class="row-actions">
      <button class="ghost" onclick="resetPw('${esc(u.user_id)}', '${esc(u.email)}')">Đặt lại mật khẩu</button>
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
      <table class="users"><thead><tr><th>Người dùng</th><th>Vai trò</th><th>Trạng thái</th>
        <th>Đăng nhập gần nhất</th><th></th></tr></thead>
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
async function toggleActive(id, active) {
  const path = active ? "activate" : "deactivate";
  if (!active && !confirm("Vô hiệu hóa người dùng này? Mọi phiên đăng nhập và API key sẽ bị khoá.")) return;
  const r = await api(`/v1/admin/users/${id}/${path}`, { method: "POST" });
  const d = await r.json();
  flash(r.ok ? (active ? "✔ đã kích hoạt" : "✔ đã vô hiệu hóa") : "✗ " + (d.detail || r.status),
        r.ok ? "ok" : "err");
  loadUsers();
}
// NHẬT KÝ KIỂM TOÁN — GET /v1/admin/audit (filter q/action + phân trang).
const AUDIT_LABELS = {
  "auth.login": "Đăng nhập", "auth.login_failed": "Đăng nhập thất bại",
  "auth.logout": "Đăng xuất", "auth.setup": "Khởi tạo", "auth.signup": "Đăng ký",
  "me.password_change": "Đổi mật khẩu", "me.name_change": "Đổi tên",
  "me.session_revoke": "Thu hồi phiên", "user.create": "Tạo user",
  "user.reset_password": "Đặt lại mật khẩu", "user.deactivate": "Khoá tài khoản",
  "user.activate": "Mở khoá", "provider.create": "Tạo provider",
  "provider.update": "Sửa provider", "provider.delete": "Xoá provider",
  "provider.sync": "Đồng bộ model", "stage.set": "Gán công đoạn",
  "stage.clear": "Gỡ công đoạn", "model.toggle": "Bật/tắt model",
  "setting.set": "Đổi setting", "setting.delete": "Xoá setting",
  "key.create": "Tạo API key", "key.revoke": "Thu hồi key",
  "prompt.update": "Sửa prompt", "prompt.reset": "Khôi phục prompt",
  "job.cancel": "Hủy job", "job.delete": "Xoá job", "config.import": "Nhập cấu hình",
};
let AUDIT_OFFSET = 0;
async function loadAudit(shift) {
  if (shift !== undefined) AUDIT_OFFSET = Math.max(0, AUDIT_OFFSET + shift);
  const q = encodeURIComponent($("audit-q") ? $("audit-q").value : "");
  const r = await api(`/v1/admin/audit?limit=25&offset=${AUDIT_OFFSET}&q=${q}`);
  if (!r.ok) return;
  const d = await r.json();
  const rows = (d.items || []).map(i => `<tr>
    <td class="mut">${i.created_at ? new Date(i.created_at * 1000).toLocaleString("vi-VN") : "—"}</td>
    <td><b>${esc(AUDIT_LABELS[i.action] || i.action)}</b></td>
    <td class="mut">${esc(i.user_email || i.user_id || "—")}</td>
    <td>${esc(i.target || "—")}</td>
    <td class="mut">${esc(i.detail || "")}</td>
    <td class="mut">${esc(i.ip || "—")}</td></tr>`).join("");
  $("audit").innerHTML = `
    <div class="card"><h2>Hành động gần đây <span class="mut">(${d.total} dòng)</span></h2>
      <div class="row"><div class="k"><b>Tìm</b><span>trong hành động/đối tượng/chi tiết</span></div>
        <input id="audit-q" placeholder="từ khoá…" value=""
          onkeydown="if(event.key==='Enter'){AUDIT_OFFSET=0;loadAudit(-AUDIT_OFFSET)}">
        <button onclick="AUDIT_OFFSET=0;loadAudit(-AUDIT_OFFSET)">Tìm</button></div>
      <table class="users"><thead><tr><th>Thời gian</th><th>Hành động</th><th>Người</th>
        <th>Đối tượng</th><th>Chi tiết</th><th>IP</th></tr></thead>
        <tbody>${rows || '<tr><td colspan="6" class="mut">Chưa có hành động nào.</td></tr>'}</tbody></table>
      <div class="row" style="margin-top:10px">
        <button class="ghost" ${AUDIT_OFFSET === 0 ? "disabled" : ""}
          onclick="loadAudit(-25)">← Trước</button>
        <span class="mut">${d.offset + 1}–${Math.min(d.offset + d.limit, d.total)} / ${d.total}</span>
        <button class="ghost" ${d.offset + d.limit >= d.total ? "disabled" : ""}
          onclick="loadAudit(25)">Sau →</button>
      </div></div>`;
}

async function logout() {
  try { await fetch("/v1/auth/logout", { method: "POST", credentials: "same-origin" }); } catch (e) {}
  location.href = "/login";
}

// ============================================================== tab AI
// Ba khối: Nhà cung cấp (Cloud + Ollama) · Công đoạn · Prompt hệ thống.
// Ghi chú: API key chỉ gửi MỘT CHIỀU lên server — khi sửa mà để trống thì giữ nguyên
// (đúng PATCH semantics phía backend), nên UI không bao giờ cần biết key thật.
const KIND_LABEL = { openai: "OpenAI-compatible", ollama: "Ollama" };
const STAGE_LABEL = { stt: "Nhận dạng giọng nói (STT)", translate: "Dịch phụ đề",
                      retranslate: "Dịch lại cho khớp timing", tts: "Tổng hợp giọng nói (TTS)",
                      dub: "Lồng tiếng (pipeline)" };
const STAGE_NOTE = {
  stt: "Gán model cloud → job STT gọi provider đó; bỏ gán = faster-whisper local.",
  translate: "Model chat dịch qua prompt. Bỏ gán = cấu hình translate.* hoặc opus-mt local.",
  retranslate: "Dùng khi bản dịch quá dài so với thời lượng — cần model ngắn gọn.",
  tts: "Cloud TTS chỉ hỗ trợ giọng PRESET — giọng CLONE (voice profile) luôn chạy local.",
  dub: "Pipeline lồng tiếng chạy engine local; model của công đoạn này phục vụ phần dịch.",
};
let AI = { providers: [], stages: {}, summary: {}, prompts: [], models: null, modelFilter: {} };

async function loadAi() {
  const [pr, st, pm] = await Promise.all([
    api("/v1/admin/providers").then(r => r.json()),
    api("/v1/admin/stages").then(r => r.json()),
    api("/v1/admin/prompts").then(r => r.json()),
  ]);
  AI = { providers: pr.providers, stages: st.stages, summary: st.summary,
         prompts: pm.prompts, models: null, modelFilter: AI.modelFilter || {} };
  renderAi();
}

// ---- Model Registry (inline): filter + list + toggle + chi tiết
async function loadModels() {
  const f = AI.modelFilter;
  const qs = new URLSearchParams({ limit: "100" });
  if (f.provider_id) qs.set("provider_id", f.provider_id);
  if (f.compatibility) qs.set("compatibility", f.compatibility);
  if (f.q) qs.set("q", f.q);
  const d = await api("/v1/admin/models?" + qs).then(r => r.json());
  AI.models = d;
  renderModels();
}

const COMP_LABEL = { compatible: "✓ Compatible", partial: "⚠ Một phần",
                     unknown: "? Không rõ", incompatible: "✕ Không tương thích" };

function renderModels() {
  const el = $("models-list");
  if (!el) return;
  const d = AI.models;
  if (!d) { el.innerHTML = '<p class="hint">Bấm "Tải mô hình" để xem registry.</p>'; return; }
  const rows = (d.items || []).map(m => `
    <div class="prov" style="padding:8px 10px">
      <div class="meta">
        <b><span class="badge">${esc(COMP_LABEL[m.compatibility?.status] || "?")}</span>
          ${esc(m.display_name || m.model_id)}
          ${m.enabled ? "" : '<span class="badge off">đã tắt</span>'}</b>
        <code>${esc(m.model_id)}</code>
        <div class="hint">${Object.entries(m.capabilities || {}).filter(([k, v]) => v === true)
          .map(([k]) => esc(k)).join(" · ") || "không có capability nào"}</div>
      </div>
      <div class="row-actions">
        <button class="ghost" onclick="modelDetail('${esc(m.id)}')">Chi tiết</button>
        <button class="ghost" onclick="toggleModel('${esc(m.id)}', ${m.enabled ? "false" : "true"})">${m.enabled ? "Tắt" : "Bật"}</button>
      </div>
    </div>`).join("");
  el.innerHTML = `<p class="hint">${d.total} model · ✓${d.breakdown.compatible} ⚠${d.breakdown.partial} ?${d.breakdown.unknown} ✕${d.breakdown.incompatible}</p>${rows}`;
}

async function toggleModel(id, enabled) {
  try { await api("/v1/admin/models/" + id, { method: "PATCH",
        headers: { "Content-Type": "application/json" }, body: JSON.stringify({ enabled }) });
    await loadModels();
  } catch (e) { flash("Lỗi: " + e.message, "err"); }
}

async function loadUserPrompts() {
  try {
    const d = await api("/v1/admin/prompt-library?limit=20").then(r => r.json());
    const el = $("user-prompts");
    $("pl-count").textContent = d.total + " prompt";
    el.innerHTML = (d.items || []).map(p => `
      <div class="prov" style="padding:6px 10px">
        <div class="meta"><b>${esc(p.name)}</b>
          <div class="hint">${esc(p.user_email || "")} · v${p.version} · ${(p.tags || []).map(esc).join(", ") || "—"}</div>
        </div>
        <code style="font-size:11px">${esc((p.content_preview || "").slice(0, 60))}…</code>
      </div>`).join("") || '<p class="hint">Chưa có prompt nào.</p>';
  } catch (e) { flash("Lỗi tải thư viện prompt: " + e.message, "err"); }
}

async function syncProv(id) {
  try {
    const r = await api("/v1/admin/providers/" + id + "/sync", { method: "POST" });
    const d = await r.json();
    if (!r.ok) { flash("Lỗi đồng bộ: " + (d.detail || r.status), "err"); return; }
    flash(`Đồng bộ xong: ${d.synced} model (${d.added} thêm · ${d.updated} cập nhật · ${d.removed} gỡ) — ${d.duration_ms}ms`);
    await loadAi();
  } catch (e) { flash("Lỗi đồng bộ: " + e.message, "err"); }
}

async function modelDetail(id) {
  const d = await api("/v1/admin/models/" + id).then(r => r.json());
  const caps = Object.entries(d.capabilities || {}).map(([k, v]) =>
    `<div>${v === true ? "✓" : v === false ? "✕" : "—"} <code>${esc(k)}</code></div>`).join("");
  const feats = [
    ...(d.compatibility?.supported_features || []).map(f => `<div style="color:var(--ok)">✓ ${esc(f)}</div>`),
    ...(d.compatibility?.partial_features || []).map(f => `<div style="color:var(--warn)">⚠ ${esc(f)}</div>`),
    ...(d.compatibility?.unsupported_features || []).map(f => `<div style="color:var(--err)">✕ ${esc(f)}</div>`),
  ].join("");
  openModal(`
    <h2>${esc(d.display_name || d.model_id)} <span class="badge">${esc(COMP_LABEL[d.compatibility?.status] || "?")}</span></h2>
    <p class="hint"><code>${esc(d.model_id)}</code> qua ${esc(d.provider_name || "")}</p>
    ${d.description ? `<p class="hint">${esc(d.description.slice(0, 600))}</p>` : ""}
    <label>Capabilities</label><div class="grid2" style="grid-template-columns:repeat(3,1fr)">${caps}</div>
    <label>Chức năng hệ thống</label><div class="grid2" style="grid-template-columns:repeat(3,1fr)">${feats}</div>
    ${(d.compatibility?.reasons || []).length ? `<p class="hint">${(d.compatibility.reasons || []).map(esc).join("<br>")}</p>` : ""}
    <p class="hint">Context: ${d.context_window ?? "—"} · Nguồn capability: ${esc(d.capability_source || "—")}</p>
    <div class="row-actions" style="margin-top:10px">
      <button class="ghost" onclick="toggleModel('${esc(d.id)}', ${d.enabled ? "false" : "true"}); closeModal()">${d.enabled ? "Tắt model" : "Bật model"}</button>
      <button onclick="closeModal()">Đóng</button>
    </div>`);
}

function renderAi() {
  const provs = AI.providers;
  const rows = provs.length ? provs.map(p => `
    <div class="prov">
      <div class="meta">
        <b><span class="dot" id="dot-${esc(p.id)}"></span>${esc(p.name)}
          <span class="badge">${esc(KIND_LABEL[p.kind] || p.kind)}</span>
          ${p.enabled ? "" : '<span class="badge off">đang tắt</span>'}</b>
        <code>${esc(p.base_url)}</code>
        <div class="hint">${p.api_key_set ? "API key: " + esc(p.api_key_hint) : "không dùng API key"}
          · <b>${p.models_count ?? 0} model</b>${p.last_synced_at ? " · đồng bộ " + new Date(p.last_synced_at * 1000).toLocaleString("vi-VN") : " · chưa đồng bộ"}</div>
        <div class="hint">✓${p.breakdown?.compatible ?? 0} compatible · ⚠${p.breakdown?.partial ?? 0} một phần · ?${p.breakdown?.unknown ?? 0} không rõ · ✕${p.breakdown?.incompatible ?? 0} không tương thích</div>
      </div>
      <div class="row-actions">
        <button class="ghost" onclick="testProv('${esc(p.id)}')">Kiểm tra kết nối</button>
        <button onclick="syncProv('${esc(p.id)}')">Đồng bộ</button>
        ${p.kind === "ollama" ? `<button class="ghost" onclick="manageModels('${esc(p.id)}')">Quản lý model</button>` : ""}
        <button class="ghost" onclick="editProv('${esc(p.id)}')">Sửa</button>
        <button class="ghost" onclick="delProv('${esc(p.id)}', '${esc(p.name)}')">Xoá</button>
      </div>
    </div>`).join("") : '<p class="hint">Chưa có nhà cung cấp nào — thêm Cloud API hoặc Ollama để dùng model ngoài.</p>';

  const stageRows = Object.keys(STAGE_LABEL).map(stage => {
    const items = AI.stages[stage] || [];
    const primary = items.find(i => i.order === 0) || {};
    const options = ['<option value="">— không dùng —</option>'].concat(
      provs.map(p => `<option value="${esc(p.id)}" ${primary.provider_id === p.id ? "selected" : ""}>${esc(p.name)} (${esc(KIND_LABEL[p.kind] || p.kind)})</option>`)
    ).join("");
    return `<div class="prov">
      <div class="meta"><b>${esc(STAGE_LABEL[stage])}</b>
        <div class="hint">${esc(STAGE_NOTE[stage] || "")}</div>
        <div class="hint">Đang dùng: <b>${esc(AI.summary[stage] || "—")}</b></div></div>
      <div class="row-actions">
        <select id="st-prov-${stage}" style="min-width:200px">${options}</select>
        <input id="st-model-${stage}" placeholder="tên model" value="${esc(primary.model || "")}" style="min-width:180px">
        <button onclick="saveStage('${stage}')">Lưu</button>
        ${primary.provider_id ? `<button class="ghost" onclick="clearStage('${stage}')">Bỏ gán</button>` : ""}
      </div></div>`;
  }).join("");

  const prompts = AI.prompts.map(p => `
    <div class="card" style="padding:14px 16px">
      <b>${esc(p.description || p.task_key)} ${p.is_default ? "" : '<span class="badge">đã sửa</span>'}</b>
      <div class="hint"><code>${esc(p.task_key)}</code></div>
      <textarea id="pm-${esc(p.task_key)}">${esc(p.content)}</textarea>
      <p class="vars">Biến dùng được: ${(p.variables || []).map(v => `<code>{${esc(v)}}</code>`).join("") || "—"}</p>
      <div class="row-actions" style="margin-top:8px">
        <button onclick="savePrompt('${esc(p.task_key)}')">Lưu prompt</button>
        ${p.editable_default ? `<button class="ghost" onclick="resetPrompt('${esc(p.task_key)}')">Khôi phục mặc định</button>` : ""}
      </div>
    </div>`).join("");

  $("ai").innerHTML = `
    <div class="card"><h2>Nhà cung cấp AI</h2>
      <div id="prov-list">${rows}</div>
      <div class="row-actions" style="margin-top:14px">
        <button onclick="editProv('')">＋ Thêm nhà cung cấp</button>
      </div>
      <p class="hint">Ollama local thường là <code>http://localhost:11434</code> (không cần API key).
        "Đồng bộ" nạp catalog model vào registry, đánh dấu capability và mức tương thích với hệ thống.</p>
    </div>
    <div class="card"><h2>Mô hình AI (registry)</h2>
      <div class="row-actions">
        <select id="mf-prov" style="min-width:180px" onchange="AI.modelFilter.provider_id=this.value; loadModels()">
          <option value="">Mọi nhà cung cấp</option>
          ${provs.map(p => `<option value="${esc(p.id)}">${esc(p.name)}</option>`).join("")}
        </select>
        <select id="mf-comp" style="min-width:170px" onchange="AI.modelFilter.compatibility=this.value; loadModels()">
          <option value="">Mọi mức tương thích</option>
          <option value="compatible">✓ Compatible</option>
          <option value="partial">⚠ Một phần</option>
          <option value="unknown">? Không rõ</option>
          <option value="incompatible">✕ Không tương thích</option>
        </select>
        <input id="mf-q" placeholder="tìm model…" style="min-width:160px"
          onchange="AI.modelFilter.q=this.value; loadModels()">
        <button onclick="loadModels()">Tải mô hình</button>
      </div>
      <div id="models-list" style="margin-top:10px"><p class="hint">Bấm "Tải mô hình" để xem registry.</p></div>
      <p class="hint">Model tắt không hiện trong selector, không được gán công đoạn, và bị loại khỏi pipeline lúc chạy — tắt ≠ xoá.</p>
    </div>
    <div class="card"><h2>Công đoạn → model</h2>${stageRows}</div>
    <div class="card"><h2>Prompt hệ thống</h2>
      <p class="hint">Sửa prompt dùng cho dịch/dịch lại. Nút Khôi phục mặc định trả về bản trong code.</p>
      <div class="grid2">${prompts}</div>
    </div>
    <div class="card"><h2>Prompt của người dùng (thư viện)</h2>
      <p class="hint">Mỗi user có thư viện prompt riêng (xem đúng người dùng tại trang "Prompt của tôi").
        Danh sách này CHỈ ĐỌC — admin không sửa/xoá hộ.</p>
      <div class="row-actions">
        <button class="ghost" onclick="loadUserPrompts()">Tải danh sách</button>
        <span id="pl-count" class="hint"></span>
      </div>
      <div id="user-prompts" style="margin-top:8px"></div>
    </div>`;
}

function closeModal() { $("modal-bg").classList.remove("on"); }
function openModal(html) { $("modal").innerHTML = html; $("modal-bg").classList.add("on"); }

function editProv(id) {
  const p = AI.providers.find(x => x.id === id) || {};
  openModal(`
    <h2>${id ? "Sửa nhà cung cấp" : "Thêm nhà cung cấp"}</h2>
    <label>Tên</label><input id="pv-name" value="${esc(p.name || "")}" placeholder="VD: DeepSeek, Ollama local">
    <label>Loại</label>
    <select id="pv-kind">
      <option value="openai" ${p.kind === "openai" || !p.kind ? "selected" : ""}>OpenAI-compatible (OpenAI, DeepSeek, Groq, vLLM, OpenRouter…)</option>
      <option value="ollama" ${p.kind === "ollama" ? "selected" : ""}>Ollama</option>
    </select>
    <label>Base URL</label>
    <input id="pv-url" value="${esc(p.base_url || "")}" placeholder="https://api.deepseek.com/v1">
    <p class="hint" id="pv-target"></p>
    <label>API key ${id ? "(để trống = giữ nguyên)" : ""}</label>
    <input id="pv-key" type="password" placeholder="${p.api_key_set ? esc(p.api_key_hint) : "sk-…"}">
    ${p.api_key_set ? '<p class="hint">Đã có key. Bấm <b>Xoá key</b> để gỡ hẳn, hoặc nhập key mới để thay.</p>' : ""}
    <label>Prefix ID (tuỳ chọn)</label><input id="pv-prefix" value="${esc(p.prefix_id || "")}">
    <div class="row-actions" style="margin-top:18px">
      <button onclick="saveProv('${esc(id)}')">Lưu</button>
      ${p.api_key_set ? `<button class="ghost" onclick="clearKey('${esc(id)}')">Xoá key</button>` : ""}
      <button class="ghost" onclick="closeModal()">Huỷ</button>
    </div>`);
  const sync = () => {
    const kind = $("pv-kind").value, url = ($("pv-url").value || "").replace(/\/+$/, "");
    $("pv-target").textContent = url
      ? `Sẽ gọi: ${url}${kind === "ollama" ? "/api/chat" : "/chat/completions"}`
      : "";
  };
  $("pv-kind").onchange = sync; $("pv-url").oninput = sync; sync();
}

async function saveProv(id) {
  const body = { name: $("pv-name").value.trim(), kind: $("pv-kind").value,
                 base_url: $("pv-url").value.trim(),
                 prefix_id: $("pv-prefix").value.trim() || null };
  const key = $("pv-key").value;
  // Chỉ gửi api_key khi người dùng THỰC SỰ nhập → để trống = giữ nguyên (PATCH semantics).
  if (key) body.api_key = key;
  const r = id
    ? await api(`/v1/admin/providers/${id}`, { method: "PATCH", body: JSON.stringify(body) })
    : await api("/v1/admin/providers", { method: "POST", body: JSON.stringify(body) });
  const d = await r.json();
  if (!r.ok) { flash("✗ " + (d.detail || r.status), "err"); return; }
  flash("✔ đã lưu " + d.name);
  closeModal(); loadAi();
}

async function clearKey(id) {
  if (!confirm("Xoá API key của nhà cung cấp này?")) return;
  const r = await api(`/v1/admin/providers/${id}`, { method: "PATCH",
                       body: JSON.stringify({ api_key: "" }) });
  flash(r.ok ? "✔ đã xoá key" : "✗ lỗi", r.ok ? "ok" : "err");
  closeModal(); loadAi();
}

async function delProv(id, name) {
  if (!confirm(`Xoá nhà cung cấp "${name}"? Các công đoạn đang dùng nó cũng bị bỏ gán.`)) return;
  const r = await api(`/v1/admin/providers/${id}`, { method: "DELETE" });
  flash(r.ok ? "✔ đã xoá" : "✗ lỗi", r.ok ? "ok" : "err");
  loadAi();
}

async function testProv(id) {
  const dot = $("dot-" + id);
  if (dot) dot.className = "dot";
  flash("⏳ đang kiểm tra kết nối…");
  const r = await api(`/v1/admin/providers/${id}/test`, { method: "POST" });
  const d = await r.json();
  if (dot) dot.className = "dot " + (d.ok ? "ok" : "bad");
  flash((d.ok ? "✔ " : "✗ ") + (d.detail || ""), d.ok ? "ok" : "err");
}

async function manageModels(id) {
  openModal(`<h2>Quản lý model Ollama</h2><div id="mm-body">⏳ đang tải…</div>
             <div class="row-actions" style="margin-top:16px"><button class="ghost" onclick="closeModal()">Đóng</button></div>`);
  const r = await api(`/v1/admin/providers/${id}/models`);
  const d = await r.json();
  if (!r.ok) { $("mm-body").innerHTML = `<p class="err">${esc(d.detail || "lỗi")}</p>`; return; }
  const list = d.models.length ? d.models.map(m => `
    <div class="prov"><div class="meta"><b>${esc(m.name)}</b>
      <div class="hint">${m.parameter_size ? esc(m.parameter_size) + " · " : ""}${m.size ? (m.size / 1e9).toFixed(2) + " GB" : ""}${m.quantization ? " · " + esc(m.quantization) : ""}</div></div>
      <div class="row-actions"><button class="ghost" onclick="delModel('${esc(id)}','${esc(m.name)}')">Xoá</button></div>
    </div>`).join("") : '<p class="hint">Chưa có model nào được cài.</p>';
  $("mm-body").innerHTML = `
    <div>${list}</div>
    <label style="margin-top:16px">Tải model mới (tên trên ollama.com/library)</label>
    <div class="row-actions">
      <input id="mm-pull" placeholder="vd: qwen2.5:7b-instruct" style="min-width:220px">
      <button onclick="pullModel('${esc(id)}')">Tải về</button>
    </div>
    <div class="progress" id="mm-prog"><i id="mm-bar"></i></div>
    <p class="hint" id="mm-status"></p>`;
}

async function pullModel(id) {
  const name = $("mm-pull").value.trim();
  if (!name) { flash("✗ nhập tên model", "err"); return; }
  $("mm-prog").classList.add("on");
  $("mm-status").textContent = "đang tải " + name + "…";
  try {
    // NDJSON stream từ backend -> tự vẽ tiến trình, không chờ tải xong mới hiện.
    const resp = await fetch(`/v1/admin/providers/${id}/pull`, {
      method: "POST", credentials: "same-origin",
      headers: { "Content-Type": "application/json" }, body: JSON.stringify({ model: name }),
    });
    const reader = resp.body.getReader();
    const dec = new TextDecoder();
    let buf = "";
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buf += dec.decode(value, { stream: true });
      const lines = buf.split("\n");
      buf = lines.pop();
      for (const line of lines) {
        if (!line.trim()) continue;
        let j = {};
        try { j = JSON.parse(line); } catch (e) { continue; }
        if (j.total) {
          $("mm-bar").style.width = Math.round(j.completed / j.total * 100) + "%";
          $("mm-status").textContent = (j.status || "") + " — " +
            (j.completed / 1e9).toFixed(2) + " / " + (j.total / 1e9).toFixed(2) + " GB";
        } else {
          $("mm-status").textContent = j.status || "";
        }
        if (j.status === "success") { $("mm-bar").style.width = "100%"; }
        if (j.status === "error") { $("mm-status").textContent = "✗ " + (j.detail || "lỗi tải"); }
      }
    }
    flash("✔ xong: " + name);
    manageModels(id);
  } catch (e) {
    $("mm-status").textContent = "✗ " + e.message;
  }
}

async function delModel(id, name) {
  if (!confirm("Xoá model " + name + "?")) return;
  const r = await api(`/v1/admin/providers/${id}/models/${encodeURIComponent(name)}`,
                      { method: "DELETE" });
  const d = await r.json();
  flash(r.ok ? "✔ đã xoá " + name : "✗ " + (d.detail || r.status), r.ok ? "ok" : "err");
  manageModels(id);
}

async function saveStage(stage) {
  const body = { provider_id: $("st-prov-" + stage).value || null,
                 model: $("st-model-" + stage).value.trim(), order: 0 };
  const r = await api(`/v1/admin/stages/${stage}`, { method: "PUT", body: JSON.stringify(body) });
  const d = await r.json();
  flash(r.ok ? "✔ đã gán công đoạn " + stage : "✗ " + (d.detail || r.status), r.ok ? "ok" : "err");
  loadAi();
}
async function clearStage(stage) {
  const r = await api(`/v1/admin/stages/${stage}`, { method: "DELETE" });
  flash(r.ok ? "✔ đã bỏ gán" : "✗ lỗi", r.ok ? "ok" : "err");
  loadAi();
}
async function savePrompt(key) {
  const content = $("pm-" + key).value;
  const r = await api(`/v1/admin/prompts/${key}`, { method: "PUT",
                       body: JSON.stringify({ content }) });
  const d = await r.json();
  flash(r.ok ? "✔ đã lưu prompt " + key : "✗ " + (d.detail || r.status), r.ok ? "ok" : "err");
  loadAi();
}
async function resetPrompt(key) {
  if (!confirm("Khôi phục prompt mặc định cho " + key + "?")) return;
  const r = await api(`/v1/admin/prompts/${key}/reset`, { method: "POST" });
  flash(r.ok ? "✔ đã khôi phục mặc định" : "✗ lỗi", r.ok ? "ok" : "err");
  loadAi();
}

loadAi();             // tab mặc định là AI
vvThemeChanged();     // đồng bộ nhãn nút sáng/tối với theme đã áp ở <head>
</script>
</body></html>"""

# Nội suy token theme (không dùng f-string: CSS/JS đầy dấu ngoặc nhọn).
ADMIN_HTML = (ADMIN_HTML
              .replace("__THEME_BOOT__", THEME_BOOT)
              .replace("__THEME_CSS__", THEME_CSS)
              .replace("__THEME_JS__", THEME_JS))
