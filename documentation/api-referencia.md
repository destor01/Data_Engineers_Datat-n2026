# Referencia de la API

> Generado con `python documentation/herramientas/generar_api.py` desde el esquema OpenAPI de
> `plataforma/app.py`. Las convenciones (autenticación, errores, ejemplos) están en
> [integration-api.md](integration-api.md).

Total: **78 operaciones** en 68 rutas.

## Índice

- [Data Audit](#data-audit) (22)
- [Survey Audit](#survey-audit) (22)
- [Quality Improvement](#quality-improvement) (13)
- [Audio Audit y plataforma](#audio-audit-y-plataforma) (21)

## Data Audit

| Método | Ruta | Función |
|---|---|---|
| GET | `/api/qa/bases` | Listar Bases |
| GET | `/api/qa/bases/{codigo}` | Detalle Base |
| GET | `/api/qa/cargas` | Listar Cargas |
| POST | `/api/qa/cargas` | Crear Carga |
| POST | `/api/qa/cargas/subida` | Registra la carga y devuelve a dónde subir el archivo original con PUT. |
| GET | `/api/qa/cargas/{carga_id}` | Detalle Carga |
| POST | `/api/qa/cargas/{carga_id}/aprobar` | Aprobar Carga |
| PUT | `/api/qa/cargas/{carga_id}/archivo` | Solo en modo local: recibe el original (con Supabase el navegador sube directo a Storage). |
| GET | `/api/qa/cargas/{carga_id}/descargar/{rol}` | Archivo local: lo entrega directo. En Supabase Storage: {"url": ...} firmada por 5 minutos. |
| GET | `/api/qa/cargas/{carga_id}/excluidos` | Excluidos |
| GET | `/api/qa/cargas/{carga_id}/hallazgos` | Hallazgos |
| POST | `/api/qa/cargas/{carga_id}/procesar` | Valida el archivo ya subido en esta misma petición y devuelve el reporte. |
| POST | `/api/qa/cargas/{carga_id}/rechazar` | Rechazar Carga |
| GET | `/api/qa/cargas/{carga_id}/reporte` | Reporte JSON de la última ejecución (el mismo formato que devuelve /procesar). |
| POST | `/api/qa/cargas/{carga_id}/reprocesar` | Vuelve a correr el motor con el mismo archivo: aplica las sugerencias ya aprobadas. |
| GET | `/api/qa/cargas/{carga_id}/sugerencias` | Sugerencias |
| GET | `/api/qa/catalogos/{codigo}` | Para el selector del front cuando el analista corrige una sugerencia. |
| GET | `/api/qa/equivalencias` | Correcciones aprobadas: cada texto de origen con el código que se le asignó. Desde la siguiente |
| DELETE | `/api/qa/equivalencias/{equivalencia_id}` | Deja de aplicar una corrección guardada. Las bases ya validadas no cambian hasta reprocesarlas. |
| GET | `/api/qa/estado` | Estado |
| POST | `/api/qa/sugerencias/{correccion_id}/aprobar` | Aprueba una sugerencia. Queda como equivalencia aprobada de la institución: desde la |
| POST | `/api/qa/sugerencias/{correccion_id}/rechazar` | Rechazar Sugerencia |

### GET `/api/qa/bases`

Listar Bases

Respuestas documentadas: 200 OK. Errores comunes: 401 sin sesión, 404 no existe, 409 estado no permite la acción, 422 datos no válidos, 503 servicio externo ocupado.

### GET `/api/qa/bases/{codigo}`

Detalle Base

| Parámetro | En | Tipo | Obligatorio | Validación |
|---|---|---|---|---|
| `codigo` | ruta | texto | sí | — |

Respuestas documentadas: 200 OK, 422 Datos no válidos. Errores comunes: 401 sin sesión, 404 no existe, 409 estado no permite la acción, 422 datos no válidos, 503 servicio externo ocupado.

### GET `/api/qa/cargas`

Listar Cargas

| Parámetro | En | Tipo | Obligatorio | Validación |
|---|---|---|---|---|
| `base` | consulta | nulo o texto | no | — |
| `estado` | consulta | nulo o texto | no | — |
| `institucion` | consulta | nulo o texto | no | — |
| `limite` | consulta | entero | no | máx. 500; por defecto 50 |

Respuestas documentadas: 200 OK, 422 Datos no válidos. Errores comunes: 401 sin sesión, 404 no existe, 409 estado no permite la acción, 422 datos no válidos, 503 servicio externo ocupado.

### POST `/api/qa/cargas`

Crear Carga

Solicitud (`multipart/form-data`):

| Campo | Tipo | Obligatorio | Validación |
|---|---|---|---|
| `file` | texto | sí | — |
| `base` | texto | sí | — |
| `anio` | entero | sí | — |
| `mes` | entero o nulo | no | — |
| `usuario` | nulo o texto | no | — |

Respuestas documentadas: 200 OK, 422 Datos no válidos. Errores comunes: 401 sin sesión, 404 no existe, 409 estado no permite la acción, 422 datos no válidos, 503 servicio externo ocupado.

### POST `/api/qa/cargas/subida`

Registra la carga y devuelve a dónde subir el archivo original con PUT.

Solicitud (`application/json`):

| Campo | Tipo | Obligatorio | Validación |
|---|---|---|---|
| `base` | texto | sí | mín. caracteres 1; máx. caracteres 50 |
| `anio` | entero | sí | mín. 1900.0; máx. 2100.0 |
| `mes` | entero o nulo | no | mín. 1.0; máx. 12.0 |
| `archivo` | texto | sí | mín. caracteres 1; máx. caracteres 300 |
| `tamano` | entero o nulo | no | mín. 0.0 |

Respuestas documentadas: 200 OK, 422 Datos no válidos. Errores comunes: 401 sin sesión, 404 no existe, 409 estado no permite la acción, 422 datos no válidos, 503 servicio externo ocupado.

### GET `/api/qa/cargas/{carga_id}`

Detalle Carga

| Parámetro | En | Tipo | Obligatorio | Validación |
|---|---|---|---|---|
| `carga_id` | ruta | texto | sí | — |

Respuestas documentadas: 200 OK, 422 Datos no válidos. Errores comunes: 401 sin sesión, 404 no existe, 409 estado no permite la acción, 422 datos no válidos, 503 servicio externo ocupado.

### POST `/api/qa/cargas/{carga_id}/aprobar`

Aprobar Carga

| Parámetro | En | Tipo | Obligatorio | Validación |
|---|---|---|---|---|
| `carga_id` | ruta | texto | sí | — |

Solicitud (`application/json`):

| Campo | Tipo | Obligatorio | Validación |
|---|---|---|---|
| `usuario` | nulo o texto | no | — |
| `comentario` | nulo o texto | no | — |

Respuestas documentadas: 200 OK, 422 Datos no válidos. Errores comunes: 401 sin sesión, 404 no existe, 409 estado no permite la acción, 422 datos no válidos, 503 servicio externo ocupado.

### PUT `/api/qa/cargas/{carga_id}/archivo`

Solo en modo local: recibe el original (con Supabase el navegador sube directo a Storage).

| Parámetro | En | Tipo | Obligatorio | Validación |
|---|---|---|---|---|
| `carga_id` | ruta | texto | sí | — |

Respuestas documentadas: 200 OK, 422 Datos no válidos. Errores comunes: 401 sin sesión, 404 no existe, 409 estado no permite la acción, 422 datos no válidos, 503 servicio externo ocupado.

### GET `/api/qa/cargas/{carga_id}/descargar/{rol}`

Archivo local: lo entrega directo. En Supabase Storage: {"url": ...} firmada por 5 minutos.

| Parámetro | En | Tipo | Obligatorio | Validación |
|---|---|---|---|---|
| `carga_id` | ruta | texto | sí | — |
| `rol` | ruta | texto | sí | — |

Respuestas documentadas: 200 OK, 422 Datos no válidos. Errores comunes: 401 sin sesión, 404 no existe, 409 estado no permite la acción, 422 datos no válidos, 503 servicio externo ocupado.

### GET `/api/qa/cargas/{carga_id}/excluidos`

Excluidos

| Parámetro | En | Tipo | Obligatorio | Validación |
|---|---|---|---|---|
| `carga_id` | ruta | texto | sí | — |

Respuestas documentadas: 200 OK, 422 Datos no válidos. Errores comunes: 401 sin sesión, 404 no existe, 409 estado no permite la acción, 422 datos no válidos, 503 servicio externo ocupado.

### GET `/api/qa/cargas/{carga_id}/hallazgos`

Hallazgos

| Parámetro | En | Tipo | Obligatorio | Validación |
|---|---|---|---|---|
| `carga_id` | ruta | texto | sí | — |
| `severidad` | consulta | nulo o texto | no | — |
| `dimension` | consulta | nulo o texto | no | — |
| `incluir_info` | consulta | sí/no | no | por defecto True |

Respuestas documentadas: 200 OK, 422 Datos no válidos. Errores comunes: 401 sin sesión, 404 no existe, 409 estado no permite la acción, 422 datos no válidos, 503 servicio externo ocupado.

### POST `/api/qa/cargas/{carga_id}/procesar`

Valida el archivo ya subido en esta misma petición y devuelve el reporte.

| Parámetro | En | Tipo | Obligatorio | Validación |
|---|---|---|---|---|
| `carga_id` | ruta | texto | sí | — |

Respuestas documentadas: 200 OK, 422 Datos no válidos. Errores comunes: 401 sin sesión, 404 no existe, 409 estado no permite la acción, 422 datos no válidos, 503 servicio externo ocupado.

### POST `/api/qa/cargas/{carga_id}/rechazar`

Rechazar Carga

| Parámetro | En | Tipo | Obligatorio | Validación |
|---|---|---|---|---|
| `carga_id` | ruta | texto | sí | — |

Solicitud (`application/json`):

| Campo | Tipo | Obligatorio | Validación |
|---|---|---|---|
| `usuario` | nulo o texto | no | — |
| `comentario` | nulo o texto | no | — |

Respuestas documentadas: 200 OK, 422 Datos no válidos. Errores comunes: 401 sin sesión, 404 no existe, 409 estado no permite la acción, 422 datos no válidos, 503 servicio externo ocupado.

### GET `/api/qa/cargas/{carga_id}/reporte`

Reporte JSON de la última ejecución (el mismo formato que devuelve /procesar).

| Parámetro | En | Tipo | Obligatorio | Validación |
|---|---|---|---|---|
| `carga_id` | ruta | texto | sí | — |

Respuestas documentadas: 200 OK, 422 Datos no válidos. Errores comunes: 401 sin sesión, 404 no existe, 409 estado no permite la acción, 422 datos no válidos, 503 servicio externo ocupado.

### POST `/api/qa/cargas/{carga_id}/reprocesar`

Vuelve a correr el motor con el mismo archivo: aplica las sugerencias ya aprobadas.

| Parámetro | En | Tipo | Obligatorio | Validación |
|---|---|---|---|---|
| `carga_id` | ruta | texto | sí | — |

Solicitud (`application/x-www-form-urlencoded`):

| Campo | Tipo | Obligatorio | Validación |
|---|---|---|---|
| `usuario` | nulo o texto | no | — |

Respuestas documentadas: 200 OK, 422 Datos no válidos. Errores comunes: 401 sin sesión, 404 no existe, 409 estado no permite la acción, 422 datos no válidos, 503 servicio externo ocupado.

### GET `/api/qa/cargas/{carga_id}/sugerencias`

Sugerencias

| Parámetro | En | Tipo | Obligatorio | Validación |
|---|---|---|---|---|
| `carga_id` | ruta | texto | sí | — |
| `estado` | consulta | texto | no | por defecto 'pendiente' |
| `columna` | consulta | nulo o texto | no | — |

Respuestas documentadas: 200 OK, 422 Datos no válidos. Errores comunes: 401 sin sesión, 404 no existe, 409 estado no permite la acción, 422 datos no válidos, 503 servicio externo ocupado.

### GET `/api/qa/catalogos/{codigo}`

Para el selector del front cuando el analista corrige una sugerencia.

| Parámetro | En | Tipo | Obligatorio | Validación |
|---|---|---|---|---|
| `codigo` | ruta | texto | sí | — |
| `q` | consulta | nulo o texto | no | — |
| `limite` | consulta | entero | no | máx. 200; por defecto 20 |

Respuestas documentadas: 200 OK, 422 Datos no válidos. Errores comunes: 401 sin sesión, 404 no existe, 409 estado no permite la acción, 422 datos no válidos, 503 servicio externo ocupado.

### GET `/api/qa/equivalencias`

Correcciones aprobadas: cada texto de origen con el código que se le asignó. Desde la siguiente
validación, ese texto se corrige solo para la institución.

| Parámetro | En | Tipo | Obligatorio | Validación |
|---|---|---|---|---|
| `institucion` | consulta | nulo o texto | no | — |
| `catalogo` | consulta | nulo o texto | no | — |
| `q` | consulta | nulo o texto | no | — |
| `limite` | consulta | entero | no | máx. 1000; por defecto 200 |

Respuestas documentadas: 200 OK, 422 Datos no válidos. Errores comunes: 401 sin sesión, 404 no existe, 409 estado no permite la acción, 422 datos no válidos, 503 servicio externo ocupado.

### DELETE `/api/qa/equivalencias/{equivalencia_id}`

Deja de aplicar una corrección guardada. Las bases ya validadas no cambian hasta reprocesarlas.

| Parámetro | En | Tipo | Obligatorio | Validación |
|---|---|---|---|---|
| `equivalencia_id` | ruta | entero | sí | — |

Respuestas documentadas: 200 OK, 422 Datos no válidos. Errores comunes: 401 sin sesión, 404 no existe, 409 estado no permite la acción, 422 datos no válidos, 503 servicio externo ocupado.

### GET `/api/qa/estado`

Estado

Respuestas documentadas: 200 OK. Errores comunes: 401 sin sesión, 404 no existe, 409 estado no permite la acción, 422 datos no válidos, 503 servicio externo ocupado.

### POST `/api/qa/sugerencias/{correccion_id}/aprobar`

Aprueba una sugerencia. Queda como equivalencia aprobada de la institución: desde la
siguiente ejecución, ese texto se codifica solo.

| Parámetro | En | Tipo | Obligatorio | Validación |
|---|---|---|---|---|
| `correccion_id` | ruta | entero | sí | — |

Solicitud (`application/json`):

| Campo | Tipo | Obligatorio | Validación |
|---|---|---|---|
| `usuario` | nulo o texto | no | — |
| `codigo` | nulo o texto | no | — |

Respuestas documentadas: 200 OK, 422 Datos no válidos. Errores comunes: 401 sin sesión, 404 no existe, 409 estado no permite la acción, 422 datos no válidos, 503 servicio externo ocupado.

### POST `/api/qa/sugerencias/{correccion_id}/rechazar`

Rechazar Sugerencia

| Parámetro | En | Tipo | Obligatorio | Validación |
|---|---|---|---|---|
| `correccion_id` | ruta | entero | sí | — |

Solicitud (`application/json`):

| Campo | Tipo | Obligatorio | Validación |
|---|---|---|---|
| `usuario` | nulo o texto | no | — |
| `comentario` | nulo o texto | no | — |

Respuestas documentadas: 200 OK, 422 Datos no válidos. Errores comunes: 401 sin sesión, 404 no existe, 409 estado no permite la acción, 422 datos no válidos, 503 servicio externo ocupado.

## Survey Audit

| Método | Ruta | Función |
|---|---|---|
| GET | `/api/surveys/documents` | Documentos |
| POST | `/api/surveys/documents` | Nuevo Documento |
| PUT | `/api/surveys/documents/{key}/archivo` | Recibir Documento |
| POST | `/api/surveys/documents/{key}/formulario` | Crear Formulario |
| POST | `/api/surveys/documents/{key}/leer` | Leer Paginas |
| POST | `/api/surveys/documents/{key}/preparar` | Preparar Documento |
| GET | `/api/surveys/interviews` | Interviews |
| POST | `/api/surveys/interviews` | Create Interview |
| GET | `/api/surveys/interviews/{key}` | Get Interview |
| PATCH | `/api/surveys/interviews/{key}` | Save Interview |
| PATCH | `/api/surveys/interviews/{key}/encuestador` | Elegir Encuestador |
| PATCH | `/api/surveys/interviews/{key}/findings/{finding_id}` | Review |
| POST | `/api/surveys/interviews/{key}/submit` | Submit Interview |
| POST | `/api/surveys/interviews/{key}/transcripts` | Transcript |
| POST | `/api/surveys/interviews/{key}/verificacion` | Preparar Verificacion |
| POST | `/api/surveys/interviews/{key}/verificacion/{n}` | Verificar Lote |
| GET | `/api/surveys/templates` | Templates |
| POST | `/api/surveys/templates` | Create Template |
| DELETE | `/api/surveys/templates/{key}` | Borrar Formulario |
| GET | `/api/surveys/templates/{key}` | Template |
| PATCH | `/api/surveys/templates/{key}` | Edit Template |
| POST | `/api/surveys/templates/{key}/publish` | Publish |

### GET `/api/surveys/documents`

Documentos

Respuestas documentadas: 200 OK. Errores comunes: 401 sin sesión, 404 no existe, 409 estado no permite la acción, 422 datos no válidos, 503 servicio externo ocupado.

### POST `/api/surveys/documents`

Nuevo Documento

Solicitud (`application/json`):

| Campo | Tipo | Obligatorio | Validación |
|---|---|---|---|
| `nombre` | texto | sí | mín. caracteres 2; máx. caracteres 150 |
| `archivo` | texto | sí | mín. caracteres 1; máx. caracteres 300 |
| `tamano` | entero | sí | mín. 1.0 |

Respuestas documentadas: 200 OK, 422 Datos no válidos. Errores comunes: 401 sin sesión, 404 no existe, 409 estado no permite la acción, 422 datos no válidos, 503 servicio externo ocupado.

### PUT `/api/surveys/documents/{key}/archivo`

Recibir Documento

| Parámetro | En | Tipo | Obligatorio | Validación |
|---|---|---|---|---|
| `key` | ruta | texto | sí | — |

Respuestas documentadas: 200 OK, 422 Datos no válidos. Errores comunes: 401 sin sesión, 404 no existe, 409 estado no permite la acción, 422 datos no válidos, 503 servicio externo ocupado.

### POST `/api/surveys/documents/{key}/formulario`

Crear Formulario

| Parámetro | En | Tipo | Obligatorio | Validación |
|---|---|---|---|---|
| `key` | ruta | texto | sí | — |

Respuestas documentadas: 200 OK, 422 Datos no válidos. Errores comunes: 401 sin sesión, 404 no existe, 409 estado no permite la acción, 422 datos no válidos, 503 servicio externo ocupado.

### POST `/api/surveys/documents/{key}/leer`

Leer Paginas

| Parámetro | En | Tipo | Obligatorio | Validación |
|---|---|---|---|---|
| `key` | ruta | texto | sí | — |

Solicitud (`application/json`):

| Campo | Tipo | Obligatorio | Validación |
|---|---|---|---|
| `desde` | entero | sí | mín. 1.0 |
| `hasta` | entero | sí | mín. 1.0 |
| `parte` | entero o nulo | no | mín. 1.0; máx. 4.0 |
| `de` | entero o nulo | no | — |

Respuestas documentadas: 200 OK, 422 Datos no válidos. Errores comunes: 401 sin sesión, 404 no existe, 409 estado no permite la acción, 422 datos no válidos, 503 servicio externo ocupado.

### POST `/api/surveys/documents/{key}/preparar`

Preparar Documento

| Parámetro | En | Tipo | Obligatorio | Validación |
|---|---|---|---|---|
| `key` | ruta | texto | sí | — |

Respuestas documentadas: 200 OK, 422 Datos no válidos. Errores comunes: 401 sin sesión, 404 no existe, 409 estado no permite la acción, 422 datos no válidos, 503 servicio externo ocupado.

### GET `/api/surveys/interviews`

Interviews

Respuestas documentadas: 200 OK. Errores comunes: 401 sin sesión, 404 no existe, 409 estado no permite la acción, 422 datos no válidos, 503 servicio externo ocupado.

### POST `/api/surveys/interviews`

Create Interview

Solicitud (`application/json`):

| Campo | Tipo | Obligatorio | Validación |
|---|---|---|---|
| `template_id` | texto | sí | — |
| `nombre` | texto | no | máx. caracteres 150; por defecto '' |

Respuestas documentadas: 200 OK, 422 Datos no válidos. Errores comunes: 401 sin sesión, 404 no existe, 409 estado no permite la acción, 422 datos no válidos, 503 servicio externo ocupado.

### GET `/api/surveys/interviews/{key}`

Get Interview

| Parámetro | En | Tipo | Obligatorio | Validación |
|---|---|---|---|---|
| `key` | ruta | texto | sí | — |

Respuestas documentadas: 200 OK, 422 Datos no válidos. Errores comunes: 401 sin sesión, 404 no existe, 409 estado no permite la acción, 422 datos no válidos, 503 servicio externo ocupado.

### PATCH `/api/surveys/interviews/{key}`

Save Interview

| Parámetro | En | Tipo | Obligatorio | Validación |
|---|---|---|---|---|
| `key` | ruta | texto | sí | — |

Solicitud (`application/json`):

| Campo | Tipo | Obligatorio | Validación |
|---|---|---|---|
| `responses` | objeto | sí | — |
| `revision` | entero | sí | mín. 1.0 |

Respuestas documentadas: 200 OK, 422 Datos no válidos. Errores comunes: 401 sin sesión, 404 no existe, 409 estado no permite la acción, 422 datos no válidos, 503 servicio externo ocupado.

### PATCH `/api/surveys/interviews/{key}/encuestador`

Elegir Encuestador

| Parámetro | En | Tipo | Obligatorio | Validación |
|---|---|---|---|---|
| `key` | ruta | texto | sí | — |

Solicitud (`application/json`):

| Campo | Tipo | Obligatorio | Validación |
|---|---|---|---|
| `hablante` | texto | sí | mín. caracteres 1; máx. caracteres 100 |

Respuestas documentadas: 200 OK, 422 Datos no válidos. Errores comunes: 401 sin sesión, 404 no existe, 409 estado no permite la acción, 422 datos no válidos, 503 servicio externo ocupado.

### PATCH `/api/surveys/interviews/{key}/findings/{finding_id}`

Review

| Parámetro | En | Tipo | Obligatorio | Validación |
|---|---|---|---|---|
| `key` | ruta | texto | sí | — |
| `finding_id` | ruta | texto | sí | — |

Solicitud (`application/json`):

| Campo | Tipo | Obligatorio | Validación |
|---|---|---|---|
| `estado` | texto | sí | — |
| `justificacion` | texto | sí | mín. caracteres 3; máx. caracteres 1000 |

Respuestas documentadas: 200 OK, 422 Datos no válidos. Errores comunes: 401 sin sesión, 404 no existe, 409 estado no permite la acción, 422 datos no válidos, 503 servicio externo ocupado.

### POST `/api/surveys/interviews/{key}/submit`

Submit Interview

| Parámetro | En | Tipo | Obligatorio | Validación |
|---|---|---|---|---|
| `key` | ruta | texto | sí | — |

Respuestas documentadas: 200 OK, 422 Datos no válidos. Errores comunes: 401 sin sesión, 404 no existe, 409 estado no permite la acción, 422 datos no válidos, 503 servicio externo ocupado.

### POST `/api/surveys/interviews/{key}/transcripts`

Transcript

| Parámetro | En | Tipo | Obligatorio | Validación |
|---|---|---|---|---|
| `key` | ruta | texto | sí | — |

Solicitud (`application/json`):

| Campo | Tipo | Obligatorio | Validación |
|---|---|---|---|
| `consent` | sí/no | sí | — |
| `entrevista_codigo` | texto | sí | — |
| `datos` | objeto | sí | — |
| `archivo` | nulo o texto | no | máx. caracteres 300 |

Respuestas documentadas: 200 OK, 422 Datos no válidos. Errores comunes: 401 sin sesión, 404 no existe, 409 estado no permite la acción, 422 datos no válidos, 503 servicio externo ocupado.

### POST `/api/surveys/interviews/{key}/verificacion`

Preparar Verificacion

| Parámetro | En | Tipo | Obligatorio | Validación |
|---|---|---|---|---|
| `key` | ruta | texto | sí | — |

Respuestas documentadas: 200 OK, 422 Datos no válidos. Errores comunes: 401 sin sesión, 404 no existe, 409 estado no permite la acción, 422 datos no válidos, 503 servicio externo ocupado.

### POST `/api/surveys/interviews/{key}/verificacion/{n}`

Verificar Lote

| Parámetro | En | Tipo | Obligatorio | Validación |
|---|---|---|---|---|
| `key` | ruta | texto | sí | — |
| `n` | ruta | entero | sí | — |

Respuestas documentadas: 200 OK, 422 Datos no válidos. Errores comunes: 401 sin sesión, 404 no existe, 409 estado no permite la acción, 422 datos no válidos, 503 servicio externo ocupado.

### GET `/api/surveys/templates`

Templates

Respuestas documentadas: 200 OK. Errores comunes: 401 sin sesión, 404 no existe, 409 estado no permite la acción, 422 datos no válidos, 503 servicio externo ocupado.

### POST `/api/surveys/templates`

Create Template

Solicitud (`application/json`):

| Campo | Tipo | Obligatorio | Validación |
|---|---|---|---|
| `schema_data` | objeto | sí | — |
| `revision` | entero o nulo | no | — |

Respuestas documentadas: 200 OK, 422 Datos no válidos. Errores comunes: 401 sin sesión, 404 no existe, 409 estado no permite la acción, 422 datos no válidos, 503 servicio externo ocupado.

### DELETE `/api/surveys/templates/{key}`

Borrar Formulario

| Parámetro | En | Tipo | Obligatorio | Validación |
|---|---|---|---|---|
| `key` | ruta | texto | sí | — |

Respuestas documentadas: 200 OK, 422 Datos no válidos. Errores comunes: 401 sin sesión, 404 no existe, 409 estado no permite la acción, 422 datos no válidos, 503 servicio externo ocupado.

### GET `/api/surveys/templates/{key}`

Template

| Parámetro | En | Tipo | Obligatorio | Validación |
|---|---|---|---|---|
| `key` | ruta | texto | sí | — |

Respuestas documentadas: 200 OK, 422 Datos no válidos. Errores comunes: 401 sin sesión, 404 no existe, 409 estado no permite la acción, 422 datos no válidos, 503 servicio externo ocupado.

### PATCH `/api/surveys/templates/{key}`

Edit Template

| Parámetro | En | Tipo | Obligatorio | Validación |
|---|---|---|---|---|
| `key` | ruta | texto | sí | — |

Solicitud (`application/json`):

| Campo | Tipo | Obligatorio | Validación |
|---|---|---|---|
| `schema_data` | objeto | sí | — |
| `revision` | entero o nulo | no | — |

Respuestas documentadas: 200 OK, 422 Datos no válidos. Errores comunes: 401 sin sesión, 404 no existe, 409 estado no permite la acción, 422 datos no válidos, 503 servicio externo ocupado.

### POST `/api/surveys/templates/{key}/publish`

Publish

| Parámetro | En | Tipo | Obligatorio | Validación |
|---|---|---|---|---|
| `key` | ruta | texto | sí | — |

Respuestas documentadas: 200 OK, 422 Datos no válidos. Errores comunes: 401 sin sesión, 404 no existe, 409 estado no permite la acción, 422 datos no válidos, 503 servicio externo ocupado.

## Quality Improvement

| Método | Ruta | Función |
|---|---|---|
| GET | `/api/improvement/institutions` | Instituciones |
| GET | `/api/improvement/manuals` | Manuales |
| POST | `/api/improvement/manuals` | Crear Manual |
| DELETE | `/api/improvement/manuals/{key}` | Borrar Manual |
| GET | `/api/improvement/manuals/{key}` | Manual |
| PATCH | `/api/improvement/manuals/{key}` | Editar Manual |
| POST | `/api/improvement/manuals/{key}/finalize` | Finalizar Manual |
| GET | `/api/improvement/manuals/{key}/pdf` | Manual Pdf |
| GET | `/api/improvement/recommendations` | Recomendaciones |
| PATCH | `/api/improvement/recommendations/{key}` | Editar Recomendacion |
| POST | `/api/improvement/recommendations/{key}/approve` | Aprobar Recomendacion |
| POST | `/api/improvement/recommendations/{key}/discard` | Descartar Recomendacion |
| POST | `/api/improvement/reports` | Recibir Reporte |

### GET `/api/improvement/institutions`

Instituciones

Respuestas documentadas: 200 OK. Errores comunes: 401 sin sesión, 404 no existe, 409 estado no permite la acción, 422 datos no válidos, 503 servicio externo ocupado.

### GET `/api/improvement/manuals`

Manuales

| Parámetro | En | Tipo | Obligatorio | Validación |
|---|---|---|---|---|
| `institucion` | consulta | nulo o texto | no | — |

Respuestas documentadas: 200 OK, 422 Datos no válidos. Errores comunes: 401 sin sesión, 404 no existe, 409 estado no permite la acción, 422 datos no válidos, 503 servicio externo ocupado.

### POST `/api/improvement/manuals`

Crear Manual

Solicitud (`application/json`):

| Campo | Tipo | Obligatorio | Validación |
|---|---|---|---|
| `institucion` | texto | sí | — |
| `recomendaciones` | lista de texto o nulo | no | — |

Respuestas documentadas: 200 OK, 422 Datos no válidos. Errores comunes: 401 sin sesión, 404 no existe, 409 estado no permite la acción, 422 datos no válidos, 503 servicio externo ocupado.

### DELETE `/api/improvement/manuals/{key}`

Borrar Manual

| Parámetro | En | Tipo | Obligatorio | Validación |
|---|---|---|---|---|
| `key` | ruta | texto | sí | — |

Respuestas documentadas: 200 OK, 422 Datos no válidos. Errores comunes: 401 sin sesión, 404 no existe, 409 estado no permite la acción, 422 datos no válidos, 503 servicio externo ocupado.

### GET `/api/improvement/manuals/{key}`

Manual

| Parámetro | En | Tipo | Obligatorio | Validación |
|---|---|---|---|---|
| `key` | ruta | texto | sí | — |

Respuestas documentadas: 200 OK, 422 Datos no válidos. Errores comunes: 401 sin sesión, 404 no existe, 409 estado no permite la acción, 422 datos no válidos, 503 servicio externo ocupado.

### PATCH `/api/improvement/manuals/{key}`

Editar Manual

| Parámetro | En | Tipo | Obligatorio | Validación |
|---|---|---|---|---|
| `key` | ruta | texto | sí | — |

Solicitud (`application/json`):

| Campo | Tipo | Obligatorio | Validación |
|---|---|---|---|
| `titulo` | texto | sí | mín. caracteres 3; máx. caracteres 200 |
| `institucion_nombre` | texto | sí | mín. caracteres 2; máx. caracteres 200 |
| `introduccion` | texto | sí | mín. caracteres 3; máx. caracteres 6000 |
| `cierre` | texto | no | máx. caracteres 4000; por defecto '' |
| `secciones` | lista de objeto | sí | — |

Respuestas documentadas: 200 OK, 422 Datos no válidos. Errores comunes: 401 sin sesión, 404 no existe, 409 estado no permite la acción, 422 datos no válidos, 503 servicio externo ocupado.

### POST `/api/improvement/manuals/{key}/finalize`

Finalizar Manual

| Parámetro | En | Tipo | Obligatorio | Validación |
|---|---|---|---|---|
| `key` | ruta | texto | sí | — |

Solicitud (`application/json`):

| Campo | Tipo | Obligatorio | Validación |
|---|---|---|---|
| `cargo` | texto | sí | mín. caracteres 2; máx. caracteres 150 |

Respuestas documentadas: 200 OK, 422 Datos no válidos. Errores comunes: 401 sin sesión, 404 no existe, 409 estado no permite la acción, 422 datos no válidos, 503 servicio externo ocupado.

### GET `/api/improvement/manuals/{key}/pdf`

Manual Pdf

| Parámetro | En | Tipo | Obligatorio | Validación |
|---|---|---|---|---|
| `key` | ruta | texto | sí | — |
| `descargar` | consulta | sí/no | no | por defecto False |

Respuestas documentadas: 200 OK, 422 Datos no válidos. Errores comunes: 401 sin sesión, 404 no existe, 409 estado no permite la acción, 422 datos no válidos, 503 servicio externo ocupado.

### GET `/api/improvement/recommendations`

Recomendaciones

| Parámetro | En | Tipo | Obligatorio | Validación |
|---|---|---|---|---|
| `institucion` | consulta | nulo o texto | no | — |

Respuestas documentadas: 200 OK, 422 Datos no válidos. Errores comunes: 401 sin sesión, 404 no existe, 409 estado no permite la acción, 422 datos no válidos, 503 servicio externo ocupado.

### PATCH `/api/improvement/recommendations/{key}`

Editar Recomendacion

| Parámetro | En | Tipo | Obligatorio | Validación |
|---|---|---|---|---|
| `key` | ruta | texto | sí | — |

Solicitud (`application/json`):

| Campo | Tipo | Obligatorio | Validación |
|---|---|---|---|
| `titulo` | texto | sí | mín. caracteres 3; máx. caracteres 200 |
| `que_ocurrio` | texto | sí | mín. caracteres 3; máx. caracteres 4000 |
| `por_que` | texto | sí | mín. caracteres 3; máx. caracteres 4000 |
| `como_corregir` | texto | sí | mín. caracteres 3; máx. caracteres 4000 |
| `como_prevenir` | texto | sí | mín. caracteres 3; máx. caracteres 4000 |
| `acciones` | lista de texto | sí | — |

Respuestas documentadas: 200 OK, 422 Datos no válidos. Errores comunes: 401 sin sesión, 404 no existe, 409 estado no permite la acción, 422 datos no válidos, 503 servicio externo ocupado.

### POST `/api/improvement/recommendations/{key}/approve`

Aprobar Recomendacion

| Parámetro | En | Tipo | Obligatorio | Validación |
|---|---|---|---|---|
| `key` | ruta | texto | sí | — |

Solicitud (`application/json`):

| Campo | Tipo | Obligatorio | Validación |
|---|---|---|---|
| `cargo` | texto | sí | mín. caracteres 2; máx. caracteres 150 |

Respuestas documentadas: 200 OK, 422 Datos no válidos. Errores comunes: 401 sin sesión, 404 no existe, 409 estado no permite la acción, 422 datos no válidos, 503 servicio externo ocupado.

### POST `/api/improvement/recommendations/{key}/discard`

Descartar Recomendacion

| Parámetro | En | Tipo | Obligatorio | Validación |
|---|---|---|---|---|
| `key` | ruta | texto | sí | — |

Respuestas documentadas: 200 OK, 422 Datos no válidos. Errores comunes: 401 sin sesión, 404 no existe, 409 estado no permite la acción, 422 datos no válidos, 503 servicio externo ocupado.

### POST `/api/improvement/reports`

Recibir Reporte

Solicitud (`application/json`):

| Campo | Tipo | Obligatorio | Validación |
|---|---|---|---|
| `report` | objeto | sí | — |
| `institucion` | nulo o texto | no | — |
| `archivo` | nulo o texto | no | máx. caracteres 300 |

Respuestas documentadas: 200 OK, 422 Datos no válidos. Errores comunes: 401 sin sesión, 404 no existe, 409 estado no permite la acción, 422 datos no válidos, 503 servicio externo ocupado.

## Audio Audit y plataforma

| Método | Ruta | Función |
|---|---|---|
| GET | `/api/calibration` | Get Calibration Endpoint |
| POST | `/api/calibration/fit` | Fit Calibration Endpoint |
| GET | `/api/extensions/status` | Status |
| GET | `/api/jobs` | List Recent Jobs |
| GET | `/api/jobs/{job_id}` | Get Job Status |
| GET | `/api/jobs/{job_id}/audio` | Get Job Audio |
| GET | `/api/jobs/{job_id}/download` | Download Transcript Txt |
| POST | `/api/jobs/{job_id}/evaluate` | Run JEV evaluation synchronously in-request so Vercel serverless never freezes background threads. |
| GET | `/api/jobs/{job_id}/evaluation/download` | Download Evaluation Json |
| PATCH | `/api/jobs/{job_id}/evaluation/rules/{rule_id}` | Edit an evaluation row on the current interview AND optionally rewrite the global rule for future transcripts. |
| GET | `/api/rules` | List Jev Rules |
| PUT | `/api/rules/{rule_id}` | Update Global Jev Rule |
| DELETE | `/api/rules/{rule_id}/override` | Reset Global Jev Rule |
| GET | `/api/salud` | Salud |
| GET | `/api/sesion` | Sesion |
| GET | `/api/status` | System Status |
| POST | `/api/storage/upload-url` | Create Direct Upload Url |
| POST | `/api/transcribe` | Create Transcription Job |
| POST | `/api/transcribe/cloud` | Start Spanish transcription + speaker diarization from an audio file already uploaded to Supabase Storage. |
| POST | `/api/transcript/example` | Load Example Encovi Transcript |
| POST | `/api/transcript/upload` | Upload Existing Transcript |

### GET `/api/calibration`

Get Calibration Endpoint

Respuestas documentadas: 200 OK. Errores comunes: 401 sin sesión, 404 no existe, 409 estado no permite la acción, 422 datos no válidos, 503 servicio externo ocupado.

### POST `/api/calibration/fit`

Fit Calibration Endpoint

Solicitud (`application/json`):

Cuerpo: nulo o objeto.

Respuestas documentadas: 200 OK, 422 Datos no válidos. Errores comunes: 401 sin sesión, 404 no existe, 409 estado no permite la acción, 422 datos no válidos, 503 servicio externo ocupado.

### GET `/api/extensions/status`

Status

Respuestas documentadas: 200 OK. Errores comunes: 401 sin sesión, 404 no existe, 409 estado no permite la acción, 422 datos no válidos, 503 servicio externo ocupado.

### GET `/api/jobs`

List Recent Jobs

| Parámetro | En | Tipo | Obligatorio | Validación |
|---|---|---|---|---|
| `limit` | consulta | entero | no | por defecto 20 |

Respuestas documentadas: 200 OK, 422 Datos no válidos. Errores comunes: 401 sin sesión, 404 no existe, 409 estado no permite la acción, 422 datos no válidos, 503 servicio externo ocupado.

### GET `/api/jobs/{job_id}`

Get Job Status

| Parámetro | En | Tipo | Obligatorio | Validación |
|---|---|---|---|---|
| `job_id` | ruta | texto | sí | — |

Respuestas documentadas: 200 OK, 422 Datos no válidos. Errores comunes: 401 sin sesión, 404 no existe, 409 estado no permite la acción, 422 datos no válidos, 503 servicio externo ocupado.

### GET `/api/jobs/{job_id}/audio`

Get Job Audio

| Parámetro | En | Tipo | Obligatorio | Validación |
|---|---|---|---|---|
| `job_id` | ruta | texto | sí | — |

Respuestas documentadas: 200 OK, 422 Datos no válidos. Errores comunes: 401 sin sesión, 404 no existe, 409 estado no permite la acción, 422 datos no válidos, 503 servicio externo ocupado.

### GET `/api/jobs/{job_id}/download`

Download Transcript Txt

| Parámetro | En | Tipo | Obligatorio | Validación |
|---|---|---|---|---|
| `job_id` | ruta | texto | sí | — |

Respuestas documentadas: 200 OK, 422 Datos no válidos. Errores comunes: 401 sin sesión, 404 no existe, 409 estado no permite la acción, 422 datos no válidos, 503 servicio externo ocupado.

### POST `/api/jobs/{job_id}/evaluate`

Run JEV evaluation synchronously in-request so Vercel serverless never freezes background threads.

| Parámetro | En | Tipo | Obligatorio | Validación |
|---|---|---|---|---|
| `job_id` | ruta | texto | sí | — |

Solicitud (`application/json`):

| Campo | Tipo | Obligatorio | Validación |
|---|---|---|---|
| `speaker_map` | objeto | no | — |
| `first_contact` | sí/no | no | por defecto True |
| `mock` | sí/no | no | por defecto False |

Respuestas documentadas: 200 OK, 422 Datos no válidos. Errores comunes: 401 sin sesión, 404 no existe, 409 estado no permite la acción, 422 datos no válidos, 503 servicio externo ocupado.

### GET `/api/jobs/{job_id}/evaluation/download`

Download Evaluation Json

| Parámetro | En | Tipo | Obligatorio | Validación |
|---|---|---|---|---|
| `job_id` | ruta | texto | sí | — |

Respuestas documentadas: 200 OK, 422 Datos no válidos. Errores comunes: 401 sin sesión, 404 no existe, 409 estado no permite la acción, 422 datos no válidos, 503 servicio externo ocupado.

### PATCH `/api/jobs/{job_id}/evaluation/rules/{rule_id}`

Edit an evaluation row on the current interview AND optionally rewrite the global rule for future transcripts.

| Parámetro | En | Tipo | Obligatorio | Validación |
|---|---|---|---|---|
| `job_id` | ruta | texto | sí | — |
| `rule_id` | ruta | texto | sí | — |

Solicitud (`application/json`):

| Campo | Tipo | Obligatorio | Validación |
|---|---|---|---|
| `override_status` | texto | no | por defecto 'keep' |
| `custom_probs` | nulo o objeto | no | — |
| `auditor_comment` | nulo o texto | no | máx. caracteres 2000 |
| `window_index` | entero o nulo | no | — |
| `update_future_rule` | sí/no | no | por defecto False |
| `rule_override` | nulo o objeto | no | — |

Respuestas documentadas: 200 OK, 422 Datos no válidos. Errores comunes: 401 sin sesión, 404 no existe, 409 estado no permite la acción, 422 datos no válidos, 503 servicio externo ocupado.

### GET `/api/rules`

List Jev Rules

Respuestas documentadas: 200 OK. Errores comunes: 401 sin sesión, 404 no existe, 409 estado no permite la acción, 422 datos no válidos, 503 servicio externo ocupado.

### PUT `/api/rules/{rule_id}`

Update Global Jev Rule

| Parámetro | En | Tipo | Obligatorio | Validación |
|---|---|---|---|---|
| `rule_id` | ruta | texto | sí | — |

Solicitud (`application/json`):

| Campo | Tipo | Obligatorio | Validación |
|---|---|---|---|
| `custom_text` | nulo o texto | no | máx. caracteres 2000 |
| `weight` | entero o nulo | no | mín. 1.0; máx. 3.0 |
| `enabled` | sí/no | no | por defecto True |
| `auditor_guidance` | nulo o texto | no | máx. caracteres 2000 |
| `questions_override` | objeto | no | — |

Respuestas documentadas: 200 OK, 422 Datos no válidos. Errores comunes: 401 sin sesión, 404 no existe, 409 estado no permite la acción, 422 datos no válidos, 503 servicio externo ocupado.

### DELETE `/api/rules/{rule_id}/override`

Reset Global Jev Rule

| Parámetro | En | Tipo | Obligatorio | Validación |
|---|---|---|---|---|
| `rule_id` | ruta | texto | sí | — |

Respuestas documentadas: 200 OK, 422 Datos no válidos. Errores comunes: 401 sin sesión, 404 no existe, 409 estado no permite la acción, 422 datos no válidos, 503 servicio externo ocupado.

### GET `/api/salud`

Salud

Respuestas documentadas: 200 OK. Errores comunes: 401 sin sesión, 404 no existe, 409 estado no permite la acción, 422 datos no válidos, 503 servicio externo ocupado.

### GET `/api/sesion`

Sesion

Respuestas documentadas: 200 OK. Errores comunes: 401 sin sesión, 404 no existe, 409 estado no permite la acción, 422 datos no válidos, 503 servicio externo ocupado.

### GET `/api/status`

System Status

Respuestas documentadas: 200 OK. Errores comunes: 401 sin sesión, 404 no existe, 409 estado no permite la acción, 422 datos no válidos, 503 servicio externo ocupado.

### POST `/api/storage/upload-url`

Create Direct Upload Url

Solicitud (`application/json`):

| Campo | Tipo | Obligatorio | Validación |
|---|---|---|---|
| `filename` | texto | sí | — |
| `content_type` | texto | no | por defecto 'audio/mpeg' |

Respuestas documentadas: 200 OK, 422 Datos no válidos. Errores comunes: 401 sin sesión, 404 no existe, 409 estado no permite la acción, 422 datos no válidos, 503 servicio externo ocupado.

### POST `/api/transcribe`

Create Transcription Job

Solicitud (`multipart/form-data`):

| Campo | Tipo | Obligatorio | Validación |
|---|---|---|---|
| `file` | texto | sí | — |
| `provider` | texto | no | por defecto 'auto' |
| `model` | texto | no | por defecto 'large-v3-turbo' |
| `denoise` | sí/no | no | por defecto True |
| `diarize` | sí/no | no | por defecto True |
| `min_speakers` | entero o nulo | no | — |
| `max_speakers` | entero o nulo | no | — |

Respuestas documentadas: 200 OK, 422 Datos no válidos. Errores comunes: 401 sin sesión, 404 no existe, 409 estado no permite la acción, 422 datos no válidos, 503 servicio externo ocupado.

### POST `/api/transcribe/cloud`

Start Spanish transcription + speaker diarization from an audio file already uploaded to Supabase Storage.

Solicitud (`application/json`):

| Campo | Tipo | Obligatorio | Validación |
|---|---|---|---|
| `job_id` | nulo o texto | no | — |
| `filename` | texto | sí | — |
| `storage_path` | texto | sí | — |
| `content_type` | texto | no | por defecto 'audio/mpeg' |
| `provider` | texto | no | por defecto 'assemblyai' |
| `diarize` | sí/no | no | por defecto True |
| `min_speakers` | entero o nulo | no | — |
| `max_speakers` | entero o nulo | no | — |

Respuestas documentadas: 200 OK, 422 Datos no válidos. Errores comunes: 401 sin sesión, 404 no existe, 409 estado no permite la acción, 422 datos no válidos, 503 servicio externo ocupado.

### POST `/api/transcript/example`

Load Example Encovi Transcript

Respuestas documentadas: 200 OK. Errores comunes: 401 sin sesión, 404 no existe, 409 estado no permite la acción, 422 datos no válidos, 503 servicio externo ocupado.

### POST `/api/transcript/upload`

Upload Existing Transcript

Solicitud (`multipart/form-data`):

| Campo | Tipo | Obligatorio | Validación |
|---|---|---|---|
| `file` | texto | sí | — |

Respuestas documentadas: 200 OK, 422 Datos no válidos. Errores comunes: 401 sin sesión, 404 no existe, 409 estado no permite la acción, 422 datos no válidos, 503 servicio externo ocupado.
