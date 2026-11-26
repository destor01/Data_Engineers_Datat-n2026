# Contrato de integración

Todas las rutas son de la API unificada, en el mismo dominio que la interfaz. Con Supabase Auth configurado, cada petición lleva `Authorization: Bearer <token de sesión>`; sin sesión válida la API responde 401. Las respuestas son JSON salvo las descargas. Los errores deben devolver un código HTTP de error y `{ "detail": "Mensaje legible" }`. El frontend valida los campos necesarios y muestra un error ante formatos incompatibles.

## Audio Audit

Contrato basado en las rutas existentes de `audio-audit/app/main.py`. El backend mantiene su responsabilidad sobre modelos, tokens, almacenamiento y procesamiento.

### Con Supabase Storage (despliegue)

1. `POST /api/storage/upload-url` con `{ "filename", "content_type" }` → `{ "job_id", "signed_upload_url", "storage_path" }`.
2. `PUT` del archivo a `signed_upload_url` (sin el token de la sesión).
3. `POST /api/transcribe/cloud` con `{ job_id, filename, storage_path, content_type, provider: "auto", diarize, min_speakers, max_speakers }` → el trabajo.

Si Storage no está configurado, el paso 1 responde 400 y la interfaz usa la ruta siguiente.

### POST /api/transcribe (local)

`multipart/form-data`:

| Campo | Tipo | Uso |
| --- | --- | --- |
| file | Archivo | Audio seleccionado |
| model | Texto | `medium`, `large-v3-turbo` o `large-v3` |
| denoise | Texto booleano | `true` o `false` |
| diarize | Texto booleano | `true` o `false` |
| min_speakers | Entero opcional | Mínimo de hablantes |
| max_speakers | Entero opcional | Máximo de hablantes |

Respuesta: `{ "job_id": "identificador" }`. El frontend permite hasta cinco minutos para enviar y recibir esta respuesta.

### GET /api/jobs/{job_id}

Se consulta cada 1,5 segundos después de recibir la respuesta anterior, hasta completarse, fallar, dejar de esperar o alcanzar dos horas de espera.

```json
{
  "job_id": "identificador",
  "status": "completed",
  "progress": 100,
  "stage": "Transcripción completada",
  "error": null,
  "result": {
    "speakers": ["Hablante 1"],
    "turns": [
      { "speaker": "Hablante 1", "start": 0, "end": 4.5, "text": "Buenos días." }
    ]
  }
}
```

Estados: `queued`, `processing`, `completed`, `error`. Los tiempos de las intervenciones están en segundos. `result` puede ser nulo antes de completarse. `result.warning` es un texto opcional.

El reproductor usa el archivo seleccionado mediante una URL temporal del navegador; la exportación TXT se construye con las intervenciones recibidas. No se necesita un endpoint adicional para estas dos funciones.

## Data Audit

Rutas de `data-audit/qa_bases_datos/backend/qa/api.py` (prefijo `/api/qa`). La carga queda registrada en PostgreSQL (tablas `carga`, `ejecucion`, `hallazgo`, `archivo`, `evento_auditoria`) a nombre del usuario que inició sesión.

### GET /api/qa/bases

Lista de `{ codigo, nombre, institucion, periodicidad, version, columnas_publicadas }`. La interfaz muestra solo las que tienen `version` activa.

### POST /api/qa/cargas/subida

```json
{ "base": "EMERGENCIAS", "anio": 2025, "mes": 11, "archivo": "emergencias.csv", "tamano": 2400 }
```

Valida base, período (las bases mensuales exigen mes), extensión (`.xlsx`, `.xls`, `.csv`, `.txt`) y tamaño (`QA_MAX_MB`, 50 por defecto). Respuesta:

```json
{ "carga_id": "uuid", "base": "EMERGENCIAS", "max_bytes": 52428800,
  "subida": { "url": "https://…/storage/v1/object/upload/sign/qa-cargas/cargas/uuid/original.csv?token=…", "metodo": "PUT", "directa": true } }
```

Con `directa: true` el archivo se sube con `PUT` a la URL firmada de Supabase Storage, sin el token de la sesión. Con `directa: false` (modo local) la URL es `/api/qa/cargas/{id}/archivo` y sí lleva el token.

### POST /api/qa/cargas/{id}/procesar

Valida el archivo subido en la misma petición (hasta 300 s en Vercel) y responde:

```json
{
  "carga_id": "uuid", "estado": "terminado", "segundos": 3.2,
  "reporte": {
    "base": "EMERGENCIAS", "total_registros": 1250, "registros_validos": 1198, "registros_excluidos": 52,
    "puntaje": 91.6, "puntajes": { "estructura": 100, "completitud": 94.2 },
    "hallazgos": [ { "severidad": "error", "mensaje": "Texto legible", "n": 32 } ]
  },
  "descargas": {
    "corregido": "/api/qa/cargas/uuid/descargar/corregido",
    "bitacora": "/api/qa/cargas/uuid/descargar/bitacora",
    "reporte": "/api/qa/cargas/uuid/descargar/reporte"
  }
}
```

Errores: 400 si el archivo no se ha subido, 409 si la carga ya se procesó (usar `/reprocesar`), 413 por tamaño, 422 si el motor no pudo validar la base (el mensaje explica la causa).

### GET /api/qa/cargas/{id}/descargar/{rol}

`rol`: `corregido`, `bitacora` o `reporte`. Con Supabase Storage responde `{ "url": "…", "nombre": "…" }` (URL firmada por 5 minutos); en local entrega el archivo. El original no se descarga por esta ruta porque contiene datos personales.

### Otras rutas

`GET /api/qa/cargas`, `GET /api/qa/cargas/{id}`, `GET /api/qa/cargas/{id}/reporte`, `/hallazgos`, `/sugerencias`, `/excluidos`, `POST /api/qa/cargas/{id}/reprocesar`, `/aprobar`, `/rechazar`, `POST /api/qa/sugerencias/{id}/aprobar|rechazar` y `GET /api/qa/catalogos/{codigo}`. `POST /api/qa/cargas` (multipart) se mantiene para uso directo de la API.
