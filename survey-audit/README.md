# Survey Audit

Convierte el cuestionario en PDF de cualquier encuesta en un formulario digital, registra las entrevistas y las verifica contra la transcripción de Audio Audit.

## Flujo

1. **Nueva entrevista:** se escribe el *Nombre de la entrevista* y se sube la *Entrevista en PDF* (hasta 50 MB). «Generar formulario de entrevista» lee el PDF por bloques de páginas con Claude (lee el texto y la imagen de cada página, por lo que también sirve para PDF escaneados) y extrae secciones, preguntas, códigos, opciones de respuesta, instrucciones y pases o saltos. Un cuestionario como ENCOVI 2023 (72 páginas) toma varios minutos; la lectura se puede detener y continuar.
2. **Revisión:** antes de finalizar se pueden corregir textos, códigos, tipo de respuesta, opciones, saltos y rangos. Las preguntas con dudas (por ejemplo, un pase a una pregunta que no existe) quedan marcadas y bloquean la finalización hasta revisarlas.
3. **Entrevistas:** cada entrevista recibe un código único (`ENT-0001`) junto a su nombre. Las respuestas se capturan en el formulario digital; las secciones por persona se repiten según el número de personas del hogar y los saltos ocultan las preguntas que no aplican. Al finalizar se valida todo y se muestran los errores en lenguaje claro.
4. **Vincular transcripción de la entrevista:** se sube el JSON descargado de Audio Audit («Descargar JSON»), se confirma la autorización de uso y se elige qué hablante es el encuestador. La transcripción queda ligada solo a esa entrevista: la misma grabación no se puede vincular a otra.
5. **Validar contra la grabación:** Claude asocia cada pregunta con los turnos de la transcripción (con sus tiempos como evidencia) y clasifica cada respuesta como *coincide*, *no coincide* o *no verificable*. Las respuestas oficiales son siempre las del formulario; la persona revisora confirma o descarta cada resultado con una justificación.

## Código

- Validación declarativa (esquemas v1 y v2, saltos y secciones por persona): `backend/survey_audit/validation.py`.
- Lectura del PDF y armado del formulario: `interfaz/backend/extensions/cuestionario.py`; llamadas a Claude: `extensions/ia.py`; API: `extensions/api.py` (`/api/surveys/*`).
- Interfaz: `interfaz/src/survey.ts`.
- `templates/pilot.synthetic.json` solo se usa en las pruebas de validación.

## Configuración

- `ANTHROPIC_API_KEY` (secreta): necesaria para generar formularios y para la verificación.
- Opcionales: `SURVEY_IA_MODELO` (por defecto `claude-sonnet-5-5`), `SURVEY_PAGINAS_BLOQUE` (páginas por petición, 2 por defecto), `SURVEY_STORAGE_BUCKET` (por defecto `encuestas`; se crea solo si no existe).
