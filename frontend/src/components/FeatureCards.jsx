import { Globe, Sparkles, Zap, Repeat } from 'lucide-react';

export function FeatureCards() {
  const features = [
    {
      Icon: Globe,
      title: '44+ Ngôn ngữ',
      description: 'Hỗ trợ đa dạng ngôn ngữ từ tiếng Việt, Anh, Nhật, Hàn, châu Âu và nhiều hơn nữa',
      bg: 'var(--info-light)',
      color: 'var(--info)',
    },
    {
      Icon: Sparkles,
      title: 'Giọng nói tự nhiên',
      description: 'AI tạo ra giọng nói sống động, truyền cảm như người thật với nhiều phong cách',
      bg: 'var(--success-light)',
      color: 'var(--success)',
    },
    {
      Icon: Zap,
      title: 'Xử lý nhanh',
      description: 'Công nghệ AI tiên tiến giúp xử lý video, audio chỉ trong vài phút thay vì hàng giờ',
      bg: 'var(--warning-light)',
      color: 'var(--warning)',
    },
    {
      Icon: Repeat,
      title: 'Clone giọng',
      description: 'Tạo giọng của riêng bạn chỉ với vài mẫu âm thanh 5-8 giây',
      bg: 'var(--primary-light)',
      color: 'var(--primary)',
    },
  ];

  return (
    <div>
      <h3 style={{ fontSize: 'var(--text-base)', marginBottom: '10px', fontWeight: 700 }}>
        Tính năng nổi bật
      </h3>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: '10px' }}>
        {features.map(({ Icon, ...feat }) => (
          <div
            key={feat.title}
            style={{
              background: 'var(--surface)',
              border: '1px solid var(--border)',
              borderRadius: 'var(--radius-lg)',
              padding: '10px 12px',
              display: 'flex',
              gap: '10px',
              alignItems: 'flex-start',
            }}
          >
            <div
              style={{
                background: feat.bg,
                borderRadius: 'var(--radius-sm)',
                width: '28px',
                height: '28px',
                color: feat.color,
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                flexShrink: 0,
              }}
            >
              <Icon size={15} strokeWidth={2} />
            </div>
            <div style={{ minWidth: 0 }}>
              <h4 style={{ fontSize: 'var(--text-sm)', fontWeight: 700, marginBottom: '2px', color: feat.color }}>
                {feat.title}
              </h4>
              <p style={{ fontSize: 'var(--text-xs)', color: 'var(--text-dim)', lineHeight: 1.5, margin: 0 }}>
                {feat.description}
              </p>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
