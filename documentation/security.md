# Seguridad, confidencialidad y gobernanza

## Controles descritos y límites

Audio Audit arranca por defecto en loopback (127.0.0.1) y realiza inferencia local según el código revisado. Los modelos se descargan inicialmente y se usa un token para el acceso a Pyannote. No se ha auditado el tráfico de red de dependencias ni se ha verificado ausencia de telemetría. No exponer el servidor en una red pública: no se ha comprobado autenticación de sus endpoints. Los audios se guardan en `uploads/`; la limpieza de trabajos terminados es limitada y la cola está en memoria. Revisar y eliminar archivos de prueba conforme a la política aplicable, también después de reiniciar.

Data Audit documenta exclusión de columnas PII identificadas de la salida corregida. Esto no equivale a anonimización garantizada: revisar campos libres, originales, bitácoras, JSON, tablas y posibles identificadores indirectos. El archivo `original.*` puede contener datos personales y requiere acceso restringido.

## Repositorio

Conservar los `.gitignore` de raíz y de `data-audit/qa_bases_datos/`. Antes de subir archivos verificar que las reglas sigan funcionando tras la reorganización; especialmente patrones anclados a rutas antiguas. Excluir archivos `.env` con credenciales, `.venv/`, modelos locales, audios, crudos, diccionarios restringidos y salidas sensibles. Mantener `.env.example` sin secretos. `.gitignore` no elimina archivos ya rastreados ni los protege en el historial.

Usar un repositorio privado mientras se revisa la autorización de publicación y facilitar acceso al jurado conforme a los lineamientos. No incluir secretos en commits, capturas o video; revocar credenciales si se exponen. Verificar versiones y licencias de software y modelos, y los términos de propiedad intelectual de la competencia antes de declarar una licencia del proyecto.

## Recomendaciones pendientes de implementación o verificación

Aplicar mínimo privilegio en PostgreSQL, almacenamiento protegido, políticas de retención y borrado, control de acceso, trazabilidad de aprobación y revisión humana. Usar exclusivamente datos de demostración autorizados o sintéticos. Las correcciones deben ser trazables; no imputar ni cambiar significado sin justificación. No se afirma cumplimiento normativo certificado ni auditoría de seguridad completada.
