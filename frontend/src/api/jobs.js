// Lớp ống dẫn job DUY NHẤT cho mọi trang tạo-nội-dung (Dub / TTS / STT /
// Subtitle). Trước đây mỗi trang tự dựng submit/poll/result và sai riêng một
// kiểu: Dub/STT/Subtitle nộp multipart KHÔNG có `type` (422), TTS nộp JSON
// thiếu `type` (422), cả bốn đọc `res.id` trong khi API trả `job_id` (poll
// `/v1/jobs/undefined` → 404), so `status === 'completed'` trong khi backend
// phát `done` (vòng chờ treo mãi), và kết quả nằm ở `/result` không trang nào
// gọi. Sửa tại MỘT điểm để không lặp lại 4 lần.
import api, { BASE } from './client.js';
import { adaptJob } from './adapt.js';

// Bước 1: nộp file → storage key (`media_url`). Backend trả `media_key`
// (không phải `key`/`url`) — main.py:489.
export async function uploadMedia(file) {
  const fd = new FormData();
  fd.append('file', file);
  const res = await api.post('/v1/media/upload', { body: fd, isMultipart: true });
  return res.media_key;
}

// Bước 2: tạo job JSON đúng chuẩn JobIn (`type` bắt buộc).
export async function createJob(payload) {
  const res = await api.post('/v1/jobs', { body: payload });
  return { ...res, jobId: res.job_id };
}

// Bước 3: chờ job chạy xong. resolve khi `done`/`failed`/`cancelled`/
// `interrupted` (GC1 — job mồ côi) hoặc hết giờ — KHÔNG ném lỗi khi failed
// (trang cần hiện `error` của job). Trả shape đã adapt (id/progress{percent}/
// error) để trang không tự bóc JSON. `cancelled` cũng phải dừng vòng: trước
// đây job bị hủy bên ngoài khiến vòng poll chạy tới hết timeout vô ích.
export async function pollJob(jobId, { onUpdate, timeoutMs = 600000, intervalMs = 2000 } = {}) {
  const deadline = Date.now() + timeoutMs;
  for (;;) {
    const job = adaptJob(await api.get(`/v1/jobs/${jobId}`));
    onUpdate?.(job);
    if (job.status === 'done' || job.status === 'failed'
        || job.status === 'cancelled' || job.status === 'interrupted') return job;
    if (Date.now() > deadline) return job;
    await new Promise((r) => setTimeout(r, intervalMs));
  }
}

// B1 — xem metadata link TRƯỚC khi tạo job (title/thumbnail/duration).
// Lỗi → ném lỗi có message thân thiện từ ERROR_MAP (UI hiển thị nguyên văn).
export async function downloadPreview(url, useCookies = false) {
  // GB8: use_cookies — xem metadata bằng cookies (video riêng tư / giới hạn
  // tuổi không xem trước được ẩn danh).
  return api.post('/v1/download/preview', { body: { url, use_cookies: useCookies } });
}

// B5 — catalog giọng đọc theo backend (local VieNeu / edge / cloud).
export async function ttsPresets(lang = 'vi') {
  return api.get(`/v1/tts/presets?lang=${encodeURIComponent(lang)}`);
}

// Hủy job đang chờ/đang chạy — job miễn phí (self-host), không trừ, không hoàn gì.
export async function cancelJob(jobId) {
  return api.post(`/v1/jobs/${jobId}/cancel`);
}

// Chạy lại job hỏng/đã hủy — TIẾP TỤC từ công đoạn đã xong (A1 sổ tay công
// đoạn): STT đã nghe xong không nghe lại, bản dịch đã dịch không dịch lại.
// Server từ chối job còn hoạt động (409) và job đã xong (409).
export async function retryJob(jobId) {
  const res = await api.post(`/v1/jobs/${jobId}/retry`);
  return { ...res, jobId: res.job_id };
}

// Xóa job khỏi lịch sử (chỉ job đã kết thúc — server từ chối job còn hoạt động).
export async function deleteJob(jobId) {
  return api.del(`/v1/jobs/${jobId}`);
}

// ---- GC2: SSE tiến độ job — thay polling list (Jobs 5s / Topbar 30s) ----
// MỘT kết nối EventSource chung cho cả app (singleton): server phát tín hiệu
// "job_ids đổi" → các trang tự refetch list. Sau (re)connect ép refetch một
// lần (onopen) — nếu không, list trắng tới khi có job đổi trạng thái. Fallback:
// EventSource lỗi lặp >3 lần/30 giây (proxy chặn, mạng lởm) → tự đóng và về
// polling 5s — trang Jobs không bao giờ chết vì SSE.
let _es = null;
const _handlers = new Set();
const _fails = [];
let _fallback = null;
// Kết nối hiện tại ĐÃ TỪNG mở thành công chưa (GC5). Server chủ động đóng sau
// 10 phút lifetime → EventSource tự reconnect là THIẾT KẾ — cờ này KHÔNG reset
// khi reconnect, chỉ reset khi tạo EventSource mới. Nhờ vậy phân biệt được:
//   - chưa từng mở nổi (401 sai phiên / 429 quá cap / proxy chặn) → lỗi chết,
//     EventSource sẽ tự reconnect VÔ HẠN → phải tự đóng ngay;
//   - đã từng mở, mạng chớp mắt → theo failWindow cũ (3 lỗi/30 giây).
let _everOpened = false;

function _authed() {
  try { return localStorage.getItem('authenticated') === 'true'; } catch { return false; }
}

function _notify(jobIds) {
  for (const h of _handlers) {
    try { h(jobIds); } catch (e) { console.error('subscribeJobs handler', e); }
  }
}

