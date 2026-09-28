import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    port: 3000,
    host: true,
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:5000',
        changeOrigin: true,
      },
      '/ws': {
        target: 'ws://127.0.0.1:5000',
        ws: true,
        configure: (proxy) => {
          proxy.on('error', (err) => {
            if (err.code === 'ECONNRESET' || err.code === 'ECONNABORTED' || err.code === 'EPIPE') return;
            console.error('[vite ws proxy error]', err);
          });
          proxy.on('proxyReqWsError', (err) => {
            if (err.code === 'ECONNRESET' || err.code === 'ECONNABORTED' || err.code === 'EPIPE') return;
            console.error('[vite ws proxy socket error]', err);
          });
        }
      }
    }
  }
})
