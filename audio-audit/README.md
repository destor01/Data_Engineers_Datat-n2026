# Auditoría de Entrevistas ENCOVI — Local + JEV

Aplicación web en español para:

1. **Transcribir entrevistas largas en español (30 min – 2 h) 100 % local** con **WhisperX** (`large-v3-turbo` en GPU) y **Pyannote** (`Hablante 1`, `Hablante 2`, …).
2. **Evaluar la calidad de la entrevista contra las 51 reglas ENCOVI 2023 (secciones A1 y A2)** mediante el motor `encovi_jev` y el modelo **TypeSafe JEV (`typesafe/jev-1.14`)** en OpenRouter.
3. **Subir transcripciones ya existentes (`.json` o `.txt`)** o cargar la entrevista de ejemplo para probar la auditoría JEV en segundos.

## Cómo ejecutarlo

Haz doble clic en `audio-audit\start.bat` (detecta automáticamente `.venv` o `..\.venv`) o ejecuta desde PowerShell en la raíz del repositorio:

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --app-dir audio-audit --host 127.0.0.1 --port 8000
```

Luego abre http://127.0.0.1:8000 en tu navegador.

## Variables en `.env`

El servidor lee automáticamente el `.env` de la raíz del repositorio y `audio-audit\.env` (sin necesidad de reiniciar al editarlo):

```env
HF_TOKEN=hf_...
OPENROUTER_API_KEY=sk-or-...
```

- **`HF_TOKEN`** (gratis): necesario solo la primera vez para descargar el modelo local de Pyannote (`https://huggingface.co/pyannote/speaker-diarization-community-1`). Tu audio nunca sale de tu computadora.
- **`OPENROUTER_API_KEY`**: necesario para llamar al modelo JEV real (`typesafe/jev-1.14`, ~\$0.0004–\$0.002 USD por entrevista). También puedes activar el **Modo prueba sin conexión** en la interfaz para probar el flujo con puntajes simulados.
