@echo off
setlocal
cd /d "%~dp0"

set "PY="
if exist ".venv\Scripts\python.exe" set "PY=.venv\Scripts\python.exe"
if not defined PY if exist "..\.venv\Scripts\python.exe" set "PY=..\.venv\Scripts\python.exe"

if not defined PY (
    echo [ERROR] No se encontro el entorno virtual ^(.venv ni ..\.venv^).
    echo Crea el entorno e instala requirements-local.txt ^(GPU local^) o requirements.txt ^(nube^).
    pause
    exit /b 1
)

if not exist "dist\index.html" (
    where npm >nul 2>nul
    if %ERRORLEVEL% EQU 0 (
        echo Compilando frontend TypeScript ^(React + Vite^)...
        if not exist "node_modules" call npm install
        call npm run build
    )
)

echo Usando Python: %PY%
echo Iniciando Auditoria de Entrevistas ENCOVI en http://127.0.0.1:8000 ...
start "" http://127.0.0.1:8000
"%PY%" -m uvicorn app.main:app --host 127.0.0.1 --port 8000
pause
