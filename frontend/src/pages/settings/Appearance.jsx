import { useState } from 'react';
import { useTheme } from '../../hooks/useTheme.jsx';
import { Card, SectionTitle, btnStyle } from './parts.jsx';

// Giao diện (scope Cá nhân): sáng/tối + gập thanh menu. Dùng ĐÚNG key hiện có
// ('theme' và 'vv_sidebar_hidden') — không tạo key mới, F5 giữ nguyên lựa chọn.
export default function Appearance() {
  const { theme, setThemeSafe } = useThemeSafe();
  const [sideHidden, setSideHidden] = useState(
    () => { try { return localStorage.getItem('vv_sidebar_hidden') === '1'; } catch { return false; } });

  const setSide = (hidden) => {
    setSideHidden(hidden);
    try { localStorage.setItem('vv_sidebar_hidden', hidden ? '1' : '0'); } catch {}
  };

  return (
    <div>
      <SectionTitle title="Giao diện" badge="personal"
        desc="chỉ áp cho trình duyệt này" />
      <Card title="Chủ đề">
        <div style={{ display: 'flex', gap: '8px' }}>
          {[
            ['light', 'Sáng'],
            ['dark', 'Tối'],
          ].map(([value, label]) => (
            <button key={value} onClick={() => setThemeSafe(value)} style={{
              ...btnStyle,
              background: theme === value ? 'var(--gradient)' : 'var(--bg)',
              color: theme === value ? '#fff' : 'var(--text)',
              border: theme === value ? 'none' : '1px solid var(--border)',
            }}>
              {label}
            </button>
          ))}
        </div>
      </Card>
      <Card title="Thanh menu trái">
        <div style={{ display: 'flex', gap: '8px' }}>
          <button onClick={() => setSide(false)} style={{
            ...btnStyle,
            background: !sideHidden ? 'var(--gradient)' : 'var(--bg)',
            color: !sideHidden ? '#fff' : 'var(--text)',
            border: !sideHidden ? 'none' : '1px solid var(--border)',
          }}>Hiện</button>
          <button onClick={() => setSide(true)} style={{
            ...btnStyle,
            background: sideHidden ? 'var(--gradient)' : 'var(--bg)',
            color: sideHidden ? '#fff' : 'var(--text)',
            border: sideHidden ? 'none' : '1px solid var(--border)',
          }}>Ẩn gọn</button>
        </div>
        <p style={{ fontSize: 'var(--text-xs)', color: 'var(--text-dim)', margin: '8px 0 0' }}>
          Áp dụng sau khi tải lại trang (trạng thái nằm trong trình duyệt này).
        </p>
      </Card>
    </div>
  );
}

// useTheme chỉ có toggle; cần đặt chính xác 'light'/'dark' từ 2 nút —
// bọc thêm setThemeSafe qua toggle có điều kiện (không sửa hook toàn cục).
function useThemeSafe() {
  const { theme, toggle } = useTheme();
  const setThemeSafe = (value) => {
    if (theme !== value) toggle();
  };
  return { theme, setThemeSafe };
}
