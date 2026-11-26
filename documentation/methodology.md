# Metodología científica y técnica

Este documento explica **cómo se obtienen los resultados** de cada módulo: entradas, procesos, algoritmos, reglas, fórmulas, salidas, excepciones y fuentes que los respaldan. Todo lo descrito está implementado y probado, salvo lo marcado explícitamente como **No implementado**. Las constantes citadas son las del código entregado (commit indicado en el [historial](historial.md)).

| Módulo | Etapa de calidad | Pregunta que responde |
|---|---|---|
| [Survey Audit](#survey-audit-captura-validada) | Prevención | ¿El formulario captura solo respuestas válidas y coherentes con los pases? |
| [Audio Audit](#audio-audit-evaluación-del-encuestador-con-jev) | Verificación | ¿El encuestador siguió el protocolo de la entrevista? |
| [Data Audit](#data-audit-depuración-y-control-de-bases) | Detección y corrección | ¿La base entregada por la institución cumple el formato y los catálogos del INE? |
| [Quality Improvement](#quality-improvement-mejora-de-procedimientos) | Mejora continua | ¿Qué debe cambiar la institución para que el error no se repita? |

Principio común: **la máquina propone y una persona decide**. Ninguna sugerencia de IA cambia un dato, una respuesta registrada o un manual sin aprobación humana, y toda decisión queda en una bitácora.

---

## Audio Audit: evaluación del encuestador con JEV

### Entradas

| Entrada | Formato | Límite |
|---|---|---|
| Grabación de la entrevista | MP3, WAV, M4A, OGG, FLAC, WEBM… (lo que acepten AssemblyAI o FFmpeg) | 50 MB (plan gratuito de Supabase) |
| Transcripción ya hecha (alternativa) | JSON de Audio Audit, TXT con `HABLANTE: texto` o `[mm:ss]` | 5 MB |
| Reglas de evaluación | `audio-audit/encovi_jev/rules_a1_a2.py` (51 reglas) | — |
| Fuente normativa | Manual del Encuestador ENCOVI 2023 (`encovi_jev/referencias/`) | — |

### 1. Preprocesamiento del audio

- **Nube (plataforma publicada):** el navegador sube el audio directo al bucket privado `audio-interviews` con una URL firmada; AssemblyAI lo descarga por otra URL firmada de 5 minutos. No se aplica filtrado previo: el proveedor recibe el archivo original.
- **Local (opcional, con GPU):** FFmpeg convierte a WAV mono 16 kHz (`-ac 1 -ar 16000`). Con «reducir ruido» aplica la cadena `highpass=f=80, lowpass=f=7600, afftdn=nf=-25, dynaudnorm=f=150:g=15` (paso alto, paso bajo, reducción de ruido estacionario y normalización dinámica).

### 2. Reconocimiento de voz (ASR) y marcas de tiempo

| Modo | Motor | Parámetros |
|---|---|---|
| Nube (por defecto) | AssemblyAI, trabajo asíncrono | `language_code=es`, puntuación y formato, `speaker_labels` |
| Nube (alternativo) | Deepgram `nova-3` | `language=es`, diarización |
| Local | WhisperX (`medium`, `large-v3-turbo` o `large-v3`) + alineación de palabras | CUDA si existe, si no CPU |

Cada turno guarda hablante, inicio y fin en segundos y texto. En modo local los segmentos del mismo hablante se unen si están a ≤ 2 s, la unión no supera 60 s ni 650 caracteres; las superposiciones de voces de ≥ 0.35 s se marcan.

### 3. Diarización e identificación de hablantes

La diarización separa **voces** (`SPEAKER_00`, `SPEAKER_01`…), no identifica personas ni roles. El sistema sugiere roles solo cuando la etiqueta ya es reconocible (por ejemplo `ENC`, `ENCUESTADOR`, `INF`); en los demás casos **el auditor asigna** en pantalla quién es *Encuestador(a)*, *Informante* u *Otra persona*. Esa asignación se guarda con la evaluación (`speaker_map`). No se usa biometría de voz ni se intenta reconocer la identidad de nadie.

### 4. Evaluación del protocolo con JEV

**Algoritmo.** Cada regla del manual se convierte en una o varias preguntas cerradas para el modelo de juicio **JEV** (`typesafe/jev-1.14`, vía OpenRouter). JEV no redacta: devuelve probabilidades.

- Preguntas **noul** (sí/no): probabilidad de «sí».
- Preguntas de **elección** (3 opciones: cumplió / no cumplió / no aplica o no se escucha): probabilidad de cada opción.

**Ventanas.** La transcripción se divide en ventanas de hasta 12 000 bytes con 2 turnos de traslape (`make_windows`), para que cualquier duración quepa y nada quede cortado entre ventanas.

**Tipos de regla y combinación.** Cada regla produce tres probabilidades que suman 1: *c* = cumplió, *v* = incumplió, *u* = no se puede saber.

| Tipo | Ejemplo | Cálculo |
|---|---|---|
| OBLIGACIÓN (momento único: apertura/cierre) | «Se presenta con nombre e institución» | En la ventana del momento: *c_w*, *v_w*. Puerta *g* = P(el momento está en la grabación): *c = g·c_w*, *v = g·v_w*, *u = (1−g) + g·u_w*. Una obligación con varias preguntas multiplica las probabilidades de «sí». |
| PROHIBICIÓN (toda la entrevista) | «No sugiere respuestas» | Promedio por ventana de (*c, v, u*), para que una entrevista larga no acumule falsos positivos. Una ventana se marca si *v_w* ≥ 0.70. |
| CONDICIONAL | «Si el informante no entiende, repite la pregunta textual» | Etapa 1: ¿ocurrió la condición? Solo las ventanas con P ≥ 0.5 pasan a la etapa 2, que juzga el cumplimiento; se promedia sobre las ocurrencias. Sin ocurrencias: *u* = 1. |
| EVIDENCIA | Elección de 3 opciones | Directo de las probabilidades de la elección. |

**Puntaje.**

- Cumplimiento ponderado = Σ *w·c* / Σ *w* sobre las reglas aplicables (peso *w* de 1 a 3 según la importancia en el manual).
- Cobertura = reglas aplicables / reglas totales.
- Distribución exacta de la tasa de cumplimiento (programación dinámica tipo Poisson-binomial), con cuantiles 5–50–95 % y P(tasa ≥ 80 %) y P(tasa ≥ 90 %).
- Riesgos: reglas con *v* ≥ 0.3, o con ventanas marcadas o en zona de revisión (0.3 ≤ *v* < 0.7).

**Veredicto** (`audio-audit/app/jev_auditor.py`):

| Veredicto | Condición |
|---|---|
| Cumplimiento alto | Puntaje ≥ 0.90, ningún riesgo alto de procedimiento y < 0.5 ventanas de conducta marcadas por hora |
| Aceptable con observaciones | Puntaje ≥ 0.75, ≤ 2 riesgos altos de procedimiento y < 2.5 ventanas marcadas por hora |
| Requiere revisión prioritaria | En otro caso |
| Sin evidencia suficiente | No hay reglas aplicables ni conducta marcada |

La duración, si no la da el audio, se estima a 865 bytes de transcripción por minuto (medido en `GUIDE_JEV_QUESTIONS.md`).

**Revisión humana.** El auditor puede editar cualquier regla (cumplió / no cumplió / no aplica, con justificación); la edición se marca como manual y recalcula el puntaje (en la prueba, 91 % → 89 %).

**Calibración.** Con al menos 30 evaluaciones etiquetadas por grupo, se ajusta un escalado de Platt para preguntas sí/no (`sigmoid(a·logit p + b)`) y una temperatura para las elecciones; se reportan Brier y ECE (10 intervalos). La calibración queda fijada a la versión del modelo. **No se ha calibrado con etiquetas reales del INE** (no hay grabaciones reales autorizadas).

### Salidas

Reporte con veredicto, puntaje global y por sección (A1 Apertura y contacto inicial, 24 reglas; A2 Conducta y actitud, 27 reglas), riesgos con la evidencia textual y minuto, tabla de las 51 reglas con estado, y descargas en JSON y TXT. El JSON se puede importar en Survey Audit.

### Excepciones

| Situación | Comportamiento |
|---|---|
| Sin `OPENROUTER_API_KEY` | La interfaz avisa que falta la llave y no calcula el puntaje; la transcripción se puede revisar igual. |
| Sin llave de transcripción | Se puede cargar una transcripción existente. |
| Audio sin voz o un solo hablante | Las reglas sin evidencia quedan como «no se puede saber»; el veredicto puede ser «Sin evidencia suficiente». |
| Error del proveedor | El trabajo queda en estado `error` con el mensaje; se puede reintentar. |

### Limitaciones del modelo

- **No se midió WER (exactitud de la transcripción), DER (diarización) ni la exactitud de JEV** frente a un auditor humano: no hay grabaciones reales autorizadas ni etiquetas. Las pruebas usaron una transcripción **sintética** con errores sembrados (A1-11, A1-12, A1-08, A2-10).
- Solo se cubren las secciones A1 y A2 del manual; el contenido de cada pregunta del cuestionario se verifica en Survey Audit.
- El español rural, otros idiomas mayas y el ruido de campo pueden degradar la transcripción.

---

## Survey Audit: captura validada

### Entradas

| Entrada | Formato |
|---|---|
| Cuestionario | PDF (probado con el Cuestionario ENCOVI 2023, 72 páginas apaisadas) o formulario JSON |
| Respuestas | Captura en el formulario digital |
| Grabación | JSON de Audio Audit («Descargar JSON») con autorización registrada |

### 1. Procesamiento del PDF (lectura y OCR)

- El PDF se guarda en el bucket privado `encuestas` y se divide en bloques de 2 páginas (`SURVEY_PAGINAS_BLOQUE`) con `pypdf`; la interfaz lee hasta 4 bloques a la vez.
- Cada bloque se envía a Claude (Haiku 5.5) como **documento PDF**: el modelo recibe el texto y la imagen de cada página, lo que cumple la función de **OCR** para páginas escaneadas o tablas. No hay un motor de OCR separado (Tesseract u otro): **OCR independiente no implementado**.
- Respuesta con esquema JSON estricto: secciones, preguntas (`codigo`, `label`, `type`, `options`, `pase_a`, `constraints`, `orden`) y **tablas compactas** (filas × columnas con el marcador «(...)»), que se expanden después a una pregunta por celda (`expandir_tablas`).
- Si una página no cabe en la respuesta, se reintenta por **zonas**: mitades, luego cuartos; si aun así falla, se inserta un marcador `pagina_no_leida` con alerta visible para captura manual. Así una página difícil nunca detiene el documento.

### 2. Extracción de preguntas y formulario dinámico

Las lecturas se unen en orden (`_lecturas_completas`), se eliminan duplicados del traslape y se genera un **formulario borrador** versión 2. El analista lo revisa en el editor (texto, tipo, opciones, pases, rangos) antes de **finalizarlo**; solo un formulario finalizado admite entrevistas. La validación del formulario (`check_template`) exige identificadores únicos, tipos permitidos (`text`, `integer`, `decimal`, `date`, `single_select`, `multi_select`), catálogo en preguntas de selección, códigos de opción únicos, condiciones que apunten a una pregunta anterior y pases con destino existente.

### 3. Catálogos, pases y alcance por persona

- **Catálogos:** cada opción conserva el código del cuestionario (no se recodifica).
- **Pases** (`pase_a`): por opción o por pregunta, hacia una pregunta, una sección o el fin. Las preguntas entre el origen y el destino quedan **no aplicables**; un pase dentro de la sección de personas no oculta preguntas del hogar y viceversa.
- **Condiciones** (`visible_when`): operadores `eq`, `ne`, `in` sobre una pregunta anterior.
- **Secciones por persona:** se repiten para cada integrante (`_personas`, de 0 a 40); las respuestas se guardan como `<pregunta>#<n>`.

### 4. Validación de respuestas (`survey_audit/validation.py`)

Determinista, sin IA y sin ejecutar expresiones del instrumento:

| Regla | Mensaje al encuestador |
|---|---|
| `required` | «Falta la respuesta.» |
| `type` (entero, decimal, texto, fecha ISO) | «Escribe un número entero, sin decimales.», etc. |
| `catalog` | «Elige una de las opciones de la lista.» / sin repetir en selección múltiple |
| `range` | «El valor debe ser mayor o igual a *min* y menor o igual a *max*.» |
| `unknown_question` | Respuesta a una pregunta que no existe |

Las respuestas de preguntas que un pase dejó sin aplicar **se conservan** para trazabilidad pero no cuentan como activas. Una entrevista solo se puede **finalizar** sin errores; si los hay, el servidor responde 422 con la lista y la interfaz lleva a cada pregunta.

### 5. Conciliación con la grabación

1. Se vincula el JSON de Audio Audit a la entrevista (con casilla de autorización obligatoria) y se indica qué hablante es el encuestador.
2. Las respuestas activas se envían en grupos de 80 junto con la transcripción compacta (`id [mm:ss] E/P(hablante): texto`), que va en caché para no pagarla en cada grupo.
3. Por cada respuesta, Claude devuelve los turnos de evidencia, lo escuchado (≤ 12 palabras) y un estado: **coincidencia**, **discrepancia** o **no verificable**. Los turnos citados se comprueban contra la transcripción; sin evidencia válida el estado pasa a «no verificable».
4. Cada resultado queda **pendiente** de revisión humana (confirmar o descartar con justificación). **La verificación nunca modifica las respuestas registradas.**

### Salidas y excepciones

Formulario versionado, entrevistas con historial de eventos, hallazgos de conciliación con evidencia y revisión. Sin `ANTHROPIC_API_KEY`, la lectura de PDF y la conciliación responden 503 pero el editor manual, la captura y la validación funcionan. Si el proveedor limita peticiones (429), la interfaz reintenta.

### Limitaciones y no implementado

- La lectura con IA puede equivocarse en tablas complejas: por eso el formulario siempre se revisa antes de finalizarlo. **No se midió la exactitud de extracción** contra una transcripción manual del cuestionario completo.
- **No implementado:** validaciones cruzadas entre preguntas (por ejemplo, edad del hijo menor que la de la madre), uso de los diccionarios de hogares y personas de ENCOVI, captura sin conexión en campo.

---

## Data Audit: depuración y control de bases

### Entradas

| Entrada | Formato |
|---|---|
| Base enviada por la institución | XLSX, XLS, CSV o TXT (separador `;`, `,`, barra vertical o tabulador detectado; UTF-8 o Latin-1); tabla simple, una hoja por mes o formato ancho |
| Definición de la base | `config/bases/*.yaml` + diccionarios oficiales del INE → PostgreSQL |
| Reglas | `config/reglas.yaml` (28) + 5 de llave única = 33 |
| Período | año y mes declarados por quien sube |

### Proceso (en orden)

1. **Lectura** (`qa/lector.py`, `python-calamine`/`pandas`). Ubica el encabezado en las primeras 25 filas buscando la fila con al menos 2 nombres o alias conocidos; une hojas mensuales; pasa el formato ancho a una fila por lectura. Registra encabezados repetidos, columnas vacías y hojas con estructura distinta.
2. **Normalización de columnas.** Empareja cada columna con una variable del INE por sus 340 alias (sin tildes ni mayúsculas). Las columnas de datos personales (nombres, CUI, direcciones…) se **eliminan** de la salida (`GEN_PII`); las desconocidas se reportan.
3. **Limpieza.** Quita espacios sobrantes y convierte textos de «sin dato» («N.D.», «-1», «IGNORADO»…) al código de ignorado del INE.
4. **Transformación.** 13 recetas calculan las columnas del INE desde el crudo: `municipio_compuesto` (depto 1 + municipio 14 → 0114), partes de fecha y hora, agrupación de hora y edad, departamento desde municipio, relleno de ceros, padre y etiqueta de catálogo (causa → grupo), mapa, constante, vacío como valor y dos formas de codificar texto.
5. **Codificación.** Si el valor ya es código válido, se deja; si hay **equivalencia aprobada** (761 iniciales + las que apruebe el analista), se traduce; si no, se reporta y se pide sugerencia:
   - **Similitud** (`rapidfuzz`, mínimo 0.80; 0.85 para `GEN_CATALOGO`); los municipios solo se buscan dentro del departamento del registro.
   - **IA** para texto libre (motivo de detención, causa de muerte): Claude Haiku 5.5, lotes de 40 textos distintos, 4 en paralelo; con catálogos pequeños la respuesta solo puede ser un código del catálogo (`enum`), con CIE-10 se envían los 15 candidatos más parecidos. Se descarta todo código inexistente y se muestran solo sugerencias con confianza ≥ 0.6. Lo que la similitud resuelve con ≥ 95 % no va a la IA. Si un lote falla, se usa similitud.
   - Valores **sin sugerencia** también van a la bandeja para que el analista elija el código, salvo que ya hayan sido rechazados.
6. **Validación.** Tipo de dato, obligatoriedad, rango y formato, más las reglas específicas de cada base y la llave única.
7. **Exclusión** de registros según reglas con acción `excluir`, guardados por motivo.
8. **Puntaje** y escritura de salidas.

### Reglas

| Código | Base | Dimensión | Severidad | Acción | Qué revisa |
|---|---|---|---|---|---|
| GEN_COLUMNA_FALTANTE | Todas | estructura | error | reportar | Falta una columna obligatoria |
| GEN_COLUMNA_DESCONOCIDA | Todas | estructura | info | reportar | Columna fuera de la definición |
| GEN_COLUMNA_DUPLICADA | Todas | estructura | advertencia | reportar | Encabezado repetido |
| GEN_COLUMNA_VACIA | Todas | estructura | info | auto_corregir | Columna vacía y sin nombre |
| GEN_PII | Todas | estructura | info | auto_corregir | Columna con datos personales (se elimina) |
| GEN_HOJAS_DISTINTAS | Todas | estructura | advertencia | reportar | Hojas con estructura distinta |
| GEN_NULO_TEXTUAL | Todas | completitud | info | auto_corregir | Texto usado como dato faltante |
| GEN_SIN_DATO | Todas | completitud | advertencia | auto_corregir | Dato faltante (código de ignorado) |
| GEN_REQUERIDA | Todas | completitud | error | reportar | Falta un dato obligatorio |
| GEN_ESPACIOS | Todas | validez | info | auto_corregir | Espacios sobrantes |
| GEN_CODIFICACION | Todas | validez | info | auto_corregir | Texto convertido al código oficial por equivalencia |
| GEN_CATALOGO | Todas | validez | error | sugerir | Valor que no existe en el catálogo |
| GEN_CODIFICACION_IA | Todas | validez | advertencia | sugerir | Texto libre pendiente de codificar |
| GEN_TIPO | Todas | validez | error | reportar | Tipo de dato incorrecto |
| GEN_RANGO | Todas | validez | advertencia | reportar | Fuera de rango |
| GEN_FORMATO | Todas | validez | error | reportar | Formato incorrecto |
| AIRE_MES_REPRESENTATIVO | Calidad del aire | representatividad | error | excluir | Mes con más de 2 días con más de 4 horas sin dato |
| AIRE_RANGO_PM | Calidad del aire | validez | advertencia | reportar | PM fuera de rango plausible |
| DEF_PERIODO_OCURRENCIA | Defunciones | oportunidad | advertencia | excluir | Ocurrida fuera del año de la carga |
| DEF_OCURRIO_EXTRANJERO | Defunciones | validez | info | excluir | Ocurrida fuera de Guatemala |
| DEF_FECHA_COHERENCIA | Defunciones | consistencia | error | reportar | Día/mes/año ≠ fecha de defunción |
| NAC_PERIODO_OCURRENCIA | Nacimientos | oportunidad | advertencia | excluir | Ocurrido fuera del año de la carga |
| NAC_HIJOS_COHERENCIA | Nacimientos | consistencia | error | reportar | Hijos tenidos ≠ vivos + muertos |
| PNC_MAYOR_EDAD_COHERENCIA | Detenidos | consistencia | error | reportar | Mayor/menor de edad ≠ edad |
| PNC_DIA_SEMANA_COHERENCIA | Detenidos | consistencia | error | reportar | Día de la semana ≠ fecha |
| PNC_MES_PERIODO | Detenidos | oportunidad | advertencia | reportar | Hecho fuera del mes de la carga |
| EMERG_SUBTIPO_AMENAZA | Emergencias | consistencia | error | reportar | Subtipo que no corresponde a la amenaza |
| EMERG_PERIODO | Emergencias | oportunidad | advertencia | reportar | Emergencia fuera del año de la carga |
| `<BASE>_LLAVE_UNICA` (×5) | Cada base | unicidad | — | reportar | Registro repetido según la llave de la base |

Las reglas, catálogos y umbrales viven en PostgreSQL (tabla `regla`, `catalogo`, `catalogo_valor`): se ajustan sin programar.

### Dimensiones de calidad y puntaje (0–100)

Siete dimensiones: **estructura, completitud, validez, consistencia, unicidad, oportunidad y representatividad**. Pesos por severidad: error = 1, advertencia = 0.5, info = 0.

- **Estructura:** 100 − 15 × errores − 5 × advertencias.
- **Reglas de columna** (genéricas `GEN_*`): 100 − 100 × Σ(*w* × celdas afectadas) ÷ (registros × columnas publicadas).
- **Reglas de registro** (específicas y llave única): 100 − 100 × Σ(*w* × registros afectados) ÷ registros.
- Cada dimensión se acota a [0, 100]. **Puntaje global** = promedio de las dimensiones que aplican a la base.

El puntaje mide **conformidad con las reglas**, no exactitud estadística del fenómeno.

### Acciones, correcciones y aprendizaje

| Acción | Efecto en la salida | Registro |
|---|---|---|
| `auto_corregir` | Cambia el valor | Corrección **aplicada** en la bitácora |
| `sugerir` | Deja el valor original | Corrección **pendiente** con código propuesto, confianza y justificación; cubre todas las filas con el mismo texto |
| `reportar` | Sin cambio | Hallazgo |
| `excluir` | Saca el registro | `registro_excluido` agrupado por motivo |

En la bandeja el analista **aprueba**, **elige otro código** (buscando en el catálogo) o **rechaza con motivo**. Lo aprobado se guarda como equivalencia de la institución y se aplica automáticamente en las siguientes cargas; lo rechazado no se vuelve a proponer. «Aplicar correcciones aprobadas» reprocesa el mismo original y genera una base corregida nueva. Finalmente, el analista aprueba o rechaza la base con comentario. Todo queda en `evento_auditoria`.

### Salidas

`original.*` (con datos personales, acceso restringido y descarga registrada), `corregido.xlsx` (formato INE, sin excluidos ni datos personales), `bitacora.xlsx` (Resumen, Hallazgos, Cambios aplicados, Sugerencias, Excluidos) y `reporte.json` (entrada para Quality Improvement).

### Validación contra lo publicado por el INE

`scripts/comparar_con_ine.py` compara el motor con el resultado del INE donde existe con qué comparar:

- **Defunciones julio 2026:** el archivo de RENAP trae la hoja cruda (10 034) y la procesada por el INE (8 841). El motor conserva **exactamente los mismos 8 841 registros**, comparados uno a uno por movimiento, sede y fecha. Excluye 1 098 por año de ocurrencia y 243 por ocurrir fuera de Guatemala (hay registros con ambas condiciones; 1 193 excluidos distintos). La segunda regla se dedujo de esta comparación.
- **Calidad del aire 2025:** aplicando la regla del INE (excluir un mes con más de 2 días con más de 4 horas sin dato), en **11 de 19** combinaciones estación–PM se conservan los mismos meses que la publicación; en las otras 8 la diferencia es de un mes y la decisión publicada no se explica con la misma regla (p. ej., mayo de Correos PM10 excluido con solo 2 horas faltantes).
- **Codificador con IA:** **19 de 20** ejemplos correctos (7/8 motivos PNC, 7/7 causas de muerte, 5/5 sitio de ocurrencia). Muestra pequeña: falta una muestra mayor ya codificada por el INE.
- Nacimientos, detenidos y emergencias no tienen versión procesada del mismo período: se validaron contra la estructura y los códigos de sus bases publicadas.

### Excepciones

Archivo ilegible o sin encabezado reconocible → 422 con mensaje; más de 50 MB → rechazo antes de subir; sin IA → solo similitud; base que tarda más de 300 s en Vercel → no termina (dividirla o desactivar IA).

---

## Quality Improvement: mejora de procedimientos

### Entradas

`reporte.json` de Data Audit (hasta 20 000 hallazgos), institución (deducida de la base) y plantillas `quality-improvement/templates/reglas.json` (30 reglas + `LLAVE_UNICA`) e `institutions.json` (RENAP, PNC, INSIVUMEH, SECONRED).

### Proceso

1. **Agrupación.** Cada hallazgo se agrupa por institución + base + año + mes + regla; el identificador es `sha256(clave)[:24]`, de modo que un nuevo reporte del mismo período **actualiza la evidencia** en lugar de duplicar recomendaciones.
2. **Priorización.** Error → alta, advertencia → media, info → baja; dentro de cada prioridad, por registros afectados.
3. **Texto base por reglas.** Para cada grupo se llenan las plantillas: qué ocurrió (con las cifras y columnas reales), por qué importa, cómo corregir, cómo prevenir y acciones.
4. **Ajuste con IA (opcional).** Claude Haiku 5.5 especifica la propuesta base en lotes de 6 grupos (4 en paralelo), con instrucción de no incluir datos personales; si falla o `MEJORA_IA=0`, queda el texto por reglas. Cada recomendación indica si la generó `reglas` o `ia`.
5. **Revisión y aprobación.** Toda recomendación nace como **borrador**; el revisor la edita, la **aprueba** con nombre y cargo o la **descarta**. Editar una aprobada la devuelve a borrador. Cada cambio queda en su historial.
6. **Manual institucional.** Con las recomendaciones aprobadas de una institución se arma un manual versionado (borrador editable → final). Se exporta a PDF con `fpdf2` y fuentes DejaVu (portada y una sección por recomendación); el borrador lleva el sello «BORRADOR».

### Salidas y límites

Recomendaciones con evidencia y trazabilidad, manuales PDF por institución y versión. **No implementado:** envío automático del manual a la institución, seguimiento de si la recomendación redujo el error en el siguiente período (se puede observar manualmente comparando reportes), tasas por unidad de conteo.

---

## Fuentes metodológicas

- Diccionarios de datos oficiales del INE (defunciones y nacimientos 2018–2022, detenidos PNC) y bases publicadas de cada estadística: ver [fuentes](data-sources.md).
- Cuestionario y Manual del Encuestador ENCOVI 2023 (INE).
- Regla de representatividad de calidad del aire indicada por el INE durante el Datatón.
- Clasificación CIE-10 incluida en el diccionario de defunciones del INE.
- Documentación del modelo JEV de TypeSafe (`audio-audit/encovi_jev/GUIDE_JEV_QUESTIONS.md`) y de los proveedores de ASR (AssemblyAI, Deepgram, WhisperX, Pyannote).
