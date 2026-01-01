import path from 'path';
import { defineConfig, loadEnv } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig(({ mode }) => {
    const env = loadEnv(mode, '.', '');
    return {
      server: {
        port: 3000,
        host: '0.0.0.0',
        proxy: {
          '/api': {
            target: env.VITE_API_PROXY_TARGET || 'http://localhost:8000',
            changeOrigin: true,
            rewrite: (p) => p.replace(/^\/api/, ''),
          },
          '/static': {
            target: env.VITE_API_PROXY_TARGET || 'http://localhost:8000',
            changeOrigin: true,
          },
        },
      },
      plugins: [react()],
      test: {
        environment: 'jsdom',
      },
      resolve: {
        alias: {
          '@': path.resolve(__dirname, '.'),
        }
      }
    };
});
