// Bộ chuyển hình dạng dữ liệu: backend thật (snake_case, phẳng) → hình mà các
// trang React sinh ra từ mock đang đọc (camelCase, lồng nhau).
//
// Vì sao cần: các trang được thiết kế theo hình dữ liệu mock; backend thật —
// nguồn sự thật đã được test kỹ — trả hình khác. Sửa từng trang là 13 nơi dễ
// sót; chuyển ở MỘT điểm (useApi khi không dùng mock) là bề mặt duy nhất phải
// giữ đồng bộ. Ghi chú bên mỗi hàm: field thật ← field trang mong đợi.

// GET /v1/usage: {free_quota, used, total, by_type}
//   → {used, limit, breakdown}  (totalJobs/runningJobs tính từ danh sách jobs)
export function adaptUsage(u) {
  if (!u || typeof u !== 'object') return { used: 0, limit: 0, breakdown: {} };
  return {
    used: Number(u.used) || 0,
    limit: Number(u.free_quota) || 0,
    breakdown: u.by_type && typeof u.by_type === 'object' ? u.by_type : {},
  };
}

// GET /v1/jobs: {"jobs": [{job_id, type, status, progress, result_key, error,
//   created_at, params, updated_at}]}
//   → mảng {id, type, status, progress{percent,message}, createdAt, ...}
export function adaptJob(j) {
  if (!j) return null;
  let progress;
  if (j.progress && typeof j.progress === 'object') {
    progress = j.progress; // đã ở dạng {percent, message}
  } else if (j.progress !== null && j.progress !== undefined) {
    progress = { percent: Number(j.progress) || 0, message: '' };
  }
  const p = j.params || {};
  // Nhãn hiển thị: tên file (media_url) → đầu đoạn text → fallback theo loại.
  const mediaName = p.media_url ? decodeURIComponent(p.media_url.split('/').pop()) : '';
  const typeLabel = TYPE_LABELS[j.type] || j.type;
  const label = mediaName || (p.text ? p.text.slice(0, 60) : typeLabel);
  return {
    id: j.job_id,
    type: j.type,
    status: j.status,
    progress,
    resultKey: j.result_key || null,
    error: j.error || null,
    createdAt: j.created_at ? new Date(j.created_at * 1000) : undefined,
    // Mới: đủ dữ liệu thật cho panel chi tiết (file/credit/hoàn thành) —
    // trước đây job.file/creditsUsed/completedAt không bao giờ có.
    params: p,
    label: label || typeLabel,
    credits: j.credits_charged ?? 0,
    updatedAt: j.updated_at ? new Date(j.updated_at * 1000) : undefined,
  };
}

const TYPE_LABELS = { dub: 'Lồng tiếng', tts: 'Văn bản → giọng nói', stt: 'Giọng nói → văn bản', translate: 'Dịch văn bản', subtitle: 'Tạo phụ đề' };

// GET /v1/voices: {voices: [{id, name, lang, engine, created_at}]}
//   → {id, name, lang, engine, isClone} (engine vieneu = giọng clone/từ mẫu)
export function adaptVoice(v) {
  if (!v || typeof v !== 'object') return null;
  return {
    id: v.id,
    name: v.name,
    lang: v.lang,
    engine: v.engine,
    isClone: v.engine === 'vieneu',
  };
}

// GET /v1/auth/me | POST /v1/auth/login | /v1/auth/setup
//   {user_id, email, role, credits, ...} → {id, name, email, role, credits}
export function adaptUser(u) {
  if (!u || typeof u !== 'object') return null;
  return {
    id: u.user_id ?? u.id,
    name: (u.email || 'user').split('@')[0],
    email: u.email,
    role: u.role,
    credits: Number(u.credits) || 0,
  };
}
