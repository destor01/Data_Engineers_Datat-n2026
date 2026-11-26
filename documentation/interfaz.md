# Interfaz integrada: instalación y operación

La carpeta versionada se llama **interfaz/**. Debe permanecer junto a audio-audit/ y data-audit/. No renombrar los motores ni duplicarlos dentro del frontend.

## Demostración

Desde la raíz del repositorio, con Node.js 20.19+ o 22.12+ y npm:

```powershell
cd interfaz
Copy-Item .env.example .env
npm ci
npm run dev
```

Copiar la plantilla solo si todavía no existe .env. Abrir la URL indicada por Vite. La demostración no envía archivos y presenta ejemplos identificados, no resultados del archivo. examples/ contiene un CSV ficticio y un WAV de silencio.

## Procesamiento real: API unificada

Todos los backends corren en un solo proceso: la API unificada de la raíz (`api/index.py`). Desde la raíz del repositorio, con Python 3.12 y un `.env` copiado de `.env.example`:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m uvicorn api.index:app --port 8000 --reload
```

En otra terminal, desde `interfaz/`, con `.env.local` copiado de `.env.example` y `VITE_APP_MODE=api`: `npm ci` y `npm run dev`. Vite envía `/api/*` al puerto 8000.

- Con Supabase configurado (`SUPABASE_URL`, `SUPABASE_ANON_KEY`, `SUPABASE_SERVICE_ROLE_KEY` en `.env`, y `VITE_SUPABASE_URL`, `VITE_SUPABASE_ANON_KEY` en `interfaz/.env.local`) la interfaz pide iniciar sesión y los archivos se guardan en Supabase Storage.
- Sin Supabase no hay login, la API solo atiende `localhost` y Data Audit guarda originales y resultados en `data-audit/qa_bases_datos/almacen/`.

`DATABASE_URL` debe apuntar a un PostgreSQL con el esquema y los catálogos cargados (`supabase/configurar.py` y `scripts/cargar_config.py`, ver [despliegue](deployment.md)). Las variables `VITE_` son públicas en el navegador: nunca contienen secretos.

## Recorrido de usuario

1. Audio Audit: elegir audio, modelo y opciones; iniciar, revisar turnos y reproductor, descargar TXT. Identificar voces no identifica el rol del encuestador.
2. Data Audit: elegir base con versión activa, período y archivo; iniciar, revisar puntuaciones, dimensiones y hallazgos; filtrar severidad; descargar resumen y archivos disponibles.
3. Dejar de esperar termina la espera en el navegador; no cancela el motor. Un error de API no activa automáticamente la demostración.

Límites: 50 MB por archivo en audio y datos (máximo del plan gratuito de Supabase; ajustable con `VITE_MAX_AUDIO_MB`, `VITE_MAX_DATA_MB` y `QA_MAX_MB`). En Vercel, cada validación de Data Audit tiene hasta 300 s. El catálogo requiere configuración previa.

## Compilación y despliegue

Desde interfaz/: `npm run typecheck`, `npm run build` y `npm run preview`. La publicación en Vercel (interfaz y API en el mismo proyecto) está en [despliegue](deployment.md).

## Datos y solución de problemas

En el despliegue, toda ruta `/api/*` exige una sesión de Supabase Auth. En local sin Supabase, la API solo responde a `localhost`. Los archivos de Data Audit quedan en el bucket privado `qa-cargas` (o en `almacen/` en local) hasta su retiro por el responsable.

| Síntoma | Comprobar |
|---|---|
| No carga el catálogo | API en el puerto 8000, DATABASE_URL, esquema y versiones activas (`supabase/configurar.py`). |
| No inicia audio | Llave de AssemblyAI o Deepgram y Supabase Storage; en local sin Supabase, WhisperX, FFmpeg y token de diarización. |
| Pide iniciar sesión otra vez | La sesión expiró o la cuenta se eliminó en Supabase → Authentication. |
| Demo después de editar .env | VITE_APP_MODE y reinicio de Vite; no basta cambiar el archivo con el proceso activo. |
| `/api/salud` responde `login: false` en Vercel | Faltan `VITE_SUPABASE_URL` / `VITE_SUPABASE_ANON_KEY` o `SUPABASE_URL` en las variables del proyecto. |
| Espera agotada | Revisar el servidor antes de repetir: el trabajo puede continuar. |

El contrato de rutas y respuestas está en [API de interfaz](../interfaz/docs/API.md). La evidencia y el plan de comprobación están en [Pruebas](testing.md).
