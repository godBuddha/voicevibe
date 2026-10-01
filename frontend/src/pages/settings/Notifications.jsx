import { useEffect, useState } from 'react';
import { Card, SectionTitle, btnStyle, errStyle, okStyle } from './parts.jsx';

// Thông báo (scope Cá nhân): thông báo trình duyệt khi job hoàn thành.
// TẮT mặc định. Chỉ hoạt động khi còn mở tab VoiceVibe — không có push server.
// Tiêu thụ: 1 GET /v1/jobs mỗi 30 giây, CHỈ khi bật (Topbar cũng đọc key này).
export const NOTIFY_KEY = 'vv_notify';

export default function Notifications() {
  const [enabled, setEnabled] = useState(
    () => { try { return localStorage.getItem(NOTIFY_KEY) === '1'; } catch { return false; } });
  const [msg, setMsg] = useState(null);
  const [err, setErr] = useState(null);

  const enable = async () => {
    setErr(null);
    setMsg(null);
    if (typeof Notification === 'undefined') {
      setErr('Trình duyệt này không hỗ trợ thông báo.');
      return;
    }
    try {
      let perm = Notification.permission;
      if (perm === 'default') {
        perm = await Notification.requestPermission();
      }
      if (perm !== 'granted') {
        setErr('Bạn đã chặn thông báo trong trình duyệt — hãy bật lại trong phần Quyền của trang.');
        return;
      }
      try { localStorage.setItem(NOTIFY_KEY, '1'); } catch {}
      setEnabled(true);
      setMsg('Đã bật — job hoàn thành sẽ hiện thông báo khi tab còn mở.');
      new Notification('VoiceVibe', { body: 'Thông báo đã được bật ✓' });
    } catch (e) {
      setErr(e.message);
    }
  };

  const disable = () => {
    try { localStorage.setItem(NOTIFY_KEY, '0'); } catch {}
    setEnabled(false);
    setMsg(null);
  };

  useEffect(() => () => {}, []);

  return (
    <div>
      <SectionTitle title="Thông báo" badge="personal"
        desc="báo khi job hoàn thành — trong tab trình duyệt" />
      <Card title="Thông báo hoàn thành job">
        <p style={{ fontSize: 'var(--text-sm)', color: 'var(--text)', margin: '0 0 8px' }}>
          Trạng thái: <b>{enabled ? 'Đang bật' : 'Tắt'}</b>
        </p>
        <p style={{ fontSize: 'var(--text-xs)', color: 'var(--text-dim)', margin: '0 0 10px' }}>
          Thông báo chỉ hiện khi tab VoiceVibe còn mở (hệ thống tự-host, không dịch vụ
          push bên ngoài). Tắt đi thì không tốn yêu cầu nào.
        </p>
        <button onClick={enabled ? disable : enable} style={{
          ...btnStyle,
          background: enabled ? 'var(--bg)' : 'var(--gradient)',
          color: enabled ? 'var(--text)' : '#fff',
          border: enabled ? '1px solid var(--border)' : 'none',
        }}>
          {enabled ? 'Tắt thông báo' : 'Bật thông báo'}
        </button>
        {msg && <div style={{ ...okStyle, marginTop: '8px' }}>{msg}</div>}
        {err && <div style={{ ...errStyle, marginTop: '8px' }}>{err}</div>}
      </Card>
    </div>
  );
}
