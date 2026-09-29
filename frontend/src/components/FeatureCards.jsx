export function FeatureCards() {
  const features = [
    {
      icon: '🌍',
      title: '44+ Ngôn ngữ',
      description: 'Hỗ trợ đa dạng ngôn ngữ từ tiếng Việt, Anh, Nhật, Hàn, châu Âu và nhiều hơn nữa',
      bg: 'var(--info-light)',
      color: 'var(--info)',
    },
    {
      icon: '🎯',
      title: 'Giọng nói tự nhiên',
      description: 'AI tạo ra giọng nói sống động, truyền cảm như người thật với nhiều phong cách',
      bg: 'var(--success-light)',
      color: 'var(--success)',
    },
    {
      icon: '⚡',
      title: 'Xử lý nhanh',
      description: 'Công nghệ AI tiên tiến giúp xử lý video, audio chỉ trong vài phút thay vì hàng giờ',
      bg: 'var(--warning-light)',
      color: 'var(--warning)',
    },
    {
      icon: '🔁',
      title: 'Clone giọng',
      description: 'Tạo giọng của riêng bạn chỉ với vài mẫu âm thanh 5-8 giây',
      bg: 'var(--primary-light)',
      color: 'var(--primary)',
    },
  ];

  return (
    <div>
      <h3 style={{ fontSize: 'var(--text-xl)', marginBottom: '24px', fontWeight: 700 }}>
        Tính năng nổi bật
      </h3>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(260px, 1fr))', gap: '20px' }}>
        {features.map((feat) => (
          <div
            key={feat.title}
            style={{
              background: 'var(--surface)',
              border: '1px solid var(--border)',
              borderRadius: 'var(--radius-lg)',
              padding: '24px',
              display: 'flex',
              gap: '16px',
              alignItems: 'flex-start',
            }}
          >
            <div
              style={{
                fontSize: '32px',
                background: feat.bg,
                borderRadius: 'var(--radius-full)',
                width: '60px',
                height: '60px',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                flexShrink: 0,
              }}
            >
              {feat.icon}
            </div>
            <div>
              <h4 style={{ fontSize: 'var(--text-lg)', fontWeight: 700, marginBottom: '8px', color: feat.color }}>
                {feat.title}
              </h4>
              <p style={{ fontSize: 'var(--text-sm)', color: 'var(--text-dim)', lineHeight: 1.5 }}>
                {feat.description}
              </p>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}