import { Link, useLocation } from 'react-router-dom';
import {
  Mic,
  Speech,
  Languages,
  Captions,
  AudioLines,
  Clapperboard,
  FileText,
  Sparkles,
  History,
  KeyRound,
  UsersRound,
  Boxes,
  Settings,
  AudioWaveform,
} from 'lucide-react';
import { useAuth } from '../hooks/useAuth.jsx';

// COMPACT UI: mỗi mục menu có icon Lucide 14px + label 12.5px, khoảng đệm 6-7px
// — mật độ cao như Open WebUI, nhìn một phát thấy được cả hệ tính năng.
const navigation = [
  {
    heading: 'TẠO NỘI DUNG VỚI AI',
    items: [
      { label: 'Chuyển văn bản thành giọng nói', to: '/tts', Icon: Mic },
      // LƯU Ý: bản mock từng có thêm mục "TTS Studio" cũng trỏ /tts — hai mục
      // cùng một trang nên bấm vào đâu cũng sáng cả hai. Hệ thống chỉ có MỘT
      // tính năng TTS, mục thừa đã bỏ.
      // Mục "Chuyển phụ đề thành giọng nói" của mock cũng đã bỏ: backend chỉ
      // có 5 loại job (tts/stt/translate/dub/subtitle), KHÔNG có pipeline
      // phụ-đề→giọng-nói — giữ lại chỉ tạo link chết bấm không ăn.
      { label: 'Tạo giọng nói của riêng bạn', to: '/voices', Icon: Speech },
    ],
  },
  {
    heading: 'DỊCH THUẬT',
    items: [
      { label: 'Dịch văn bản', to: '/translate-text', Icon: Languages },
      { label: 'Dịch phụ đề', to: '/subtitle', Icon: Captions },
      { label: 'Dịch âm thanh', to: '/translate-audio', Icon: AudioLines },
      { label: 'Dịch video', to: '/dub', Icon: Clapperboard },
      { label: 'Prompt của tôi', to: '/prompts', Icon: Sparkles },
    ],
  },
  {
    heading: 'AI GIỌI NÓI & VIDEO',
    items: [
      { label: 'Chuyển giọng nói thành văn bản', to: '/stt', Icon: FileText },
      // Hai mục mock "Tạo video bằng AI" và "Thay đổi giọng nói" đã bỏ —
      // backend không có pipeline nào cho chúng, giữ lại chỉ tạo link chết
      // (đã gặp thật với "Chuyển phụ đề thành giọng nói").
    ],
  },
];

const bottomLinks = [
  { label: 'Lịch sử Jobs', to: '/jobs', Icon: History },
  { label: 'API cho nhà phát triển', to: '/api-keys', Icon: KeyRound },
];

const adminLinks = [
  { label: 'Quản lý Users', to: '/admin/users', Icon: UsersRound },
  { label: 'AI Model Hub', to: '/admin/model-hub', Icon: Boxes },
  { label: 'Cài đặt hệ thống', to: '/admin/settings', Icon: Settings },
];

const itemStyle = (active) => ({
  display: 'flex',
  alignItems: 'center',
  gap: '8px',
  padding: '6px 8px',
  borderRadius: 'var(--radius-sm)',
  color: active ? 'var(--primary)' : 'var(--text-dim)',
  background: active ? 'var(--primary-light)' : 'transparent',
  textDecoration: 'none',
  transition: 'all 0.15s',
  fontSize: 'var(--text-sm)',
  fontWeight: active ? 600 : 400,
  overflow: 'hidden',
  textOverflow: 'ellipsis',
  whiteSpace: 'nowrap',
  marginBottom: '2px',
});

const headingStyle = {
  fontSize: '10px',
  fontWeight: 600,
  letterSpacing: '0.04em',
  color: 'var(--text-muted)',
  textTransform: 'uppercase',
  margin: '10px 8px 4px',
};

export default function Sidebar() {
  const { user } = useAuth();
  const location = useLocation();
  // Mục QUẢN TRỊ chỉ dành cho admin — trước đây hiện cho MỌI user, bấm vào thì
  // API trả 403 và các trang nuốt lỗi lặng lẽ → bảng trống trơ (đã gặp thật).
  const isAdmin = user?.role === 'admin';

  return (
    <aside
      className="scrollbar-thin"
      style={{
        width: 'var(--sidebar-w)',
        minWidth: 'var(--sidebar-w)',
        background: 'var(--surface)',
        borderRight: '1px solid var(--border)',
        padding: '12px 10px',
        display: 'flex',
        flexDirection: 'column',
        zIndex: 'var(--z-sidebar)',
        // Cả cột cuộn một khối: trước đây vùng menu có cuộn riêng (flex:1 +
        // overflow:auto) còn phần cuối (Jobs/API/Quản trị)
        // chiếm gần nửa chiều cao -> vùng menu còn ~5 dòng, "Chuyển giọng nói
        // thành văn bản", "Dịch video"... bị giấu dưới cuộn không ai thấy.
      }}
    >
      {/* Logo — một hàng mảnh thay khối logo 40px + tagline chiếm chỗ */}
      <Link
        to="/"
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: '8px',
          padding: '4px 8px 12px',
          textDecoration: 'none',
        }}
      >
        <div
          style={{
            width: '26px',
            height: '26px',
            flexShrink: 0,
            background: 'linear-gradient(135deg, var(--gradient-start), var(--gradient-end))',
            borderRadius: 'var(--radius-sm)',
            color: '#fff',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
          }}
        >
          <AudioWaveform size={15} strokeWidth={2.2} />
        </div>
        <span style={{ fontSize: 'var(--text-base)', fontWeight: 700, color: 'var(--fg-strong)' }}>
          VoiceVibe
        </span>
      </Link>

      <div className="scrollbar-thin" style={{ flex: 1 }}>
        {navigation.map((group) => (
          <div key={group.heading}>
            <h4 style={headingStyle}>{group.heading}</h4>
            {group.items.map(({ label, to, Icon }) => {
              const active = location.pathname === to;
              return (
                <Link key={to} to={to} style={itemStyle(active)} title={label}>
                  <Icon size={14} strokeWidth={2} style={{ flexShrink: 0, opacity: active ? 1 : 0.75 }} />
                  <span style={{ overflow: 'hidden', textOverflow: 'ellipsis' }}>{label}</span>
                </Link>
              );
            })}
          </div>
        ))}
      </div>

      <div>
        {bottomLinks.map(({ label, to, Icon }) => (
          <Link key={to} to={to} style={itemStyle(location.pathname === to)} title={label}>
            <Icon size={14} strokeWidth={2} style={{ flexShrink: 0, opacity: 0.75 }} />
            <span style={{ overflow: 'hidden', textOverflow: 'ellipsis' }}>{label}</span>
          </Link>
        ))}

        {isAdmin && <h4 style={{ ...headingStyle, marginTop: '12px' }}>QUẢN TRỊ</h4>}
        {isAdmin && adminLinks.map(({ label, to, Icon }) => {
          const active = location.pathname === to;
          return (
            <Link key={to} to={to} style={itemStyle(active)} title={label}>
              <Icon size={14} strokeWidth={2} style={{ flexShrink: 0, opacity: active ? 1 : 0.75 }} />
              <span style={{ overflow: 'hidden', textOverflow: 'ellipsis' }}>{label}</span>
            </Link>
          );
        })}
      </div>
    </aside>
  );
}
