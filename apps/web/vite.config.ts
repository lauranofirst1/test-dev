import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

const apiTarget = `http://localhost:${process.env.API_PORT ?? '8000'}`

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/api': { target: apiTarget, changeOrigin: true },
      // 업로드된 조각 보드 그림은 백엔드가 /media 로 서빙한다.
      '/media': { target: apiTarget, changeOrigin: true },
    },
  },
})
