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

## Procesamiento real: tres terminales

Preparar Audio Audit con su README y Data Audit con la guía de instalación general: PostgreSQL, esquema y diccionarios autorizados. Desde interfaz/, configurar .env:

```dotenv
VITE_APP_MODE=api
VITE_AUDIO_API_URL=/audio-service
VITE_DATA_API_URL=/
AUDIO_BACKEND_URL=http://127.0.0.1:8000
DATA_BACKEND_URL=http://127.0.0.1:8001
DATABASE_URL=postgresql://usuario:clave@127.0.0.1:5432/quality_audit
```

Los valores de usuario y clave son marcadores. DATABASE_URL no lleva prefijo VITE_; las variables VITE_ son públicas en el navegador. Reiniciar Vite al cambiar .env. Si los motores están en otra ubicación, DATA_ENGINE_PATH apunta al backend/ original que contiene qa/.

Terminal de audio, desde la raíz del repositorio, tras instalar sus dependencias:

```powershell
cd audio-audit
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Para diarización, preparar acceso al modelo y token desde la interfaz original en http://127.0.0.1:8000. La nueva interfaz no administra tokens.

Terminal de datos, desde la raíz del repositorio:

```powershell
cd interfaz
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r ..\data-audit\qa_bases_datos\backend\requirements.txt -r backend\requirements.txt
.\.venv\Scripts\python.exe -m uvicorn backend.main:app --host 127.0.0.1 --port 8001
```

La instalación del adaptador no crea el esquema ni carga catálogos. Usar un solo worker. El adaptador consulta definiciones de PostgreSQL, procesa con qa.motor y genera salidas con qa.salidas. No registra cargas ni aprobaciones en PostgreSQL. Guarda originales y resultados en interfaz/backend/almacen/.

Terminal de interfaz, desde interfaz/: npm run dev. El proxy lleva /audio-service/* al puerto 8000 eliminando ese prefijo y /data-api/* al 8001 sin eliminarlo. El navegador usa el mismo origen; un acceso directo a los puertos de backend puede necesitar CORS.

## Recorrido de usuario

1. Audio Audit: elegir audio, modelo y opciones; iniciar, revisar turnos y reproductor, descargar TXT. Identificar voces no identifica el rol del encuestador.
2. Data Audit: elegir base con versión activa, período y archivo; iniciar, revisar puntuaciones, dimensiones y hallazgos; filtrar severidad; descargar resumen y archivos disponibles.
3. Dejar de esperar termina la espera en el navegador; no cancela el motor. Un error de API no activa automáticamente la demostración.

Límites: frontend audio 500 MB; frontend y adaptador datos 100 MB. El límite de audio de la interfaz no representa una validación del tamaño por el backend original. El catálogo requiere configuración previa. El adaptador admite una auditoría por proceso; una segunda recibe 409 después de recibir su carga.

## Compilación y despliegue

Desde interfaz/: npm run typecheck, npm run build y npm run preview. dev y preview usan el proxy configurado. Un servidor estático que aloje solo dist/ debe configurar /audio-service y /data-api hacia los servicios. Vite preview es para revisión local. No se ha verificado una publicación externa.

## Datos y solución de problemas

No publicar los servicios sin implementar los controles de acceso que requiera el entorno. Los archivos de almacén quedan hasta su retiro por el responsable; no existe limpieza automática en este adaptador. Antes de borrar, esperar a que finalicen trabajos y confirmar la política aplicable.

| Síntoma | Comprobar |
|---|---|
| No carga el catálogo | Puerto 8001, DATABASE_URL, esquema y versiones activas. |
| No inicia audio | Puerto 8000, dependencias, FFmpeg/modelos y token si se solicita diarización. |
| No encuentra qa/ | Ubicación de data-audit o DATA_ENGINE_PATH. |
| Demo después de editar .env | VITE_APP_MODE y reinicio de Vite; no basta cambiar el archivo con el proceso activo. |
| Error al publicar dist | Proxy del alojamiento y rutas del mismo origen. |
| Espera agotada | Revisar el servidor antes de repetir: el trabajo puede continuar. |

El contrato de rutas y respuestas está en [API de interfaz](../interfaz/docs/API.md). La evidencia y el plan de comprobación están en [Pruebas](testing.md).
