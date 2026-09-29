import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../hooks/useAuth.jsx';

export default function Setup() {
  const [name, setName] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [confirm, setConfirm] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const navigate = useNavigate();
  const { setupAccount } = useAuth();

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!name || !email || !password) {
      setError('Vui lòng điền đầy đủ thông tin');
      return;
    }
    if (password.length < 6) {
      setError('Mật khẩu phải có ít nhất 6 ký tự');
      return;
    }
    if (password !== confirm) {
      setError('Mật khẩu không khớp');
      return;
    }
    try {
      setLoading(true);
      await setupAccount(name, email, password);
      localStorage.setItem('authenticated', 'true');
      navigate('/');
    } catch (err) {
      setError('Tạo tài khoản thất bại, vui lòng thử lại');
    } finally {
      setLoading(false);
    }
  };

  const gotoLogin = () => {
    navigate('/login');
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
        <h2 style={{ marginBottom: '12px', fontSize: 'var(--text-3xl)' }}>Tạo tài khoản mới</h2>
        <p style={{ color: 'var(--text-dim)', marginBottom: '40px' }}>
          Bắt đầu hành trình AI Voice của bạn
        </p>

        <form onSubmit={handleSubmit} style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
          <input
            type="text"
            placeholder="Tên đầy đủ"
            value={name}
            onChange={(e) => setName(e.target.value)}
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
          <input
            type="password"
            placeholder="Xác nhận mật khẩu"
            value={confirm}
            onChange={(e) => setConfirm(e.target.value)}
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
            {loading ? 'Đang tạo tài khoản...' : 'Tạo tài khoản'}
          </button>
          <div style={{ textAlign: 'center', marginTop: '16px' }}>
            <span style={{ color: 'var(--text-dim)', fontSize: 'var(--text-sm)' }}>
              Đã có tài khoản?{' '}
              <button
                type="button"
                onClick={gotoLogin}
                style={{
                  color: 'var(--primary)',
                  cursor: 'pointer',
                  background: 'none',
                  border: 'none',
                  padding: 0,
                  fontSize: 'var(--text-sm)',
                }}
              >
                Đăng nhập
              </button>
            </span>
          </div>
        </form>
      </div>
    </div>
  );
}