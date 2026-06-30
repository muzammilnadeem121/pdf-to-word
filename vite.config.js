// vite.config.js
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/upload':   'http://127.0.0.1:8000',
      '/convert':  'http://127.0.0.1:8000',
      '/download': 'http://127.0.0.1:8000',
      '/health':   'http://127.0.0.1:8000',
    },
  },
})