# Seguridad, confidencialidad y secreto estadístico

Quality Audit maneja bases con datos personales, grabaciones de entrevistas y respuestas de hogares. Este documento describe qué protege el sistema hoy, qué no, y qué riesgos quedan con su mitigación. No se afirma cumplimiento normativo certificado ni una auditoría de seguridad externa.

## 1. Marco normativo

- **Secreto estadístico.** La Ley Orgánica del INE, **Decreto Ley 3-85, artículo 25, según la referencia documental oficial** del Datatón, establece la confidencialidad de la información individual que recibe el INE con fines estadísticos. El sistema se diseñó para que ningún resultado publicable permita identificar a una persona, hogar o empresa, y para que la información individual solo la vea personal autorizado.
- **Protección de datos personales.** Se aplican los principios de minimización (solo se procesa lo necesario), finalidad (uso exclusivamente estadístico y de control de calidad) y trazabilidad (cada acción queda registrada).
- **Condiciones del Datatón.** Se usaron datos proporcionados por el INE solo en las computadoras del equipo y datos sintéticos para todo lo que se publica o se muestra.

## 2. Datos que maneja cada módulo

| Módulo | Dato sensible | Dónde se guarda | Quién lo ve |
|---|---|---|---|
| Data Audit | Archivo original de la institución (nombres, CUI, direcciones…) | Bucket privado `qa-cargas` (o disco local sin Supabase) | Usuarios autenticados, con descarga registrada |
| Data Audit | Base corregida | Mismo bucket | Sin columnas de datos personales |
| Audio Audit | Grabación y transcripción de la entrevista | Bucket privado `audio-interviews` y tabla `audio_jobs` | Usuarios autenticados |
| Survey Audit | Respuestas del hogar y transcripción vinculada | `quality_extensions.state` (PostgreSQL) | Usuarios autenticados |
| Survey Audit | Cuestionario PDF | Bucket privado `encuestas` | Usuarios autenticados |
| Quality Improvement | Hallazgos agregados (sin datos personales) | `quality_extensions.state` | Usuarios autenticados |

El detalle de tablas y buckets está en el [modelo de datos](modelo-datos.md).

## 3. Cómo se evita identificar personas, hogares y empresas

- **Eliminación de columnas personales.** Data Audit descarta de la base corregida las columnas identificadas como datos personales (regla `GEN_PII`). La lista se declara en la definición de cada base (`config/bases/*.yaml`, clave `pii`); en defunciones, por ejemplo, incluye CUI y nombre del fallecido y 32 columnas con datos de la madre y el padre (CUI, nombre, dirección, fecha de nacimiento…).
- **El original nunca se publica.** Se conserva solo para reprocesar y auditar; su descarga queda en `evento_auditoria` con usuario y fecha.
- **Salidas agregadas.** Bitácoras, reportes y recomendaciones de Quality Improvement trabajan con conteos y valores de catálogo, no con registros individuales. Los registros excluidos se guardan agrupados por motivo.
- **Minimización hacia la IA.** Al codificador de Data Audit solo se envían los **textos distintos** de una columna de texto libre (p. ej., «PORTACION ILEGAL DE ARMA»), nunca filas completas, nombres, CUI ni fechas; las cadenas de 6 o más dígitos se enmascaran antes de enviarse, y la columna de quien certifica no se envía.
- **Identificación de hablantes.** La diarización solo separa voces («SPEAKER_00»); no se usa biometría ni se reconoce la identidad de nadie. El rol lo asigna el auditor.
- **Ejemplos públicos sintéticos.** Capturas de pantalla y ejemplos del repositorio usan exclusivamente datos sintéticos.

**Límite:** eliminar columnas no garantiza anonimización. Campos de texto libre (descripciones de emergencias, motivos) o combinaciones raras de variables pueden permitir identificación indirecta. Antes de publicar una base, el INE debe aplicar su control de divulgación habitual.

## 4. Grabaciones y transcripciones

