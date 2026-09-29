import { ThemeProvider } from './hooks/useTheme.jsx';
import { ApiProvider } from './hooks/useApi.jsx';
import { AuthProvider } from './hooks/useAuth.jsx';
import { RouterProvider } from 'react-router-dom';
import router from './router.jsx';
import './styles/tokens.css';
import './styles/global.css';

export default function App() {
  return (
    <ThemeProvider>
      <ApiProvider>
        <AuthProvider>
          <RouterProvider router={router} />
        </AuthProvider>
      </ApiProvider>
    </ThemeProvider>
  );
}