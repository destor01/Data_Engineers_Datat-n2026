# Fuentes de información

Inventario de todas las fuentes usadas para construir, configurar y probar Quality Audit. Se distinguen tres tipos:

| Tipo | Qué es | ¿Está en el repositorio? |
|---|---|---|
| **Oficial INE compartida por la organización** | Diccionarios y bases publicadas por el INE, enviados a los equipos por correo electrónico por un miembro de la organización del Datatón | No se copia la base completa; se indica por ruta. Las reglas y alias derivados sí están versionados. |
| **Proporcionada por el INE** | Entregada a los equipos durante el Datatón (crudos institucionales) | **No.** Contiene datos personales; se usa solo localmente. |
| **Sintética** | Creada por el equipo para pruebas y demostración; no describe personas reales | Sí, marcada como sintética. |

**Fuente principal:** las bases y diccionarios oficiales del INE de estadísticas vitales (defunciones y nacimientos), detenidos de la PNC, calidad del aire y emergencias, más el Cuestionario y el Manual del Encuestador de la ENCOVI 2023. De ellos salen los 31 catálogos, 15 086 códigos, 761 equivalencias, 235 variables y 340 alias que usa Data Audit, y las 51 reglas de Audio Audit.

> Los diccionarios y bases publicadas se recibieron por correo electrónico de la organización del Datatón el 24 y 25 de noviembre de 2026; el paquete de crudos institucionales tiene fecha interna del 23 de noviembre de 2026.

## Data Audit

### Bases proporcionadas por el INE (crudos institucionales)

Recibidas en el paquete «Conjunto de datos_ instituciones.zip» (fecha interna 23-nov-2026). Son los archivos tal como los enviaría cada institución al INE.

| Archivo | Institución | Período de referencia | Formato | Unidad de observación | Registros | Restricciones |
|---|---|---|---|---|---:|---|
| Defunciones Julio_renap_2026.xlsx | RENAP | Julio 2026 | XLSX, 2 hojas (cruda y procesada por el INE), 82 columnas | Defunción inscrita | 10 034 crudos / 8 841 publicados | Nombres, CUI y otros datos personales |
| Nacimientos_Junio_renap_2026.xlsx | RENAP | Junio 2026 | XLSX, 53 columnas | Nacimiento inscrito | 30 093 | Datos personales de madre, padre y recién nacido |
| Base general de detenidos octubre_PNC_2026.xlsx | PNC | Octubre 2026 | XLSX, 50 columnas con encabezados repetidos | Persona detenida (hecho) | 4 255 | Datos personales y de hechos delictivos |
| Datos de Calidad del aire_INSIVUMEH_2025.xlsx | INSIVUMEH | 2025 | XLSX formato ancho (estación y PM en dos filas de encabezado) | Lectura horaria de PM por estación | 166 440 lecturas | Sin datos personales |
| Emergencias_SECONRED_2025.xlsx | SECONRED | 2025 | XLSX, una hoja por mes, 3 filas de encabezado combinadas | Evento atendido | 7 337 | Direcciones y descripciones libres |

