import { CircleCheck, TriangleAlert, CircleHelp, CircleX } from 'lucide-react';

// Badge tương thích — LUÔN CẢ icon LẮM chữ (yêu cầu accessibility: không dùng
// màu làm tín hiệu duy nhất). 4 trạng thái của compatibility engine.
const MAP = {
  compatible: { Icon: CircleCheck, text: 'Compatible', bg: 'var(--success-light)', color: 'var(--success)' },
  partial: { Icon: TriangleAlert, text: 'Một phần', bg: 'var(--warning-light)', color: 'var(--warning)' },
  unknown: { Icon: CircleHelp, text: 'Không rõ', bg: 'var(--bg)', color: 'var(--text-dim)' },
  incompatible: { Icon: CircleX, text: 'Không tương thích', bg: 'var(--danger-light)', color: 'var(--danger)' },
};

export default function CompatBadge({ status, small = false }) {
  const m = MAP[status] || MAP.unknown;
  return (
    <span
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        gap: '4px',
        padding: small ? '1px 7px' : '2px 9px',
        borderRadius: 'var(--radius-xs)',
        background: m.bg,
        color: m.color,
        fontSize: small ? '10px' : 'var(--text-xs)',
        fontWeight: 600,
        whiteSpace: 'nowrap',
      }}
      title={`Tương thích: ${m.text}`}
    >
      <m.Icon size={small ? 11 : 12} strokeWidth={2.2} />
      {m.text}
    </span>
  );
}
