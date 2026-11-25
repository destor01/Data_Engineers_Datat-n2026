@echo off
cd /d "%~dp0"
echo Iniciando Transcriptor Local de Entrevistas en http://127.0.0.1:8000 ...
start "" http://127.0.0.1:8000
".venv\Scripts\python.exe" -m uvicorn app.main:app --host 127.0.0.1 --port 8000
pause
