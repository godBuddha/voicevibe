import {
  Mic,
  Clapperboard,
  History,
  Speech,
  FileText,
  Captions,
  KeyRound,
  ChartLine,
} from 'lucide-react';

export function QuickTools({ navigate }) {
  const tools = [
    { label: 'Tạo giọng nói', Icon: Mic, to: '/tts', color: 'var(--primary)', bg: 'var(--primary-light)' },
    { label: 'Dịch video', Icon: Clapperboard, to: '/dub', color: 'var(--info)', bg: 'var(--info-light)' },
    { label: 'Lịch sử jobs', Icon: History, to: '/jobs', color: 'var(--success)', bg: 'var(--success-light)' },
    { label: 'Quản lý giọng', Icon: Speech, to: '/voices', color: 'var(--accent)', bg: 'var(--accent-light)' },
    { label: 'Giọng nói thành text', Icon: FileText, to: '/stt', color: 'var(--info)', bg: 'var(--info-light)' },
    { label: 'Tạo phụ đề', Icon: Captions, to: '/subtitle', color: 'var(--warning)', bg: 'var(--warning-light)' },
    { label: 'API Keys', Icon: KeyRound, to: '/api-keys', color: 'var(--danger)', bg: 'var(--danger-light)' },
    { label: 'Mức sử dụng', Icon: ChartLine, to: '/', color: 'var(--success)', bg: 'var(--success-light)' },
  ];

  return (
    <div>
      <h3 style={{ fontSize: 'var(--text-base)', marginBottom: '10px', fontWeight: 700 }}>
        Công cụ nhanh
      </h3>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(110px, 1fr))', gap: '8px' }}>
        {tools.map(({ Icon, ...tool }) => (
          <button
            key={tool.label}
            onClick={() => navigate(tool.to)}
            style={{
              background: 'var(--surface)',
              border: '1px solid var(--border)',
              borderRadius: 'var(--radius-md)',
              padding: '10px 6px',
              textAlign: 'center',
              cursor: 'pointer',
              transition: 'all 0.15s',
              display: 'flex',
              flexDirection: 'column',
              alignItems: 'center',
              gap: '6px',
            }}
            onMouseEnter={(e) => {
              e.currentTarget.style.transform = 'translateY(-2px)';
              e.currentTarget.style.boxShadow = 'var(--shadow)';
              e.currentTarget.style.borderColor = 'var(--border-strong)';
            }}
            onMouseLeave={(e) => {
              e.currentTarget.style.transform = 'none';
              e.currentTarget.style.boxShadow = 'none';
              e.currentTarget.style.borderColor = 'var(--border)';
            }}
          >
            <div
              style={{
                width: '30px',
                height: '30px',
                borderRadius: 'var(--radius-sm)',
                background: tool.bg,
                color: tool.color,
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
              }}
            >
              <Icon size={15} strokeWidth={2} />
            </div>
            <div style={{ fontSize: 'var(--text-xs)', fontWeight: 600, color: 'var(--text)', lineHeight: 1.3 }}>
              {tool.label}
            </div>
          </button>
        ))}
      </div>
    </div>
  );
}