function _startFallback() {
  if (_fallback) return;
  console.warn('SSE không ổn định — về chế độ poll 5 giây');
  _fallback = setInterval(() => _notify(null), 5000);
}

function _stopFallback() {
  if (_fallback) { clearInterval(_fallback); _fallback = null; }
}

function _connect() {
  if (_es) _es.close();
  // Chưa đăng nhập thì KHÔNG mở SSE — EventSource 401 sẽ tự reconnect vô hạn
  // (console lỗi 401 dồn dập trên trang login — audit GC5 bắt được).
  if (!_authed()) return;
  _es = new EventSource('/v1/jobs/events');
  _everOpened = false;
  _es.addEventListener('change', (ev) => {
    _fails.length = 0;
    _stopFallback();
    let ids = null;
    try { ids = JSON.parse(ev.data).job_ids; } catch { /* tín hiệu rỗng vẫn refetch */ }
    _notify(ids);
  });
  _es.onopen = () => {
    _everOpened = true;
    _fails.length = 0;
    _notify(null); // refetch ngay sau (re)connect — Last-Event-ID lo phần tiếp diễn
  };
  _es.onerror = () => {
    if (!_everOpened) {
      // Chưa từng mở nổi: 401 sai phiên / 429 quá cap kết nối / proxy chặn.
      // Đóng ngay, về polling 5s nếu đang đăng nhập; chưa đăng nhập thì thôi
      // (đừng tạo thêm 401 trên trang login).
      _es.close();
      _es = null;
      _fails.length = 0;
      if (_authed()) _startFallback();
      return;
    }
    const now = Date.now();
    _fails.push(now);
    while (_fails.length && now - _fails[0] > 30000) _fails.shift();
    if (_fails.length > 3) {
      _es.close();
      _es = null;
      _startFallback();
    }
    // EventSource tự reconnect trước khi đạt ngưỡng — không làm gì thêm.
  };
}

export function subscribeJobs(onChange) {
  _handlers.add(onChange);
  if (!_es && !_fallback) _connect();
  return () => {
    _handlers.delete(onChange);
    if (!_handlers.size) {
      if (_es) { _es.close(); _es = null; }
      _stopFallback();
    }
  };
}

// GC5 #2 — công cụ dò (spa_audit) dùng: đóng SSE ngay trong trang cũ TRƯỚC
// khi điều hướng tới trang mới, nhả slot HTTP/1 của Chrome (SSE mở mãi chiếm
// 1 trong ~6 kết nối/host → fetch sau chờ slot → navigation timeout cận biên
// khi audit chạy chuỗi dày đặc). Trình duyệt thật KHÔNG gọi hàm này — chỉ
// script dò chạy chuỗi goto liên tiếp cần.
export function closeJobsStreamNow() {
  if (_es) { _es.close(); _es = null; }
  _stopFallback();
}

if (typeof window !== 'undefined') {
  try { window.__vv_close_es = closeJobsStreamNow; } catch { /* SSR */ }
}

// ---- GC3: phiên bản kết quả + nhân bản job ----

// Danh sách phiên bản kết quả (append-only) — cờ `current` = đang hiện hành.
export async function listArtifacts(jobId) {
  return api.get(`/v1/jobs/${jobId}/artifacts`);
}

// Khôi phục phiên bản làm kết quả hiện hành (chỉ đổi con trỏ, file không đụng).
export async function restoreArtifact(jobId, version) {
  return api.post(`/v1/jobs/${jobId}/artifacts/${version}/restore`);
}

// Nhân bản job thành job mới — patch là tham số muốn đổi (JSON, có thể {}).
export async function duplicateJob(jobId, patch = {}) {
  const res = await api.post(`/v1/jobs/${jobId}/duplicate`, { body: patch });
  return { ...res, jobId: res.job_id };
}

// Bước 4: kết quả. Text (SRT/TXT ≤64KB) → backend gửi kèm `content`. Media →
// fetch blob (cookie đi kèm) → objectURL, chắc chắn phát được không phụ thuộc
// cách <audio>/<video> gửi cookie cross-origin.
export async function getResult(jobId) {
  const res = await api.get(`/v1/jobs/${jobId}/result`);
  if (res.kind === 'text' && res.content != null) return res;
  const r = await fetch(BASE + res.download_url, { credentials: 'include' });
  if (!r.ok) throw new Error(`tải kết quả ${r.status}`);
  return { ...res, url: URL.createObjectURL(await r.blob()) };
}

// Phân tích SRT thật (kết quả STT = transcript.srt, phụ đề = subtitle.srt).
// Dòng chữ có thể mang người nói dạng `[SPEAKER_00]` (stt.to_srt) hoặc
// `SPEAKER_00: ` (subtitle.build_cues) — tách ra thành field `speaker`.
export function parseSrt(text) {
  const cues = [];
  const blocks = String(text || '').replace(/\r\n/g, '\n').trim().split(/\n{2,}/);
  const toSec = (t) => {
    const m = t.trim().match(/(\d+):(\d+):(\d+)[,.](\d+)/);
    return m ? +m[1] * 3600 + +m[2] * 60 + +m[3] + +m[4] / 1000 : 0;
  };
  for (const b of blocks) {
    const lines = b.split('\n');
    const i = lines.findIndex((l) => l.includes('-->'));
    if (i < 0) continue;
    const [a, z] = lines[i].split('-->');
    let body = lines.slice(i + 1).join('\n').trim();
    if (!body) continue;
    let speaker = '';
    const spk = body.match(/^\[?((?:SPEAKER)_\d+)\]?:?\s*/);
    if (spk) {
      speaker = spk[1];
      body = body.slice(spk[0].length).trim();
    }
    cues.push({ start: toSec(a), end: toSec(z), text: body, speaker });
  }
  return cues;
}
