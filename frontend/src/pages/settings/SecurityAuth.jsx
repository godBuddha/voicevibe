import { useEffect, useState } from 'react';
import { Card, Field, SectionTitle, inputStyle, btnStyle, errStyle, okStyle } from './parts.jsx';

// Xác thực (scope Hệ thống): cổng đăng ký công khai + key quản trị.
// Reuse đúng API settings hiện có (PUT /v1/admin/settings/{key}) — không backend mới.
// Convention secret: để trống = GIỮ NGUYÊN giá trị cũ (PATCH semantics).
export default function SecurityAuth() {
  const [signupOn, setSignupOn] = useState(false);
  const [adminKey, setAdminKey] = useState('');
  const [loaded, setLoaded] = useState(false);
  const [msg, setMsg] = useState(null);
  const [err, setErr] = useState(null);

  useEffect(() => {
    (async () => {
      try {
        const res = await fetch('/v1/admin/settings', { credentials: 'include' });
        const d = await res.json();
        if (res.ok) {
          const rows = d.settings || [];
          const su = rows.find((r) => r.key === 'auth.allow_signup');
          setSignupOn(su?.value === true || su?.value === 'true');
          setLoaded(true);
        } else setErr(d.detail || 'Không tải được cài đặt.');
      } catch (e) { setErr(e.message); }
    })();
  }, []);

  const put = async (key, value, isSecret) => {
    setMsg(null); setErr(null);
    try {
      const res = await fetch(`/v1/admin/settings/${encodeURIComponent(key)}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({ value, ...(isSecret ? { is_secret: true } : {}) }),
      });
      const d = await res.json();
      if (res.ok) setMsg(`Đã lưu ${key}.`);
      else setErr(d.detail || 'Không lưu được.');
      return res.ok;
    } catch (e) { setErr(e.message); return false; }
  };

  const toggleSignup = async () => {
    const next = !signupOn;
    if (await put('auth.allow_signup', next)) setSignupOn(next);
  };

  const saveAdminKey = async () => {
    // Ô rỗng = không gửi (giữ nguyên) — đúng convention PATCH của secret.
    if (!adminKey.trim()) { setErr('Nhập giá trị MỚI — ô để trống nghĩa là giữ nguyên.'); return; }
    if (await put('admin.api_key', adminKey.trim(), true)) {
      setAdminKey('');
      setMsg('Đã lưu admin.api_key — đường gọi API quản trị bằng header X-Admin-Key đã mở.');
    }
  };

  return (
    <div>
      <SectionTitle title="Xác thực" badge="system"
        desc="ai được tự vào hệ thống và đường API quản trị" />
      {msg && <div style={{ ...okStyle, marginBottom: '10px' }}>{msg}</div>}
      {err && <div style={{ ...errStyle, marginBottom: '10px' }}>{err}</div>}
      <Card title="Đăng ký công khai">
        <p style={{ fontSize: 'var(--text-sm)', color: 'var(--text)', margin: '0 0 8px' }}>
          Trạng thái: <b>{loaded ? (signupOn ? 'Mở' : 'Đóng (mặc định)') : '...'}</b>
        </p>
        <p style={{ fontSize: 'var(--text-xs)', color: 'var(--text-dim)', margin: '0 0 10px' }}>
          Đóng = chỉ quản trị viên tạo tài khoản (Trang Thành viên). Mở = ai biết URL
          cũng tự đăng ký được — cân nhắc trước khi mở trên server công khai.
        </p>
        <button onClick={toggleSignup} disabled={!loaded} style={{
          ...btnStyle,
          background: signupOn ? 'var(--bg)' : 'var(--gradient)',
          color: signupOn ? 'var(--text)' : '#fff',
          border: signupOn ? '1px solid var(--border)' : 'none',
          opacity: loaded ? 1 : 0.6,
        }}>
          {signupOn ? 'Đóng đăng ký' : 'Mở đăng ký công khai'}
        </button>
      </Card>

      <Card title="Admin API key (X-Admin-Key)">
        <Field label="Giá trị mới"
          hint="Để trống và không bấm = giữ nguyên. Đặt rỗng hoàn toàn phải làm trong Cấu hình chung. Khi đặt: script/cron có thể gọi API quản trị bằng header X-Admin-Key mà không cần phiên đăng nhập.">
          <input type="password" value={adminKey} style={inputStyle}
            onChange={(e) => setAdminKey(e.target.value)}
            placeholder="Nhập giá trị MỚI (để trống = giữ nguyên)" autoComplete="new-password" />
        </Field>
        <button onClick={saveAdminKey} style={btnStyle}>Lưu</button>
      </Card>

      <Card title="Mật khẩu">
        <p style={{ fontSize: 'var(--text-sm)', color: 'var(--text)', margin: 0 }}>
          Độ dài tối thiểu: <b>8 ký tự</b> (bắt buộc ở mọi nơi nhập mật khẩu). Người dùng
          tự đổi mật khẩu của mình trong Hồ sơ; quản trị viên đặt lại cho người khác
          trong Trang Thành viên.
        </p>
      </Card>
    </div>
  );
}
