import { defineConfig, loadEnv } from 'vite';

// En desarrollo, /api/* va a la API unificada (uvicorn api.index:app --port 8000, desde la raíz).
// En Vercel no hace falta: la interfaz y la API comparten dominio.
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '');
  const proxy = {
    '/api': {
      target: env.API_BACKEND_URL || 'http://127.0.0.1:8000',
      changeOrigin: true,
      timeout: 600_000,
      proxyTimeout: 600_000
    }
  };
  return { server: { proxy }, preview: { proxy } };
});
