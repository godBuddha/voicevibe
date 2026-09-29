const BASE = import.meta.env.VITE_API_BASE || '';

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

  if (res.status === 401) {
    if (onUnauthorized) onUnauthorized();
    throw new Error('Unauthorized');
  }

  if (!res.ok) {
    const err = await res.json().catch(() => ({ message: res.statusText }));
    throw new Error(err.message || `HTTP ${res.status}`);
  }

  if (res.status === 204) return null;
  return res.json();
}

export const api = {
  get: (path, opts) => request('GET', path, opts),
  post: (path, opts) => request('POST', path, opts),
  put: (path, opts) => request('PUT', path, opts),
  patch: (path, opts) => request('PATCH', path, opts),
  del: (path, opts) => request('DELETE', path, opts),
};

export default api;
