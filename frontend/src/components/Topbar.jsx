import { useEffect, useRef, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import {
  Bell, CheckCheck, CircleAlert, LogOut, PanelLeftClose, PanelLeftOpen,
  Search, Settings as SettingsIcon, Sun, Moon, Timer,
} from 'lucide-react';
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

const menuStyle = {
  position: 'absolute',
  top: 'calc(100% + 6px)',
  right: 0,
  minWidth: '230px',
  background: 'var(--surface)',
  border: '1px solid var(--border)',
  borderRadius: 'var(--radius)',
  boxShadow: 'var(--shadow-md)',
  zIndex: 'var(--z-modal)',
  padding: '6px',
};

const menuItem = {
  display: 'flex', alignItems: 'center', gap: '8px',
  padding: '7px 9px', borderRadius: 'var(--radius-sm)',
  color: 'var(--text)', textDecoration: 'none', fontSize: 'var(--text-sm)',
  cursor: 'pointer', border: 'none', background: 'transparent', width: '100%',
  textAlign: 'left',
};

const STATUS_LABELS = {
  queued: { label: 'Đang chờ', Icon: Timer, color: 'var(--text-dim)' },
  running: { label: 'Đang chạy', Icon: Timer, color: 'var(--info)' },
  done: { label: 'Hoàn thành', Icon: CheckCheck, color: 'var(--success)' },
  failed: { label: 'Thất bại', Icon: CircleAlert, color: 'var(--danger)' },
};

export default function Topbar({ sidebarHidden, onToggleSidebar }) {
  const { theme, toggle } = useTheme();
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const [searchOpen, setSearchOpen] = useState(false);
  const [menu, setMenu] = useState(null); // 'avatar' | 'bell' | null
  const [jobs, setJobs] = useState([]);
  const [notifyOn, setNotifyOn] = useState(false);
  const prevStatusRef = useRef({});
  const wrapRef = useRef(null);

  // Chuông THẬT: GET /v1/jobs mỗi 30s (đủ nhẹ, pattern Jobs.jsx) — badge đếm
  // job chưa xong, dropdown liệt kê, thông báo trình duyệt khi bật pref.
  useEffect(() => {
    let alive = true;
    const poll = async () => {
      try {
        const res = await fetch('/v1/jobs?limit=20', { credentials: 'include' });
        if (!res.ok || !alive) return;
        const d = await res.json();
        const list = d.jobs || [];
        setJobs(list);
        // Phát hiện CHUYỂN trạng thái (đang chạy → hoàn thành/thất bại) để báo.
        try { setNotifyOn(localStorage.getItem('vv_notify') === '1'); } catch {}
        if (typeof Notification !== 'undefined'
            && Notification.permission === 'granted'
            && (typeof localStorage !== 'undefined' && localStorage.getItem('vv_notify') === '1')) {
          for (const j of list) {
            const before = prevStatusRef.current[j.job_id];
            if (before && before !== j.status
                && (j.status === 'done' || j.status === 'failed')) {
              const s = STATUS_LABELS[j.status];
              new Notification(`VoiceVibe — ${s.label}`, {
                body: `${s.label}: job ${(j.params?.media_url || j.params?.text || j.type || '').toString().slice(0, 60)}`,
              });
            }
            prevStatusRef.current[j.job_id] = j.status;
          }
        } else {
          for (const j of list) prevStatusRef.current[j.job_id] = j.status;
        }
      } catch {
        // Im lặng — chuông không được gây lỗi console khi api tạm chết.
      }
    };
    poll();
    const t = setInterval(poll, 30000);
    return () => { alive = false; clearInterval(t); };
  }, []);

  // Bấm ra ngoài → đóng dropdown.
  useEffect(() => {
    const onDoc = (e) => {
      if (wrapRef.current && !wrapRef.current.contains(e.target)) setMenu(null);
    };
    document.addEventListener('mousedown', onDoc);
    return () => document.removeEventListener('mousedown', onDoc);
  }, []);

  const toggleNotify = async () => {
    try {
      if (notifyOn) {
        localStorage.setItem('vv_notify', '0');
        setNotifyOn(false);
        return;
      }
      let perm = Notification.permission;
      if (perm === 'default') perm = await Notification.requestPermission();
      if (perm === 'granted') {
        localStorage.setItem('vv_notify', '1');
        setNotifyOn(true);
      }
    } catch {
      // không hỗ trợ Notification — bỏ qua
    }
  };

  const active = jobs.filter((j) => j.status === 'queued' || j.status === 'running');

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

      <div style={{ display: 'flex', alignItems: 'center', gap: '4px' }} ref={wrapRef}>
        <button
          onClick={toggle}
          title={theme === 'dark' ? 'Chuyển sang sáng' : 'Chuyển sang tối'}
          style={iconBtn}
        >
          {theme === 'dark' ? <Sun size={15} /> : <Moon size={15} />}
        </button>

        {/* Chuông THẬT: badge đếm job chưa xong + dropdown job gần đây */}
        <div style={{ position: 'relative' }}>
          <button
            onClick={() => setMenu(menu === 'bell' ? null : 'bell')}
            title="Job & thông báo"
            style={{ ...iconBtn, position: 'relative' }}
          >
            <Bell size={15} />
            {active.length > 0 && (
              <span style={{
                position: 'absolute', top: '-2px', right: '-2px',
                minWidth: '14px', height: '14px', borderRadius: 'var(--radius-full)',
                background: 'var(--info)', color: '#fff', fontSize: '9px',
                fontWeight: 700, display: 'flex', alignItems: 'center',
                justifyContent: 'center', padding: '0 3px',
              }}>
                {active.length}
              </span>
            )}
          </button>
          {menu === 'bell' && (
            <div style={{ ...menuStyle, minWidth: '280px' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '4px 9px' }}>
                <b style={{ fontSize: 'var(--text-sm)' }}>Job gần đây</b>
                <button onClick={toggleNotify} style={{
                  fontSize: 'var(--text-xs)', cursor: 'pointer', border: '1px solid var(--border)',
                  background: notifyOn ? 'var(--success-light)' : 'var(--bg)',
                  color: notifyOn ? 'var(--success)' : 'var(--text-dim)',
                  borderRadius: 'var(--radius-full)', padding: '2px 8px', fontWeight: 600,
                }}>
                  {notifyOn ? 'Thông báo: bật' : 'Thông báo: tắt'}
                </button>
              </div>
              {jobs.length === 0 ? (
                <div style={{ padding: '8px 9px', fontSize: 'var(--text-sm)', color: 'var(--text-dim)' }}>
                  Chưa có job nào.
                </div>
              ) : jobs.slice(0, 6).map((j) => {
                const s = STATUS_LABELS[j.status] || STATUS_LABELS.queued;
                const label = j.params?.media_url?.split('/').pop()
                  || (j.params?.text ? j.params.text.slice(0, 40) : j.type);
                return (
                  <div key={j.job_id} style={{
                    display: 'flex', alignItems: 'center', gap: '8px',
                    padding: '5px 9px', fontSize: 'var(--text-sm)',
                  }}>
                    <s.Icon size={13} style={{ color: s.color, flexShrink: 0 }} />
                    <span style={{ flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', color: 'var(--text)' }}>
                      {label}
                    </span>
                    <span style={{ color: s.color, fontSize: 'var(--text-xs)', whiteSpace: 'nowrap' }}>
                      {s.label}
                    </span>
                  </div>
                );
              })}
              <Link to="/jobs" onClick={() => setMenu(null)} style={{ ...menuItem, color: 'var(--primary)', fontWeight: 600 }}>
                Xem tất cả trong Lịch sử Jobs →
              </Link>
            </div>
          )}
        </div>

        {/* Avatar → dropdown tài khoản (trước đây chỉ là khối chữ + nút logout) */}
        <div style={{ position: 'relative', marginLeft: '4px' }}>
          <button
            onClick={() => setMenu(menu === 'avatar' ? null : 'avatar')}
            title="Tài khoản"
            style={{
              display: 'flex', alignItems: 'center', gap: '6px', cursor: 'pointer',
              background: 'transparent', border: 'none', padding: '2px 4px',
              borderRadius: 'var(--radius-sm)',
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
            <div style={{ fontSize: 'var(--text-sm)', fontWeight: 600, color: 'var(--text)', whiteSpace: 'nowrap' }}>
              {user?.name}
            </div>
          </button>
          {menu === 'avatar' && (
            <div style={menuStyle}>
              <div style={{ padding: '7px 9px', borderBottom: '1px solid var(--border)', marginBottom: '4px' }}>
                <div style={{ fontSize: 'var(--text-sm)', fontWeight: 700, color: 'var(--text)' }}>
                  {user?.name}
                </div>
                <div style={{ fontSize: 'var(--text-xs)', color: 'var(--text-dim)' }}>
                  {user?.email}
                </div>
              </div>
              <button
                onClick={() => { setMenu(null); navigate('/settings/profile'); }}
                style={menuItem}
              >
                <SettingsIcon size={14} /> Cài đặt
              </button>
              <button
                onClick={() => { setMenu(null); logout(); }}
                style={{ ...menuItem, color: 'var(--danger)' }}
              >
                <LogOut size={14} /> Đăng xuất
              </button>
            </div>
          )}
        </div>
      </div>
    </header>
  );
}
