export const BASE = import.meta.env.VITE_API_BASE || '';

let onUnauthorized = null;

export function setOnUnauthorized(fn) {
  onUnauthorized = fn;
}

async function request(method, path, options = {}) {
  const { body, isMultipart, query } = options;
  let url = BASE + path;
  if (query) {
    const params = new URLSearchParams(query);
    url += '?' + params.toString();
  }

  const headers = {};
  let fetchBody = undefined;

  if (body !== undefined) {
    if (isMultipart) {
      fetchBody = body;
    } else {
      headers['Content-Type'] = 'application/json';
      fetchBody = JSON.stringify(body);
    }
  }

  const res = await fetch(url, {
    method,
    headers,
    body: fetchBody,
    credentials: 'include',
  });

  // Đọc body MỘT lần. 401 cũng mang detail tiếng Việt ("Email hoặc mật khẩu
  // không đúng") — trước đây nhánh 401 ném 'Unauthorized' TRƯỚC khi kịp đọc
  // body, trang đăng nhập hiện chữ không liên quan thay vì lý do thật.
  let payload = {};
  try {
    payload = await res.json();
  } catch { /* 204/không body */ }

  if (res.status === 401) {
    if (onUnauthorized) onUnauthorized();
    throw new Error(payload.detail || 'Unauthorized');
  }

  if (!res.ok) {
    // Backend trả lý do tiếng Việt trong `detail` ({detail: "bilingual cần
    // target_lang…"}). Trước đây chỉ đọc `message` → người dùng thấy vô nghĩa
    // "HTTP 422" thay vì lý do thật (đã gặp thật khi dò UI).
    throw new Error(payload.detail || payload.message || `HTTP ${res.status}`);
  }

  if (res.status === 204) return null;
  return payload;
}

export const api = {
  get: (path, opts) => request('GET', path, opts),
  post: (path, opts) => request('POST', path, opts),
  put: (path, opts) => request('PUT', path, opts),
  patch: (path, opts) => request('PATCH', path, opts),
  del: (path, opts) => request('DELETE', path, opts),
};

export default api;
