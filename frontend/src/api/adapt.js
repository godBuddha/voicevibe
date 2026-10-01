// Bộ chuyển hình dạng dữ liệu: backend thật (snake_case, phẳng) → hình mà các
// trang React sinh ra từ mock đang đọc (camelCase, lồng nhau).
//
// Vì sao cần: các trang được thiết kế theo hình dữ liệu mock; backend thật —
// nguồn sự thật đã được test kỹ — trả hình khác. Sửa từng trang là 13 nơi dễ
// sót; chuyển ở MỘT điểm (useApi khi không dùng mock) là bề mặt duy nhất phải
// giữ đồng bộ. Ghi chú bên mỗi hàm: field thật ← field trang mong đợi.

// GET /v1/usage: {total_jobs, by_type, by_status, running} — ĐẾM JOB (self-host
//   miễn phí, không có đơn vị tiền tệ).
export function adaptUsage(u) {
  if (!u || typeof u !== 'object') return { totalJobs: 0, running: 0, breakdown: {}, byStatus: {} };
  return {
    totalJobs: Number(u.total_jobs) || 0,
    running: Number(u.running) || 0,
    breakdown: u.by_type && typeof u.by_type === 'object' ? u.by_type : {},
    byStatus: u.by_status && typeof u.by_status === 'object' ? u.by_status : {},
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
    // Mới: đủ dữ liệu thật cho panel chi tiết (file/hoàn thành) — trước đây
    // job.file/completedAt không bao giờ có.
    params: p,
    label: label || typeLabel,
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
//   {user_id, email, role, ...} → {id, name, email, role}
export function adaptUser(u) {
  if (!u || typeof u !== 'object') return null;
  return {
    id: u.user_id ?? u.id,
    // Settings → Hồ sơ cho đặt TÊN hiển thị lưu DB (users.name). Chưa đặt thì
    // fallback phần trước '@' của email — giữ đúng hành vi cũ cho user cũ.
    name: u.name || (u.email || 'user').split('@')[0],
    email: u.email,
    role: u.role,
  };
}