- **Autorización.** Survey Audit exige marcar una casilla de autorización antes de vincular una transcripción a una entrevista; sin ella el servidor rechaza el vínculo. La autorización informada del hogar para grabar debe obtenerse en campo según el protocolo del INE (el manual del encuestador lo contempla); el sistema no la sustituye.
- **Uso.** La grabación solo sirve como evidencia: la conciliación **nunca cambia** las respuestas registradas.
- **Subida directa y privada.** El audio va del navegador al bucket privado con una URL firmada; el proveedor de transcripción lo descarga con otra URL firmada válida 5 minutos.
- **Transferencia a servicios externos.** En la plataforma publicada el audio se envía a AssemblyAI (o Deepgram), la transcripción a OpenRouter/TypeSafe para la evaluación JEV y a Anthropic para la conciliación de Survey Audit. Para un uso institucional con grabaciones reales existe el **modo local** (WhisperX + Pyannote), donde el audio no sale de la computadora; la evaluación JEV y la conciliación siguen necesitando un servicio externo (ver riesgos).

## 5. Control de acceso

- **Autenticación.** En la plataforma publicada, toda ruta `/api/*` excepto `/api/salud` exige un token válido de Supabase Auth; sin sesión responde 401. El registro público está desactivado: solo entran cuentas creadas por el administrador (ver [accesos](accesos.md)).
- **Sin Supabase** (instalación local), la API **solo atiende `localhost`** y responde 403 a cualquier otro host. Si en Vercel faltara la configuración de Supabase, la API responde 503: nunca queda abierta por olvido.
- **Mismo origen.** Las operaciones de escritura solo se aceptan desde el mismo origen de la interfaz (403 «Origen no permitido» en otro caso).
- **Llaves fuera de la interfaz.** Las rutas heredadas de Audio Audit para guardar llaves desde el navegador están bloqueadas en la plataforma (403): las llaves solo se configuran en el servidor.
- **Base de datos.** Row Level Security activo en todas las tablas públicas y sin permisos para los roles del navegador (`anon`, `authenticated`); solo el servidor accede con la llave `service_role`.
- **Archivos.** Buckets privados; las descargas usan URLs firmadas de 5 minutos.
- **Cabeceras HTTP.** `X-Content-Type-Options: nosniff`, `Referrer-Policy: strict-origin-when-cross-origin`, `X-Frame-Options: DENY`. La documentación interactiva de la API está desactivada en producción.
- **No implementado:** roles diferenciados (analista, supervisor, administrador) y permisos por institución. Hoy toda cuenta autenticada accede a todos los módulos.

## 6. Credenciales

- Las llaves (`SUPABASE_SERVICE_ROLE_KEY`, `DATABASE_URL`, `ANTHROPIC_API_KEY`, `ASSEMBLYAI_API_KEY`, `OPENROUTER_API_KEY`) viven **solo** en las variables de entorno de Vercel marcadas como *Sensitive*, o en el `.env` local que Git ignora.
- Las variables `VITE_*` se incluyen en el JavaScript público; solo llevan la URL de Supabase y la llave *anon*, públicas por diseño.
- `.gitignore` excluye `.env`, `uploads/`, `almacen/`, `.local_data/`, `.jev_cache/`, `node_modules` y `dist`. Se revisó el historial completo de Git: no contiene llaves reales (solo el marcador `sk-ant-...` de un ejemplo).
- `audio-audit/tests/check_security.py` comprueba automáticamente que la API de audio rechace peticiones de otros hosts u orígenes y que respete los límites de entrada; pasa en la versión entregada.
- Las contraseñas de las cuentas del jurado se escriben en [accesos](accesos.md) **solo después** de hacer privado el repositorio.

## 7. Almacenamiento, retención y eliminación

