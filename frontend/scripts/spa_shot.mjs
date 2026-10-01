// Chụp ảnh màn hình SPA React — thay thế cho ui_shot.py (dành cho UI inline).
//
// Luồng: đăng nhập bằng API thật (POST /v1/auth/login, lấy Set-Cookie), gắn
// cookie vào browser, đi qua từng route, chụp cả light và dark (đặt
// data-theme trước khi chụp để không lệch màu do transition).
//
// Run:  node scripts/spa_shot.mjs --base http://127.0.0.1:8801 \
//         --api http://127.0.0.1:18080 --out docs/screenshots-spa \
//         --email admin@demo.local --password '...'
// puppeteer-core v24 xuất `launch` trực tiếp (không còn `chromium` như cũ).
import { launch } from 'puppeteer-core';
import { spawn } from 'node:child_process';
import { existsSync, mkdirSync } from 'node:fs';
import path from 'node:path';

function arg(name, dflt) {
  const i = process.argv.indexOf(`--${name}`);
  return i >= 0 ? process.argv[i + 1] : dflt;
}

const BASE = arg('base', 'http://127.0.0.1:8801');
const API = arg('api', 'http://127.0.0.1:18080');
const OUT = arg('out', 'docs/screenshots-spa');
const EMAIL = arg('email', '');
const PASSWORD = arg('password', '');

if (!existsSync(OUT)) mkdirSync(OUT, { recursive: true });

// Đăng nhập bằng fetch thuần — cookie phiên là nguồn sự thật của UI, không
// phải cờ localStorage dựng sẵn.
const loginRes = await fetch(`${API}/v1/auth/login`, {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({ email: EMAIL, password: PASSWORD }),
});
if (!loginRes.ok) {
  console.error(`login ${loginRes.status}: ${await loginRes.text()}`);
  process.exit(1);
}
const setCookie = loginRes.headers.get('set-cookie') || '';
const cookiePairs = setCookie.split(';').filter((c) => c.includes('='));
const [name, ...rest] = cookiePairs[0].split('=');
const sessionCookie = { name: name.trim(), value: rest.join('=').trim(), domain: '127.0.0.1', path: '/' };

const SHOTS = [
  ['00-login', '/login', false],
  ['01-dashboard', '/', true],
  ['02-dub', '/dub', true],
  ['03-tts', '/tts', true],
  ['04-voices', '/voices', true],
  ['05-stt', '/stt', true],
  ['06-subtitle', '/subtitle', true],
  ['15-translate-text', '/translate-text', true],
  ['16-translate-audio', '/translate-audio', true],
  ['07-jobs', '/jobs', true],
  ['08-api-keys', '/api-keys', true],
  // SETTINGS HUB: route /admin/* cũ tự redirect về hub — chụp thẳng section mới.
  ['10-admin-users', '/settings/members', true],
  ['11-admin-model-hub', '/settings/ai-platform', true],
  ['12-admin-settings', '/settings/config', true],
  ['13-dashboard-dark', '/', true, 'dark'],
  ['14-dub-dark', '/dub', true, 'dark'],
  ['25-settings-profile', '/settings/profile', true],
  ['26-settings-sessions', '/settings/sessions', true],
  ['28-settings-system', '/settings/system', true],
  ['29-settings-audit', '/settings/audit', true],
  ['30-settings-advanced', '/settings/import-export', true],
];

const browser = await launch({
  executablePath: process.env.CHROME_PATH || '/usr/bin/google-chrome',
  args: ['--no-sandbox', '--enable-unsafe-swiftshader'],
});
const page = await browser.newPage();
await page.setViewport({ width: 1440, height: 900, deviceScaleFactor: 2 });
await page.setCookie(sessionCookie);

// Chrome headless mặc định `prefers-color-scheme: dark` — useTheme đọc matchMedia
// lúc mount nên mọi ảnh "sáng" thành ra dark y hệt ảnh dark (đã gặp thật: cả bộ
// ảnh F5 đều dark, 00=01=13 và 02=14 trùng byte). Ép sáng làm mặc định; ảnh
// dark đặt riêng ở dưới.
await page.emulateMediaFeatures([{ name: 'prefers-color-scheme', value: 'light' }]);

// protectedLoader đọc cờ localStorage (do useAuth đặt sau khi đăng nhập qua UI)
// — gắn cookie một mình không đủ: SPA chạy từ đầu không biết có phiên. Đặt cờ
// trước, đúng như UI thật sẽ có sau lần đăng nhập đầu tiên.
await page.goto(`${BASE}/login`, { waitUntil: 'networkidle0', timeout: 30000 });
await page.evaluate(() => localStorage.setItem('authenticated', 'true'));

const errors = [];
page.on('pageerror', (e) => errors.push(String(e)));

for (const [name, route, authed, theme] of SHOTS) {
  if (name === '00-login') {
    // Chụp trang đăng nhập THẬT: gỡ cookie + cờ localStorage, nếu không guard
    // thấy "đã đăng nhập" và redirect về dashboard (đã gặp thật).
    await page.deleteCookie(sessionCookie);
    await page.goto(`${BASE}/login`, { waitUntil: 'networkidle0', timeout: 30000 });
    await page.evaluate(() => localStorage.clear());
    await page.reload({ waitUntil: 'networkidle0', timeout: 30000 });
    await new Promise((r) => setTimeout(r, 300));
    await page.screenshot({ path: path.join(OUT, `${name}.png`) });
    console.log(`shot ${name} ← ${route}`);
    // Khôi phục phiên cho các ảnh còn lại.
    await page.setCookie(sessionCookie);
    continue;
  }
  // useTheme đọc localStorage 'theme' ĐÚNG LÚC KHỞI TẠO state — đặt qua
  // evaluateOnNewDocument để giá trị có sẵn trước khi app mount (đặt sau mount
  // chỉ đổi attribute DOM, React state vẫn cũ).
  await page.evaluateOnNewDocument((t) => {
    localStorage.setItem('theme', t || 'light');
  }, theme);
  await page.goto(`${BASE}${route}`, { waitUntil: 'networkidle0', timeout: 30000 });
  if (authed) {
    // SPA không có server-render: mỗi goto là một app mới — đảm bảo cờ còn nằm
    // trong localStorage của profile này.
    await page.evaluate(() => localStorage.setItem('authenticated', 'true'));
    await page.goto(`${BASE}${route}`, { waitUntil: 'networkidle0', timeout: 30000 });
  }
  if (theme) {
    // Đặt theme TRƯỚC khi chụp và đợi transition kết thúc — tránh viền
    // chuyển màu nửa vời trong ảnh.
    await page.evaluate((t) => {
      document.documentElement.setAttribute('data-theme', t);
    }, theme);
    await new Promise((r) => setTimeout(r, 400));
  }
  await new Promise((r) => setTimeout(r, 300));
  await page.screenshot({ path: path.join(OUT, `${name}.png`) });
  console.log(`shot ${name} ← ${route}${theme ? ` (${theme})` : ''}`);
}

await browser.close();
if (errors.length) {
  console.error('PAGE ERRORS:');
  for (const e of errors) console.error(' ', e.slice(0, 200));
  process.exit(1);
}
console.log('SPA SHOTS PASSED — no page errors');
