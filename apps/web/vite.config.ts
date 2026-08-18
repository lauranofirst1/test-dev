import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/api': { target: 'http://localhost:8000', changeOrigin: true },
      // 업로드된 조각 보드 그림은 백엔드가 /media 로 서빙한다.
      '/media': { target: 'http://localhost:8000', changeOrigin: true },
    },
  },
})
