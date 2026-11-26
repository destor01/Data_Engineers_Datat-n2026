# Pruebas y resultados

Este documento reúne la evidencia de que el sistema funciona: matriz de pruebas, resultados cuantitativos y cómo repetirlas. Se distingue siempre entre lo **verificado** (ejecutado y observado), lo **reportado por el equipo** (ejecutado con datos confidenciales que no pueden publicarse) y lo **no medido**.

**Entorno de prueba:** Ubuntu 24.04.5, 2 vCPU, 7 GB RAM, Python 3.13.18, Node 22.23.5, PostgreSQL 16.15, Chrome for Testing 153 con Playwright 1.65.2. Commit `def8d15` (más la documentación). Fecha: 25–26 nov 2026.

## Matriz de pruebas

Estado: ✅ verificado · 🟡 parcial (con la limitación indicada).

| ID | Prueba | Datos usados | Procedimiento | Resultado esperado | Resultado obtenido | Estado |
|---|---|---|---|---|---|---|
| T01 | **Instalación limpia** | Repositorio clonado en carpeta vacía; diccionarios oficiales del INE | Pasos 2–6 de [instalación](installation.md) en un entorno nuevo | Dependencias, esquema, catálogos, API e interfaz funcionando | `pip install` 9.8 s (43 paquetes); esquemas aplicados; `cargar_config` 2.4 s (33 reglas, 5 bases, 31 catálogos, 15 086 códigos); `npm ci` + build 5.5 s | ✅ |
| T02 | **Inicio de servicios** | — | `uvicorn api.index:app`; `vite preview`; `/api/salud` | API e interfaz responden; protección por host | `{"ok":true,"login":false,"entorno":"local"}`; `/api/qa/bases` lista 5; host ajeno → 403 | ✅ |
| T03 | **Carga de audio** | Audio de prueba (sin voz) y Supabase simulado | Pedir URL firmada, subir y crear trabajo | URL firmada, archivo en bucket privado, `job_id` | Flujo completo con almacenamiento simulado (`flujo.py`: «FLUJO OK»); límite de 50 MB validado en la interfaz | 🟡 con Storage simulado; en producción lo usa el equipo |
| T04 | **Transcripción** | — | AssemblyAI / Deepgram / WhisperX | Turnos con hablante y tiempos | Sin grabación real autorizada; se probaron la carga de transcripciones (JSON/TXT) y la normalización de hablantes | 🟡 · **WER y DER no medidos** |
| T05 | **Auditoría de entrevista** | Transcripción ENCOVI sintética con errores sembrados (A1-08, A1-11, A1-12, A2-10) | Asignar roles → evaluar → revisar reporte → editar una regla → calibración | Veredicto, puntaje por sección, riesgos con evidencia, edición recalcula | Evaluación simulada: 91 % global (A1 83 %, A2 97 %); tras editar una regla → 89 %; 51 reglas listadas; 30 pruebas unitarias de JEV en verde | ✅ con JEV simulado · **exactitud de JEV no medida** |
| T06 | **Carga de PDF** | PDF sintético de 5 páginas; Cuestionario ENCOVI 2023 (72 p.) | Subir, preparar bloques y leer | Bloques leídos; página difícil no detiene el documento | Sintético: lectura completa con una página que fuerza lectura por zonas y marcador `pagina_no_leida`. ENCOVI en producción: las 72 páginas leídas y formulario generado tras corregir la página 6 con tablas compactas y zonas; costo 1.04 USD | ✅ |
| T07 | **Generación de formulario** | Lecturas del PDF sintético | Armar formulario, editar, finalizar | Formulario v2 con secciones, pases, tablas y sección por persona | Formulario generado y finalizado; secciones abiertas se conservan al editar | ✅ |
| T08 | **Validación de respuestas** | Formulario piloto y generado | Capturar con errores y finalizar | Errores de obligatoriedad, tipo, catálogo, rango; pases ocultan preguntas | 6 pruebas unitarias (pases, alcance por persona, conservación de respuestas inactivas) + recorrido en navegador: 422 con lista de errores y navegación a cada pregunta | ✅ |
| T09 | **Conciliación** | `hogar15-transcripcion.json` sintética | Vincular con autorización, elegir encuestador, verificar, revisar hallazgos | Coincidencia / discrepancia / no verificable con evidencia; respuestas registradas sin cambios | Hallazgos con turnos de evidencia; revisión confirmada/descartada; sin autorización → 422 | ✅ con IA simulada · **exactitud no medida** |
| T10 | **Carga de bases** | CSV sintético (41 filas); 5 crudos reales | Subir por la interfaz y por CLI | Encabezado detectado, columnas emparejadas | Sintético: 41 registros, CSV con encabezado en fila 1 detectado; reales: 53/53, 24/24, 49/50, 82/82 columnas reconocidas | ✅ sintético · ✅ reales (equipo) |
| T11 | **Detección de errores** | Mismos | Procesar | Hallazgos por regla y dimensión | Sintético: 23 hallazgos, puntaje 92.2; reales: ver tabla de resultados | ✅ |
| T12 | **Corrección de datos** | CSV con municipios mal escritos | Aprobar, elegir código, rechazar con motivo; reprocesar | Bandeja; equivalencias reutilizadas; rechazados no vuelven | 5–8 sugerencias en bandeja; puntaje 91.2 → 91.6 tras reprocesar; la equivalencia se aplicó sola en la siguiente carga; valor rechazado no se volvió a proponer | ✅ |
| T13 | **Generación de reportes** | Mismos | Descargar salidas | Original, corregido, bitácora, reporte JSON | 4 archivos; `emergencias_2025_03_corregido.xlsx` descargado desde la interfaz; descarga del original registrada | ✅ |
| T14 | **Recomendaciones** | `reporte.json` del CSV sintético | Importar en QI, editar, aprobar con cargo, descartar | Grupos por institución+base+período+regla; reimportar no duplica | Recomendaciones agrupadas y priorizadas; reimportación actualiza evidencia; editar una aprobada la regresa a borrador | ✅ (texto por reglas; IA simulada) |
| T15 | **Manual institucional** | Recomendaciones aprobadas | Crear, editar, finalizar, PDF | Manual versionado y PDF legible | PDF con portada y una sección por recomendación aprobada; el borrador lleva el sello «BORRADOR» | ✅ |
| T16 | **Manejo de errores** | Entradas inválidas | Archivo vacío/extensión no válida, > 50 MB, sin sesión, host ajeno, origen ajeno, IA no configurada, IA ocupada, reporte de QI con otro formato | Mensaje claro sin exponer secretos | 401 sin sesión; 403 host/origen; 413/422 por tamaño o formato; 503 sin `ANTHROPIC_API_KEY`; reintento automático ante 429; `check_security` en verde | ✅ |

