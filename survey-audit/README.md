# Survey Audit

Contrato y validación declarativa en `backend/survey_audit`. Instrumento de demostración explícitamente sintético en `templates/pilot.synthetic.json`.

La API se registra en el backend común desde `interfaz/backend/extensions/api.py`; la interfaz utiliza `/api/surveys`. La persistencia es PostgreSQL, con almacenamiento de archivo solo en modo demo explícito.

Las respuestas históricas no aplicables se conservan y se excluyen de las respuestas activas. La conciliación compara evidencia seleccionada por un revisor sin modificar la captura original. El constructor completo y el piloto oficial ENCOVI continúan pendientes. Ver `documentation/integration-api.md`.
