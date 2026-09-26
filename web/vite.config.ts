import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// The production deployment proxies /api through nginx; the dev server
// proxies it to a locally running API instead.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/api': 'http://localhost:8000',
    },
  },
})
