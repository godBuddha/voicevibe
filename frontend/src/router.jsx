import { createBrowserRouter, redirect, Navigate } from 'react-router-dom';
import Layout from './components/Layout.jsx';
import Login from './pages/Login.jsx';
import Setup from './pages/Setup.jsx';
import Dashboard from './pages/Dashboard.jsx';
import Dub from './pages/Dub.jsx';
import TTS from './pages/TTS.jsx';
import Voices from './pages/Voices.jsx';
import STT from './pages/STT.jsx';
import Subtitle from './pages/Subtitle.jsx';
import Jobs from './pages/Jobs.jsx';
import ApiKeys from './pages/ApiKeys.jsx';
import AdminUsers from './pages/admin/Users.jsx';
import AdminModelHub from './pages/admin/ModelHub.jsx';
import AdminSettings from './pages/admin/Settings.jsx';
import Pricing from './pages/Pricing.jsx';

function protectedLoader() {
  // BẪY: bản sinh đầu tiên viết `!localStorage.getItem(...) === 'true'` —
  // toán tử `!` chạy TRƯỚC `===` nên biểu thức luôn sai, guard thành trang
  // trí (mọi ai vào thẳng URL đều thấy app dù chưa đăng nhập).
  if (localStorage.getItem('authenticated') !== 'true') {
    return redirect('/login');
  }
  return null;
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
      { path: 'jobs', element: <Jobs /> },
      { path: 'api-keys', element: <ApiKeys /> },
      { path: 'pricing', element: <Pricing /> },
      {
        path: 'admin',
        children: [
          { index: true, element: <Navigate to="/admin/users" replace /> },
          { path: 'users', element: <AdminUsers /> },
          { path: 'model-hub', element: <AdminModelHub /> },
          { path: 'settings', element: <AdminSettings /> },
        ],
      },
    ],
  },
]);