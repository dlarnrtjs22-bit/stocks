import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
// 이 설정은 개발 서버에서 /api 요청을 FastAPI 백엔드로 넘긴다.
export default defineConfig({
    plugins: [react()],
    server: {
        host: '127.0.0.1',
        port: 5173,
        proxy: {
            '/api': {
                target: 'http://127.0.0.1:5056',
                changeOrigin: true,
            },
        },
    },
});
