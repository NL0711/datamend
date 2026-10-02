import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5199,
    proxy: {
      '/api': {
        target: 'http://localhost:8899',
        changeOrigin: true,
      },
      '/ws': {
        target: 'ws://localhost:8899',
        ws: true,
      },
    },
  },
});
