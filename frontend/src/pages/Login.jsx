import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../hooks/useAuth.jsx';

export default function Login() {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const navigate = useNavigate();
  const { login } = useAuth();

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!email || !password) {
      setError('Vui lòng nhập cả email và mật khẩu');
      return;
    }
    try {
      setLoading(true);
      await login(email, password);
      localStorage.setItem('authenticated', 'true');
      navigate('/');
    } catch (err) {
      setError('Email hoặc mật khẩu không đúng');
    } finally {
      setLoading(false);
    }
  };

  const gotoSetup = () => {
    navigate('/setup');
  };

  return (
    <div
      style={{
        minHeight: '100vh',
        background: 'var(--gradient)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        padding: '32px',
      }}
    >
      <div
        style={{
          background: 'var(--surface)',
          borderRadius: 'var(--radius-lg)',
          padding: '48px',
          width: '100%',
          maxWidth: '440px',
          textAlign: 'center',
        }}
      >
        <h2 style={{ marginBottom: '12px', fontSize: 'var(--text-3xl)' }}>Chào mừng trở lại</h2>
        <p style={{ color: 'var(--text-dim)', marginBottom: '40px' }}>
          Đăng nhập vào tài khoản YupVox của bạn
        </p>

        <form onSubmit={handleSubmit} style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
          <div>
            <input
              type="email"
              placeholder="Email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              style={{
                width: '100%',
                padding: '14px 16px',
                borderRadius: 'var(--radius)',
                border: '1px solid var(--border)',
                fontSize: 'var(--text-base)',
                background: 'var(--bg)',
                color: 'var(--text)',
              }}
              required
            />
          </div>
          <div>
            <input
              type="password"
              placeholder="Mật khẩu"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              style={{
                width: '100%',
                padding: '14px 16px',
                borderRadius: 'var(--radius)',
                border: '1px solid var(--border)',
                fontSize: 'var(--text-base)',
                background: 'var(--bg)',
                color: 'var(--text)',
              }}
              required
            />
          </div>
          {error && (
            <div style={{ color: 'var(--danger)', fontSize: 'var(--text-sm)', textAlign: 'left' }}>
              {error}
            </div>
          )}
          <button
            type="submit"
            disabled={loading}
            style={{
              padding: '14px 24px',
              borderRadius: 'var(--radius)',
              background: 'var(--gradient)',
              color: '#fff',
              border: 'none',
              fontSize: 'var(--text-base)',
              fontWeight: 600,
              cursor: loading ? 'not-allowed' : 'pointer',
              opacity: loading ? 0.7 : 1,
            }}
          >
            {loading ? 'Đang đăng nhập...' : 'Đăng nhập'}
          </button>
          <div style={{ textAlign: 'center', marginTop: '16px' }}>
            <span style={{ color: 'var(--text-dim)', fontSize: 'var(--text-sm)' }}>
              Chưa có tài khoản?{' '}
              <button
                type="button"
                onClick={gotoSetup}
                style={{
                  color: 'var(--primary)',
                  cursor: 'pointer',
                  background: 'none',
                  border: 'none',
                  padding: 0,
                  fontSize: 'var(--text-sm)',
                }}
              >
                Đăng ký ngay
              </button>
            </span>
          </div>
        </form>
      </div>
    </div>
  );
}