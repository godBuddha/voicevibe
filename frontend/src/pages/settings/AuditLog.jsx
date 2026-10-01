import { useCallback, useEffect, useState } from 'react';
import { ChevronLeft, ChevronRight } from 'lucide-react';
import { Card, SectionTitle, inputStyle, errStyle } from './parts.jsx';

// Nhật ký kiểm toán (scope Hệ thống) — GET /v1/admin/audit.
// Ghi THẬT từ backend (audit.py): chỉ HÀNH ĐỘNG (login/đổi user/setting/...),
// không log GET — bảng không phình, tín hiệu thật.
const PAGE_SIZE = 25;

function fmtTime(unix) {
  if (!unix) return '—';
  return new Date(unix * 1000).toLocaleString('vi-VN', { dateStyle: 'short', timeStyle: 'short' });
}

const ACTION_LABELS = {
  'auth.login': 'Đăng nhập',
  'auth.login_failed': 'Đăng nhập thất bại',
  'auth.logout': 'Đăng xuất',
  'auth.setup': 'Khởi tạo hệ thống',
  'auth.signup': 'Đăng ký',
  'me.password_change': 'Đổi mật khẩu',
  'me.name_change': 'Đổi tên hiển thị',
  'me.session_revoke': 'Thu hồi phiên',
  'user.create': 'Tạo user',
  'user.reset_password': 'Đặt lại mật khẩu',
  'user.deactivate': 'Khoá tài khoản',
  'user.activate': 'Mở khoá tài khoản',
  'provider.create': 'Tạo provider',
  'provider.update': 'Sửa provider',
  'provider.delete': 'Xoá provider',
  'provider.sync': 'Đồng bộ model',
  'stage.set': 'Gán công đoạn',
  'stage.clear': 'Gỡ gán công đoạn',
  'model.toggle': 'Bật/tắt model',
  'setting.set': 'Đổi setting',
  'setting.delete': 'Xoá setting',
  'key.create': 'Tạo API key',
  'key.revoke': 'Thu hồi API key',
  'prompt.update': 'Sửa prompt hệ thống',
  'prompt.reset': 'Khôi phục prompt',
  'job.cancel': 'Hủy job',
  'job.delete': 'Xoá job',
  'config.import': 'Nhập cấu hình',
};

