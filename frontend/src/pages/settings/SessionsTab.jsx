import { useCallback, useEffect, useState } from 'react';
import { LogOut, MonitorSmartphone } from 'lucide-react';
import { Card, SectionTitle, btnStyle, errStyle, okStyle } from './parts.jsx';

// Phiên đăng nhập (scope Cá nhân) — bảng sessions có sẵn của backend, giờ có API.
// Hàng "Thiết bị này" KHÔNG có nút thu hồi (thu hồi phiên hiện tại = tự đá mình;
// muốn thoát thì dùng Đăng xuất ở góc phải trên).
function fmtTime(unix) {
  if (!unix) return '—';
  const d = new Date(unix * 1000);
  return d.toLocaleString('vi-VN', { dateStyle: 'short', timeStyle: 'short' });
}

function agentName(ua) {
  if (!ua) return 'Không rõ';
  if (/edg\//i.test(ua)) return 'Edge';
  if (/chrome|crios/i.test(ua)) return 'Chrome';
  if (/firefox|fxios/i.test(ua)) return 'Firefox';
  if (/safari/i.test(ua)) return 'Safari';
  return ua.split(' ')[0]?.slice(0, 18) || 'Không rõ';
}

export default function SessionsTab() {
  const [rows, setRows] = useState([]);
  const [err, setErr] = useState(null);
  const [msg, setMsg] = useState(null);

  const load = useCallback(async () => {
    try {
      const res = await fetch('/v1/me/sessions', { credentials: 'include' });
      const d = await res.json();
      if (res.ok) setRows(d.sessions || []);
      else setErr(d.detail || 'Không tải được phiên.');
    } catch (e) {
      setErr(e.message);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const revoke = async (hash) => {
    setMsg(null); setErr(null);
    try {
      const res = await fetch(`/v1/me/sessions/${hash}`, { method: 'DELETE', credentials: 'include' });
      if (res.ok) { setMsg('Đã đăng xuất thiết bị đó.'); load(); }
      else setErr((await res.json()).detail || 'Không thu hồi được.');
    } catch (e) { setErr(e.message); }
  };

  const revokeOthers = async () => {
    setMsg(null); setErr(null);
    try {
      const res = await fetch('/v1/me/sessions', { method: 'DELETE', credentials: 'include' });
      const d = await res.json();
      if (res.ok) { setMsg(`Đã đăng xuất ${d.revoked} thiết bị khác.`); load(); }
      else setErr(d.detail || 'Không thu hồi được.');
    } catch (e) { setErr(e.message); }
  };

  const others = rows.filter((r) => !r.current);

  return (
    <div>
      <SectionTitle title="Phiên đăng nhập" badge="personal"
        desc="thiết bị nào đang đăng nhập bằng tài khoản của bạn" />
      {err && <div style={{ ...errStyle, marginBottom: '10px' }}>{err}</div>}
      {msg && <div style={{ ...okStyle, marginBottom: '10px' }}>{msg}</div>}
      <Card
        title="Thiết bị đang đăng nhập"
        right={others.length > 0 && (
          <button onClick={revokeOthers} style={{
            ...btnStyle, background: 'var(--danger-light)', color: 'var(--danger)',
            display: 'flex', alignItems: 'center', gap: '6px',
          }}>
            <LogOut size={13} /> Đăng xuất mọi thiết bị khác
          </button>
        )}
      >
        {rows.length === 0 ? (
          <p style={{ fontSize: 'var(--text-sm)', color: 'var(--text-dim)', margin: 0 }}>
            Không có phiên nào.
          </p>
        ) : (
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 'var(--text-sm)' }}>
            <thead>
              <tr style={{ color: 'var(--text-dim)', textAlign: 'left' }}>
                <th style={{ padding: '4px 8px', fontWeight: 600 }}>Thiết bị</th>
                <th style={{ padding: '4px 8px', fontWeight: 600 }}>IP</th>
                <th style={{ padding: '4px 8px', fontWeight: 600 }}>Đăng nhập</th>
                <th style={{ padding: '4px 8px', fontWeight: 600 }}>Hoạt động</th>
                <th style={{ padding: '4px 8px' }}></th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.token_hash} style={{
                  borderTop: '1px solid var(--border)',
                  background: r.current ? 'var(--primary-light)' : 'transparent',
                }}>
                  <td style={{ padding: '5px 8px', color: 'var(--text)' }}>
                    <span style={{ display: 'inline-flex', alignItems: 'center', gap: '6px' }}>
                      <MonitorSmartphone size={13} style={{ opacity: 0.6, flexShrink: 0 }} />
                      {r.current ? <b>Thiết bị này</b> : agentName(r.user_agent)}
                    </span>
                  </td>
                  <td style={{ padding: '5px 8px', color: 'var(--text-dim)' }}>{r.ip || '—'}</td>
                  <td style={{ padding: '5px 8px', color: 'var(--text-dim)' }}>{fmtTime(r.created_at)}</td>
                  <td style={{ padding: '5px 8px', color: 'var(--text-dim)' }}>{fmtTime(r.last_seen_at)}</td>
                  <td style={{ padding: '5px 8px', textAlign: 'right' }}>
                    {!r.current && (
                      <button onClick={() => revoke(r.token_hash)} style={{
                        background: 'transparent', border: '1px solid var(--border)',
                        color: 'var(--danger)', borderRadius: 'var(--radius-sm)',
                        padding: '3px 8px', fontSize: 'var(--text-xs)', cursor: 'pointer',
                      }}>
                        Thu hồi
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Card>
    </div>
  );
}