Los recorridos completos en navegador (Playwright) se ejecutaron con Supabase y la IA **simulados** para no gastar créditos ni usar datos reales: `nav_datos`, `nav_survey`, `nav_audio`, `nav_qi`, `navegador` (interfaz general) y `flujo` (subida a Storage + procesamiento), los seis en verde. Las capturas del [manual de usuario](user-guide.md) salen de esos recorridos.

## Resultados con crudos reales

Ejecutados por el equipo con los crudos que entregó el INE, en sus computadoras (los datos no pueden publicarse). Fuente: `data-audit/qa_bases_datos/backend/README.md`; se repiten con `scripts/comparar_con_ine.py`.

| Base | Recibidos | Válidos | Excluidos | Puntaje | Sugerencias pendientes | Tiempo |
|---|---:|---:|---:|---:|---:|---:|
| Calidad del aire 2025 (INSIVUMEH) | 166 440 lecturas | 75 240 | 91 200 | 88.8 | 0 | 7 s |
| Defunciones julio 2026 (RENAP) | 10 034 | 8 841 | 1 193 | 97.8 | 751 | 7 s |
| Nacimientos junio 2026 (RENAP) | 30 093 | 22 515 | 7 578 | 96.9 | 0 | 5 s |
| Emergencias 2025 (SECONRED) | 7 337 | 7 337 | 0 | 96.6 | 5 | 1 s |
| Detenidos octubre 2026 (PNC) | 4 255 | 4 255 | 0 | 98.0 | 30 | 1 s |
| **Total** | **218 159** | **118 188** | **99 971** | — | **786** | **21 s** |

Los totales suman registros de distinta naturaleza (lecturas, inscripciones, hechos), no personas.

**Registros excluidos y motivos**

| Base | Motivo (regla) | Registros |
|---|---|---:|
| Calidad del aire | Mes no representativo: más de 2 días con más de 4 horas sin dato (`AIRE_MES_REPRESENTATIVO`) | 91 200 lecturas |
| Defunciones | Ocurrida fuera del año de la carga (`DEF_PERIODO_OCURRENCIA`) | 1 098 |
| Defunciones | Ocurrida fuera de Guatemala (`DEF_OCURRIO_EXTRANJERO`) | 243 |
| Defunciones | Total distinto (hay registros con ambos motivos) | 1 193 |
| Nacimientos | Ocurrido fuera del año de la carga (`NAC_PERIODO_OCURRENCIA`) | 7 578 |

**Validación contra lo publicado por el INE**

