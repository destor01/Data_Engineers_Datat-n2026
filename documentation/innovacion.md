# Innovación y diferenciación

## 1. Un ciclo completo de aseguramiento de calidad, no una herramienta aislada

La mayoría de las soluciones de calidad de datos atacan una sola etapa: validar un archivo, transcribir un audio o revisar una encuesta. Quality Audit integra **las cuatro etapas del ciclo de calidad** en una sola plataforma, con un mismo inicio de sesión, una misma base de datos y una bitácora común:

| Etapa | Módulo | Momento |
|---|---|---|
| **Prevención de errores** | Survey Audit | Antes y durante la captura: el formulario no acepta respuestas inválidas |
| **Verificación de entrevistas** | Audio Audit | Después de la entrevista: se comprueba que se siguió el protocolo |
| **Detección y corrección** | Data Audit | Al recibir la base: se encuentran, explican y corrigen los errores |
| **Mejora de procedimientos** | Quality Improvement | Después: el error se convierte en una recomendación para que no se repita |

Los módulos se alimentan entre sí: la transcripción de Audio Audit es la evidencia con la que Survey Audit verifica las respuestas, y el reporte de Data Audit es la entrada de Quality Improvement. El resultado es un **ciclo cerrado**: lo que se detecta hoy se previene en el siguiente envío.

## 2. Elementos diferenciadores

1. **Del PDF al formulario validado.** Survey Audit convierte un cuestionario impreso (72 páginas de la ENCOVI) en un formulario digital con catálogos, pases y secciones por persona, sin programarlo a mano. Las páginas difíciles se leen por zonas para que ninguna detenga el proceso.
2. **La grabación como evidencia, no como sustituto.** La conciliación compara lo registrado con lo dicho y muestra el minuto exacto, pero **nunca cambia** la respuesta: respeta la cadena de custodia del dato.
3. **Evaluación probabilística del protocolo.** En lugar de pedir a un modelo una opinión en texto, cada regla del manual se traduce en preguntas cerradas a un modelo de juicio (JEV) y el puntaje se calcula con fórmulas explícitas: probabilidades de cumplir, incumplir y «no se puede saber», puertas para momentos únicos, promedios por ventana para que la duración no castigue, y distribución exacta de la tasa de cumplimiento. Es auditable y calibrable con las correcciones del supervisor.
4. **Depuración que aprende.** Data Audit guarda cada corrección aprobada como equivalencia de la institución y la aplica sola en el siguiente envío; lo rechazado no se vuelve a proponer. El costo de IA baja con el uso.
5. **Validado contra el resultado real del INE.** En defunciones el motor conserva exactamente los mismos 8 841 registros que dejó el INE, y descubrió una regla no documentada (exclusión de defunciones ocurridas en el extranjero).
6. **Configuración en lugar de programación.** Bases, alias de columnas, catálogos, reglas, umbrales, plantillas de recomendación y reglas de entrevista son datos editables. Agregar una base nueva es escribir un YAML.
7. **Explicaciones para no programadores.** Cada hallazgo, sugerencia y recomendación se redacta en lenguaje claro: qué ocurrió, por qué importa, cómo corregirlo y cómo prevenirlo.
8. **Privacidad desde el diseño.** Columnas personales eliminadas, solo textos distintos y enmascarados hacia la IA, modo local para audio, y todo funciona sin IA si la institución lo decide.

## 3. Integración de metodologías

| Disciplina | Cómo se aplica |
|---|---|
| Calidad de datos (dimensiones estándar) | 7 dimensiones con pesos por severidad y puntaje 0–100 por base y período |
| Normas de codificación oficial | Catálogos y CIE-10 del INE cargados sin alterar el significado de ningún código |
| Supervisión de campo | Reglas del Manual del Encuestador ENCOVI 2023 convertidas en criterios verificables |
| Estadística y probabilidad | Combinación de probabilidades, distribución Poisson-binomial, calibración de Platt y por temperatura, Brier y ECE |
| Procesamiento de lenguaje y voz | ASR, diarización, similitud de texto y modelos de lenguaje con salidas estructuradas |
| Mejora continua | Recomendaciones agrupadas por institución, base, período y regla, con aprobación y versiones |

## 4. Adaptabilidad a distintas fuentes estadísticas

Las cinco bases probadas son deliberadamente distintas: registros vitales con 82 columnas y datos personales (RENAP), hechos policiales con encabezados repetidos (PNC), mediciones ambientales en formato ancho (INSIVUMEH) y emergencias con una hoja por mes y encabezados combinados (SECONRED). El mismo motor las procesa todas. Survey Audit acepta cualquier cuestionario en PDF y Audio Audit cualquier conjunto de reglas expresadas como preguntas cerradas.

## 5. Aporte de la inteligencia artificial

La IA se usa donde el trabajo manual es más costoso y siempre bajo control humano:

| Tarea manual actual | Aporte de la IA | Control |
|---|---|---|
| Codificar a mano motivos de detención y causas de muerte | Sugiere el código con confianza y justificación | Aprobación del analista; códigos inexistentes descartados |
| Programar un formulario a partir del cuestionario | Lee el PDF y propone el formulario | Revisión obligatoria antes de finalizar |
| Escuchar entrevistas completas | Señala los minutos con posibles incumplimientos | El supervisor confirma o corrige |
| Comparar respuestas con grabaciones | Encuentra los turnos de evidencia | El revisor confirma o descarta |
| Redactar retroalimentación a instituciones | Precisa recomendaciones con las cifras reales | Aprobación con nombre y cargo |

Ninguna de estas tareas depende de la IA para funcionar: sin ella, el sistema sigue validando, sugiriendo por similitud y generando recomendaciones con plantillas.
