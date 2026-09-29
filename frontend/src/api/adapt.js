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

// GET /v1/jobs: {"jobs": [{job_id, type, status, progress, result_key, error, created_at}]}
//   → mảng {id, type, status, progress{percent,message}, createdAt, ...}
export function adaptJob(j) {
  if (!j) return null;
  let progress;
  if (j.progress && typeof j.progress === 'object') {
    progress = j.progress; // đã ở dạng {percent, message}
  } else if (j.progress !== null && j.progress !== undefined) {
    progress = { percent: Number(j.progress) || 0, message: '' };
  }
  return {
    id: j.job_id,
    type: j.type,
    status: j.status,
    progress,
    resultKey: j.result_key || null,
    error: j.error || null,
    createdAt: j.created_at ? new Date(j.created_at * 1000) : undefined,
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