| Comparación | Resultado |
|---|---|
| Defunciones: registros conservados vs. hoja procesada por el INE | **8 841 de 8 841** idénticos (uno a uno por movimiento, sede y fecha) |
| Calidad del aire: meses conservados vs. publicación 2025 | **11 de 19** combinaciones estación–PM idénticas; 8 difieren en un mes (decisiones del INE no explicables con su propia regla) |
| Codificador con IA vs. código correcto | **19 de 20** (motivos PNC 7/8, causas de muerte 7/7, sitio 5/5). Muestra pequeña |
| Columnas reconocidas | nacimientos 53/53, emergencias 24/24, detenidos 49/50 (la faltante es una columna sin nombre), defunciones 82/82 |
| Textos cubiertos por equivalencias sin IA | sexo, escolaridad, sitio de nacimiento y día de la semana 100 %; estado civil 99.8–100 %; MOTIVO de PNC 24.5 % (el resto va a sugerencias) |

**Hallazgos relevantes para el INE:** códigos de departamento y municipio inexistentes enviados por RENAP («0519», «0137», depto 43); 5 796 nacimientos (19 %) sin departamento de ocurrencia; cambios de columnas entre meses en SECONRED, valores «**» en conteos y caracteres dañados; 531 textos distintos de MOTIVO en PNC sin código.

## Resultados cuantitativos (resumen)

| Indicador | Valor | Tipo |
|---|---|---|
| Registros procesados (crudos reales) | 218 159 | Reportado por el equipo |
| Registros excluidos y motivos | 99 971 (ver tabla) | Reportado |
| Sugerencias pendientes de aprobación (reales) | 786 | Reportado |
| Puntajes de calidad (reales) | 88.8 – 98.0 | Reportado |
| Tiempo de procesamiento por base (reales) | 1 – 7 s | Reportado |
| Reglas aplicadas | Data Audit 33 · Audio Audit 51 · Survey 5 tipos de validación + pases · QI 31 plantillas | Verificado en código |
| Costo de IA para generar el formulario de la ENCOVI 2023 (72 páginas) | 1.04 USD por cuestionario | Medido en producción |
| Base sintética: registros / hallazgos / sugerencias / puntaje / tiempo | 41 / 23 / 5 / 92.2 / 0.67 s | Verificado |
| Correcciones aplicadas en la prueba de bandeja | aprobadas, elegidas y rechazadas; puntaje 91.2 → 91.6 | Verificado |
| Concordancia con el INE (defunciones) | 100 % (8 841/8 841) | Reportado, reproducible con el script |
| Exactitud del codificador con IA | 95 % (19/20) | Reportado, muestra pequeña |
| Exactitud de transcripción (WER), diarización (DER), JEV, extracción del PDF, conciliación | **No medida** | — |
| Pruebas automáticas | 40 en verde (Survey 6, extensiones 4, JEV 30) + `check_security` + verificación de tipos de la interfaz | Verificado |

## Lo que no se midió y cómo medirlo

| Métrica | Por qué no se midió | Protocolo propuesto |
|---|---|---|
| WER de la transcripción | Sin grabaciones reales autorizadas | 20+ entrevistas con transcripción manual de referencia; WER = (sustituciones + eliminaciones + inserciones) / palabras de referencia |
| DER de la diarización | Mismo motivo | Segmentos de hablante anotados a mano; DER con collar de 0.25 s |
| Exactitud de JEV | Sin etiquetas de auditores del INE | ≥ 30 evaluaciones etiquetadas por grupo de reglas; Brier, ECE y acuerdo con el auditor (ya implementados en `calibration.py`) |
| Extracción del cuestionario | Sin versión digital de referencia | Comparar preguntas, opciones y pases extraídos con la versión oficial del CAPI del INE |
| Conciliación | Sin entrevistas reales con grabación | Sembrar discrepancias conocidas y medir sensibilidad y especificidad |

## Cómo repetir las pruebas

```bash
# Survey Audit: motor de validación (6 pruebas)
cd survey-audit && PYTHONPATH=backend python -m pytest -q tests

# Extensiones: lectura por zonas, formularios, QI (4 pruebas)
cd interfaz/backend && python -m pytest -q tests

# Audio Audit: matemáticas de JEV, reglas y calibración (30 pruebas) y seguridad
cd audio-audit/encovi_jev && python -m pytest -q
cd audio-audit && python tests/check_security.py

# Interfaz: verificación de tipos y compilación
cd interfaz && npm run typecheck && npm run build

# Data Audit: base sintética de punta a punta (requiere catálogos cargados)
cd data-audit/qa_bases_datos/backend
python -m qa.cli procesar --base EMERGENCIAS --archivo ../../../documentation/ejemplos/emergencias_sintetica.csv \
  --anio 2025 --mes 3 --sin-guardar --almacen /tmp/salida
```

Resultado esperado del último comando: 41 registros, puntaje 92.2 (estructura 100, completitud 67.3, validez 91.1, consistencia 100, unicidad 95.1, oportunidad 100), 23 hallazgos y 5 sugerencias pendientes.