export default function AuditLog() {
  const [items, setItems] = useState([]);
  const [total, setTotal] = useState(0);
  const [q, setQ] = useState('');
  const [action, setAction] = useState('');
  const [userId, setUserId] = useState('');
  const [offset, setOffset] = useState(0);
  const [err, setErr] = useState(null);

  const load = useCallback(async () => {
    try {
      const params = new URLSearchParams();
      if (q.trim()) params.set('q', q.trim());
      if (action) params.set('action', action);
      if (userId.trim()) params.set('user_id', userId.trim());
      params.set('limit', String(PAGE_SIZE));
      params.set('offset', String(offset));
      const res = await fetch(`/v1/admin/audit?${params}`, { credentials: 'include' });
      const d = await res.json();
      if (res.ok) { setItems(d.items || []); setTotal(d.total || 0); }
      else setErr(d.detail || 'Không tải được nhật ký.');
    } catch (e) {
      setErr(e.message);
    }
  }, [q, action, userId, offset]);

  useEffect(() => { load(); }, [load]);

  const actions = Object.entries(ACTION_LABELS).sort(([a], [b]) => a.localeCompare(b));

  return (
    <div>
      <SectionTitle title="Nhật ký kiểm toán" badge="system"
        desc="ai đã làm gì — đăng nhập, đổi cấu hình, quản trị user" />
      {err && <div style={{ ...errStyle, marginBottom: '10px' }}>{err}</div>}

      <div style={{ display: 'flex', gap: '8px', marginBottom: '10px', flexWrap: 'wrap' }}>
        <input value={q} onChange={(e) => { setQ(e.target.value); setOffset(0); }}
          placeholder="Tìm trong hành động/đối tượng…" style={{ ...inputStyle, maxWidth: '220px' }} />
        <select value={action} onChange={(e) => { setAction(e.target.value); setOffset(0); }}
          style={{ ...inputStyle, maxWidth: '200px' }}>
          <option value="">Mọi hành động</option>
          {actions.map(([key, label]) => (
            <option key={key} value={key}>{label}</option>
          ))}
        </select>
        <input value={userId} onChange={(e) => { setUserId(e.target.value); setOffset(0); }}
          placeholder="user_id (tuỳ chọn)" style={{ ...inputStyle, maxWidth: '160px' }} />
        <span style={{ fontSize: 'var(--text-sm)', color: 'var(--text-dim)', alignSelf: 'center' }}>
          {total} dòng
        </span>
      </div>

      <Card title="Hành động gần đây">
        {items.length === 0 ? (
          <p style={{ fontSize: 'var(--text-sm)', color: 'var(--text-dim)', margin: 0 }}>
            Chưa có hành động nào khớp.
          </p>
        ) : (
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 'var(--text-sm)' }}>
            <thead>
              <tr style={{ color: 'var(--text-dim)', textAlign: 'left' }}>
                <th style={{ padding: '4px 8px', fontWeight: 600 }}>Thời gian</th>
                <th style={{ padding: '4px 8px', fontWeight: 600 }}>Hành động</th>
                <th style={{ padding: '4px 8px', fontWeight: 600 }}>Người</th>
                <th style={{ padding: '4px 8px', fontWeight: 600 }}>Đối tượng</th>
                <th style={{ padding: '4px 8px', fontWeight: 600 }}>Chi tiết</th>
                <th style={{ padding: '4px 8px', fontWeight: 600 }}>IP</th>
              </tr>
            </thead>
            <tbody>
              {items.map((i) => (
                <tr key={i.id} style={{ borderTop: '1px solid var(--border)' }}>
                  <td style={{ padding: '5px 8px', color: 'var(--text-dim)', whiteSpace: 'nowrap' }}>
                    {fmtTime(i.created_at)}
                  </td>
                  <td style={{ padding: '5px 8px', color: 'var(--text)', whiteSpace: 'nowrap' }}>
                    {ACTION_LABELS[i.action] || i.action}
                  </td>
                  <td style={{ padding: '5px 8px', color: 'var(--text-dim)', whiteSpace: 'nowrap' }}>
                    {i.user_email || (i.user_id ? i.user_id : '—')}
                  </td>
                  <td style={{ padding: '5px 8px', color: 'var(--text)', wordBreak: 'break-all', maxWidth: '220px' }}>
                    {i.target || '—'}
                  </td>
                  <td style={{ padding: '5px 8px', color: 'var(--text-dim)', wordBreak: 'break-all', maxWidth: '200px' }}>
                    {i.detail || ''}
                  </td>
                  <td style={{ padding: '5px 8px', color: 'var(--text-dim)' }}>{i.ip || '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
        {total > PAGE_SIZE && (
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginTop: '8px' }}>
            <button disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}
              style={{ ...iconBtnCss, opacity: offset === 0 ? 0.4 : 1 }}>
              <ChevronLeft size={14} />
            </button>
            <span style={{ fontSize: 'var(--text-xs)', color: 'var(--text-dim)' }}>
              {offset + 1}–{Math.min(offset + PAGE_SIZE, total)} / {total}
            </span>
            <button disabled={offset + PAGE_SIZE >= total}
              onClick={() => setOffset(offset + PAGE_SIZE)}
              style={{ ...iconBtnCss, opacity: offset + PAGE_SIZE >= total ? 0.4 : 1 }}>
              <ChevronRight size={14} />
            </button>
          </div>
        )}
      </Card>
    </div>
  );
}

const iconBtnCss = {
  width: '24px', height: '24px', borderRadius: 'var(--radius-sm)',
  border: '1px solid var(--border)', background: 'var(--bg)',
  color: 'var(--text-dim)', cursor: 'pointer',
  display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
};
