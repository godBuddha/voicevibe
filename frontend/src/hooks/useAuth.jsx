import { createContext, useContext, useState, useEffect } from 'react';
import { useApi } from './useApi.jsx';
import { adaptUser } from '../api/adapt.js';

// LƯU Ý SHAPE: backend trả JSON phẳng ({user_id, email, ...}) — KHÔNG có bọc
// {data: ...}. Bản sinh đầu tiên đọc res.data và luôn setUser(undefined);
// đã sửa thành chuyển bằng adaptUser ngay tại đây.
const AuthContext = createContext();

export function AuthProvider({ children }) {
  const { api } = useApi();
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    (async () => {
      try {
        // 401 khi chưa đăng nhập là trạng thái BÌNH THƯỜNG lúc mở app —
        // client đã tự gọi setOnUnauthorized ở useApi; bắt ở đây để không
        // văng lỗi chưa bắt trong console.
        const res = await api.get('/v1/auth/me');
        const u = adaptUser(res);
        setUser(u);
        localStorage.setItem('authenticated', 'true');
      } catch {
        setUser(null);
        localStorage.removeItem('authenticated');
      } finally {
        setLoading(false);
      }
    })();
  }, [api]);

  const login = async (email, password) => {
    const res = await api.post('/v1/auth/login', { body: { email, password } });
    // login trả {user_id, email, role, credits, redirect} — set trước, rồi
    // hỏi lại /v1/auth/me để có is_admin từ nguồn chính thống.
    localStorage.setItem('authenticated', 'true');
    try {
      setUser(adaptUser(await api.get('/v1/auth/me')));
    } catch {
      setUser(adaptUser(res));
    }
  };

  const logout = async () => {
    try {
      await api.post('/v1/auth/logout');
    } finally {
      localStorage.removeItem('authenticated');
      setUser(null);
      window.location.href = '/login';
    }
  };

  const signup = async (email, password) => {
    // Đăng ký công khai mặc định TẮT trong backend (auth.allow_signup) —
    // endpoint có thể trả 403; trang gọi phải hiển thị thông báo đó.
    const res = await api.post('/v1/auth/signup', { body: { email, password } });
    localStorage.setItem('authenticated', 'true');
    setUser(adaptUser(res));
  };

  const setupAccount = async (_name, email, password) => {
    // Backend SetupIn chỉ nhận email + password — trường tên bị bỏ qua.
    const res = await api.post('/v1/auth/setup', { body: { email, password } });
    localStorage.setItem('authenticated', 'true');
    try {
      setUser(adaptUser(await api.get('/v1/auth/me')));
    } catch {
      setUser(adaptUser(res));
    }
  };

  const value = {
    user,
    loading,
    login,
    logout,
    signup,
    setupAccount,
    isAuthenticated: !!user,
  };

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  return useContext(AuthContext);
}
