# Quality Improvement

Convierte los hallazgos de Data Audit en recomendaciones y en un manual institucional en PDF.

## Flujo

1. **Subir reporte de Data Audit:** se importa manualmente el `reporte.json` descargado de Data Audit. Los hallazgos se agrupan por institución, base, período y regla; volver a subir el mismo período actualiza la evidencia sin duplicar recomendaciones.
2. **Recomendaciones:** cada grupo explica qué ocurrió, por qué es un problema, cómo corregirlo y cómo prevenirlo, con acciones concretas y la evidencia (columnas, casos, porcentaje y filas). Las explicaciones parten de `templates/reglas.json` y, si hay `ANTHROPIC_API_KEY`, Claude las ajusta a cada caso. Se pueden editar, aprobar indicando el cargo o descartar; cada cambio queda en el historial.
3. **Manual institucional:** reúne las recomendaciones aprobadas de una institución. Antes de finalizarlo se puede editar el título, el nombre de la institución a la que va dirigido, la presentación, cada recomendación y el cierre. Se ve y descarga en PDF; al finalizarlo (con el cargo de quien lo aprueba) ya no se puede modificar.

## Código

- Instituciones y bases: `templates/institutions.json`; explicaciones por regla: `templates/reglas.json`.
- API (`/api/improvement/*`): `interfaz/backend/extensions/improvement.py`; PDF: `extensions/manual_pdf.py` (fuentes DejaVu incluidas).
- Interfaz: `interfaz/src/improvement.ts`.

## Configuración

- `ANTHROPIC_API_KEY` (secreta, opcional): mejora la redacción. Sin ella se usan las explicaciones estándar de cada regla.
- Opcionales: `MEJORA_IA_MODELO` (por defecto `claude-haiku-5-5`) y `MEJORA_IA=0` para no usar IA.
