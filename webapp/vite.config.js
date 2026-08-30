import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

// 开发与预览都把接口转发到本地后端。
// /health 在后端根路径而非 /api 下，需单独代理，
// 否则健康检查会命中 vite 自身并拿到 index.html。
const proxy = {
  '/api': 'http://localhost:8000',
  '/health': 'http://localhost:8000',
}

export default defineConfig({
  plugins: [vue()],
  server: { proxy },
  // 生产由后端同源托管 dist，preview 用代理模拟这一环境
  preview: { proxy },
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: ['./tests/setup.js'],
    exclude: ['node_modules/**', 'dist/**'],
  },
})
