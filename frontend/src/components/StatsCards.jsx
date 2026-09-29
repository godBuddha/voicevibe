export function StatsCards({ usage }) {
  const stats = [
    { label: 'Tổng credit đã dùng', value: usage?.used.toLocaleString('vi-VN') ?? 0, color: 'var(--primary)' },
    { label: 'Credit còn lại', value: (usage?.limit - usage?.used).toLocaleString('vi-VN') ?? 0, color: 'var(--success)' },
    { label: 'Tổng jobs đã xử lý', value: usage?.totalJobs || 0, color: 'var(--info)' },
    { label: 'Jobs đang chạy', value: usage?.runningJobs || 0, color: 'var(--warning)' },
  ];

  return (
    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: '24px' }}>
      {stats.map((stat) => (
        <div
          key={stat.label}
          style={{
            background: 'var(--surface)',
            border: '1px solid var(--border)',
            borderRadius: 'var(--radius-lg)',
            padding: '24px',
            display: 'flex',
            flexDirection: 'column',
            justifyContent: 'center',
          }}
        >
          <div style={{ fontSize: 'var(--text-xl)', fontWeight: 700, color: stat.color, marginBottom: '8px' }}>
            {stat.value}
          </div>
          <div style={{ color: 'var(--text-dim)', fontSize: 'var(--text-sm)' }}>
            {stat.label}
          </div>
        </div>
      ))}
    </div>
  );
}