| Elemento | Retención actual | Eliminación |
|---|---|---|
| Originales, corregidos y bitácoras de Data Audit | Hasta que el responsable los retire | Manual, desde Supabase Storage (no hay botón en la interfaz) |
| Audios y transcripciones | Hasta que el responsable los retire | Manual, desde Supabase Storage y la tabla `audio_jobs` |
| Formularios en borrador, manuales en borrador | — | Desde la interfaz (los finalizados no se borran) |
| Correcciones guardadas (equivalencias) | Permanentes | Se pueden quitar desde la interfaz; queda registrado |
| Archivos temporales de procesamiento | Duración de la petición | Automática |

**No implementado:** política de retención automática (p. ej., borrar audios a los N días). Se recomienda definirla con el INE antes de cualquier piloto.

## 8. Trazabilidad

- **Data Audit:** `evento_auditoria` registra subida, procesamiento, descarga del original, aprobación/rechazo de cada corrección (con motivo), equivalencias creadas o quitadas y la decisión final sobre la base, con usuario y fecha. `correccion` guarda valor anterior, nuevo, origen (similitud, IA, analista), confianza y estado.
- **Audio Audit:** cada edición manual de una regla queda marcada con justificación y se distingue de la evaluación automática.
- **Survey Audit:** cada entrevista tiene historial de eventos y número de revisión; cada hallazgo de conciliación guarda quién lo revisó, cuándo y por qué.
- **Quality Improvement:** cada recomendación guarda historial, generador (`reglas` o `ia`) y aprobación con nombre y cargo; los manuales son versionados.

## 9. Servicios externos y datos que reciben

| Servicio | Qué recibe | Cuándo | Alternativa local |
|---|---|---|---|
| Supabase (PostgreSQL, Storage, Auth) | Todo lo que guarda la plataforma | Siempre en la versión publicada | PostgreSQL propio y disco local |
| Vercel | Peticiones a la API (procesamiento en memoria) | Siempre en la versión publicada | Servidor propio |
| AssemblyAI / Deepgram | Audio completo | Al transcribir en la nube | WhisperX + Pyannote local |
| OpenRouter → TypeSafe JEV | Transcripción por ventanas | Al evaluar con JEV | No disponible |
| Anthropic (Claude) | Páginas del cuestionario (público); transcripción y respuestas registradas (conciliación); textos distintos enmascarados (Data Audit); hallazgos agregados (QI) | Al usar cada función | Data Audit: `QA_IA_PROVEEDOR=ollama` o `ninguno`; QI: `MEJORA_IA=0`; Survey: captura y validación funcionan sin IA |

Las condiciones de uso, retención y entrenamiento de cada proveedor dependen de sus términos comerciales vigentes; el INE debe revisarlas y, si corresponde, firmar acuerdos de tratamiento de datos antes de usar datos reales. El detalle de costos está en [IA y servicios](ia-y-servicios.md).

## 10. Riesgos y mitigaciones

| Riesgo | Impacto | Mitigación actual | Recomendación |
|---|---|---|---|
| Identificación indirecta por texto libre o combinaciones raras | Alto | Eliminación de columnas personales; salidas agregadas | Control de divulgación del INE antes de publicar |
| Grabaciones con datos personales enviadas a proveedores externos | Alto | URLs firmadas de 5 min; modo local disponible para transcribir | Usar modo local o acuerdos de tratamiento de datos |
| Conciliación de Survey envía la transcripción completa a Anthropic | Medio–alto | Solo con autorización marcada; se puede no usar | Modelo local o acuerdo de tratamiento |
| Cuentas compartidas o sin roles | Medio | Registro público desactivado; bitácora por usuario | Roles y permisos por institución |
| Fuga de llaves | Alto | Variables *Sensitive*; `.gitignore`; revisión del historial | Rotación periódica y gestor de secretos institucional |
| Archivos retenidos indefinidamente | Medio | Buckets privados | Política de retención automática |
| Error de la IA tomado como verdad | Medio | Toda sugerencia requiere aprobación humana | Calibrar con muestras etiquetadas por el INE |
| Proveedor gratuito pausado o caído | Bajo (prototipo) | Instalación local reproducible | Infraestructura institucional |
