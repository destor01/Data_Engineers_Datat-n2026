# Declaración de uso de inteligencia artificial, servicios de pago y servicios en la nube

Declaración obligatoria según la Nota Conceptual del Datatón. Se separan dos usos: la IA que **ayudó a construir** el sistema y la IA que **forma parte** del producto.

## 1. IA usada en el desarrollo

| Herramienta | Finalidad | Participación | Supervisión | Ejecución | Limitaciones |
|---|---|---|---|---|---|
| **Claude Opus 5.5** (Anthropic), mediante Claude Code | Asistente de programación: redactar y modificar código, pruebas, scripts de captura, migraciones y documentación; depurar errores de despliegue; revisar costos de tokens | Coautor declarado en 13 commits de la rama principal (trailer `Co-Authored-By: Claude Opus 5.5`, ver [historial](historial.md)), en Survey Audit, Quality Improvement, la integración de JEV en la interfaz, la bandeja de Data Audit, el despliegue y esta documentación | Derek Tórtola definió cada requerimiento, revisó los cambios, ejecutó las pruebas y decidió qué se publicaba. Toda cifra de la documentación sale de pruebas ejecutadas o del código | Externa (servicio de Anthropic). Sin acceso a llaves: los secretos se configuraron solo en Vercel | Puede proponer código con errores; por eso cada cambio se verificó con pruebas unitarias y recorridos en navegador. No tuvo acceso a los crudos con datos personales |
| **Gemini Pro** (Google) | Asistente de programación y redacción usado por Guillermo Martínez en sus contribuciones a Audio Audit | Apoyo en el código de transcripción, evaluación JEV y seguridad de la API de audio | Guillermo Martínez revisó y probó lo generado antes de cada commit | Externa (servicio de Google) | Puede proponer código con errores; sin acceso a llaves ni a datos con información personal |
| **ChatGPT Plus** (OpenAI) | Asistente de programación y redacción usado por Jennifer Morales en sus contribuciones | Apoyo en la organización de módulos, la interfaz común y la documentación inicial | Jennifer Morales revisó y probó lo generado antes de cada commit | Externa (servicio de OpenAI) | Puede proponer código con errores; sin acceso a llaves ni a datos con información personal |

## 2. IA integrada en el producto

| Herramienta | Módulo y finalidad | Participación en el resultado | Supervisión humana | Ejecución | Limitaciones |
|---|---|---|---|---|---|
| **Claude Haiku 5.5** (`claude-haiku-5-5`, API de Anthropic) | Survey Audit: leer el PDF (texto e imagen de página) y armar el formulario | Propone secciones, preguntas, opciones y pases | El formulario es borrador hasta que el analista lo revisa y finaliza | Externa | Puede omitir o leer mal celdas de tablas complejas; páginas no leídas se marcan |
| Claude Haiku 5.5 | Survey Audit: conciliar respuestas con la grabación | Clasifica cada respuesta en coincide / no coincide / no verificable con evidencia | Cada resultado queda pendiente de confirmar o descartar; nunca cambia respuestas | Externa | Exactitud no medida |
| Claude Haiku 5.5 | Data Audit: sugerir códigos de catálogo para texto libre (motivo PNC, causa CIE-10, sitio) | Sugerencia con confianza ≥ 0.6 y justificación | Toda sugerencia requiere aprobación; códigos inexistentes se descartan | Externa; alternativa local con Ollama o desactivable | 19/20 aciertos en una muestra pequeña |
| Claude Haiku 5.5 | Quality Improvement: precisar el texto de las recomendaciones | Reescribe la propuesta base de cada grupo | Toda recomendación nace como borrador y requiere aprobación con cargo | Externa; desactivable (`MEJORA_IA=0`) | Puede generalizar; la evidencia y las cifras vienen del reporte, no del modelo |
| **JEV** (`typesafe/jev-1.14`, vía OpenRouter) | Audio Audit: juzgar si se cumplió cada regla del manual del encuestador | Devuelve probabilidades; el puntaje lo calcula el sistema con fórmulas documentadas | El auditor puede corregir cada regla; la calibración aprende de esas correcciones | Externa | No calibrado con etiquetas del INE; exactitud no medida |
| **AssemblyAI** (modelo Universal por defecto) / **Deepgram Nova-3** | Audio Audit: transcripción en español y diarización | Produce el texto y los hablantes | El auditor revisa el texto y asigna los roles | Externa | WER/DER no medidos; ruido y variantes del español afectan |
| **WhisperX** (pesos Whisper de OpenAI) + **Pyannote** `speaker-diarization-community-1` | Audio Audit en modo local | Igual que el anterior | Igual | **Local** (GPU opcional) | Requiere GPU para tiempos razonables y token de Hugging Face para Pyannote |
| **RapidFuzz** (no es IA generativa) | Data Audit: similitud de texto | Sugerencias por parecido de escritura | Igual que las de IA | Local | Solo corrige variantes de escritura |

