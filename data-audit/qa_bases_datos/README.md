# QA de bases de datos — Quality Audit

Motor de auditoría de calidad para las bases que las instituciones envían al INE
(RENAP, PNC, INSIVUMEH, SECONRED). Revisa estructura, completitud, validez,
consistencia, unicidad y oportunidad; corrige lo que se puede corregir sin cambiar
el significado y deja el resto como sugerencias para que un analista las apruebe.

- `schema.sql`: esquema PostgreSQL (19 tablas).
- `backend/`: configuración, motor, scripts y documentación completa en `backend/README.md`.
- `DOCUMENTACION.md`: documentación técnica (arquitectura, decisiones, flujo, API, costos, escalabilidad y seguridad).

Los crudos y diccionarios del INE no se suben al repositorio (ver `.gitignore`).
