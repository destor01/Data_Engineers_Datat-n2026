# Metodología de auditoría

## Audio Audit

1. Convertir el audio a WAV mono de 16 kHz mediante FFmpeg. Si se activa reducción de ruido, aplicar filtros de frecuencia, reducción de ruido estacionario y normalización dinámica.
2. Transcribir en español mediante WhisperX con el modelo elegido: `medium`, `large-v3-turbo` o `large-v3`.
3. Alinear palabras con sus marcas temporales; si falla la alineación fina, el código contempla marcas por segmento.
4. Si se solicita, ejecutar diarización con Pyannote y asignar etiquetas de hablante. La diarización distingue voces, no acredita identidad ni rol.
5. Agrupar segmentos del mismo hablante con separación de hasta 2 s, extensión de hasta 60 s y texto combinado de hasta 650 caracteres. Marcar superposiciones según intervalos detectados (umbral 0.35 s). Exportar TXT.

La inferencia selecciona CUDA si está disponible, o CPU en caso contrario. No se ha demostrado entrenamiento propio ni precisión sobre entrevistas reales. Para evaluar cumplimiento de boletas se propone usar preguntas de referencia, mapear turnos al rol encuestador y clasificar preguntas completas, omitidas o alteradas, con revisión humana y evidencia temporal. Esta fase no se atribuye al código revisado.

## Data Audit

El motor documentado evalúa estructura, completitud, validez, consistencia, unicidad y oportunidad. Lee el crudo, empareja alias, elimina de la salida columnas identificadas como personales, normaliza valores, calcula variables, codifica con catálogos, valida y aplica exclusiones. Se documentan 13 tipos de transformación: municipio compuesto, partes de fecha y hora, agrupación de hora y edad, departamento desde municipio, relleno de ceros, padre y etiqueta de catálogo, mapa, constante, vacío como valor y dos modalidades de codificación de texto.

Las acciones son `auto_corregir`, `sugerir`, `reportar` y `excluir`. Las sugerencias permanecen pendientes de aprobación; las equivalencias conocidas permiten estandarizar códigos. RapidFuzz es el codificador actual por similitud; la integración de un modelo adicional de IA está prevista, no demostrada.

## Indicadores

Según el README del backend, error pesa 1, advertencia 0.5 e informativo 0. Estructura: 100 menos 15 por error y 5 por advertencia. Para reglas genéricas se utiliza la proporción de celdas afectadas respecto de registros por columnas publicadas; para reglas específicas, la proporción de registros afectados. El puntaje global promedia las dimensiones aplicables. La fórmula exacta de penalización y sus límites deben verificarse en `qa/motor.py`. Este puntaje no equivale a exactitud de clasificación.

La regla ambiental sugerida por INE se refiere a representatividad mensual según horas y días sin datos. Los umbrales exactos, inclusividad y agregación deben confirmarse con el área técnica antes de tratarlos como norma definitiva.

## Papel de la interfaz

La interfaz no modifica las reglas ni constituye una nueva métrica: presenta resultados de los motores. Los resultados de demostración no proceden del archivo seleccionado. En HTTP, el adaptador genera archivos sin persistir cargas en PostgreSQL. Los turnos de voz no acreditan identidad o rol. Ver [arquitectura](architecture.md).
