# Fuentes de datos

## Registros administrativos

El INE compartió al equipo ejemplos de crudos de defunciones, nacimientos, hechos delictivos y estadísticas ambientales mediante comunicación del 24 de noviembre de 2026. El README del backend declara cinco bases configuradas:

| Base | Institución de origen declarada | Periodo de resultados reportado |
|---|---|---|
| Defunciones | RENAP | Julio 2026 |
| Nacimientos | RENAP | Junio 2026 |
| Detenidos | PNC | Octubre 2026 |
| Calidad del aire | INSIVUMEH | 2025 |
| Emergencias | SECONRED | 2025 |

Referencias: [Portal INE](https://www.ine.gob.gt/) y [bases de hechos delictivos](https://www.ine.gob.gt/bases-de-datos/hechos-delictivos/), enlace proporcionado por la coordinación. El README menciona diccionarios de defunciones y nacimientos 2018–2022 y un diccionario de detenidos PNC. Registrar enlaces exactos, versiones, fechas de descarga y condiciones de uso de cada base pública efectivamente usada antes de entregar. La nota conceptual exige al menos una base pública del INE; la evidencia concreta de su uso debe quedar identificada.

Los crudos y diccionarios no se suben al repositorio conforme al README del módulo. No asumir que el permiso para analizarlos equivale a autorización para distribuirlos. Preparar muestras sintéticas o expresamente autorizadas, con trazabilidad de su origen.

## Entrevistas

El INE indicó el 24 de noviembre de 2026 que no puede proporcionar audios reales debido a confidencialidad. Propuso utilizar un simulador y orientar la auditoría al filtrado y reconocimiento de la voz del encuestador y la correcta formulación de preguntas. Por ello se propone grabar entrevistas ficticias con consentimiento y sin información personal real, acompañadas de boletas de referencia y transcripciones manuales. No se afirma que se hayan generado ni evaluado 20 horas de audio.

## Fuentes internas

- Nota Conceptual Datatón INE 2026, lineamientos de categoría tecnológica.
- Comunicaciones de coordinación del INE, 23 y 24 de noviembre de 2026.
- README de Audio Audit y código `app/main.py`, `app/transcriber.py`.
- [README de Data Audit](../data-audit/qa_bases_datos/backend/README.md).
