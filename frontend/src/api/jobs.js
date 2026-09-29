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

// Bước 3: chờ job chạy xong. resolve khi `done`/`failed` hoặc hết giờ —
// KHÔNG ném lỗi khi failed (trang cần hiện `error` của job). Trả shape đã
// adapt (id/progress{percent}/error) để trang không tự bóc JSON.
export async function pollJob(jobId, { onUpdate, timeoutMs = 600000, intervalMs = 2000 } = {}) {
  const deadline = Date.now() + timeoutMs;
  for (;;) {
    const job = adaptJob(await api.get(`/v1/jobs/${jobId}`));
    onUpdate?.(job);
    if (job.status === 'done' || job.status === 'failed') return job;
    if (Date.now() > deadline) return job;
    await new Promise((r) => setTimeout(r, intervalMs));
  }
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
