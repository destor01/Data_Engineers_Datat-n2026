# Transcriptor Local de Entrevistas (Español)

Aplicación web MVP 100 % local para transcribir entrevistas largas en español (30 min a 2 horas), con audio ruidoso y múltiples hablantes, usando **WhisperX** (`large-v3-turbo` en GPU) y **Pyannote** para identificar hablantes (`Hablante 1`, `Hablante 2`, …).

## Cómo ejecutarlo

1. Haz doble clic en `start.bat` o ejecuta en PowerShell:
   ```powershell
   .\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
   ```
2. Abre `http://127.0.0.1:8000` en tu navegador.

## Configuración única para identificar hablantes (Pyannote)

El reconocimiento de voz corre 100 % local, pero los modelos de diarización de Pyannote están alojados en Hugging Face bajo licencia gratuita:

1. Crea o inicia sesión en una cuenta gratuita de [Hugging Face](https://huggingface.co/).
2. Acepta los términos de uso gratuitos en:
   - https://huggingface.co/pyannote/speaker-diarization-community-1
3. Genera un token de lectura (**Read**) en https://huggingface.co/settings/tokens.
4. Pégalo directamente en la interfaz web (se guarda localmente en `.env`) o cópialo en `.env` como `HF_TOKEN=hf_...`.

> Tu audio **nunca** se envía a internet; el token solo se usa para descargar el modelo a tu computadora la primera vez.
