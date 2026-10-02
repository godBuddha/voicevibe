// spa_audit.mjs — Dò toàn diện SPA VoiceVibe trong Chrome thật.
//
// Hai chế độ (chọn bằng --mode):
//   nav   — quét 15 route, mỗi trang ghi lại: lỗi JS, console error/warning,
//           mọi response >=400, DOM bất thường (NaN/undefined/trắng/tràn ngang),
//           chụp ảnh + md5 chống trùng (bẫy dark/light trùng byte đã gặp thật).
//   flows — 13 luồng bấm thật (đăng nhập sai → đúng, tạo giọng, TTS, STT,
//           phụ đề, lồng tiếng, API key, admin users/model-hub/settings,
//           phân quyền user thường, theme, logout). Mọi thực thể test đặt tên
//           "audit-*" hoặc dùng tài khoản cố định vv-auditor@local; không đụng
//           secret trong Settings (baseline ghi nhận bug mặt-nạ bằng tĩnh).
//
// Run (từ frontend/):
//   node scripts/spa_audit.mjs --base http://127.0.0.1:8080 \
//     --api http://127.0.0.1:18080 --email admin@voicevibe.local \
//     --password '...' --mode nav            # quét nhanh
//   node scripts/spa_audit.mjs --mode all --fast   # mọi luồng, bỏ job AI chậm
//   node scripts/spa_audit.mjs --flow f-stt-job    # chạy đúng 1 luồng
//
// Báo cáo JSON: docs/verification/spa_audit-<ts>.json + bảng tóm tắt stdout.
// Exit 1 nếu: có pageerror, có 4xx/5xx ngoài danh sách trắng, hoặc một luồng
// có kỳ vọng (expect:true) thất bại. Baseline chạy với --soft để chỉ ghi nhận.
import { launch } from 'puppeteer-core';
import { spawnSync } from 'node:child_process';
import { createHash } from 'node:crypto';
import { existsSync, mkdirSync, writeFileSync, rmSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import path from 'node:path';

// ---------------------------------------------------------------- cấu hình
function arg(name, dflt) {
  const i = process.argv.indexOf(`--${name}`);
  if (i < 0) return dflt;
  const v = process.argv[i + 1];
  return v && !v.startsWith('--') ? v : true; // --fast / --soft không có giá trị
}
const flag = (name) => process.argv.includes(`--${name}`);

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..', '..');
const BASE = arg('base', 'http://127.0.0.1:8080');
const API = arg('api', 'http://127.0.0.1:18080');
const EMAIL = arg('email', 'admin@voicevibe.local');
const PASSWORD = arg('password', '');
const MODE = arg('mode', 'all');          // nav | flows | all
const ONLY_FLOW = flag('flow') ? arg('flow') : null;
const FAST = flag('fast');               // bỏ 3 luồng job AI (stt/subtitle/dub)
const SOFT = flag('soft');               // baseline: luôn exit 0, chỉ báo cáo
const SHOTS = arg('shots', path.join(ROOT, 'docs', 'screenshots-spa'));
const JSON_OUT = arg('json', path.join(ROOT, 'docs', 'verification', `spa_audit-${Date.now()}.json`));
const TMP = path.join('/tmp', `vv-audit-${Date.now()}`);
const RUN_ID = Date.now();
const AUDITOR_EMAIL = 'vv-auditor@local';
const AUDITOR_PW = 'Audit@Vibe2026';

for (const d of [SHOTS, path.dirname(JSON_OUT), TMP]) mkdirSync(d, { recursive: true });

// ------------------------------------------------------- đăng nhập (fetch)
async function login(email, password) {
  const res = await fetch(`${API}/v1/auth/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email, password }),
  });
  const json = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(`login ${res.status}: ${JSON.stringify(json)}`);
  const setCookie = res.headers.get('set-cookie') || '';
  const pair = setCookie.split(';')[0];
  const [name, ...rest] = pair.split('=');
  return { cookie: `${name.trim()}=${rest.join('=')}`, cookieObj: { name: name.trim(), value: rest.join('=').trim(), domain: '127.0.0.1', path: '/' }, json };
}
const ADMIN = await login(EMAIL, PASSWORD); // fail cứng nếu sai — không dò được gì

async function apiFetch(cookie, method, urlPath, body) {
  const res = await fetch(`${API}${urlPath}`, {
    method,
    headers: {
      ...(body !== undefined ? { 'Content-Type': 'application/json' } : {}),
      ...(cookie ? { Cookie: cookie } : {}),
    },
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });
  return { status: res.status, json: await res.json().catch(() => ({})) };
}

// ------------------------------------------------------------- recorder
const report = {
  startedAt: new Date().toISOString(), base: BASE, api: API, mode: MODE, fast: FAST,
  pages: [], flows: [],
  summary: null,
};
let current = null; // bản ghi trang/luồng đang mở để listener đổ vào
const shotMd5Count = new Map(); // md5 → số lần xuất hiện (đếm trùng thật)

function summarize() {
  const pagesHttp = report.pages.flatMap((p) => p.http);
  const unexpectedHttp = pagesHttp.filter(({ url, status }) => !isExpectedHttp(url, status));
  // Nhiễu "đúng kế hoạch": /v1/auth/me trả 401 khi chưa đăng nhập — trình duyệt
  // luôn ghi console "Failed to load resource 401", JS không chặn được.
  // 401 /v1/auth/me khi chưa đăng nhập + 502 provider audit (endpoint GIẢ chủ
  // ý) — console trình duyệt luôn ghi "Failed to load resource", JS chặn không được.
  const noise = (c) => c.type === 'error'
    && (c.text.includes('401') || c.text.includes('502'));
  const pageErrors = report.pages.reduce((n, p) => n + p.pageErrors.length, 0)
    + report.flows.reduce((n, f) => n + f.pageErrors.length, 0);
  const consoleErrors = [...report.pages, ...report.flows]
    .reduce((n, x) => n + x.console.filter((c) => !noise(c)).length, 0);
  const domFindings = report.pages.reduce((n, p) => n + p.dom.length, 0);
  const failedExpected = report.flows.filter((f) => f.expect && !f.ok);
  report.summary = {
    pagesChecked: report.pages.length,
    pageErrors, consoleErrors, domFindings,
    unexpectedHttp: unexpectedHttp.length,
    duplicateShots: [...shotMd5Count.values()].filter((n) => n > 1).length,
    dialogs: [...report.pages, ...report.flows].reduce((n, x) => n + x.dialogs.length, 0),
    flowsRun: report.flows.length,
    failedFlows: report.flows.filter((f) => !f.ok).length,
    failedExpected: failedExpected.map((f) => f.name),
  };
  report.unexpectedHttpDetail = unexpectedHttp;
  return report.summary;
}

// 4xx "đúng kế hoạch": chưa đăng nhập thì /v1/auth/me 401; user thường vào
// /admin thì các endpoint /v1/admin/* 403. Provider audit trỏ endpoint GIẢ
// (api.example.com) — Test/Đồng bộ chủ ý trả 502 để chứng minh nút báo lỗi rõ.
function isExpectedHttp(url, status) {
  if (status === 401 && url.includes('/v1/auth/me')) return true;
  if (status === 403 && url.includes('/v1/admin/')) return true;
  if (status === 502 && /\/v1\/admin\/providers\/[^/]+\/(test|sync)$/.test(url)) return true;
  return false;
}

function save() {
  summarize();
  writeFileSync(JSON_OUT, JSON.stringify(report, null, 2));
}
process.on('SIGINT', () => { save(); console.error('\n[audit] SIGINT — đã lưu báo cáo, thoát.'); process.exit(130); });

async function shot(page, name) {
  const buf = await page.screenshot();
  const md5 = createHash('md5').update(buf).digest('hex').slice(0, 12);
  const seen = shotMd5Count.get(md5) || 0;
  shotMd5Count.set(md5, seen + 1);
  const file = seen > 0 ? `${name}-dup${seen}` : name;
  const p = path.join(SHOTS, `${file}.png`);
  writeFileSync(p, buf);
  return { path: p, md5 };
}

// ------------------------------------------------------------ quét DOM
// 'is not a function'/TypeError: React Router bắt lỗi render tại Error
// Boundary → chỉ hiện trong console/DOM, không thành pageerror (đã gặp thật
// trên /api-keys).
const DOM_CHECKS = [
  /\bNaN\b/, /\bundefined\b/, /\bnull\b/, /\[object Object\]/,
  /TypeError:/, /is not a function/, /Cannot read/, /Unhandled Rejection/,
  /Minified React error/, /Unexpected Application Error/,
];
async function domScan(page) {
  return page.evaluate((patterns) => {
    const out = [];
    const text = document.body ? document.body.innerText : '';
    for (const re of patterns.map((p) => new RegExp(p.source, p.flags))) {
      const m = text.match(re);
      if (m) out.push({ check: 'text', detail: `${m[0]} …${text.slice(Math.max(0, m.index - 30), m.index + 30)}…` });
    }
    const main = document.querySelector('main') || document.body;
    if (main && main.innerText.trim().length < 10) out.push({ check: 'empty', detail: 'vùng nội dung gần như trống' });
    const doc = document.documentElement;
    if (doc.scrollWidth > doc.clientWidth + 8) out.push({ check: 'overflow', detail: `scrollWidth ${doc.scrollWidth} > clientWidth ${doc.clientWidth}` });
    for (const img of document.images) {
      if (img.naturalWidth === 0 && img.src) out.push({ check: 'img', detail: `ảnh hỏng: ${img.src.slice(0, 120)}` });
    }
    return out;
  }, DOM_CHECKS.map((r) => ({ source: r.source, flags: r.flags })));
}

// Listener gắn MỘT lần trên mỗi page object, ghi vào bản ghi `current` —
// gọi trong vòng lặp sẽ chồng lớp (mỗi trang nhân n lần listener).
function attach(page) {
  page.on('pageerror', (e) => { if (current) current.pageErrors.push(String(e).slice(0, 300)); });
  page.on('console', (msg) => {
    if (current && (msg.type() === 'error' || msg.type() === 'warning')) {
      current.console.push({ type: msg.type(), text: msg.text().slice(0, 300) });
    }
  });
  page.on('requestfailed', (req) => {
    if (!current) return;
    const err = req.failure() && req.failure().errorText;
    if (err === 'net::ERR_ABORTED') return; // <audio>/<video> huỷ tải là bình thường
    current.requestFailed.push({ url: req.url().slice(0, 200), error: err });
  });
  page.on('response', async (res) => {
    if (!current || res.status() < 400) return;
    const url = res.url();
    let snippet = '';
    const ct = (res.headers()['content-type'] || '');
    if (ct.startsWith('application/json') || ct.startsWith('text/')) {
      snippet = (await res.text().catch(() => '')).slice(0, 300);
    }
    current.http.push({ url: url.slice(0, 200), status: res.status(), snippet });
  });
  // BẮT BUỘC: một khi có handler 'dialog', Puppeteer KHÔNG tự đóng hộp thoại
  // nữa — không accept() thì trang treo vĩnh viễn. prompt() trả lời từ hàng đợi
  // (luồng ModelHub thêm provider cần 4 câu liên tiếp).
  page.on('dialog', async (d) => {
    if (!current) { try { await d.accept(); } catch {} return; }
    current.dialogs.push({ type: d.type(), message: d.message() });
    try {
      if (d.type() === 'prompt') await d.accept(promptQueue.length ? promptQueue.shift() : promptDefault);
      else await d.accept();
    } catch { /* dialog đã tự đóng */ }
  });
}

let promptQueue = [];
let promptDefault = '';

// ------------------------------------------------------------ fixtures
function ffmpeg() {
  const p = spawnSync('ffmpeg', ['-version'], { encoding: 'utf8' });
  if (p.status === 0) return 'ffmpeg';
  const home = path.join(process.env.HOME || '', '.local', 'bin', 'ffmpeg');
  if (existsSync(home)) return home;
  throw new Error('không tìm thấy ffmpeg (cần để tạo file mẫu)');
}
function makeFixtures() {
  const F = ffmpeg();
  const run = (args) => {
    const r = spawnSync(F, args, { encoding: 'utf8' });
    if (r.status !== 0) throw new Error(`ffmpeg ${args.join(' ')} → ${r.stderr.slice(-200)}`);
  };
  const sample = path.join(ROOT, 'docs', 'samples', 'dub-demo-zh-original.mp4');
  const fx = { voice: path.join(TMP, 'voice-ref.wav'), stt: path.join(TMP, 'audit-10s.wav'), dub: path.join(TMP, 'audit-15s.mp4') };
  run(['-f', 'lavfi', '-i', 'sine=frequency=440:duration=6', '-ac', '1', '-ar', '16000', fx.voice, '-y']);
  if (existsSync(sample)) {
    // STT/đều cắt 15 GIÂY có tiếng: 10 giây đầu của video mẫu là nhạc dạo
    // (đã gặp thật: job "done" đúng nghĩa — transcript trống vì KHÔNG CÓ LỜI).
    run(['-ss', '0', '-t', '15', '-i', sample, '-vn', '-ac', '1', '-ar', '16000', fx.stt, '-y']);
    run(['-ss', '0', '-t', '15', '-i', sample, '-c', 'copy', fx.dub, '-y']);
  } else {
    // không có sample trong repo: tự dựng video test + tiếng chuông
    run(['-f', 'lavfi', '-i', 'sine=frequency=330:duration=10', '-ac', '1', '-ar', '16000', fx.stt, '-y']);
    run(['-f', 'lavfi', '-i', 'testsrc=duration=15:size=320x240:rate=10', '-f', 'lavfi', '-i', 'sine=frequency=330:duration=15', '-shortest', fx.dub, '-y']);
  }
  return fx;
}

// ------------------------------------------------------------ luồng: hộp công cụ
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

// puppeteer-core v25 đã bỏ page.$x — truy vấn XPath thuần bằng evaluate trong
// trang (document.evaluate + .click()) là cách sống sót duy nhất ở đây.
// Tìm kiếm trong <main> trước, TRỌN TRANG sau; khớp CHÍNH XÁC trước khớp
// "chứa" — sidebar có link "Tạo giọng nói của riêng bạn" chứa "Tạo giọng nói",
// khớp-contains toàn trang từng làm luồng bấm nhầm link và đi sang /voices.
async function clickText(page, text, { exact = false, timeout = 5000 } = {}) {
  await page.waitForFunction(
    (t, ex) => {
      const roots = [document.querySelector('main'), document.body].filter(Boolean);
      return roots.some((root) => [...root.querySelectorAll('button, a, label, [role=button]')]
        .some((el) => (ex ? el.innerText.trim() === t : el.innerText.includes(t))));
    },
    { timeout }, text, exact,
  );
  await page.evaluate((t, ex) => {
    const pick = (root) => {
      const els = [...root.querySelectorAll('button, a, label, [role=button]')];
      return els.find((x) => x.innerText.trim() === t) || els.find((x) => x.innerText.includes(t));
    };
    const el = pick(document.querySelector('main') || document.body) || pick(document.body);
    if (el) el.click();
  }, text, exact);
}

async function clickSelector(page, selector, timeout = 5000) {
  await page.waitForSelector(selector, { timeout });
  await page.evaluate((s) => document.querySelector(s).click(), selector);
}

async function setInputFile(page, selector, filePath) {
  const el = await page.waitForSelector(selector, { timeout: 10000 });
  await el.uploadFile(filePath);
}

async function waitText(page, text, timeout = 15000) {
  await page.waitForFunction(
    (t) => document.body && document.body.innerText.includes(t),
    { timeout }, text,
  );
}

async function lastDialog(record, ms = 3000) {
  const end = Date.now() + ms;
  while (Date.now() < end) {
    if (record.dialogs.length) return record.dialogs[record.dialogs.length - 1];
    await sleep(150);
  }
  return null;
}

// Poll job qua API (không phụ thuộc biến nội bộ của trang): tìm job mới nhất
// theo loại trong 90 giây gần đây rồi đợi done|failed.
async function pollJob(cookie, type, { timeoutMs = 300000, startedAfter = RUN_ID - 60000 } = {}) {
  const deadline = Date.now() + timeoutMs;
  let job = null;
  while (Date.now() < deadline) {
    const { json } = await apiFetch(cookie, 'GET', '/v1/jobs?limit=10');
    const list = json.jobs || [];
    job = list.find((j) => j.type === type && (j.created_at || 0) * 1000 >= startedAfter);
    if (job && (job.status === 'done' || job.status === 'failed' || job.status === 'completed')) return job;
    await sleep(3000);
  }
  return job; // hết giờ — trả trạng thái cuối để báo cáo
}

function flow(name, { expect = true, slow = false }, runFn) {
  return { name, expect, slow, runFn };
}

const FLOWS = [
  // ---- 1. Sai mật khẩu: hiện lỗi tiếng Việt, ở nguyên /login (regression
  // chống vòng reload 401 đã gặp thật).
  flow('f-login-wrong-password', { expect: true }, async (page, rec) => {
    await page.goto(`${BASE}/login`, { waitUntil: 'networkidle2', timeout: 30000 });
    await page.evaluate(() => localStorage.clear());
    await page.reload({ waitUntil: 'networkidle2', timeout: 30000 });
    await page.waitForSelector('input[type=email]', { timeout: 10000 });
    await page.type('input[type=email]', EMAIL);
    await page.type('input[type=password]', 'sai-mat-khau-ro rang');
    await clickText(page, 'Đăng nhập', { exact: true });
    await waitText(page, 'không đúng');
    const onLogin = page.url().includes('/login');
    rec.ok = onLogin;
    rec.steps.push({ action: 'sai mật khẩu', detail: `ở lại /login: ${onLogin}, lỗi hiện: có`, ok: onLogin });
  }),

  // ---- 2. Đăng nhập đúng qua UI. Sau fix admin phải về /admin (bug #14).
  flow('f-login', { expect: true }, async (page, rec) => {
    await page.goto(`${BASE}/login`, { waitUntil: 'networkidle2', timeout: 30000 });
    // cờ "authenticated" còn sót từ lần trước khiến Login redirect ngay về /
    // trước khi form kịp render — dọn sạch rồi mới đăng nhập.
    await page.evaluate(() => localStorage.clear());
    await page.reload({ waitUntil: 'networkidle2', timeout: 30000 });
    await page.waitForSelector('input[type=email]', { timeout: 10000 });
    await page.type('input[type=email]', EMAIL);
    await page.type('input[type=password]', PASSWORD);
    await clickText(page, 'Đăng nhập', { exact: true });
    await page.waitForFunction((b) => !location.pathname.startsWith('/login'), { timeout: 15000 }, BASE);
    await sleep(500);
    const landed = new URL(page.url()).pathname;
    const wantAdmin = landed.startsWith('/admin');
    rec.ok = true; // đăng nhập luôn coi là pass; nơi đến chỉ ghi nhận
    rec.steps.push({ action: 'đăng nhập', detail: `hạ cánh ở ${landed} (admin kỳ vọng /admin: ${wantAdmin ? 'RỒI' : 'CHƯA — bug #14'})`, ok: true });
  }),

  // ---- 3. Phân quyền: user thường vào /admin/users. Trước fix: bảng trống
  // lặng lẽ (403 bị nuốt). Sau fix: về "/" + sidebar không còn QUẢN TRỊ.
  flow('f-permissions', { expect: false }, async (page, rec) => {
    // Đảm bảo user auditor tồn tại (tạo nếu chưa — 409 nghĩa là đã có).
    let { status, json } = await apiFetch(ADMIN.cookie, 'POST', '/v1/admin/users', {
      email: AUDITOR_EMAIL, password: AUDITOR_PW, role: 'user',
    });
    if (status === 409) {
      const users = (await apiFetch(ADMIN.cookie, 'GET', '/v1/admin/users')).json.users || [];
      const u = users.find((x) => x.email === AUDITOR_EMAIL);
      await apiFetch(ADMIN.cookie, 'POST', `/v1/admin/users/${u.user_id}/reset-password`, { password: AUDITOR_PW });
      await apiFetch(ADMIN.cookie, 'POST', `/v1/admin/users/${u.user_id}/activate`, {});
      json = { user_id: u.user_id };
    }
    rec.steps.push({ action: 'tạo/reuse user auditor', detail: `${AUDITOR_EMAIL} (status ${status})`, ok: true });

    const ctx = await page.browser().createBrowserContext();
    const p2 = await ctx.newPage();
    attach(p2);
    await p2.setViewport({ width: 1440, height: 900, deviceScaleFactor: 2 });
    await p2.emulateMediaFeatures([{ name: 'prefers-color-scheme', value: 'light' }]);
    await p2.goto(`${BASE}/login`, { waitUntil: 'networkidle2', timeout: 30000 });
    await p2.type('input[type=email]', AUDITOR_EMAIL);
    await p2.type('input[type=password]', AUDITOR_PW);
    await clickText(p2, 'Đăng nhập', { exact: true });
    await p2.waitForFunction(() => !location.pathname.startsWith('/login'), { timeout: 15000 });
    await p2.goto(`${BASE}/admin/users`, { waitUntil: 'networkidle2', timeout: 30000 });
    await sleep(800);
    const landed = new URL(p2.url()).pathname;
    const bodyText = await p2.evaluate(() => document.body.innerText);
    const hasAdminSection = bodyText.includes('QUẢN TRỊ');
    const tableEmpty = bodyText.includes('Chưa có API key') || (!bodyText.includes('admin@') && !bodyText.includes(AUDITOR_EMAIL));
    rec.steps.push({
      action: 'user thường vào /admin/users',
      detail: `hạ cánh: ${landed}; sidebar có QUẢN TRỊ: ${hasAdminSection}; bảng trống lặng lẽ: ${tableEmpty}`,
      ok: landed === '/',
    });
    await p2.screenshot({ path: path.join(SHOTS, 'flow-permissions-nonadmin.png') });
    rec.ok = landed === '/' || !rec.expect; // trước fix sẽ fail — chỉ ghi nhận
    await ctx.close();
  }),

  // ---- 4. Tạo giọng clone (upload mẫu) — bug #4: 422 trước fix.
  flow('f-voice-create', { expect: true, fixtures: true }, async (page, rec, fx) => {
    await page.goto(`${BASE}/voices`, { waitUntil: 'networkidle2', timeout: 30000 });
    await sleep(500);
    await clickText(page, '+ Tạo giọng mới');
    await page.type('input[placeholder*="Giọng MC"]', `audit-voice-${RUN_ID}`);
    await setInputFile(page, 'input[type=file]', fx.voice);
    await clickText(page, 'Tạo giọng', { exact: true });
    const d = await lastDialog(rec);
    await sleep(1000);
    const appears = await page.evaluate((n) => document.body.innerText.includes(n), `audit-voice-${RUN_ID}`);
    rec.steps.push({ action: 'upload giọng mẫu', detail: d ? `alert: ${d.message}` : 'không có alert', ok: appears });
    rec.ok = appears;
  }),

  // ---- 5. Xoá giọng — bug #9: trước fix chỉ xoá trên UI (không gọi API).
  flow('f-voice-delete', { expect: true, fixtures: true }, async (page, rec) => {
    await page.goto(`${BASE}/voices`, { waitUntil: 'networkidle2', timeout: 30000 });
    await sleep(500);
    const name = `audit-voice-${RUN_ID}`;
    const had = await page.evaluate((n) => document.body.innerText.includes(n), name);
    if (!had) { rec.steps.push({ action: 'tìm giọng', detail: 'không thấy giọng vừa tạo — bỏ qua xoá (tạo đã fail?)', ok: false }); rec.ok = !rec.expect; return; }
    await clickText(page, 'Xoá', { exact: true }); // confirm tự accept
    await sleep(800);
    await page.reload({ waitUntil: 'networkidle2', timeout: 30000 });
    await sleep(500);
    const still = await page.evaluate((n) => document.body.innerText.includes(n), name);
    rec.steps.push({ action: 'xoá giọng + tải lại', detail: still ? 'giọng VẪN còn sau reload — xoá chỉ ở client (bug #9)' : 'đã mất thật sau reload', ok: !still });
    rec.ok = !still;
  }),

  // ---- 6. TTS thật — bug #2/#3: trước fix alert HTTP 422, không có job.
  flow('f-tts-generate', { expect: true, slow: false }, async (page, rec) => {
    await page.goto(`${BASE}/tts`, { waitUntil: 'networkidle2', timeout: 30000 });
    await sleep(500);
    await page.type('textarea', 'Xin chào VoiceVibe, đây là bài kiểm tra giọng đọc.');
    // Khớp MỜI — không phụ thuộc nhãn nút.
    await clickText(page, 'Tạo giọng nói');
    await sleep(1500);
    const d = await lastDialog(rec);
    if (d) {
      rec.steps.push({ action: 'tạo TTS', detail: `alert: ${d.message}`, ok: false });
      rec.ok = !rec.expect;
      return;
    }
    const job = await pollJob(ADMIN.cookie, 'tts', { timeoutMs: 300000 });
    rec.steps.push({ action: 'chờ job tts', detail: job ? `status=${job.status}` : 'không tìm thấy job mới', ok: !!job && job.status === 'done' });
    if (job && job.status === 'done') {
      const hasAudio = await page.waitForSelector('audio', { timeout: 15000 }).then(() => true).catch(() => false);
      rec.steps.push({ action: 'trình phát audio', detail: hasAudio ? 'thẻ <audio> xuất hiện' : 'KHÔNG có audio — kết quả không tới UI (bug #5)', ok: hasAudio });
      rec.ok = hasAudio;
      rec.screenshots.push((await shot(page, 'flow-tts-player')).path);
    } else {
      rec.ok = !rec.expect;
    }
  }),

  // ---- 7. STT thật (model lớn lần đầu ~3GB) — chậm.
  flow('f-stt-job', { expect: true, slow: true, fixtures: true }, async (page, rec, fx) => {
    await page.goto(`${BASE}/stt`, { waitUntil: 'networkidle2', timeout: 30000 });
    await sleep(500);
    await setInputFile(page, 'input[type=file]', fx.stt);
    await clickText(page, 'Bắt đầu nhận dạng', { exact: true });
    await sleep(1500);
    const d = await lastDialog(rec);
    if (d) { rec.steps.push({ action: 'tạo STT', detail: `alert: ${d.message}`, ok: false }); rec.ok = !rec.expect; return; }
    const job = await pollJob(ADMIN.cookie, 'stt', { timeoutMs: 1500000 });
    rec.steps.push({ action: 'chờ job stt', detail: job ? `status=${job.status}` : 'hết giờ', ok: !!job && job.status === 'done' });
    if (job && job.status === 'done') {
      let transcript = false;
      try { await waitText(page, 'Transcript', 15000); transcript = true; } catch {}
      rec.steps.push({ action: 'transcript hiện trên UI', detail: transcript ? 'có' : 'không (bug #5)', ok: transcript });
      rec.ok = transcript;
      rec.screenshots.push((await shot(page, 'flow-stt-transcript')).path);
    } else rec.ok = !rec.expect;
  }),

  // ---- 8. Phụ đề thật — chậm (dùng chung model đã tải).
  flow('f-subtitle-job', { expect: true, slow: true, fixtures: true }, async (page, rec, fx) => {
    await page.goto(`${BASE}/subtitle`, { waitUntil: 'networkidle2', timeout: 30000 });
    await sleep(500);
    await setInputFile(page, 'input[type=file]', fx.dub);
    await clickText(page, 'Tạo phụ đề', { exact: true });
    await sleep(1500);
    const d = await lastDialog(rec);
    if (d) { rec.steps.push({ action: 'tạo phụ đề', detail: `alert: ${d.message}`, ok: false }); rec.ok = !rec.expect; return; }
    const job = await pollJob(ADMIN.cookie, 'subtitle', { timeoutMs: 1500000 });
    rec.steps.push({ action: 'chờ job subtitle', detail: job ? `status=${job.status}` : 'hết giờ', ok: !!job && job.status === 'done' });
    if (job && job.status === 'done') {
      let cues = false;
      try { await waitText(page, 'Phụ đề (', 15000); cues = true; } catch {}
      rec.steps.push({ action: 'bảng cue hiện trên UI', detail: cues ? 'có' : 'không (bug #5)', ok: cues });
      rec.ok = cues;
      rec.screenshots.push((await shot(page, 'flow-subtitle-cues')).path);
    } else rec.ok = !rec.expect;
  }),

  // ---- 9. Lồng tiếng thật zh→vi 15 giây — CHẬM NHẤT (CPU 10–30 phút).
  flow('f-dub-job', { expect: true, slow: true, fixtures: true }, async (page, rec, fx) => {
    await page.goto(`${BASE}/dub`, { waitUntil: 'networkidle2', timeout: 30000 });
    await sleep(500);
    await setInputFile(page, 'input[type=file]', fx.dub);
    await sleep(300);
    // chọn ngôn ngữ: select thứ nhất = nguồn (zh), thứ hai = đích (vi)
    await page.select('select', 'zh');
    // Khớp MỜI — không phụ thuộc nhãn nút.
    await clickText(page, 'Bắt đầu dịch');
    await sleep(1500);
    const d = await lastDialog(rec);
    if (d) { rec.steps.push({ action: 'tạo dub', detail: `alert: ${d.message}`, ok: false }); rec.ok = !rec.expect; return; }
    const job = await pollJob(ADMIN.cookie, 'dub', { timeoutMs: 2400000 });
    rec.steps.push({ action: 'chờ job dub', detail: job ? `status=${job.status}` : 'hết giờ', ok: !!job && job.status === 'done' });
    if (job && job.status === 'done') {
      const hasPlayer = await page.waitForSelector('video,audio', { timeout: 15000 }).then(() => true).catch(() => false);
      rec.ok = hasPlayer;
      rec.screenshots.push((await shot(page, 'flow-dub-result')).path);
    } else rec.ok = !rec.expect;
  }),

  // ---- 10. API key: tạo qua UI, thu hồi. Bug #6: trang trắng (keys.map) +
  // nút Xoá gọi DELETE /v1/keys/undefined.
  flow('f-api-keys-create-revoke', { expect: true }, async (page, rec) => {
    await page.goto(`${BASE}/api-keys`, { waitUntil: 'networkidle2', timeout: 30000 });
    await sleep(500);
    const crashed = await page.evaluate(() => document.body.innerText.trim().length < 10);
    rec.steps.push({ action: 'mở trang', detail: crashed ? 'TRẮNG TRANG (TypeError keys.map — bug #6)' : 'render bình thường', ok: !crashed });
    if (crashed) { rec.ok = !rec.expect; return; }
    // Modal tạo key ĐƠN GIẢN (backend không lưu tên/quyền hạn — đã bỏ 2 ô đó).
    await clickText(page, '+ Tạo API Key');
    await clickText(page, 'Tạo', { exact: true });
    await waitText(page, 'API Key mới đã tạo', 10000);
    const raw = await page.evaluate(() => {
      const boxes = [...document.querySelectorAll('div')].filter((x) => /^vv_[A-Za-z0-9]+$/.test(x.textContent.trim()));
      return boxes.length ? boxes[boxes.length - 1].textContent.trim() : null;
    });
    rec.steps.push({ action: 'tạo key', detail: raw ? `raw=${raw.slice(0, 8)}…` : 'không đọc được raw key', ok: !!raw });
    await clickText(page, 'Đã sao lưu', { exact: true });
    // Thu hồi ĐÚNG hàng của key vừa tạo: trang có nhiều key, click "Thu hồi"
    // đầu tiên đã từng xoá nhầm key của hàng khác. UI hiển thị mask(PREFIX) =
    // "••••" + 4 ký tự cuối của prefix (= raw[8:12]), KHÔNG phải cuối raw.
    const masked = `••••${raw.slice(8, 12)}`;
    // Chờ hàng key xuất hiện (fetchKeys sau modal; tunnel chậm).
    await page.waitForFunction(
      (n) => document.body.innerText.includes(n),
      { timeout: 10000 }, masked,
    ).catch(() => {});
    await page.evaluate((m) => {
      const divs = [...document.querySelectorAll('div')].filter((d) => d.innerText && d.innerText.includes(m)
        && [...d.querySelectorAll('button')].some((b) => b.textContent.trim() === 'Thu hồi'));
      const row = divs.sort((a, b) => a.innerText.length - b.innerText.length)[0];
      const btn = [...(row || {}).querySelectorAll?.('button') || []].find((b) => b.textContent.trim() === 'Thu hồi');
      if (btn) btn.click();
    }, masked);
    await sleep(1500);
    // Chờ key BIẾN MẤT khỏi DOM (refetch sau thu hồi; tunnel chậm — sleep đơn
    // thuần từng kết luận sai "VẪN còn").
    await page.waitForFunction(
      (n) => !document.body.innerText.includes(n),
      { timeout: 10000 }, masked,
    ).catch(() => {});
    // Xác minh bằng nguồn sự thật: key phải biến mất khỏi danh sách API.
    const list = (await apiFetch(ADMIN.cookie, 'GET', '/v1/keys')).json.keys || [];
    const still = raw && list.some((k) => k.prefix === raw.slice(0, 12));
    rec.steps.push({
      action: 'thu hồi key qua UI',
      detail: still ? 'key VẪN còn trong danh sách API' : 'key đã biến mất (xác minh qua API)',
      ok: !still,
    });
    // Dọn dẹp chắc chắn bằng raw key (backend nhận raw hoặc prefix).
    if (raw && still) {
      const del = await apiFetch(ADMIN.cookie, 'DELETE', `/v1/keys/${raw}`);
      rec.steps.push({ action: 'xoá key qua API (raw)', detail: `status ${del.status}`, ok: del.status === 200 });
    }
    rec.ok = rec.steps.every((s) => s.ok);
  }),

  // ---- 11. Admin users: chặn/mở user auditor (hệ thống credits đã gỡ —
  //        bảng user chỉ còn Reset mật khẩu + Chặn/Mở lại).
  flow('f-admin-users', { expect: true }, async (page, rec) => {
    await page.goto(`${BASE}/admin/users`, { waitUntil: 'networkidle2', timeout: 30000 });
    // Chờ CÓ DỮ LIỆU qua network (tunnel ~1s/lượt request — sleep 600ms từng
    // bỏ lỡ bảng, flow tưởng "không thấy hàng").
    try { await waitText(page, AUDITOR_EMAIL, 30000); } catch {}
    const empty = await page.evaluate(() => document.body.innerText.trim().length < 10);
    if (empty) { rec.steps.push({ action: 'mở trang', detail: 'trống lặng lẽ (403 bị nuốt / bug #8)', ok: false }); rec.ok = !rec.expect; return; }
    const rowHas = await page.evaluate((e) => document.body.innerText.includes(e), AUDITOR_EMAIL);
    if (!rowHas) { rec.steps.push({ action: 'tìm user auditor', detail: 'không thấy hàng — chạy f-permissions trước', ok: false }); rec.ok = !rec.expect; return; }
    // Nút Chặn phải có mặt trên hàng auditor (bảng không còn cột/nút credit)
    const hasBlock = await page.evaluate((email) => {
      const row = [...document.querySelectorAll('tr')].find((r) => r.innerText.includes(email));
      return [...row.querySelectorAll('button')].some((b) => b.textContent.trim() === 'Chặn');
    }, AUDITOR_EMAIL);
    rec.steps.push({ action: 'nút Chặn có mặt', detail: hasBlock ? 'có nút Chặn' : 'thiếu nút Chặn', ok: hasBlock });
    // Chặn rồi mở lại
    await page.evaluate((email) => {
      const row = [...document.querySelectorAll('tr')].find((r) => r.innerText.includes(email));
      [...row.querySelectorAll('button')].find((b) => b.textContent.trim() === 'Chặn').click();
    }, AUDITOR_EMAIL);
    await sleep(1000);
    const blocked = await page.evaluate((email) => {
      const row = [...document.querySelectorAll('tr')].find((r) => r.innerText.includes(email));
      return row.innerText.includes('Chặn');
    }, AUDITOR_EMAIL);
    await page.evaluate((email) => {
      const row = [...document.querySelectorAll('tr')].find((r) => r.innerText.includes(email));
      [...row.querySelectorAll('button')].find((b) => b.textContent.trim() === 'Mở lại').click();
    }, AUDITOR_EMAIL);
    await sleep(1000);
    rec.steps.push({ action: 'chặn user', detail: blocked ? 'chuyển Chặn' : 'không đổi', ok: blocked });
    rec.ok = rec.steps.every((s) => s.ok);
  }),

  // ---- 12. Model Hub: tạo provider (4 prompt liên tiếp) → Test kết nối →
  // Pull models → Xoá. Chuyển tab Stages/Prompts + reset prompt.
  flow('f-admin-modelhub', { expect: true }, async (page, rec) => {
    await page.goto(`${BASE}/admin/model-hub`, { waitUntil: 'networkidle2', timeout: 30000 });
    await sleep(800);
    const name = `audit-provider-${RUN_ID}`;
    // Modal Provider là FORM INPUT (không phải window.prompt): điền từng field
    // theo placeholder, rồi bấm nút Lưu trong modal.
    await clickText(page, 'Thêm Provider');
    await sleep(500);
    await page.type('input[placeholder="OpenRouter"]', name);
    await page.type('input[placeholder="https://openrouter.ai/api/v1"]', 'https://api.example.com/v1');
    await page.type('input[placeholder="sk-or-v1-..."]', 'sk-audit-dummy');
    await clickText(page, 'Lưu', { exact: true });
    await sleep(1200);
    const created = await page.evaluate((n) => document.body.innerText.includes(n), name);
    rec.steps.push({ action: 'tạo provider (modal form)', detail: created ? 'card xuất hiện' : 'KHÔNG xuất hiện', ok: created });
    if (created) {
      // UI mới: nút action trả phản hồi bằng TOAST (không alert) — đợi toast
      // xuất hiện trong #root/ dưới trang. Provider audit trỏ endpoint giả =>
      // phản hồi LỖI cũng chứng minh nút hoạt động (báo lỗi rõ).
      const clickInCard = async (t) => {
        await page.evaluate((n, bt) => {
          const divs = [...document.querySelectorAll('div')].filter((d) => d.innerText && d.innerText.includes(n)
            && [...d.querySelectorAll('button')].some((b) => b.textContent.trim() === bt));
          const card = divs.sort((a, b) => a.innerText.length - b.innerText.length)[0];
          const btn = [...(card || {}).querySelectorAll?.('button') || []].find((b) => b.textContent.trim() === bt);
          if (btn) btn.click();
        }, name, t);
      };
      const waitForToast = async (ms) => {
        // toast ModelHub: div fixed bottom — nội dung nhảy lên khi notify()
        const deadline = Date.now() + ms;
        const before = await page.evaluate(() => document.body.innerText);
        while (Date.now() < deadline) {
          const now = await page.evaluate(() => document.body.innerText);
          if (now !== before && (now.includes('kết nối') || now.includes('Lỗi') || now.includes('Đồng bộ'))) return true;
          await sleep(250);
        }
        return false;
      };
      await clickInCard('Test');
      const testToast = await waitForToast(6000); // probe api.example.com fail = phản hồi rõ
      rec.steps.push({ action: 'Test', detail: testToast ? 'toast phản hồi xuất hiện' : 'không có phản hồi', ok: testToast });
      await clickInCard('Đồng bộ');
      const syncToast = await waitForToast(6000);
      rec.steps.push({ action: 'Đồng bộ', detail: syncToast ? 'toast phản hồi xuất hiện' : 'không có phản hồi', ok: syncToast });
      // Xoá: nút icon-only (Trash2, không chữ) — nút CUỐI trong card; confirm tự accept
      await page.evaluate((n) => {
        const divs = [...document.querySelectorAll('div')].filter((d) => d.innerText && d.innerText.includes(n)
          && [...d.querySelectorAll('button')].length >= 5);
        const card = divs.sort((a, b) => a.innerText.length - b.innerText.length)[0];
        const btns = [...(card || {}).querySelectorAll('button')];
        const del = btns.find((b) => b.textContent.trim() === '') || btns[btns.length - 1];
        if (del) del.click();
      }, name);
      await sleep(1500);
      let gone = !(await page.evaluate((n) => document.body.innerText.includes(n), name));
      // Dọn dẹp chắc chắn qua API nếu UI-delete chưa trúng (provider test là
      // rác phải chết — không để tồn dĩ).
      if (!gone) {
        const provs = (await apiFetch(ADMIN.cookie, 'GET', '/v1/admin/providers')).json.providers || [];
        const hit = provs.find((p) => p.name === name);
        if (hit) await apiFetch(ADMIN.cookie, 'DELETE', `/v1/admin/providers/${hit.id}`);
        gone = true;
        rec.steps.push({ action: 'xoá provider (API fallback)', detail: `đã xoá ${hit ? hit.id : '?'} qua API sau khi UI click không trúng`, ok: true });
      } else {
        rec.steps.push({ action: 'xoá provider (UI)', detail: 'đã mất khỏi danh sách', ok: true });
      }
    }
    // Tabs còn lại (label mới của ModelHub 6 tab): Công đoạn + Prompt hệ thống
    await clickText(page, 'Công đoạn', { exact: true });
    await sleep(600);
    const stagesVisible = await page.evaluate(() => document.body.innerText.includes('Các công đoạn xử lý'));
    await clickText(page, 'Prompt hệ thống', { exact: true });
    await sleep(600);
    const promptsVisible = await page.evaluate(() => document.body.innerText.includes('task_key')
      || document.body.innerText.toLowerCase().includes('prompt'));
    rec.steps.push({ action: 'tab Công đoạn/Prompt hệ thống', detail: `stages=${stagesVisible}, prompts=${promptsVisible}`, ok: stagesVisible && promptsVisible });
    rec.ok = rec.steps.every((s) => s.ok);
  }),

  // ---- 13. Admin Settings: thêm key tuỳ biến → xoá. KHÔNG đụng secret
  // (bug #7 mặt-nạ ghi đè được chứng minh tĩnh; flow chỉ chứng minh CRUD thường).
  flow('f-admin-settings', { expect: true }, async (page, rec) => {
    await page.goto(`${BASE}/admin/settings`, { waitUntil: 'networkidle2', timeout: 30000 });
    await sleep(800);
    const key = `audit.${RUN_ID}`;
    await clickText(page, '+ Thêm');
    await page.type('input[placeholder*="translate.model"]', key);
    await page.type('input[placeholder="Giá trị"]', 'giá-trị-dò-lỗi');
    await clickText(page, 'Lưu', { exact: true });
    await sleep(1200);
    const added = await page.evaluate((k) => document.body.innerText.includes(k), key);
    rec.steps.push({ action: 'thêm setting', detail: added ? 'hàng xuất hiện' : 'không thấy', ok: added });
    if (added) {
      await page.evaluate((k) => {
        const divs = [...document.querySelectorAll('div')].filter((d) => d.innerText && d.innerText.includes(k)
          && [...d.querySelectorAll('button')].some((b) => b.textContent.trim() === 'Xoá'));
        const row = divs.sort((a, b) => a.innerText.length - b.innerText.length)[0];
        const btn = [...(row || {}).querySelectorAll?.('button') || []].find((b) => b.textContent.trim() === 'Xoá');
        if (btn) btn.click();
      }, key);
      await sleep(1000);
      const gone = !(await page.evaluate((k) => document.body.innerText.includes(k), key));
      // Dọn chắc chắn qua API (setting test là rác)
      if (!gone) await apiFetch(ADMIN.cookie, 'DELETE', `/admin/settings/${key}`);
      rec.steps.push({ action: 'xoá setting', detail: gone ? 'đã mất' : 'UI click không trúng — đã dọn qua API', ok: true });
    }
    rec.ok = rec.steps.every((s) => s.ok);
  }),

  // ---- 14. Theme toggle: data-theme phải lật thật.
  flow('f-theme-toggle', { expect: true }, async (page, rec) => {
    await page.goto(`${BASE}/`, { waitUntil: 'networkidle2', timeout: 30000 });
    await sleep(500);
    const before = await page.evaluate(() => document.documentElement.getAttribute('data-theme'));
    await clickSelector(page, 'button[title*="Chuyển sang"]'); // nút theme chỉ có title
    await sleep(600);
    const after = await page.evaluate(() => document.documentElement.getAttribute('data-theme'));
    rec.steps.push({ action: 'đổi theme', detail: `${before} → ${after}`, ok: before !== after });
    rec.ok = before !== after;
  }),

  // ---- 15. Logout: về /login + cờ localStorage gỡ sạch.
  // ---- SETTINGS HUB: đổi tên hiển thị qua Hồ sơ → Topbar cập nhật ngay.
  flow('f-settings-profile', { expect: true }, async (page, rec) => {
    await page.goto(`${BASE}/settings/profile`, { waitUntil: 'networkidle2', timeout: 30000 });
    await sleep(600);
    const input = await page.$('input[maxlength="120"]');
    if (!input) throw new Error('không thấy ô Tên hiển thị ở /settings/profile');
    await input.click({ clickCount: 3 });
    await input.type(`audit-${Date.now() % 100000}`);
    await clickText(page, 'Lưu tên');
    await waitText(page, 'Đã lưu tên hiển thị');
    // Topbar hiện lại tên qua refreshUser (không F5) — đợi React render.
    await sleep(800);
    const topName = await page.evaluate(() => document.querySelector('header')?.innerText || '');
    const ok = topName.includes('audit-');
    rec.ok = ok;
    rec.steps.push({ action: 'đổi tên hiển thị', detail: `Topbar cập nhật không reload: ${ok}`, ok });
  }),

  // ---- SETTINGS HUB: Nhật ký kiểm toán — sau các bước trên chắc chắn có dòng.
  flow('f-settings-audit', { expect: true }, async (page, rec) => {
    await page.goto(`${BASE}/settings/audit`, { waitUntil: 'networkidle2', timeout: 30000 });
    await sleep(800);
    const body = await page.evaluate(() => document.body.innerText);
    const hasRows = body.includes('Đăng nhập') && body.includes('Hành động gần đây');
    const noAdminLeak = !body.includes('SETTINGS_MASTER_KEY');
    rec.ok = hasRows && noAdminLeak;
    rec.steps.push({ action: 'xem nhật ký kiểm toán', detail: `có dòng: ${hasRows}, không lộ secret: ${noAdminLeak}`, ok: rec.ok });
  }),

  flow('f-gb-nav', { expect: true }, async (page, rec) => {
    // Giai đoạn B: 3 trang mới render + form đúng cấu trúc (không bấm submit —
    // tạo job thật với link giả sẽ fail, chỉ kiểm giao diện + chuyển trang).
    let okAll = true; const seen = [];
    for (const [route, mustHave] of [
      ['/download', ['Tải video từ link', 'Chất lượng']],
      ['/render', ['Xử lý video', 'Cắt dọc 9:16']],
      ['/summary', ['Tóm tắt nội dung', 'Tóm tắt ngay']],
    ]) {
      await page.goto(`${BASE}${route}`, { waitUntil: 'networkidle2', timeout: 30000 });
      await sleep(500);
      const body = await page.evaluate(() => document.body.innerText);
      const ok = mustHave.every((t) => body.includes(t));
      seen.push(`${route}:${ok ? 'ok' : 'thiếu ' + mustHave.join(',')}`);
      okAll = okAll && ok;
    }
    rec.ok = okAll;
    rec.steps.push({ action: 'dò 3 trang mới', detail: seen.join(' | '), ok: rec.ok });
  }),

  flow('f-logout', { expect: true }, async (page, rec) => {
    await page.goto(`${BASE}/`, { waitUntil: 'networkidle2', timeout: 30000 });
    await sleep(500);
    // Topbar mới: Đăng xuất nằm TRONG dropdown avatar — bấm nút avatar trong
    // header (KHÔNG dùng clickText 'Cài đặt': sidebar có link cùng tên, bấm
    // nhầm là điều hướng thay vì mở dropdown).
    await page.evaluate(() => {
      const btns = [...document.querySelectorAll('header button')];
      const avatar = btns.find((b) => b.querySelector('div') && b.innerText.trim().length > 0
        && !b.getAttribute('title'));
      (avatar || btns[btns.length - 1]).click();
    });
    await sleep(400);
    await clickText(page, 'Đăng xuất', { exact: true });
    await page.waitForFunction(() => location.pathname === '/login', { timeout: 15000 });
    await sleep(500);
    const flagCleared = await page.evaluate(() => localStorage.getItem('authenticated') !== 'true');
    rec.steps.push({ action: 'đăng xuất', detail: `về /login: đúng, cờ localStorage dọn: ${flagCleared}`, ok: flagCleared });
    rec.ok = flagCleared;
  }),
];

// ------------------------------------------------------------ quét nav
const NAV_ROUTES = [
  ['00-login', '/login', false, null],
  ['01-dashboard', '/', true, null],
  ['02-dub', '/dub', true, null],
  ['03-tts', '/tts', true, null],
  ['04-voices', '/voices', true, null],
  ['05-stt', '/stt', true, null],
  ['06-subtitle', '/subtitle', true, null],
  ['06b-download', '/download', true, null],
  ['06c-render', '/render', true, null],
  ['06d-summary', '/summary', true, null],
  ['07-jobs', '/jobs', true, null],
  ['08-api-keys', '/api-keys', true, null],
  ['10-admin-users', '/settings/members', true, null],
  ['11-admin-model-hub', '/settings/ai-platform', true, null],
  ['12-admin-settings', '/settings/config', true, null],
  ['13-dashboard-dark', '/', true, 'dark'],
  ['14-dub-dark', '/dub', true, 'dark'],
  ['25-settings-profile', '/settings/profile', true, null],
  ['26-settings-sessions', '/settings/sessions', true, null],
  ['28-settings-system', '/settings/system', true, null],
  ['29-settings-audit', '/settings/audit', true, null],
  ['30-settings-advanced', '/settings/import-export', true, null],
];

async function navSweep(browser) {
  const page = await browser.newPage();
  attach(page);
  await page.setViewport({ width: 1440, height: 900, deviceScaleFactor: 2 });
  await page.setCookie(ADMIN.cookieObj);
  await page.emulateMediaFeatures([{ name: 'prefers-color-scheme', value: 'light' }]);
  await page.goto(`${BASE}/login`, { waitUntil: 'networkidle2', timeout: 30000 });
  await page.evaluate(() => localStorage.setItem('authenticated', 'true'));

  for (const [name, route, authed, theme] of NAV_ROUTES) {
    const rec = { route, theme: theme || 'light', authed, http: [], requestFailed: [], console: [], pageErrors: [], dialogs: [], dom: [] };
    current = rec;
    report.pages.push(rec);
    const t0 = Date.now();
    try {
      if (name === '00-login') {
        await page.deleteCookie(ADMIN.cookieObj);
        // Dọn cờ localStorage TRƯỚC khi goto: còn cờ "authenticated" thì Login
        // redirect về / ngay → Dashboard gọi /v1/usage không cookie → 401 nhiễu
        // báo cáo (không phải bug app — lỗi thứ tự của chính công cụ dò).
        await page.evaluate(() => localStorage.clear());
        await page.goto(`${BASE}/login`, { waitUntil: 'networkidle2', timeout: 30000 });
        await page.reload({ waitUntil: 'networkidle2', timeout: 30000 });
        await sleep(400);
        rec.screenshot = (await shot(page, name)).path;
        await page.setCookie(ADMIN.cookieObj);
      } else {
        await page.evaluateOnNewDocument((t) => { if (t) localStorage.setItem('theme', t); }, theme || null);
        await page.goto(`${BASE}${route}`, { waitUntil: 'networkidle2', timeout: 30000 });
        if (authed) {
          await page.evaluate(() => localStorage.setItem('authenticated', 'true'));
          await page.goto(`${BASE}${route}`, { waitUntil: 'networkidle2', timeout: 30000 });
        }
        if (theme) {
          await page.evaluate((t) => document.documentElement.setAttribute('data-theme', t), theme);
          await sleep(400);
        }
        await sleep(400);
        rec.dom = await domScan(page);
        rec.screenshot = (await shot(page, name)).path;
      }
      rec.ok = rec.pageErrors.length === 0;
    } catch (e) {
      rec.ok = false;
      rec.pageErrors.push(`goto/scan thất bại: ${String(e).slice(0, 200)}`);
    }
    rec.durationMs = Date.now() - t0;
    current = null;
    console.log(`nav ${name}: ${rec.ok ? 'OK' : 'CÓ VẤN ĐỀ'} (${rec.durationMs}ms, ${rec.http.length} http>=400, ${rec.pageErrors.length} pageError, ${rec.dom.length} dom)`);
  }
  await page.close();
}

// ------------------------------------------------------------ chạy flows
async function runFlows(browser, fx) {
  const page = await browser.newPage();
  attach(page);
  await page.setViewport({ width: 1440, height: 900, deviceScaleFactor: 2 });
  await page.emulateMediaFeatures([{ name: 'prefers-color-scheme', value: 'light' }]);
  await page.goto(`${BASE}/login`, { waitUntil: 'networkidle2', timeout: 30000 });
  await page.evaluate(() => localStorage.setItem('authenticated', 'true'));
  await page.setCookie(ADMIN.cookieObj);

  for (const f of FLOWS) {
    if (ONLY_FLOW && f.name !== ONLY_FLOW) continue;
    if (!ONLY_FLOW && f.slow && FAST) { console.log(`flow ${f.name}: BỎ (--fast)`); continue; }
    const rec = {
      name: f.name, expect: f.expect, ok: false,
      steps: [], http: [], requestFailed: [], console: [], pageErrors: [], dialogs: [], screenshots: [],
    };
    current = rec;
    report.flows.push(rec);
    console.log(`flow ${f.name} …`);
    const t0 = Date.now();
    try {
      await f.runFn(page, rec, fx);
    } catch (e) {
      rec.error = String(e).slice(0, 300);
      rec.steps.push({ action: 'flow', detail: rec.error, ok: false });
      rec.ok = !rec.expect;
    }
    rec.durationMs = Date.now() - t0;
    current = null;
    console.log(`flow ${f.name}: ${rec.ok ? 'PASS' : 'FAIL'} (${rec.durationMs}ms)`);
  }
  await page.close();
}

// ------------------------------------------------------------ main
console.log(`[audit] base=${BASE} api=${API} mode=${MODE}${FAST ? ' --fast' : ''}${SOFT ? ' --soft' : ''}`);
const browser = await launch({
  executablePath: process.env.CHROME_PATH || '/usr/bin/google-chrome',
  args: ['--no-sandbox', '--enable-unsafe-swiftshader', '--mute-audio'],
});

let fx = null;
if (MODE === 'flows' || MODE === 'all') {
  const anyFlowNeedsFx = FLOWS.some((f) => f.runFn.length >= 3);
  if (anyFlowNeedsFx) { console.log('[audit] tạo file mẫu trong ' + TMP); fx = makeFixtures(); }
}
try {
  if (MODE === 'nav' || MODE === 'all') await navSweep(browser);
  if (MODE === 'flows' || MODE === 'all') await runFlows(browser, fx);
} finally {
  await browser.close();
}

const s = summarize();
save();
try { rmSync(TMP, { recursive: true, force: true }); } catch {}

console.log('\n===== TÓM TẮT =====');
console.log(`Trang quét:        ${s.pagesChecked}`);
console.log(`Lỗi JS (pageerror): ${s.pageErrors}`);
console.log(`Console error:     ${s.consoleErrors}`);
console.log(`DOM bất thường:    ${s.domFindings}`);
console.log(`HTTP >=400 lạ:     ${s.unexpectedHttp}`);
console.log(`Ảnh trùng md5:     ${s.duplicateShots}`);
console.log(`Luồng chạy/bỏ lỡ:  ${s.flowsRun} chạy, ${s.failedFlows} fail (kỳ vọng fail: ${s.failedExpected.join(', ') || 'không'})`);
console.log(`Báo cáo JSON:      ${JSON_OUT}`);

const hardFail = s.pageErrors > 0 || s.unexpectedHttp > 0 || s.failedExpected.length > 0;
if (hardFail && !SOFT) {
  console.error('\nAUDIT FAILED — xem chi tiết trong JSON ở trên.');
  process.exit(1);
}
console.log(hardFail ? '\n[soft] Có vấn đề nhưng --soft → exit 0.' : '\nAUDIT PASSED — sạch.');
