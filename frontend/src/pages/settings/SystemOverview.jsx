import { useEffect, useState } from 'react';
import { Card, SectionTitle, errStyle } from './parts.jsx';

// Tổng quan hệ thống (scope Hệ thống) — GET /v1/admin/system, chỉ đọc.
// Ghi chú THẬT: setting DB `media_root` chỉ là hiển thị, runtime đọc env —
// UI không được nói dối self-host về chỗ file thật nằm đâu.
function fmtBytes(n) {
  if (n === null || n === undefined) return '—';
  const units = ['B', 'KB', 'MB', 'GB', 'TB'];
  let v = Number(n);
  let i = 0;
  while (v >= 1024 && i < units.length - 1) { v /= 1024; i += 1; }
  return `${v.toFixed(v >= 10 || i === 0 ? 0 : 1)} ${units[i]}`;
}

export default function SystemOverview() {
  const [info, setInfo] = useState(null);
  const [err, setErr] = useState(null);

  useEffect(() => {
    (async () => {
      try {
        const res = await fetch('/v1/admin/system', { credentials: 'include' });
        const d = await res.json();
        if (res.ok) setInfo(d);
        else setErr(d.detail || 'Không tải được trạng thái hệ thống.');
      } catch (e) {
        setErr(e.message);
      }
    })();
  }, []);

  return (
    <div>
      <SectionTitle title="Tổng quan hệ thống" badge="system"
        desc="trạng thái thật của instance self-hosted này — chỉ đọc" />
      {err && <div style={{ ...errStyle, marginBottom: '10px' }}>{err}</div>}
      {info && (
        <>
          <Card title="Database">
            <Row k="Loại" v={info.db?.dialect || '—'} />
            <Row k="Phiên bản" v={info.db?.version || '—'} mono />
          </Card>
          <Card title="Hàng đợi job">
            <Row k="Chế độ" v={info.queue?.mode === 'inline' ? 'Chạy tại máy (inline)' : 'Celery worker'} />
            <Row k="Broker" v={info.queue?.broker === 'redis-ok' ? 'Redis — hoạt động'
              : info.queue?.broker === 'inline' ? 'Không dùng (inline)'
                : 'Redis — KHÔNG kết nối được'} />
            <Row k="Job đang chạy" v={String(info.jobs_running ?? '—')} />
          </Card>
          <Card title="Lưu trữ media">
            <Row k="Chế độ" v={info.storage?.mode === 's3'
              ? `S3/MinIO (bucket ${info.storage?.root})` : 'Thư mục tại máy'} />
            <Row k="Đường dẫn (env MEDIA_ROOT)" v={info.storage?.root || '—'} mono />
            <Row k="Dung lượng trống" v={fmtBytes(info.storage?.free_bytes)} />
            <p style={{ fontSize: 'var(--text-xs)', color: 'var(--text-dim)', margin: '8px 0 0' }}>
              Runtime đọc biến môi trường <code>MEDIA_ROOT</code> — setting
              {' '}<code>media_root</code> trong Cấu hình chung chỉ để hiển thị.
            </p>
          </Card>
          <Card title="Khác">
            <Row k="Python" v={info.python || '—'} mono />
            <Row k="Mật khẩu tối thiểu" v={`${info.password_min_length} ký tự`} />
            <Row k="Phiên đã hết hạn (chưa dọn)" v={String(info.sessions_expired ?? '—')} />
          </Card>
        </>
      )}
    </div>
  );
}

function Row({ k, v, mono }) {
  return (
    <div style={{ display: 'flex', gap: '10px', padding: '3px 0', fontSize: 'var(--text-sm)' }}>
      <span style={{ color: 'var(--text-dim)', minWidth: '180px', flexShrink: 0 }}>{k}</span>
      <span style={{ color: 'var(--text)', fontFamily: mono ? 'ui-monospace, monospace' : 'inherit',
        wordBreak: 'break-all' }}>{v}</span>
    </div>
  );
}
