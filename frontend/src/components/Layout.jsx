import { useState } from 'react';
import { Outlet } from 'react-router-dom';
import Sidebar from './Sidebar.jsx';
import Topbar from './Topbar.jsx';

// Sidebar ẨN HOÀN TOÀN khi gập (theo phong cách Open WebUI) — toàn bộ hàng
// ngang nhường cho màn hình chính. Lựa chọn này là của người dùng nên ghi nhớ
// trong localStorage: F5 hay mở tab mới vẫn giữ nguyên trạng thái vừa chọn.
const HIDDEN_KEY = 'vv_sidebar_hidden';

function readHidden() {
  try {
    return localStorage.getItem(HIDDEN_KEY) === '1';
  } catch {
    return false; // localStorage bị chặn (iframe/cứu độ riêng tư) -> hiện bình thường
  }
}

export default function Layout() {
  const [sidebarHidden, setSidebarHidden] = useState(readHidden);

  const toggleSidebar = () => {
    setSidebarHidden((prev) => {
      try {
        localStorage.setItem(HIDDEN_KEY, prev ? '0' : '1');
      } catch {}
      return !prev;
    });
  };

  return (
    <div style={{ display: 'flex', height: '100%', width: '100%' }}>
      {!sidebarHidden && <Sidebar />}
      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', minWidth: 0, overflow: 'hidden' }}>
        <Topbar sidebarHidden={sidebarHidden} onToggleSidebar={toggleSidebar} />
        <main style={{ flex: 1, width: '100%', overflow: 'auto' }}>
          <Outlet />
        </main>
      </div>
    </div>
  );
}