**Transformaciones aplicadas:** lectura del encabezado, emparejamiento de columnas por alias, eliminación de columnas personales, limpieza, recodificación a los códigos del INE, exclusiones según las reglas y puntaje (ver [metodología](methodology.md#data-audit-depuración-y-control-de-bases)).
**Finalidad:** probar Data Audit con datos reales y compararlo con lo publicado por el INE. Los resultados están en [Pruebas](testing.md#resultados-con-crudos-reales).
**Manejo:** solo en las computadoras del equipo; nunca se subieron al repositorio, a la plataforma de demostración ni a servicios de IA (al codificador con IA solo van textos distintos de una columna, sin filas, nombres ni números de identificación; ver [seguridad](security.md)).

### Diccionarios oficiales del INE

Configuran las variables, catálogos y códigos oficiales. `scripts/cargar_config.py` los lee **sin modificar el significado de ningún código** (ver [diccionario de datos](diccionario-datos.md)).

| Archivo | Nombre oficial / contenido | Período | Formato | Uso | Recepción |
|---|---|---|---|---|---|
| diccionario-defunciones-2018-2022.xlsx | Diccionario de datos de defunciones (hojas Defunciones y CIE-10) | 2018–2022 | XLSX | Variables, catálogos y CIE-10 de defunciones (`--dicc-defunciones`) | 24–25 nov 2026 |
| diccionario-nacimientos-2018-2022.xlsx | Diccionario de datos de nacimientos | 2018–2022 | XLSX | Variables y catálogos de nacimientos (`--dicc-nacimientos`) | 24–25 nov 2026 |
| 20250527171331…xlsx | Diccionario de datos de Detenidos, PNC | Vigente 2025 | XLSX | Variables y catálogos de detenidos, incluidas las causas de detención (`--dicc-pnc`) | 24–25 nov 2026 |

### Bases publicadas por el INE (referencia de estructura)

Sirven para comprobar que la salida corregida tenga las mismas columnas, orden y códigos que lo que publica el INE.

| Archivo | Contenido | Período | Formato | Uso |
|---|---|---|---|---|
| defunciones_2025.xlsx | Base publicada de defunciones | 2025 | XLSX | Estructura de salida (26 columnas) |
| nacimientos_2025.xlsx, nacimientos-2022.xlsx | Bases publicadas de nacimientos | 2025 y 2022 | XLSX | Estructura de salida (40 columnas) y códigos usados |
| 20240528163735…xlsx | Microdatos publicados de detenidos PNC (núm_corre, año_ocu…) | 2023 | XLSX | Estructura de salida (19 columnas) y grupos de causa |
| 20250527170608…xlsx | Cuadros estadísticos de detenidos PNC (Portada, Índice, Cuadros) | 2025 | XLSX | Referencia de agregación |
| base-monitoreo_aire_2025_insivumeh.xlsx | Base publicada de monitoreo de calidad del aire | 2025 | XLSX | Estructura (12 columnas) y meses conservados (comparación 11/19) |
| 2.-base-eventos_22_-conred.csv | Base publicada de eventos de CONRED | 2022 | CSV separado por `;` | Estructura de emergencias (26 columnas) |

Todas recibidas por correo electrónico de la organización del Datatón el 24–25 nov 2026; restricciones: las propias de la publicación del INE (datos ya anonimizados).

### Regla indicada por el INE

La regla de representatividad mensual de calidad del aire (excluir el mes con más de 2 días con más de 4 horas sin dato) fue indicada por el INE durante el Datatón; se implementó como `AIRE_MES_REPRESENTATIVO` con umbrales editables.

## Survey Audit y Audio Audit

| Fuente | Institución | Nombre oficial | Período | Formato | Uso | Restricciones |
|---|---|---|---|---|---|---|
| Cuestionario ENCOVI 2023 | INE | Encuesta Nacional de Condiciones de Vida 2023 — cuestionario de hogares | Levantamiento 2023 | PDF, 72 páginas apaisadas (778 KB) | Prueba de lectura del PDF y generación del formulario dinámico | Documento público; no se versiona el PDF en el repositorio |
| Manual del Encuestador ENCOVI 2023 | INE | Manual del Encuestador ENCOVI 2023 | 2023 | PDF; extracto de reglas en Markdown (`audio-audit/encovi_jev/referencias/`) | Base normativa de las 51 reglas de Audio Audit (apertura, contacto, conducta) y de las buenas prácticas de captura | Documento público; el repositorio guarda solo las reglas resumidas por el equipo |

**Diccionarios de hogares y personas de la ENCOVI:** **no se usaron**. La validación estadística cruzada con esos diccionarios **no está implementada** (ver [limitaciones](limitaciones.md)).

## Datos sintéticos

Creados por el equipo. No provienen de ninguna persona, hogar ni empresa real; sirven para que el jurado repita cada prueba sin datos confidenciales.

| Archivo | Módulo | Contenido | Errores sembrados |
|---|---|---|---|
| `documentation/ejemplos/emergencias_sintetica.csv` | Data Audit | 41 emergencias con columnas tipo SECONRED | Municipios mal escritos («Mixcoo», «Villa Nuevaa», «Chinautlaa»), departamento inexistente (99) o vacío, valor no numérico («abc») en personas afectadas, filas incompletas y registros repetidos |
| `documentation/ejemplos/cuestionario_sintetico.pdf` | Survey Audit | Cuestionario de 2 páginas: vivienda, tabla de equipamiento con pases y sección por persona | — (sirve para generar el formulario) |
| `documentation/ejemplos/transcripcion_sintetica.json` | Survey / Audio Audit | Entrevista sintética en el formato que descarga Audio Audit | Se dicen «ocho horas» de agua (para comparar con lo registrado) |
| `documentation/ejemplos/generar_ejemplos.py` | — | Script que vuelve a crear el PDF y la transcripción | — |
| `audio-audit/encovi_jev/examples/transcript_example.json` | Audio Audit | Entrevista ENCOVI simulada, marcada SINTÉTICA | Incumplimientos A1-08, A1-11, A1-12, A2-10 |
| `interfaz/examples/datos-demostracion.csv`, `silencio-demostracion.wav` | Interfaz (modo demo) | CSV ficticio y audio de silencio | — |
| `survey-audit/templates/pilot.synthetic.json` | Survey Audit | Formulario piloto versión 1 | — |

**Grabaciones:** no se usaron grabaciones reales de entrevistas del INE. Las pruebas de audio se hicieron con transcripciones sintéticas y audios de prueba sin datos personales.

## Reportes de auditoría (Quality Improvement)

Quality Improvement no usa una fuente externa: su entrada es el `reporte.json` que genera Data Audit. En las pruebas se usaron reportes generados con los datos sintéticos; los reportes de los crudos reales se revisaron solo localmente. Las plantillas de recomendación (`quality-improvement/templates/reglas.json`) fueron redactadas por el equipo a partir de las reglas de Data Audit.
