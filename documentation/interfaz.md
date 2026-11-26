# Interfaz integrada: operación

La interfaz común vive en `interfaz/` (TypeScript + Vite, sin framework). Reúne los cuatro módulos con un solo inicio de sesión y habla con la API unificada (`api/index.py`). La instalación completa está en [instalación](installation.md) y la publicación en [despliegue](deployment.md); el uso paso a paso, en el [manual de usuario](user-guide.md).

## Estructura

| Archivo | Contenido |
|---|---|
| `src/main.ts` | Navegación, inicio de sesión (Supabase), formularios de audio y datos |
| `src/audio.ts` | Audio Audit: transcripción, roles, evaluación JEV, reporte, edición, reglas y calibración |
| `src/datos.ts` | Data Audit: detalle de auditoría, bandeja de correcciones, historial y correcciones guardadas |
| `src/survey.ts` | Survey Audit: PDF → formulario, editor, captura, grabación y verificación |
| `src/improvement.ts` | Quality Improvement: recomendaciones y manuales |
| `src/services/` | Clientes HTTP de la API |
| `examples/` | CSV ficticio y WAV de silencio para el modo demo |

## Modos

| Modo | Variable | Comportamiento |
|---|---|---|
| API (normal) | `VITE_APP_MODE=api` | Usa la API unificada en `/api/*` |
| Demostración | `VITE_APP_MODE=demo` | Muestra ejemplos sin backend; no procesa el archivo elegido |
| Con login | `VITE_SUPABASE_URL` y `VITE_SUPABASE_ANON_KEY` definidas | Pide iniciar sesión y envía el token en cada petición |
| Sin login | Sin esas variables | Solo para uso local: la API atiende únicamente `localhost` |

Para probar Survey Audit y Quality Improvement sin PostgreSQL se puede definir `QA_STORAGE=demo` en el `.env` del servidor: el estado se guarda en `interfaz/backend/almacen/extensions.demo.json` (solo datos sintéticos).

## Comandos

Desde `interfaz/`:

```bash
npm ci              # instalar dependencias exactas
npm run dev         # desarrollo en http://127.0.0.1:5173 (reenvía /api/* a API_BACKEND_URL)
npm run typecheck   # verificación de tipos
npm run build       # compilación a dist/
npm run preview     # servir dist/ localmente
```

## Límites

- 50 MB por archivo de audio o de datos (`VITE_MAX_AUDIO_MB`, `VITE_MAX_DATA_MB`; en el servidor, `QA_MAX_MB`).
- La lectura de un PDF largo se hace por bloques desde el navegador: la página debe quedar abierta mientras se lee (se puede continuar después).
- «Dejar de esperar» termina la espera en el navegador; no cancela el trabajo en el servidor.

## Solución de problemas

| Síntoma | Comprobar |
|---|---|
| No carga el catálogo de bases | API encendida, `DATABASE_URL` y catálogos cargados (`cargar_config`) |
| No inicia el audio | Llave de AssemblyAI o Deepgram y Supabase Storage; en local sin Supabase, WhisperX, FFmpeg y token de diarización |
| Pide iniciar sesión otra vez | La sesión venció o la cuenta se eliminó en Supabase → Authentication |
| Sigue en modo demo tras editar `.env.local` | Reiniciar `npm run dev` o recompilar |
| `/api/salud` responde `login: false` en Vercel | Faltan `VITE_SUPABASE_URL` / `VITE_SUPABASE_ANON_KEY` o `SUPABASE_URL` |
| La evaluación de audio dice «simulada» | Falta `OPENROUTER_API_KEY` en el servidor |

Contrato de la API: [referencia completa](api-referencia.md) y [convenciones](integration-api.md).
