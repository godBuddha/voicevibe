"""Theme tokens — một nguồn sự thật duy nhất cho màu sắc (sáng + tối).

Lý do tồn tại: UI inline trước đây hardcode ~33 màu rải rác trong CSS/inline SVG/JS,
nên không thể có dark mode. Module này gom TOÀN BỘ màu vào hai khối:
  :root                    -> chế độ sáng (mặc định)
  html[data-theme="dark"]  -> chế độ tối

QUY TẮC: không được có mã màu hex nào ngoài hai khối đó. Ngoại lệ duy nhất là các
số đo layout (--side-w, --top-h) — chúng không phải màu nên không cần bản tối.
`tests/test_theme.py` cưỡng chế quy tắc này.

Cách dùng trong một trang:
    from .theme import THEME_BOOT, THEME_CSS, THEME_JS
    HTML = f'''<html><head>
      {THEME_BOOT}            <!-- phải TRƯỚC stylesheet để không nhấp nháy -->
      <style>{THEME_CSS}
        /* CSS riêng của trang, chỉ dùng var() */
      </style></head>
    <body>...<script>{THEME_JS}</script></body></html>'''
"""
from __future__ import annotations

# --------------------------------------------------------------------------- CSS
# Bảng màu TỐI lấy đúng palette của bản redesign cũ (frontend/assets/app.css)
# để giữ nguyên cảm giác thị giác đã được duyệt.
THEME_CSS = """
:root {
  /* --- nền & bề mặt --- */
  --bg:#f6f5fb; --bg2:#efeef8; --card:#ffffff; --side:#ffffff;
  --line:#e8e6f5; --fg:#23213a; --mut:#8b88a8;
  /* --- màu nhấn & trạng thái --- */
  --acc:#7c5cff; --acc2:#a78bfa; --on-acc:#ffffff;
  --ok:#22c58b; --warn:#ffb020; --err:#ff5d73;
  /* --- bề mặt tương tác --- */
  --hover:#f3f1fc; --input:#fbfaff; --chip:#f6f4ff;
  --sidecard-from:#f4f0ff; --sidecard-to:#eef9f4;
  --hero-grad:linear-gradient(120deg,#7c5cff 0%,#a78bfa 55%,#22c58b 130%);
  /* --- pill trạng thái job --- */
  --pill-done-bg:#e6f9f1; --pill-run-bg:#fff5e0; --pill-run-fg:#c77c00;
  --pill-fail-bg:#ffe9ec; --pill-queue-bg:#f0eefb;
  /* --- khối code / biểu đồ --- */
  --track:#f0eefb; --code-bg:#f3f1fc; --pre-bg:#23213a; --pre-fg:#d7d5f5;
  --chart-tts:#22c58b; --chart-stt:#38bdf8; --chart-translate:#7c5cff;
  --chart-dub:#a78bfa; --chart-subtitle:#ffb020; --chart-other:#ff8a4c;
  /* --- số đo layout (KHÔNG theme) --- */
  --side-w:248px; --top-h:60px;
}

html[data-theme="dark"] {
  --bg:#0f1220; --bg2:#141830; --card:#181c2f; --side:#141830;
  --line:#2a2f4a; --fg:#e8eaf6; --mut:#9aa0c0;
  --acc:#7c6cff; --acc2:#a78bfa; --on-acc:#ffffff;
  --ok:#5dd39e; --warn:#ffd479; --err:#ff7b7b;
  --hover:#1b2040; --input:#0d1020; --chip:#1b2040;
  --sidecard-from:#1b2040; --sidecard-to:#182a24;
  --hero-grad:linear-gradient(120deg,#7c5cff 0%,#a78bfa 55%,#22c58b 130%);
  --pill-done-bg:#14332a; --pill-run-bg:#3a2e12; --pill-run-fg:#ffd479;
  --pill-fail-bg:#3a1c22; --pill-queue-bg:#232842;
  --track:#232842; --code-bg:#0d1020; --pre-bg:#0b0e1a; --pre-fg:#d7d5f5;
  --chart-tts:#5dd39e; --chart-stt:#38bdf8; --chart-translate:#7c6cff;
  --chart-dub:#a78bfa; --chart-subtitle:#ffd479; --chart-other:#ff8a4c;
}
"""

# ------------------------------------------------------------------- BOOT (head)
# Chèn TRƯỚC stylesheet: đặt data-theme ngay lập tức để trang không "nháy" màu
# sáng rồi mới chuyển sang tối. Cố tình viết rất ngắn và bọc try/catch vì
# localStorage có thể bị chặn (chế độ riêng tư) — khi đó rơi về mặc định hệ thống.
THEME_BOOT = """<script>(function(){try{
var t=localStorage.getItem('yv_theme');
if(t!=='light'&&t!=='dark'){
  t=(window.matchMedia&&window.matchMedia('(prefers-color-scheme: dark)').matches)?'dark':'light';
}
document.documentElement.setAttribute('data-theme',t);
}catch(e){}})();</script>"""

# --------------------------------------------------------------------- JS runtime
# Không chứa hex: màu biểu đồ đọc từ CSS var nên tự đổi theo theme.
# Nhãn nút lật theo trạng thái qua thuộc tính data-theme-label.
THEME_JS = """
var YV_THEME_KEY = 'yv_theme';
var YV_THEME_LISTENERS = [];

function yvGetTheme() {
  return document.documentElement.getAttribute('data-theme') === 'dark' ? 'dark' : 'light';
}
function yvSetTheme(t) {
  document.documentElement.setAttribute('data-theme', t);
  try { localStorage.setItem(YV_THEME_KEY, t); } catch (e) {}
  yvThemeChanged();
}
function yvToggleTheme() {
  yvSetTheme(yvGetTheme() === 'dark' ? 'light' : 'dark');
}
function yvOnThemeChange(fn) { YV_THEME_LISTENERS.push(fn); }
function yvCssVar(name) {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
}
function yvThemeChanged() {
  var dark = yvGetTheme() === 'dark';
  var label = dark ? '☀️ Chế độ sáng' : '🌙 Chế độ tối';
  document.querySelectorAll('[data-theme-label]').forEach(function (el) {
    el.textContent = label;
  });
  YV_THEME_LISTENERS.forEach(function (fn) { try { fn(); } catch (e) {} });
}
"""