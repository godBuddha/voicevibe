import { ListTodo, CircleCheck, LoaderCircle, CircleX } from 'lucide-react';

export function StatsCards({ usage }) {
  // Self-host miễn phí: thống kê ĐẾM JOB, không có đơn vị tiền tệ.
  // COMPACT UI: thẻ ngang thấp — icon 28px trái, số + nhãn phải, thay khối
  // dọc padding 24px mỗi thẻ.
  const stats = [
    { label: 'Tổng jobs', value: usage?.totalJobs || 0, color: 'var(--primary)', Icon: ListTodo, bg: 'var(--primary-light)' },
    { label: 'Hoàn thành', value: usage?.byStatus?.done || 0, color: 'var(--success)', Icon: CircleCheck, bg: 'var(--success-light)' },
    { label: 'Jobs đang chạy', value: usage?.running || 0, color: 'var(--warning)', Icon: LoaderCircle, bg: 'var(--warning-light)' },
    { label: 'Thất bại', value: usage?.byStatus?.failed || 0, color: 'var(--danger)', Icon: CircleX, bg: 'var(--danger-light)' },
  ];

  return (
    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: '10px' }}>
      {stats.map((stat) => (
        <div
          key={stat.label}
          style={{
            background: 'var(--surface)',
            border: '1px solid var(--border)',
            borderRadius: 'var(--radius-lg)',
            padding: '10px 12px',
            display: 'flex',
            alignItems: 'center',
            gap: '10px',
          }}
        >
          <div
            style={{
              width: '28px',
              height: '28px',
              borderRadius: 'var(--radius-sm)',
              background: stat.bg,
              color: stat.color,
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              flexShrink: 0,
            }}
          >
            <stat.Icon size={15} strokeWidth={2} />
          </div>
          <div style={{ minWidth: 0 }}>
            <div style={{ fontSize: 'var(--text-lg)', fontWeight: 700, color: 'var(--text)', lineHeight: 1.2 }}>
              {stat.value}
            </div>
            <div style={{ color: 'var(--text-dim)', fontSize: 'var(--text-xs)' }}>
              {stat.label}
            </div>
          </div>
        </div>
      ))}
    </div>
  );
}
