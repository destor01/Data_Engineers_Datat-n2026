import { defineConfig, loadEnv } from 'vite';

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '');
  const proxy = {
    '/api': {
      target: env.DATA_BACKEND_URL || 'http://127.0.0.1:8001',
      changeOrigin: true,
      timeout: 120_000,
      proxyTimeout: 120_000
    },
    '/audio-service': {
      target: env.AUDIO_BACKEND_URL || 'http://127.0.0.1:8000',
      changeOrigin: true,
      rewrite: (path: string) => path.replace(/^\/audio-service/, ''),
      timeout: 600_000,
      proxyTimeout: 600_000
    },
    '/data-api': {
      target: env.DATA_BACKEND_URL || 'http://127.0.0.1:8001',
      changeOrigin: true,
      timeout: 600_000,
      proxyTimeout: 600_000
    }
  };
  return { server: { proxy }, preview: { proxy } };
});
