# Quality Audit · Interfaz integrada

Copia esta carpeta a la raíz del repositorio, junto a audio-audit/ y data-audit/. Incluye el frontend corregido, proxy local y un adaptador HTTP que utiliza el motor Data Audit original.

## Demostración

Requiere Node.js 20.19+ o 22.12+ y npm. Desde esta carpeta, en PowerShell:

```powershell
Copy-Item .env.example .env
npm ci
npm run dev
```

Abre la dirección que muestre Vite. En modo demo los archivos permanecen en el navegador y las cifras y transcripciones son ejemplos. examples/ contiene un CSV ficticio y un segundo de silencio; no sirven para validar el motor real.

## Integración real

Edita .env y reinicia Vite:

```dotenv
VITE_APP_MODE=api
VITE_AUDIO_API_URL=/audio-service
VITE_DATA_API_URL=/
AUDIO_BACKEND_URL=http://127.0.0.1:8000
DATA_BACKEND_URL=http://127.0.0.1:8001
DATABASE_URL=postgresql://usuario:clave@127.0.0.1:5432/quality_audit
```

DATABASE_URL solo la lee Python. No antepongas VITE_ a secretos. El proxy evita solicitudes entre orígenes sin modificar Audio Audit.

Terminal 1, desde la raíz del repositorio: instala primero Audio Audit según su README (Python, FFmpeg, modelos y dependencias). Después:

```powershell
cd audio-audit
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Si activas identificación de hablantes, configura antes el token en la interfaz original http://127.0.0.1:8000 y acepta las condiciones del modelo de diarización.

Terminal 2, desde interfaz-integrada/: necesita Python 3.11+, PostgreSQL y esquema, configuración y diccionarios cargados según documentation/installation.md del repositorio.

```powershell
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r ..\data-audit\qa_bases_datos\backend\requirements.txt -r backend\requirements.txt
.\.venv\Scripts\python.exe -m uvicorn backend.main:app --host 127.0.0.1 --port 8001
```

El adaptador importa qa/ del motor original. Si está en otra ubicación configura DATA_ENGINE_PATH en .env con la ruta absoluta a backend/ que contiene qa/.

Terminal 3, desde interfaz-integrada/:

```powershell
npm run dev
```

El catálogo muestra bases con versiones activas. El adaptador ejecuta las reglas originales y genera corregido.xlsx, bitacora.xlsx y reporte.json en backend/almacen/. No registra cargas ni aprobaciones en PostgreSQL. Admite una auditoría simultánea por proceso; utiliza un solo worker. Una conexión fallida muestra un error y no activa resultados ficticios.

## Compilar y revisar

```powershell
npm run typecheck
npm run build
npm run preview
```

El resultado se genera en dist/. La vista previa local usa el mismo proxy. Publicar solo dist/ requiere configurar en el alojamiento las rutas /audio-service y /data-api hacia los servicios; el proxy Vite no se incluye en los archivos estáticos.

## Alcance

Uso local: el adaptador no tiene autenticación. Los archivos recibidos y las salidas permanecen en backend/almacen/ hasta que el responsable los retire según su política. Dejar de esperar no cancela el trabajo del servidor. El adaptador aplica un límite de 100 MB a datos; la interfaz permite hasta 500 MB de audio.

El .gitignore excluye .env, .venv/, node_modules/, dist/ y backend/almacen/. No agregues entradas reales a Git.

La compilación se comprueba en esta entrega. Python, PostgreSQL, transcripción y diarización necesitan verificación en el equipo que tenga instalados los motores. No se realizaron pruebas de navegador ni se ejecutó el adaptador Python en este entorno.
