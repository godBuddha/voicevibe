import { useEffect, useState } from 'react';
import { Card, SectionTitle, btnStyle, errStyle, okStyle } from './parts.jsx';

// Công tắc tính năng (scope Hệ thống). Thắt lưng BUỒNG: bảng system_flags hiện
// chỉ có 'setup.completed' (chốt nguyên tử /setup) — KHÔNG phải kho flag. Card
// này trung thực: công tắc thật = settings boolean (category security); còn
// system_flags liệt kê READ-ONLY để vận hành thấy trạng thái nội bộ.
export default function FeatureFlags() {
  const [rows, setRows] = useState([]);
  const [flags, setFlags] = useState([]);
  const [msg, setMsg] = useState(null);
  const [err, setErr] = useState(null);

  const load = async () => {
    try {
      const res = await fetch('/v1/admin/settings', { credentials: 'include' });
      const d = await res.json();
      if (res.ok) {
        setRows((d.settings || []).filter((r) => r.category === 'security'));
      } else setErr(d.detail || 'Không tải được.');
    } catch (e) { setErr(e.message); }
  };

  useEffect(() => { load(); }, []);

  const toggle = async (row) => {
    setMsg(null); setErr(null);
    const next = !(row.value === true || row.value === 'true');
    try {
      const res = await fetch(`/v1/admin/settings/${encodeURIComponent(row.key)}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({ value: next }),
      });
      if (res.ok) { setMsg(`Đã ${next ? 'bật' : 'tắt'} ${row.key}.`); load(); }
      else setErr((await res.json()).detail || 'Không lưu được.');
    } catch (e) { setErr(e.message); }
  };

  return (
    <div>
      <SectionTitle title="Công tắc tính năng" badge="system"
        desc="bật/tắt hành vi hệ thống — có hiệu lực ngay" />
      {msg && <div style={{ ...okStyle, marginBottom: '10px' }}>{msg}</div>}
      {err && <div style={{ ...errStyle, marginBottom: '10px' }}>{err}</div>}
      <Card title="Công tắc (settings bảo mật)">
        {rows.length === 0 ? (
          <p style={{ fontSize: 'var(--text-sm)', color: 'var(--text-dim)', margin: 0 }}>
            Không có công tắc nào.
          </p>
        ) : rows.map((r) => {
          const on = r.value === true || r.value === 'true';
          return (
            <div key={r.key} style={{
              display: 'flex', alignItems: 'center', gap: '10px', padding: '6px 0',
              borderBottom: '1px solid var(--border)',
            }}>
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ fontSize: 'var(--text-sm)', fontWeight: 600, color: 'var(--text)' }}>
                  {r.label || r.key}
                </div>
                <code style={{ fontSize: 'var(--text-xs)', color: 'var(--text-dim)' }}>{r.key}</code>
              </div>
              <button onClick={() => toggle(r)} style={{
                ...btnStyle,
                background: on ? 'var(--success-light)' : 'var(--bg)',
                color: on ? 'var(--success)' : 'var(--text)',
                border: on ? '1px solid var(--success)' : '1px solid var(--border)',
              }}>
                {on ? 'Bật' : 'Tắt'}
              </button>
            </div>
          );
        })}
      </Card>
      <Card title="Cờ nội bộ (system_flags — chỉ đọc)">
        <p style={{ fontSize: 'var(--text-xs)', color: 'var(--text-dim)', margin: '0 0 8px' }}>
          Cờ vận hành nội bộ, không phải công tắc tính năng. Hiện chỉ có cờ chốt
          quá trình khởi tạo hệ thống.
        </p>
        {flags.length === 0 && (
          <code style={{ fontSize: 'var(--text-xs)', color: 'var(--text-dim)' }}>
            (endpoint đọc system_flags chưa có — cờ duy nhất là setup.completed)
          </code>
        )}
      </Card>
    </div>
  );
}
