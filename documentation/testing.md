# Pruebas y resultados

## Resultados reportados por el equipo: Data Audit

| Base | Recibidos | Válidos | Excluidos | Puntaje | Sugerencias | Tiempo |
|---|---:|---:|---:|---:|---:|---:|
| Calidad del aire 2025 | 166440 | 75240 | 91200 | 88.8 | 0 | 7 s |
| Defunciones julio 2026 | 10034 | 8841 | 1193 | 97.8 | 751 | 7 s |
| Nacimientos junio 2026 | 30093 | 22515 | 7578 | 96.9 | 0 | 5 s |
| Emergencias 2025 | 7337 | 7337 | 0 | 96.6 | 5 | 1 s |
| Detenidos octubre 2026 | 4255 | 4255 | 0 | 98.0 | 30 | 1 s |
| Total de registros | 218159 | 118188 | 99971 | — | — | — |

Fuente: README del backend, sección «Resultados con los crudos reales». No se han reproducido estos resultados de forma independiente. Los tiempos no son comparables sin conocer equipo, configuración y condiciones de ejecución. Los totales agregan registros de distinta naturaleza; no representan personas únicas.

El README reporta igualdad en el conteo de defunciones conservadas (8841); no se ha comprobado identidad registro a registro. Los motivos de exclusión citados (1098 y 243) suman 1341 frente a 1193 excluidos; podría existir solapamiento, pero debe verificarse antes de interpretar las cifras. Para aire, se reportan coincidencias en 11 de 19 combinaciones estación/contaminante y diferencias de un mes en las otras ocho; las reglas deben confirmarse con INE.

## Plan de pruebas pendiente

| ID | Prueba | Criterio de aceptación | Estado |
|---|---|---|---|
| A1 | Inicio de servidor local | Página y endpoint `/api/status` disponibles | Pendiente |
| A2 | Audio simulado breve en español | TXT no vacío y marcas ordenadas | Pendiente |
| A3 | Dos voces simuladas | Etiquetas comparables con referencia manual | Pendiente |
| A4 | Audio ruidoso y voces solapadas | Registrar errores y comportamiento de alertas | Pendiente |
| A5 | Archivo vacío / token ausente | Error controlado sin exposición de secretos | Pendiente |
| D1 | Instalación limpia y carga de configuración | Base y definiciones disponibles | Pendiente |
| D2 | Datos sintéticos con nulos y duplicados | Hallazgos y acciones esperados | Pendiente |
| D3 | Archivo autorizado | Original, corregido, bitácora y JSON según configuración | Pendiente |
| D4 | Privacidad | Sin PII en salida publicable ni en Git | Pendiente |
| D5 | Comparación INE | Evidencia y explicación de discrepancias | Pendiente |

Para Audio Audit se propone calcular WER = (sustituciones + eliminaciones + inserciones)/palabras de referencia, y DER para diarización conforme a un protocolo explícito. No existen métricas verificadas en la documentación recibida. Registrar fecha, commit, entorno, muestra, resultado y evidencia de cada prueba.

## Interfaz: matriz de aceptación

| ID | Caso | Criterio | Estado |
|---|---|---|---|
| I01 | Compilar frontend del commit auditado | tsc y Vite terminan sin errores | Aprobado en copia local |
| I02 | Inicio, Audio y Datos | Navegación, teclado y vistas móviles utilizables | Pendiente |
| I03 | Demo con WAV y CSV incluidos | Ejemplos identificados, sin envío a API | Pendiente en navegador |
| I04 | Vacío, extensión y tamaño inválidos | Mensaje y formulario recuperable | Pendiente |
| I05 | Dejar de esperar y reintentar | Recuperación sin afirmar cancelación del servidor | Pendiente |
| I06 | TXT/JSON y filtro de severidad | Descargas identificadas y filtro correcto | Pendiente |
| I07 | Catálogo real | Solo bases con versión activa; error controlado sin conexión | Pendiente |
| I08 | Datos autorizados | Resultado y tres descargas HTTP coherentes con CLI sin guardar | Pendiente |
| I09 | Audio breve real | Progreso, turnos, reproducción y TXT | Pendiente |
| I10 | Diarización con/sin token | Resultado o error controlado, sin exponer token | Pendiente |
| I11 | Dos auditorías simultáneas | Una ejecución por proceso; segunda recibe 409 | Pendiente |
| I12 | Vista previa y publicación | Rutas de proxy disponibles, sin confundir preview con producción | Pendiente |

Evidencia 2026-11-25: npm ci desde caché y npm run build en copia del frontend actual; Vite 6.4.6, ocho módulos. Sin pruebas nuevas de navegador ni motores. Registrar commit, entorno, muestra autorizada, resultado observado y evidencia por cada fila.
