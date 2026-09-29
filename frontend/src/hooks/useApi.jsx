import { createContext, useContext, useState, useCallback, useEffect, useMemo } from 'react';
import { mockRequest } from '../api/mock.js';
import api, { setOnUnauthorized } from '../api/client.js';
import { adaptUsage, adaptJob, adaptVoice } from '../api/adapt.js';

// Mock chỉ bật khi RÕ RÀNG yêu cầu (VITE_USE_MOCK=1) — mặc định là API thật.
// Bản build trong Docker (docker/web.Dockerfile) không set biến này nên luôn
// gọi backend thật; dev thuần UI dùng `VITE_USE_MOCK=1 npm run dev`.
const USE_MOCK = import.meta.env.VITE_USE_MOCK === '1';

const ApiContext = createContext();

// Điểm chuyển hình dạng duy nhất: các đường endpoint có hình khác giữa mock
// và backend thật được map tại đây, trang gọi không phải biết sự khác biệt.
const REAL_ADAPTERS = {
  '/v1/usage': (d) => adaptUsage(d),
  '/v1/jobs': (d) => ({ items: (d.jobs || []).map(adaptJob) }),
  // /v1/voices & /v1/keys: backend bọc {voices|keys: [...]}, trang đọc mảng.
  // (Trước đây ApiKeys setKeys({keys: []}) rồi keys.map → TypeError trắng trang.)
  '/v1/voices': (d) => (d.voices || []).map(adaptVoice),
  '/v1/keys': (d) => d.keys || [],
  '/v1/pricing': (d) => d.pricing || {},
};

export function ApiProvider({ children }) {
  const [useMock, setUseMock] = useState(USE_MOCK);

  useEffect(() => {
    setOnUnauthorized(() => {
      // 401 từ bất kỳ fetch nào → quay về login. Ghi dấu localStorage để
      // protectedLoader (router) chặn ngay cả trước khi AuthProvider kịp hỏi.
      localStorage.removeItem('authenticated');
      // Đã đứng ở /login thì KHÔNG reload: AuthProvider hỏi /me lúc mount →
      // 401 → reload → /me → ... vòng lặp reload vô hạn cho khách chưa đăng
      // nhập (trang login nhấp nháy không dừng).
      if (window.location.pathname !== '/login') {
        window.location.href = '/login';
      }
    });
  }, []);

  const request = useCallback((method, path, options = {}) => {
    const p = path.startsWith('/') ? path : `/${path}`;
    if (useMock) {
      return mockRequest(method.toUpperCase(), p, options);
    }
    return api[method](p, options).then((data) => {
      if (method === 'get' && REAL_ADAPTERS[p] && data && typeof data === 'object') {
        return REAL_ADAPTERS[p](data);
      }
      return data;
    });
  }, [useMock]);

  // useMemo BẮT BUỘC: value tạo mới mỗi render → `api` đổi tham chiếu →
  // useEffect(..., [api]) ở useAuth bắn lại /v1/auth/me sau MỖI render → khi
  // chưa đăng nhập: 401 → onUnauthorized reload /login → lặp vô hạn (networkidle
  // không bao giờ ổn, người dùng thật thì liên tục gọi API). Bản cũ "chạy được"
  // là nhờ backend rate-limit chấm dứt vòng lặp một cách may rủi.
  const value = useMemo(
    () => ({
      api: {
        get: (path, opts) => request('get', path, opts),
        post: (path, opts) => request('post', path, opts),
        put: (path, opts) => request('put', path, opts),
        patch: (path, opts) => request('patch', path, opts),
        del: (path, opts) => request('del', path, opts),
      },
      toggleMock: () => setUseMock((prev) => !prev),
      useMock,
    }),
    [request, useMock],
  );

  return <ApiContext.Provider value={value}>{children}</ApiContext.Provider>;
}

export function useApi() {
  return useContext(ApiContext);
}
