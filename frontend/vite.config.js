import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    host: true,
    // Dev same-origin: proxy thẳng sang backend để cookie phiên SameSite=Lax
    // hoạt động nguyên trạng — KHÔNG cần CORS khi dev (CORS chỉ bắt buộc khi
    // SPA chạy từ origin khác; prod qua Caddy luôn same-origin).
    // Target override được bằng VV_API_TARGET (ví dụ máy đã chiếm cổng 8000).
    proxy: {
      '/v1': process.env.VV_API_TARGET || 'http://127.0.0.1:8000',
      '/media': process.env.VV_API_TARGET || 'http://127.0.0.1:8000',
    },
  },
});
