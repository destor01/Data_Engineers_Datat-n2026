# Contrato de integración

Todas las rutas se resuelven respecto a la dirección pública del servicio configurado en `.env`. Las respuestas son JSON salvo las descargas. Los errores deben devolver un código HTTP de error y `{ "detail": "Mensaje legible" }`. El frontend valida los campos necesarios y muestra un error ante formatos incompatibles.

## Audio Audit

Contrato basado en las rutas existentes de `audio-audit/app/main.py`. El backend mantiene su responsabilidad sobre modelos, tokens, almacenamiento y procesamiento.

### POST /api/transcribe

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

Implementado por backend/main.py de esta entrega mediante el motor original. Consulta PostgreSQL para cargar versiones activas y catálogos, procesa con qa.motor y genera archivos con qa.salidas. No registra cargas ni aprobaciones en PostgreSQL. El adaptador local escucha en 8001 y el proxy Vite lo publica bajo /data-api.

### GET /data-api/bases

```json
[
  { "codigo": "DETENIDOS", "nombre": "Detenidos · PNC" }
]
```

Una lista vacía debe representar que no hay bases configuradas; el formulario no permite procesar hasta tener opciones.

### POST /data-api/procesar

`multipart/form-data`: `file` (XLSX, XLS o CSV), `base` (código), `anio` (entero), `mes` (entero de 1 a 12). Año y mes representan el período de referencia; la aplicabilidad de reglas por período depende de la base y del motor. El frontend espera la respuesta hasta diez minutos. Para trabajos más largos, el equipo debería acordar un contrato por trabajos similar al de audio.

```json
{
  "reporte": {
    "base": "DETENIDOS",
    "total_registros": 100,
    "registros_validos": 95,
    "registros_excluidos": 5,
    "puntaje": 92.5,
    "puntajes": { "completitud": 95, "validez": 90 },
    "hallazgos": [
      { "severidad": "error", "mensaje": "Campos obligatorios vacíos.", "n": 5 }
    ]
  },
  "descargas": {
    "corregido": "/data-api/descargas/identificador/corregido",
    "bitacora": "/data-api/descargas/identificador/bitacora"
  }
}
```

`puntaje` puede ser nulo si no se calcula. Las dimensiones se reciben como un diccionario de puntuaciones entre 0 y 100; el frontend dibuja las barras en esa escala. Las severidades admitidas son `error`, `advertencia` e `info`. `n` es opcional. `descargas` puede estar vacío. Las descargas deben usar HTTP/HTTPS y pertenecer al mismo origen del servicio de datos. El backend debe responder con el contenido y encabezados adecuados para descargar cada archivo.

## Responsabilidades del backend

Aplicar validación de archivos, límites, permisos, reglas institucionales y política de conservación. Con el proxy local, el navegador usa el mismo origen. Si se accede directamente a los backend, CORS debe admitir el origen del frontend; las rutas deben admitir HTTPS si la interfaz se publica con HTTPS. El contrato actual no incorpora autenticación ni aprobación de sugerencias; esas capacidades requieren un acuerdo y una implementación adicionales antes de exponer información restringida.

## Descargas del adaptador

GET /data-api/descargas/{job_id}/{role}, con job_id hexadecimal de 32 caracteres y role corregido, bitacora o reporte. Devuelve 404 si no existe. POST puede responder 400 por formato/base vacía o no configurada, 413 por carga mayor de 100 MB, 409 por ejecución ocupada, 422 por parámetros inválidos, 503 por DATABASE_URL ausente y 500 por fallo general; GET bases usa 503 para fallos de consulta. No se exponen originales mediante esta ruta.
