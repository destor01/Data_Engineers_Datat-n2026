# Quality Improvement

Configuración institucional en `templates/institutions.json`. El router y la persistencia compartida están en `interfaz/backend/extensions/improvement.py` y `repository.py`; no hay otra aplicación ni base separada.

Consume reporte.json autorizado de Data Audit mediante `/api/improvement/reports`. No modifica el motor. Recomendaciones deterministas, fuentes identificadas, manuales versionados y descarga Markdown. Ver `documentation/integration-api.md` para iniciar todo el proyecto.
