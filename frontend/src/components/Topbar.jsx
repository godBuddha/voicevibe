import { useState } from 'react';
import { Link } from 'react-router-dom';
import { useTheme } from '../hooks/useTheme.jsx';
import { useAuth } from '../hooks/useAuth.jsx';

export default function Topbar() {
  const { theme, toggle } = useTheme();
  const { user, logout } = useAuth();
  const [searchOpen, setSearchOpen] = useState(false);

  return (
    <header
      style={{
        height: 'var(--topbar-h)',
        background: 'var(--surface)',
        borderBottom: '1px solid var(--border)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        padding: '0 24px',
      }}
    >
      <div style={{ flex: 1, maxWidth: '500px' }}>
        <div
          style={{
            position: 'relative',
          }}
          onClick={() => setSearchOpen(!searchOpen)}
        >
          <input
            type="text"
            placeholder="Tìm kiếm (⌘K)"
            style={{
              width: '100%',
              padding: '8px 12px 8px 36px',
              borderRadius: 'var(--radius)',
              border: '1px solid var(--border)',
              background: 'var(--bg)',
              color: 'var(--text)',
              fontSize: 'var(--text-sm)',
            }}
          />
          <svg width="18" height="18" fill="none" style={{ position: 'absolute', left: '12px', top: '50%', transform: 'translateY(-50%)', opacity: 0.5 }}>
            <path d="M8.5 15C11.5376 15 14 12.5376 14 9.5C14 6.46243 11.5376 4 8.5 4C5.46243 4 3 6.46243 3 9.5C3 12.5376 5.46243 15 8.5 15Z" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
            <path d="M12.5 12.5L16 16" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
          </svg>
        </div>
      </div>

      <div style={{ display: 'flex', alignItems: 'center', gap: '16px' }}>
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: '8px',
            padding: '6px 12px',
            borderRadius: 'var(--radius-full)',
            background: 'var(--info-light)',
            color: 'var(--info)',
            fontSize: 'var(--text-sm)',
            fontWeight: 600,
          }}
        >
          <span>💎 Credits: {(user?.credits ?? 0).toLocaleString('vi-VN')}</span>
        </div>

        <button
          onClick={toggle}
          title={theme === 'dark' ? 'Chuyển sang sáng' : 'Chuyển sang tối'}
          style={{
            width: '40px',
            height: '40px',
            borderRadius: 'var(--radius)',
            background: 'var(--bg)',
            border: '1px solid var(--border)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            color: 'var(--text-dim)',
          }}
        >
          {theme === 'dark' ? '☀️' : '🌙'}
        </button>

        <button
          title="Thông báo"
          style={{
            width: '40px',
            height: '40px',
            borderRadius: 'var(--radius)',
            background: 'var(--bg)',
            border: '1px solid var(--border)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            color: 'var(--text-dim)',
          }}
        >
          🔔
        </button>

        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: '12px',
          }}
        >
          <div
            style={{
              width: '40px',
              height: '40px',
              borderRadius: 'var(--radius-full)',
              background: 'var(--gradient)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              color: '#fff',
              fontWeight: 700,
            }}
          >
            {user?.name?.charAt(0)?.toUpperCase() ?? 'A'}
          </div>
          <div>
            <div style={{ fontSize: 'var(--text-sm)', fontWeight: 600, color: 'var(--text)' }}>
              {user?.name}
            </div>
            <button
              onClick={logout}
              style={{
                fontSize: 'var(--text-xs)',
                color: 'var(--text-dim)',
                textDecoration: 'none',
                cursor: 'pointer',
                background: 'none',
                border: 'none',
                padding: 0,
              }}
            >
              Đăng xuất
            </button>
          </div>
        </div>
      </div>
    </header>
  );
}