import { useState } from 'react';
import { Link } from 'react-router-dom';
import { PanelLeftClose, PanelLeftOpen, Search, Sun, Moon, Bell, LogOut } from 'lucide-react';
import { useTheme } from '../hooks/useTheme.jsx';
import { useAuth } from '../hooks/useAuth.jsx';

// Nút icon vuông nhỏ 28px — chuẩn compact: đủ vùng bấm, không chiếm chỗ.
const iconBtn = {
  width: '28px',
  height: '28px',
  borderRadius: 'var(--radius-sm)',
  background: 'transparent',
  border: 'none',
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'center',
  color: 'var(--text-dim)',
  cursor: 'pointer',
  flexShrink: 0,
};

export default function Topbar({ sidebarHidden, onToggleSidebar }) {
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
        padding: '0 12px',
        gap: '12px',
        flexShrink: 0,
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: '8px', flex: 1, maxWidth: '420px' }}>
        {/* Gập/mở sidebar: ẩn hoàn toàn -> nhường nguyên hàng ngang cho nội dung */}
        <button
          onClick={onToggleSidebar}
          title={sidebarHidden ? 'Hiện thanh menu' : 'Ẩn thanh menu'}
          style={iconBtn}
        >
          {sidebarHidden ? <PanelLeftOpen size={16} /> : <PanelLeftClose size={16} />}
        </button>
        <div style={{ position: 'relative', width: '100%' }} onClick={() => setSearchOpen(!searchOpen)}>
          <input
            type="text"
            placeholder="Tìm kiếm (⌘K)"
            style={{
              width: '100%',
              padding: '5px 10px 5px 28px',
              borderRadius: 'var(--radius-sm)',
              border: '1px solid var(--border)',
              background: 'var(--bg)',
              color: 'var(--text)',
              fontSize: 'var(--text-sm)',
            }}
          />
          <Search
            size={13}
            style={{ position: 'absolute', left: '9px', top: '50%', transform: 'translateY(-50%)', opacity: 0.5 }}
          />
        </div>
      </div>

      <div style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
        <button
          onClick={toggle}
          title={theme === 'dark' ? 'Chuyển sang sáng' : 'Chuyển sang tối'}
          style={iconBtn}
        >
          {theme === 'dark' ? <Sun size={15} /> : <Moon size={15} />}
        </button>

        <button title="Thông báo" style={iconBtn}>
          <Bell size={15} />
        </button>

        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: '8px',
            marginLeft: '8px',
            paddingLeft: '10px',
            borderLeft: '1px solid var(--border)',
          }}
        >
          <div
            style={{
              width: '26px',
              height: '26px',
              borderRadius: 'var(--radius-full)',
              background: 'var(--gradient)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              color: '#fff',
              fontSize: 'var(--text-xs)',
              fontWeight: 700,
              flexShrink: 0,
            }}
          >
            {user?.name?.charAt(0)?.toUpperCase() ?? 'A'}
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
            <div style={{ fontSize: 'var(--text-sm)', fontWeight: 600, color: 'var(--text)', whiteSpace: 'nowrap' }}>
              {user?.name}
            </div>
            <button
              onClick={logout}
              title="Đăng xuất"
              style={{ ...iconBtn, width: '24px', height: '24px' }}
            >
              <LogOut size={13} />
            </button>
          </div>
        </div>
      </div>
    </header>
  );
}
