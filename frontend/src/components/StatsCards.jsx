export function StatsCards({ usage }) {
  // Self-host miễn phí: thống kê ĐẾM JOB, không có đơn vị tiền tệ.
  const stats = [
    { label: 'Tổng jobs', value: usage?.totalJobs || 0, color: 'var(--primary)' },
    { label: 'Hoàn thành', value: usage?.byStatus?.done || 0, color: 'var(--success)' },
    { label: 'Jobs đang chạy', value: usage?.running || 0, color: 'var(--warning)' },
    { label: 'Thất bại', value: usage?.byStatus?.failed || 0, color: 'var(--danger)' },
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
