export function QuickTools({ navigate }) {
  const tools = [
    { label: 'Tạo giọng nói', icon: '🗣️', to: '/tts' },
    { label: 'Dịch video', icon: '🎬', to: '/dub' },
    { label: 'Lịch sử jobs', icon: '📋', to: '/jobs' },
    { label: 'Quản lý giọng', icon: '🎤', to: '/voices' },
    { label: 'Chuyển giọng nói thành text', icon: '📝', to: '/stt' },
    { label: 'Tạo phụ đề', icon: '🎞️', to: '/subtitle' },
    { label: 'API Keys', icon: '🔑', to: '/api-keys' },
    { label: 'Mức sử dụng', icon: '📈', to: '/' },
  ];

  return (
    <div>
      <h3 style={{ fontSize: 'var(--text-xl)', marginBottom: '24px', fontWeight: 700 }}>
        Công cụ nhanh
      </h3>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(140px, 1fr))', gap: '16px' }}>
        {tools.map((tool) => (
          <button
            key={tool.label}
            onClick={() => navigate(tool.to)}
            style={{
              background: 'var(--surface)',
              border: '1px solid var(--border)',
              borderRadius: 'var(--radius-md)',
              padding: '20px 16px',
              textAlign: 'center',
              cursor: 'pointer',
              transition: 'all 0.2s',
              display: 'flex',
              flexDirection: 'column',
              alignItems: 'center',
              gap: '12px',
            }}
            onMouseEnter={(e) => {
              e.target.style.transform = 'translateY(-4px)';
              e.target.style.boxShadow = 'var(--shadow-md)';
            }}
            onMouseLeave={(e) => {
              e.target.style.transform = 'none';
              e.target.style.boxShadow = 'none';
            }}
          >
            <div style={{ fontSize: '28px' }}>{tool.icon}</div>
            <div style={{ fontSize: 'var(--text-sm)', fontWeight: 600, color: 'var(--text)' }}>
              {tool.label}
            </div>
          </button>
        ))}
      </div>
    </div>
  );
}