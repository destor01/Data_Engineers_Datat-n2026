# Quality Audit · Interfaz integrada

Frontend (Vite + TypeScript) de la plataforma: login, Audio Audit, Data Audit, Survey Audit y Quality Improvement. Habla con la **API unificada** de la raíz del repositorio (`api/index.py`), que reúne los backends de `audio-audit/`, `data-audit/` e `interfaz/backend/extensions`.

En producción se publica junto con la API en un solo proyecto de Vercel: ver [despliegue](../documentation/deployment.md).

## Demostración (sin backend)

Requiere Node.js 20.19+ o 22.12+ y npm. Desde esta carpeta:

```powershell
Copy-Item .env.example .env.local
# en .env.local: VITE_APP_MODE=demo
npm ci
npm run dev
```

En modo demo los archivos permanecen en el navegador y las cifras y transcripciones son ejemplos.

## Con la API unificada (local)

1. En la raíz del repositorio: copiar `.env.example` a `.env`, instalar `requirements.txt` y arrancar la API:

   ```powershell
   .\.venv\Scripts\python.exe -m uvicorn api.index:app --port 8000 --reload
   ```

2. En esta carpeta: copiar `.env.example` a `.env.local` con `VITE_APP_MODE=api` y `npm run dev`. Vite envía `/api/*` al puerto 8000.

Con `VITE_SUPABASE_URL` y `VITE_SUPABASE_ANON_KEY` la interfaz pide iniciar sesión con Supabase Auth y envía el token en cada llamada. Sin ellas (y sin Supabase en la API) no hay login y todo queda en `localhost`.

## Flujos

- **Data Audit:** `POST /api/qa/cargas/subida` → el navegador sube el archivo (directo a Supabase Storage con URL firmada, o a la API en local) → `POST /api/qa/cargas/{id}/procesar` devuelve el reporte. Las descargas pasan por la API, que entrega una URL firmada de corta duración.
- **Audio Audit:** `POST /api/storage/upload-url` → subida directa a Storage → `POST /api/transcribe/cloud` → consulta de `/api/jobs/{id}`. Sin Supabase Storage, usa `POST /api/transcribe` (WhisperX local).
- **Survey Audit y Quality Improvement:** `/api/surveys/*` y `/api/improvement/*`.

## Compilar

```powershell
npm run typecheck
npm run build
npm run preview
```

`preview` usa el mismo proxy a la API. Los límites de tamaño que valida la interfaz se ajustan con `VITE_MAX_AUDIO_MB` y `VITE_MAX_DATA_MB` (por defecto 50, el máximo por archivo del plan gratuito de Supabase).

Documentación general: [instalación y operación integrada](../documentation/interfaz.md) · [contrato de API](docs/API.md).
