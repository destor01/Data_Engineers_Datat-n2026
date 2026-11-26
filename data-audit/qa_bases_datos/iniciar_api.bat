@echo off
REM Inicia la API de QA de bases de datos en http://localhost:8001 (documentacion en /docs)
cd /d %~dp0
if not exist .env (
  echo Falta el archivo .env. Copia .env.example como .env y pon tu DATABASE_URL.
  pause
  exit /b 1
)
python -m uvicorn qa.servidor:app --app-dir backend --port 8001 --reload
