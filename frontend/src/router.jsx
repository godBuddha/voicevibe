import { createBrowserRouter, redirect, Navigate } from 'react-router-dom';
import Layout from './components/Layout.jsx';
import { AuthProvider, useAuth } from './hooks/useAuth.jsx';
import Login from './pages/Login.jsx';
import Setup from './pages/Setup.jsx';
import Dashboard from './pages/Dashboard.jsx';
import Dub from './pages/Dub.jsx';
import TTS from './pages/TTS.jsx';
import Voices from './pages/Voices.jsx';
import STT from './pages/STT.jsx';
import Subtitle from './pages/Subtitle.jsx';
import TranslateText from './pages/TranslateText.jsx';
import TranslateAudio from './pages/TranslateAudio.jsx';
import Download from './pages/Download.jsx';
import Render from './pages/Render.jsx';
import Summary from './pages/Summary.jsx';
import Jobs from './pages/Jobs.jsx';
import ApiKeys from './pages/ApiKeys.jsx';
import Prompts from './pages/Prompts.jsx';
import SettingsHub from './pages/settings/SettingsHub.jsx';

function protectedLoader() {
  // BẪY: bản sinh đầu tiên viết `!localStorage.getItem(...) === 'true'` —
  // toán tử `!` chạy TRƯỚC `===` nên biểu thức luôn sai, guard thành trang
  // trí (mọi ai vào thẳng URL đều thấy app dù chưa đăng nhập).
  if (localStorage.getItem('authenticated') !== 'true') {
    return redirect('/login');
  }
  return null;
}

// Router guard là CỬA SÁU: ẩn link ở Sidebar không đủ — gõ thẳng /admin/* vẫn
// vào được và nhận 403 lặng lẽ (các trang nuốt lỗi → bảng trống). Chờ
// /v1/auth/me trả role rồi mới render; user thường về "/".
function RequireAdmin({ children }) {
  const { user, loading } = useAuth();
  if (loading) return null; // chờ profile — không nhấp nháy redirect
  if (user?.role !== 'admin') return <Navigate to="/" replace />;
  return children;
}

export default createBrowserRouter([
  {
    path: '/login',
    element: <Login />,
    loader: () => {
      if (localStorage.getItem('authenticated') === 'true') {
        return redirect('/');
      }
      return null;
    },
  },
  {
    path: '/setup',
    element: <Setup />,
    loader: () => {
      if (localStorage.getItem('authenticated') === 'true') {
        return redirect('/');
      }
      return null;
    },
  },
  {
    path: '/',
    element: <Layout />,
    loader: protectedLoader,
    children: [
      { index: true, element: <Dashboard /> },
      { path: 'dub', element: <Dub /> },
      { path: 'tts', element: <TTS /> },
      { path: 'voices', element: <Voices /> },
      { path: 'stt', element: <STT /> },
      { path: 'subtitle', element: <Subtitle /> },
      { path: 'translate-text', element: <TranslateText /> },
      { path: 'translate-audio', element: <TranslateAudio /> },
      { path: 'download', element: <Download /> },
      { path: 'render', element: <Render /> },
      { path: 'summary', element: <Summary /> },
      { path: 'jobs', element: <Jobs /> },
      { path: 'prompts', element: <Prompts /> },
      // SETTINGS HUB — Control Center cho cả user thường lẫn admin. Sidebar
      // riêng theo scope (Cá nhân / Hệ thống); section không hợp lệ → hồ sơ.
      { path: 'settings', element: <SettingsHub /> },
      { path: 'settings/:section', element: <SettingsHub /> },
      // REDIRECT một chiều: link cũ không chết, mọi người đi qua hub.
      { path: 'api-keys', element: <Navigate to="/settings/api-keys" replace /> },
      { path: 'admin', element: <Navigate to="/settings/members" replace /> },
      { path: 'admin/users', element: <Navigate to="/settings/members" replace /> },
      { path: 'admin/model-hub', element: <Navigate to="/settings/ai-platform" replace /> },
      { path: 'admin/settings', element: <Navigate to="/settings/config" replace /> },
    ],
  },
]);