// Server tĩnh dev có SPA fallback — thay thế `python3 -m http.server` khi
// chụp/kiểm thử: python trả 404 cho mọi route sâu (/dub, /admin/...) vì không
// có file thật, trong khi prod (Caddy) phục vụ index.html cho route client-side.
// KHÔNG dùng cho production — prod dùng Caddy (docker/web.Dockerfile).
//
// Run:  node scripts/spa_static.mjs [distDir] [port]
import { createServer } from 'node:http';
import { readFileSync, existsSync, statSync } from 'node:fs';
import path from 'node:path';

const ROOT = path.resolve(process.argv[2] || 'dist');
const PORT = Number(process.argv[3] || 8801);
const MIME = {
  '.html': 'text/html', '.js': 'text/javascript', '.css': 'text/css',
  '.svg': 'image/svg+xml', '.png': 'image/png', '.ico': 'image/x-icon',
  '.json': 'application/json', '.woff2': 'font/woff2',
};

createServer((req, res) => {
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
}).listen(PORT, '127.0.0.1', () => console.log(`spa_static ${ROOT} → http://127.0.0.1:${PORT}`));
