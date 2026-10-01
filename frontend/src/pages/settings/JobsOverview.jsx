import { useEffect, useState } from 'react';
import { Card, SectionTitle, errStyle } from './parts.jsx';

// Tổng quan jobs TOÀN HỆ (scope Hệ thống) — GET /v1/admin/overview.
// Đếm JOB (self-host miễn phí — không có đơn vị tiền tệ, đúng chuẩn đã chốt).
const TYPE_LABELS = { dub: 'Lồng tiếng', tts: 'Văn bản → giọng nói', stt: 'Giọng nói → văn bản',
  translate: 'Dịch văn bản', subtitle: 'Tạo phụ đề' };
const STATUS_LABELS = { queued: 'Đang chờ', running: 'Đang chạy', done: 'Hoàn thành',
  failed: 'Thất bại', cancelled: 'Đã hủy' };

export default function JobsOverview() {
  const [data, setData] = useState(null);
  const [err, setErr] = useState(null);

  useEffect(() => {
    (async () => {
      try {
        const res = await fetch('/v1/admin/overview', { credentials: 'include' });
        const d = await res.json();
        if (res.ok) setData(d);
        else setErr(d.detail || 'Không tải được thống kê.');
      } catch (e) { setErr(e.message); }
    })();
  }, []);

  return (
    <div>
      <SectionTitle title="Tổng quan jobs" badge="system"
        desc="toàn hệ thống — mọi người dùng" />
      {err && <div style={{ ...errStyle, marginBottom: '10px' }}>{err}</div>}
      {data && (
        <>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(140px, 1fr))', gap: '10px', marginBottom: '12px' }}>
            <Stat label="Tổng job" value={data.total_jobs} />
            <Stat label="Đang chạy" value={data.running} accent="var(--info)" />
            <Stat label="Người dùng" value={data.users?.total} sub={`${data.users?.admins || 0} quản trị`} />
            <Stat label="Giọng mẫu" value={data.voices} />
            <Stat label="API key đang hoạt động" value={data.api_keys?.active} sub={`tổng ${data.api_keys?.total || 0}`} />
          </div>
          <Card title="Job theo trạng thái">
            {Object.entries(data.by_status || {}).length === 0 ? (
              <p style={{ fontSize: 'var(--text-sm)', color: 'var(--text-dim)', margin: 0 }}>Chưa có job nào.</p>
            ) : Object.entries(STATUS_LABELS).map(([k, label]) => (
              <Row key={k} k={label} v={data.by_status?.[k] || 0} />
            ))}
          </Card>
          <Card title="Job theo loại">
            {Object.entries(data.by_type || {}).length === 0 ? (
              <p style={{ fontSize: 'var(--text-sm)', color: 'var(--text-dim)', margin: 0 }}>Chưa có job nào.</p>
            ) : Object.entries(data.by_type || {}).map(([k, v]) => (
              <Row key={k} k={TYPE_LABELS[k] || k} v={v} />
            ))}
          </Card>
          <Card title="AI Platform">
            <Row k="Providers (đang bật)" v={`${data.providers?.enabled || 0} / ${data.providers?.total || 0}`} />
            <Row k="Models trong registry (đang bật)" v={`${data.models?.enabled || 0} / ${data.models?.total || 0}`} />
          </Card>
        </>
      )}
    </div>
  );
}

function Stat({ label, value, sub, accent }) {
  return (
    <div style={{
      background: 'var(--surface)', border: '1px solid var(--border)',
      borderRadius: 'var(--radius)', padding: '10px 12px',
    }}>
      <div style={{ fontSize: 'var(--text-xs)', color: 'var(--text-dim)', marginBottom: '2px' }}>
        {label}
      </div>
      <div style={{ fontSize: 'var(--text-2xl)', fontWeight: 700, color: accent || 'var(--text)' }}>
        {value ?? '—'}
      </div>
      {sub && <div style={{ fontSize: 'var(--text-xs)', color: 'var(--text-dim)' }}>{sub}</div>}
    </div>
  );
}

function Row({ k, v }) {
  return (
    <div style={{ display: 'flex', justifyContent: 'space-between', padding: '4px 0', fontSize: 'var(--text-sm)', borderBottom: '1px solid var(--border)' }}>
      <span style={{ color: 'var(--text)' }}>{k}</span>
      <b style={{ color: 'var(--text)' }}>{v}</b>
    </div>
  );
}
