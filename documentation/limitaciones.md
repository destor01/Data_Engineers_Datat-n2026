# Limitaciones y posibles mejoras

Cada limitación indica su impacto, cómo se mitiga hoy y qué solución se propone. Las soluciones futuras son propuestas del equipo, no compromisos del INE.

## Limitaciones

| # | Limitación | Impacto | Mitigación actual | Solución futura |
|---|---|---|---|---|
| L1 | **Disponibilidad de audios reales.** No se contó con grabaciones reales autorizadas de entrevistas. | Alto: WER, DER y la exactitud de JEV no están medidos; los puntajes de audio no están validados frente a un supervisor del INE. | Transcripciones sintéticas con errores sembrados; modo de prueba claramente marcado como simulado; edición manual de cada regla. | Muestra autorizada de 20–30 entrevistas con transcripción y evaluación humana de referencia; medir WER/DER y calibrar JEV (ya implementado en `calibration.py`). |
| L2 | **Procesamiento del lenguaje.** El ASR y JEV están ajustados para español general; no cubren idiomas mayas ni variantes rurales con vocabulario local. | Medio–alto en áreas rurales e indígenas. | Revisión humana del texto; reglas que no se pueden evaluar quedan como «sin evidencia» en lugar de incumplidas. | Probar modelos multilingües; vocabulario personalizado; reglas específicas por idioma con el área de pueblos indígenas del INE. |
| L3 | **Ruido acústico** (calle, animales, varias voces). | Medio: errores de transcripción y de separación de hablantes. | Filtro de ruido en modo local; el auditor asigna los roles y puede corregir. | Recomendaciones de grabación en campo; micrófono de solapa; medición del efecto del ruido. |
| L4 | **Complejidad del PDF.** Tablas anchas, celdas combinadas y pases gráficos (flechas) son difíciles de interpretar. | Medio: el formulario generado puede tener errores. | Tablas compactas, lectura por zonas, marcador de página no leída y revisión obligatoria antes de finalizar. | Importar directamente la definición CAPI/XLSForm del INE cuando exista; plantillas por encuesta. |
| L5 | **Precisión de OCR.** No hay motor de OCR independiente; la lectura de páginas escaneadas depende del modelo de IA. | Medio: no se ha medido la exactitud de extracción. | Revisión humana del formulario completo. | Medir contra un cuestionario digitalizado de referencia; OCR local (p. ej., Tesseract) como respaldo. |
| L6 | **Disponibilidad de diccionarios.** Data Audit depende de los diccionarios públicos (2018–2022 en estadísticas vitales). Faltan códigos para valores nuevos («Consular» en tipo de inscripción) y la ENCOVI no usa sus diccionarios de hogares y personas. | Medio: valores sin código quedan en la bandeja; no hay validación cruzada estadística en Survey. | Bandeja de correcciones con búsqueda en catálogo; reglas y catálogos editables en PostgreSQL. | Incorporar diccionarios vigentes del INE y los de la ENCOVI; confirmar con el INE los puntos pendientes (6 causas PNC sin grupo, «Consular», «**» de SECONRED, meses de aire). |
| L7 | **Capacidad de cómputo.** En Vercel Hobby cada petición dura máximo 300 s y los archivos 50 MB; la transcripción local sin GPU es lenta. | Medio: bases muy grandes con IA o PDFs extensos pueden no terminar en una petición. | Lectura del PDF en bloques paralelos; la IA de Data Audit solo procesa textos distintos y resultados guardados; transcripción asíncrona en la nube. | Servidor institucional sin límite de tiempo y cola de trabajos; GPU para el modo local. |
| L8 | **Intervención humana necesaria.** Sugerencias, formularios, conciliaciones, evaluaciones y recomendaciones requieren aprobación. | Bajo (decisión de diseño): el sistema no elimina trabajo humano, lo enfoca. | Bandejas, filtros y explicaciones en lenguaje claro; lo aprobado se reutiliza. | Métricas de carga de trabajo; aprobación por lotes para casos de alta confianza. |
| L9 | **Escalabilidad del estado de Survey y QI.** Se guarda como un documento JSONB transaccional en PostgreSQL; las cuentas no tienen roles. | Medio con muchos usuarios simultáneos o miles de entrevistas. | Bloqueo transaccional y número de revisión para evitar pérdidas. | Normalizar en tablas (formularios, entrevistas, hallazgos, recomendaciones), paginar y agregar roles por institución. |
| L10 | **Transferencia a servicios externos** de audio y transcripciones. | Alto con datos reales. | Modo local de transcripción; IA desactivable en Data Audit y QI; autorización obligatoria en Survey. | Acuerdos de tratamiento de datos o modelos locales para JEV y conciliación. |
| L11 | **Retención de archivos.** No hay borrado automático de originales y audios. | Medio (confidencialidad). | Buckets privados, URLs firmadas de 5 minutos, descargas registradas. | Política de retención con borrado programado. |
| L12 | **Codificador con IA validado con muestra pequeña** (19/20). | Medio. | Umbral de confianza ≥ 0.6, códigos inexistentes descartados, aprobación humana. | Medir con una muestra grande ya codificada por el INE. |

## Funcionalidades solicitadas o previstas no implementadas

| Funcionalidad | Estado |
|---|---|
| OCR independiente del modelo de IA | No implementado (la IA lee texto e imagen de cada página) |
| Validaciones cruzadas entre preguntas del cuestionario (p. ej., edades de padres e hijos) | No implementado |
| Uso de los diccionarios de hogares y personas de la ENCOVI | No implementado |
| Captura de entrevistas sin conexión en campo | No implementado |
| Roles y permisos por institución | No implementado |
| Política de retención y borrado automático | No implementado |
| Envío automático de manuales a las instituciones y seguimiento de su efecto | No implementado |
| Evaluación JEV de secciones del cuestionario más allá de A1–A2 | No implementado |
| Conexión automática Data Audit → Quality Improvement (hoy se descarga y sube el JSON) | No implementado |
| Medición de WER, DER, exactitud de JEV, de extracción del PDF y de conciliación | Pendiente de datos reales autorizados |

## Posibles mejoras (priorizadas)

1. Validar con datos reales autorizados y medir las métricas pendientes (L1, L5, L12).
2. Roles por institución, retención automática y acuerdos de tratamiento de datos (L9–L11).
3. Importar formularios CAPI existentes y validaciones cruzadas (L4, L6).
4. Servidor institucional con cola de trabajos (L7).
5. Conectar automáticamente Data Audit con Quality Improvement y medir si las recomendaciones reducen los errores en el período siguiente.
