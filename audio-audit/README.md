# Auditoría de Entrevistas ENCOVI — TypeScript + Python + Vercel + Supabase

Aplicación web con **frontend en React + Vite + TypeScript** y **backend en Python (FastAPI)** lista para desplegarse como MVP en **Vercel + Supabase** o ejecutarse localmente.

## Capacidades principales

1. **Separación de hablantes (`Hablante 1`, `Hablante 2`, …) en la nube o en GPU local**:
   - **En Vercel / sin token de Hugging Face**: soporte nativo para **AssemblyAI (`Universal-2`, ~$0.17 USD/h con diarización incluida + $50 gratis)** y **Deepgram (`Nova-3`, $200 en créditos gratis)**. Los archivos de audio largos (30 min – 2 h) se suben directo desde el navegador a **Supabase Storage** con URLs firmadas (evitando el límite de 4.5 MB de Vercel).
   - **En equipo local con GPU**: mantiene intacto el flujo 100 % local con **WhisperX** (`large-v3-turbo`) + **Pyannote**.
2. **Evaluación automática ENCOVI A1–A2 con JEV (`typesafe/jev-1.14` en OpenRouter)**: evalúa las 51 reglas del Manual del Encuestador ENCOVI 2023.
3. **Edición de evaluaciones y reescritura de criterios para próximas transcripciones**:
   - En cada una de las 51 evaluaciones (y en los principales riesgos) puedes hacer clic en **«Editar»** para:
     1. **Corregir el dictamen de la entrevista actual** (`Cumplida`, `Incumplida`, `No aplica` o porcentaje personalizado + nota del auditor), recalculando al instante las métricas globales y por sección.
     2. **Reescribir la regla / criterio JEV (instrucciones, opciones, peso o guía adicional del auditor)** y guardarla en **Supabase** para que se aplique automáticamente a las **próximas transcripciones**.

## Despliegue en Supabase y Vercel

1. **Supabase**:
   - Abre el **SQL Editor** en tu proyecto de Supabase y ejecuta [`supabase/schema.sql`](./supabase/schema.sql) (crea el bucket privado `audio-interviews` y las tablas `audio_audit_jobs`, `audio_audit_rule_overrides` y `audio_audit_evaluation_edits`).
2. **Vercel**:
   - Importa el repositorio en Vercel y configura **Root Directory** como `audio-audit`.
   - Agrega las variables de entorno en Vercel (`Project Settings → Environment Variables`):
     - `SUPABASE_URL`
     - `SUPABASE_SERVICE_ROLE_KEY`
     - `OPENROUTER_API_KEY`
     - `ASSEMBLYAI_API_KEY` *(o `DEEPGRAM_API_KEY`)*
   - Despliega: Vercel compilará el frontend TypeScript (`npm run build` → `dist/`) y publicará FastAPI en `/api/*` usando `api/index.py` y `requirements.txt` (ligero, sin PyTorch).

## Ejecución local

```powershell
cd audio-audit
npm install
npm run build
..\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Para desarrollo interactivo del frontend TypeScript con recarga en caliente:

```powershell
# Terminal 1 (Backend Python en :8000)
..\.venv\Scripts\python.exe -m uvicorn app.main:app --app-dir audio-audit --host 127.0.0.1 --port 8000

# Terminal 2 (Frontend Vite + TypeScript en :5173 con proxy a /api)
cd audio-audit && npm run dev
```
