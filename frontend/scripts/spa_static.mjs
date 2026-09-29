// Server tĩnh dev có SPA fallback + TÙY CHỌN proxy API — thay thế
// `python3 -m http.server` khi chụp/kiểm thử: python trả 404 cho mọi route sâu
// (/dub, /admin/...) vì không có file thật, trong khi prod (Caddy) phục vụ
// index.html cho route client-side.
//
// KHÔNG dùng cho production — prod dùng Caddy (docker/web.Dockerfile).
//
// Proxy API (--api): Caddy trên prod proxy `/v1/*`, `/media/*`, `/healthz`,
// vào api:8000 — chế độ này nhại đúng hành vi đó để chạy
// SPA + API same-origin KHÔNG cần Node/Docker (bản self-host qua SSH tunnel
// trên GPU box): UI gọi path tương đối → cookie SameSite=Lax hoạt động, CORS
// không cần (đã gặp thật: tách cổng 8080→18080 phải bật CORS + CSRF allow-list).
//
// Run:  node scripts/spa_static.mjs [distDir] [port] [--api http://127.0.0.1:8000]
import { createServer, request as httpRequest } from 'node:http';
import { readFileSync, existsSync, statSync } from 'node:fs';
import path from 'node:path';

const args = process.argv.slice(2);
const ROOT = path.resolve(args[0] || 'dist');
const PORT = Number(args[1] || 8801);
const API_FLAG = args.indexOf('--api');
// Cụm đường dẫn prod-Caddy proxy vào api (Caddyfile: /v1/*, /media/*,
// /healthz). CHÚ Ý: /admin/settings KHÔNG được proxy — đó là ROUTE của SPA
// (gõ thẳng URL/F5 phải mở ứng dụng; JSON settings đã dời sang /v1/admin/settings
// — trùng đường thì trình duyệt hiện JSON thô thay vì app, đã gặp thật).
const API_PATTERNS = [/^\/v1\//, /^\/media\//, /^\/healthz$/];
const API_TARGET = API_FLAG >= 0 ? new URL(args[API_FLAG + 1] || 'http://127.0.0.1:8000') : null;
const MIME = {
  '.html': 'text/html', '.js': 'text/javascript', '.css': 'text/css',
  '.svg': 'image/svg+xml', '.png': 'image/png', '.ico': 'image/x-icon',
  '.json': 'application/json', '.woff2': 'font/woff2',
};

function proxyApi(req, res) {
  // Giữ nguyên method/headers/body (cookie + Content-Type multipart) — chỉ đổi
  // đích. HOST PHẢI GIỮ NGUYÊN: auth.py so CSRF `Origin` với `Host` — ghi đè
  // host thành đích nội bộ (127.0.0.1:8000) làm mọi POST từ tunnel/proxy bị
  // 403 "cross-origin request blocked" (Caddy prod giữ Host gốc nên không mắc;
  // đã gặp thật trên GPU box: tạo giọng/TTS/alert 403 toàn bộ qua SSH tunnel).
  const opts = {
    hostname: API_TARGET.hostname,
    port: API_TARGET.port,
    path: req.url,
    method: req.method,
    headers: req.headers,
  };
  const upstream = httpRequest(opts, (api) => {
    res.writeHead(api.statusCode, api.headers);
    api.pipe(res);
  });
  upstream.on('error', (e) => {
    res.writeHead(502, { 'Content-Type': 'application/json' });
    res.end(JSON.stringify({ detail: `api không phản hồi: ${e.message}` }));
  });
  req.pipe(upstream);
}

createServer((req, res) => {
  if (API_TARGET && API_PATTERNS.some((re) => re.test(req.url || '/'))) {
    return proxyApi(req, res);
  }
  const urlPath = decodeURIComponent((req.url || '/').split('?')[0]);
  let file = path.join(ROOT, path.normalize(urlPath).replace(/^(\.\.[/\\])+/, ''));
  // Đường ngoài root hoặc trỏ tới thư mục → fallback index.html (SPA route).
  if (!file.startsWith(ROOT) || !existsSync(file) || statSync(file).isDirectory()) {
    file = path.join(ROOT, 'index.html');
  }
  const body = readFileSync(file);
  res.writeHead(200, {
    'Content-Type': MIME[path.extname(file)] || 'application/octet-stream',
    'Cache-Control': 'no-store',
  });
  res.end(body);
}).listen(PORT, '127.0.0.1', () =>
  console.log(`spa_static ${ROOT} → http://127.0.0.1:${PORT}${API_TARGET ? ` (proxy → ${API_TARGET.href})` : ''}`));
