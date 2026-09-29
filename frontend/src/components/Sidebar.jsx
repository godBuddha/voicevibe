import { useState } from 'react';
import { Link, useLocation } from 'react-router-dom';
import { useTheme } from '../hooks/useTheme.jsx';

const navigation = [
  {
    heading: 'TẠO NỘI DUNG VỚI AI',
    items: [
      { label: 'Chuyển văn bản thành giọng nói', to: '/tts' },
      { label: 'TTS Studio', to: '/tts' },
      // Chưa có pipeline phụ-đề→giọng-nói: để '#' (hạng mục bị khoá) thay vì
      // trỏ /dub — bản mock trỏ bừa khiến highlight nhầm trên /dub.
      { label: 'Chuyển phụ đề thành giọng nói', to: '#' },
      { label: 'Tạo giọng nói của riêng bạn', to: '/voices' },
    ],
  },
  {
    heading: 'DỊCH THUẬT',
    items: [
      // Dịch văn bản/âm thanh có trong API (type=translate) nhưng chưa có trang
      // riêng — giữ '#' thay vì trỏ nhầm.
      { label: 'Dịch văn bản', to: '#' },
      { label: 'Dịch phụ đề', to: '/subtitle' },
      { label: 'Dịch âm thanh', to: '#' },
      { label: 'Dịch video', to: '/dub' },
    ],
  },
  {
    heading: 'AI GIỌI NÓI & VIDEO',
    items: [
      { label: 'Chuyển giọng nói thành văn bản', to: '/stt' },
      { label: 'Tạo video bằng AI', to: '#' },
      { label: 'Thay đổi giọng nói', to: '#' },
    ],
  },
];

const bottomLinks = [
  { label: 'Lịch sử Jobs', to: '/jobs' },
  { label: 'API cho nhà phát triển', to: '/api-keys' },
  { label: 'Gói dịch vụ & Giá', to: '/pricing' },
];

const adminLinks = [
  { label: 'Quản lý Users', to: '/admin/users' },
  { label: 'AI Model Hub', to: '/admin/model-hub' },
  { label: 'Cài đặt hệ thống', to: '/admin/settings' },
];