**Principio aplicado:** ninguna salida de IA se convierte en dato oficial sin una decisión humana registrada.

## 3. Servicios de pago y en la nube

| Servicio | Uso | Plan usado en el Datatón | Costo | Restricciones |
|---|---|---|---|---|
| **Vercel** | Publica la interfaz y la API (función Python) | Hobby (gratuito) | 0 | 300 s máximo por petición; uso no comercial según el plan |
| **Supabase** | PostgreSQL 16, Storage privado y Auth | Free | 0 | 50 MB por archivo, 500 MB de base, 1 GB de archivos; el proyecto se pausa tras una semana sin uso |
| **GitHub** | Repositorio y control de versiones | Gratuito | 0 | — |
| **Anthropic API** (Claude Haiku 5.5) | IA de Survey, Data Audit y QI | Pago por uso | 0.10 USD por millón de tokens de entrada y 0.50 USD por millón de salida (prompts ≤ 100 mil tokens; precio vigente al 25-nov-2026) | Requiere llave y crédito |
| **OpenRouter** → JEV | Evaluación del encuestador | Pago por uso | 0.042 USD por millón de tokens de entrada; salida sin costo | Requiere llave |
| **AssemblyAI** | Transcripción y diarización | Pago por uso (con crédito inicial) | ≈ 0.15 USD por hora de audio + 0.02 USD por hora de diarización | Requiere llave |
| **Deepgram** (alternativo) | Transcripción | Pago por uso (con crédito inicial) | Según su tarifa vigente | Requiere llave |
| **Hugging Face** | Descarga del modelo Pyannote (modo local) | Gratuito | 0 | Aceptar condiciones del modelo y token |

Los precios cambian: verificar en la página de cada proveedor antes de presupuestar.

## Costos

### Medidos o estimados con el uso real

| Operación | Costo | Base |
|---|---|---|
| Data Audit, primera carga de defunciones con IA (≈ 10 000 textos) | ≈ 0.32 USD | Estimación del equipo con tokens por lote (`DOCUMENTACION.md`) |
| Data Audit, primera carga de PNC (≈ 520 textos) | ≈ 0.014 USD | Ídem |
| Data Audit, cargas siguientes | Una fracción de la primera | Las sugerencias se guardan y no se vuelven a pedir |
| Data Audit sin IA | 0 | `QA_IA_PROVEEDOR=ninguno` |
| Evaluación JEV de la entrevista de ejemplo (simulada) | El reporte muestra tokens y costo por evaluación | Campo `usage` del reporte |
| Generar el formulario del cuestionario ENCOVI 2023 (72 páginas) | **1.04 USD por cuestionario** | Medido con la arquitectura actual (Haiku 5.5, bloques de 2 páginas, tablas compactas y lectura por zonas) |

### Medidas de reducción de costo implementadas

- Haiku 5.5 en toda la plataforma (el modelo más económico de Claude).
- Caché de la transcripción en la conciliación (los grupos siguientes pagan ≈ 10 % de ese texto) y grupos de 80 preguntas.
- Tablas compactas en la lectura del PDF y lectura por zonas solo cuando una página no cabe.
- Data Audit: solo textos distintos, lo que la similitud resuelve no va a la IA y cada sugerencia se paga una sola vez.
- Todo módulo funciona sin IA (con menos automatización).

### Costo de adopción estimado (propuesta)

Con infraestructura propia del INE (un servidor con PostgreSQL) el software no tiene costo de licencia; el gasto variable queda en los servicios de IA y transcripción que se decida usar, o en una GPU si se opta por el modo local. Ver [aplicabilidad institucional](aplicabilidad-institucional.md).
