import { useState } from 'react';
import { useAuth } from '../../hooks/useAuth.jsx';
import { Card, Field, SectionTitle, inputStyle, btnStyle, errStyle, okStyle } from './parts.jsx';

// Hồ sơ cá nhân (scope Cá nhân): tên hiển thị + đổi mật khẩu của chính mình.
// Sai mật khẩu hiện tại backend trả 403 — hiện inline TẠI ĐÂY; tuyệt đối không
// bị client.js đá ra /login (đó là lý do backend cố tình không trả 401).
export default function Profile() {
  const { user, refreshUser } = useAuth();
  const [name, setName] = useState(user?.name || '');
  const [nameMsg, setNameMsg] = useState(null);
  const [currentPw, setCurrentPw] = useState('');
  const [newPw, setNewPw] = useState('');
  const [pwMsg, setPwMsg] = useState(null);
  const [pwErr, setPwErr] = useState(null);

  const saveName = async () => {
    setNameMsg(null);
    try {
      const res = await fetch('/v1/me', {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({ name }),
      });
      const d = await res.json();
      if (res.ok) {
        setNameMsg('Đã lưu tên hiển thị.');
        await refreshUser();
      } else {
        setNameMsg(d.detail || 'Không lưu được.');
      }
    } catch (e) {
      setNameMsg(e.message);
    }
  };

  const changePassword = async () => {
    setPwErr(null);
    setPwMsg(null);
    try {
      const res = await fetch('/v1/me/password', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({ current_password: currentPw, new_password: newPw }),
      });
      const d = await res.json();
      if (res.ok) {
        setPwMsg(`Đã đổi mật khẩu${d.sessions_revoked ? ` — ${d.sessions_revoked} phiên khác đã bị đăng xuất` : ''}.`);
        setCurrentPw('');
        setNewPw('');
      } else {
        // 403 (sai mật khẩu hiện tại) / 422 (mật khẩu mới yếu) hiện ngay tại đây.
        setPwErr(d.detail || 'Không đổi được mật khẩu.');
      }
    } catch (e) {
      setPwErr(e.message);
    }
  };

  return (
    <div>
      <SectionTitle title="Hồ sơ" badge="personal"
        desc="tên hiển thị và mật khẩu của riêng bạn" />
      <Card title="Tên hiển thị">
        <Field label="Tên" hint="Hiện ở góc phải trên và trong thư viện prompt. Đang dùng: email của bạn.">
          <input value={name} onChange={(e) => setName(e.target.value)} style={inputStyle}
            placeholder={user?.email?.split('@')[0]} maxLength={120} />
        </Field>
        <button onClick={saveName} style={btnStyle}>Lưu tên</button>
        {nameMsg && <div style={{ ...okStyle, marginTop: '8px' }}>{nameMsg}</div>}
      </Card>

      <Card title="Đổi mật khẩu">
        <Field label="Mật khẩu hiện tại">
          <input type="password" value={currentPw} autoComplete="current-password"
            onChange={(e) => setCurrentPw(e.target.value)} style={inputStyle}
            placeholder="Nhập mật khẩu đang dùng" />
        </Field>
        <Field label="Mật khẩu mới" hint="Tối thiểu 8 ký tự. Đổi xong, mọi thiết bị KHÁC sẽ bị đăng xuất.">
          <input type="password" value={newPw} autoComplete="new-password"
            onChange={(e) => setNewPw(e.target.value)} style={inputStyle}
            placeholder="Nhập mật khẩu mới" />
        </Field>
        <button onClick={changePassword} disabled={!currentPw || !newPw}
          style={{ ...btnStyle, opacity: !currentPw || !newPw ? 0.6 : 1 }}>
          Đổi mật khẩu
        </button>
        {pwMsg && <div style={{ ...okStyle, marginTop: '8px' }}>{pwMsg}</div>}
        {pwErr && <div style={{ ...errStyle, marginTop: '8px' }}>{pwErr}</div>}
      </Card>
    </div>
  );
}