export default function Sidebar() {
  const [expanded, setExpanded] = useState(true);
  const { theme } = useTheme();
  const location = useLocation();

  return (
    <aside
      style={{
        width: expanded ? 'var(--sidebar-w)' : '64px',
 minWidth: '64px',
        background: 'var(--surface)',
        borderRight: '1px solid var(--border)',
        padding: expanded ? '32px 20px' : '20px 16px',
        display: 'flex',
        flexDirection: 'column',
        transition: 'width 0.3s',
        zIndex: 'var(--z-sidebar)',
      }}
    >
      <div style={{ marginBottom: '32px' }}>
        <Link
          to="/"
          style={{
            display: expanded ? 'block' : 'flex',
            alignItems: 'center',
            justifyContent: 'center',
          }}
        >
          <div
            style={{
              width: expanded ? '120px' : '32px',
              height: expanded ? '40px' : '32px',
              background: 'linear-gradient(135deg, var(--gradient-start), var(--gradient-end))',
              borderRadius: 'var(--radius)',
              fontWeight: 700,
              color: '#fff',
              display: 'flex',
              alignItems: 'center',
              justifyContent: expanded ? 'center' : 'center',
              fontSize: expanded ? '18px' : '20px',
            }}
          >
            {expanded ? 'VoiceVibe' : 'V'}
          </div>
        </Link>
        {expanded && (
          <p style={{ fontSize: 'var(--text-sm)', color: 'var(--text-dim)', marginTop: '8px' }}>
            AI Voice cho một thế giới mới
          </p>
        )}
      </div>

      <div style={{ flex: 1, overflow: 'auto' }} className="scrollbar-thin">
        {navigation.map((group) => (
          <div key={group.heading} style={{ marginBottom: expanded ? '24px' : '12px' }}>
            {expanded && (
              <h4
                style={{
                  fontSize: 'var(--text-xs)',
                  fontWeight: 600,
                  color: 'var(--text-muted)',
                  textTransform: 'uppercase',
                  marginBottom: '8px',
                }}
              >
                {group.heading}
              </h4>
            )}
            {group.items.map((item) => (
              <Link
                key={item.to}
                to={item.to}
                style={{
                  display: 'block',
                  padding: expanded ? '10px 12px' : '8px',
                  borderRadius: 'var(--radius)',
                  color: location.pathname === item.to ? 'var(--primary)' : 'var(--text-dim)',
                  background: location.pathname === item.to ? 'var(--primary-light)' : 'transparent',
                  textDecoration: 'none',
                  transition: 'all 0.2s',
                  fontSize: expanded ? 'var(--text-sm)' : '12px',
                  fontWeight: location.pathname === item.to ? 600 : 400,
                  marginBottom: expanded ? '4px' : '2px',
                  overflow: 'hidden',
                  textOverflow: 'ellipsis',
                  whiteSpace: 'nowrap',
                }}
                title={!expanded ? item.label : undefined}
              >
                {expanded ? item.label : item.label.charAt(0)}
              </Link>
            ))}
          </div>
        ))}
      </div>

      <div>
        {bottomLinks.map((link) => (
          <Link
            key={link.to}
            to={link.to}
            style={{
              display: expanded ? 'block' : 'flex',
              padding: expanded ? '10px 12px' : '8px',
              borderRadius: 'var(--radius)',
              color: 'var(--text-dim)',
              textDecoration: 'none',
              transition: 'all 0.2s',
              fontSize: expanded ? 'var(--text-sm)' : '12px',
              marginBottom: expanded ? '4px' : '2px',
              overflow: 'hidden',
              textOverflow: 'ellipsis',
              whiteSpace: 'nowrap',
            }}
            title={!expanded ? link.label : undefined}
          >
            {expanded ? link.label : link.label.charAt(0)}
          </Link>
        ))}

        {expanded && (
          <h4
            style={{
              fontSize: 'var(--text-xs)',
              fontWeight: 600,
              color: 'var(--text-muted)',
              textTransform: 'uppercase',
              marginBottom: '8px',
              marginTop: '16px',
            }}
          >
            QUẢN TRỊ
          </h4>
        )}
        {adminLinks.map((link) => (
          <Link
            key={link.to}
            to={link.to}
            style={{
              display: expanded ? 'block' : 'flex',
              padding: expanded ? '10px 12px' : '8px',
              borderRadius: 'var(--radius)',
              color: location.pathname === link.to ? 'var(--primary)' : 'var(--text-dim)',
              background: location.pathname === link.to ? 'var(--primary-light)' : 'transparent',
              textDecoration: 'none',
              transition: 'all 0.2s',
              fontSize: expanded ? 'var(--text-sm)' : '12px',
              fontWeight: location.pathname === link.to ? 600 : 400,
              marginBottom: expanded ? '4px' : '2px',
              overflow: 'hidden',
              textOverflow: 'ellipsis',
              whiteSpace: 'nowrap',
            }}
            title={!expanded ? link.label : undefined}
          >
            {expanded ? link.label : link.label.charAt(0)}
          </Link>
        ))}

        {expanded && (
          <div
            style={{
              background: 'linear-gradient(135deg, var(--gradient-start), var(--gradient-end))',
              borderRadius: 'var(--radius)',
              padding: '16px',
              color: '#fff',
            }}
          >
            <h5 style={{ fontSize: 'var(--text-sm)', fontWeight: 700, marginBottom: '4px' }}>
              Miễn phí 50.000 Credits
            </h5>
            <p style={{ fontSize: 'var(--text-xs)', opacity: 0.9, marginBottom: '12px' }}>
              Bắt dùng ngay các tính năng AI
            </p>
            <button
              style={{
                background: '#fff',
                color: 'var(--primary)',
                borderRadius: 'var(--radius-full)',
                padding: '8px 16px',
                fontSize: 'var(--text-xs)',
                fontWeight: 600,
                width: '100%',
                border: 'none',
              }}
            >
              Nâng cấp
            </button>
          </div>
        )}
      </div>
    </aside>
  );
}