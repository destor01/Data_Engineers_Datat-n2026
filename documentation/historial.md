# Historial de desarrollo

El proyecto se desarrolló durante el Datatón INE Guatemala 2026, del **24 al 26 de noviembre de 2026**, en el repositorio [destor01/Data_Engineers_Datat-n2026](https://github.com/destor01/Data_Engineers_Datat-n2026). El historial completo es público para el jurado en GitHub (`git log --all --graph`); este documento lo resume. Horas en hora de Guatemala (UTC−6).

## Equipo y contribuciones reales

Contribuciones según los commits de la rama principal.

| Integrante | Usuario de GitHub | Commits | Contribuciones principales |
|---|---|---:|---|
| Derek Tórtola | `destor01` | 20 | Motor y API de Data Audit (lectura, reglas, catálogos, puntaje, codificador con IA, bandeja de correcciones, historial); integración de los módulos en una API; despliegue unificado en Vercel + Supabase con login; Survey Audit desde PDF; Quality Improvement con manual PDF; calibración y reporte JEV en la interfaz común; documentación técnica |
| Guillermo Martínez | `guillermo-martinez42` | 4 | Primera versión de Audio Audit (transcripción con WhisperX y diarización); evaluación del encuestador con JEV; transcripción en la nube (AssemblyAI/Deepgram) y evaluaciones editables; endurecimiento de seguridad de la API de audio |
| Jennifer Morales | `Jennifer` | 11 | Organización de los módulos Audio Audit y Data Audit; integración del primer frontend común; documentación inicial y de arquitectura; preparación del despliegue; revisión y fusión de los PR #1, #2, #4 y #5 |

## Ramas

| Rama | Propósito |
|---|---|
| `main` | Versión entregada; se publica en Vercel |
| `audio-audit` | Desarrollo de Audio Audit (transcripción, JEV, nube) |
| `data-audit`, `qa-bases-datos` | Desarrollo del motor y la API de Data Audit |
| `survey-audit`, `quality-improvement` | Desarrollo de los módulos de captura y mejora |
| `fronted`, `integration` | Integración de la interfaz común |
| `deploy-vercel-supabase` | Despliegue unificado |
| `documentation` | Documentación |
| `revert-1-audio-audit`, `revert-2-data-audit` | Reversiones creadas desde GitHub durante la reorganización del 24-nov |

## Pull requests

| PR | Rama | Contenido | Fusionado por |
|---|---|---|---|
| #1 | `audio-audit` | Módulo Audio Audit organizado | Jennifer Morales |
| #2 | `data-audit` | Módulo Data Audit | Jennifer Morales |
| #4 | `data-audit` | Reorganización de Data Audit | Jennifer Morales |
| #5 | `documentation` | Documentación técnica inicial | Jennifer Morales |
| #6 | `qa-bases-datos` | API de QA de bases de datos (fusionado localmente) | Derek Tórtola |
| #7 | `deploy-vercel-supabase` | Despliegue unificado con login | Derek Tórtola |


## Commits de la rama principal

La última columna indica los commits que declaran en el mensaje la coautoría de Claude. Guillermo Martínez usó Gemini Pro y Jennifer Morales ChatGPT Plus como asistentes en sus contribuciones (ver [declaración de IA](ia-y-servicios.md)).

| Fecha | Commit | Autor | Mensaje | Coautoría IA |
|---|---|---|---|---|
| 24-Nov 16:49 | `15f5add` | Guillermo Martínez | first commit |  |
| 24-Nov 21:14 | `80a7fce` | Derek Tórtola (destor01) | Motor de validación de bases de datos (QA) |  |
| 24-Nov 21:30 | `3ae0fb1` | Derek Tórtola (destor01) | API de QA de bases de datos |  |
| 24-Nov 21:40 | `a5ff7ea` | Jennifer Morales | Refactor: organize Audio Audit module |  |
| 24-Nov 21:48 | `81f2cf0` | Jennifer Morales | Merge pull request #1 from destor01/audio-audit |  |
| 24-Nov 21:52 | `f73ceb4` | Jennifer Morales | Merge pull request #2 from destor01/data-audit |  |
| 24-Nov 22:04 | `1d5cd2b` | Jennifer Morales | Refactor: organize Data Audit module |  |
| 24-Nov 22:08 | `b6d8c76` | Jennifer Morales | Merge pull request #4 from destor01/data-audit |  |
| 24-Nov 22:23 | `cb23f7f` | Jennifer Morales | Docs: add Quality Audit technical documentation |  |
| 24-Nov 22:25 | `cd3bd71` | Jennifer Morales | Merge pull request #5 from destor01/documentation |  |
| 24-Nov 22:29 | `7829dca` | Jennifer Morales | Docs: add Data Audit module README |  |
| 25-Nov 11:46 | `980d29d` | Guillermo Martínez | added Jev implementation |  |
| 25-Nov 12:22 | `0c40a40` | Jennifer Morales | Integra frontend de Quality Audit y agrega conexión con Audio Audit y Data Audit |  |
| 25-Nov 13:22 | `e782bca` | Jennifer Morales | Docs: update documentation and frontend architecture |  |
| 25-Nov 18:15 | `e2d9262` | Guillermo Martínez | Cheapest Speech-to-Text + Speaker Diarization (No Hugging Face Token) also added Editable Evaluations (Current Interview + Future Transcripts) and Vercel + Supabase Architecture |  |
| 25-Nov 19:08 | `9c00a3a` | Derek Tórtola (destor01) | Codificador con IA y sitio de defunción |  |
| 25-Nov 19:54 | `c8c8439` | Jennifer Morales | deploy+ |  |
| 25-Nov 21:09 | `7c5d09f` | Derek Tórtola (destor01) | Documentación técnica del módulo de QA |  |
| 25-Nov 21:10 | `369981c` | Derek Tórtola (destor01) | Integra el módulo de QA en data-audit |  |
| 25-Nov 21:29 | `af2106c` | Guillermo Martínez | Harden audio-audit API: auth, CSRF/rebinding guards, input limits |  |
| 25-Nov 21:48 | `870cacf` | Derek Tórtola (destor01) | Merge qa-bases-datos: API de QA de bases de datos (PR #6) | Sí |
| 25-Nov 21:48 | `8ad6490` | Derek Tórtola (destor01) | Merge audio-audit: transcripción en la nube, evaluación JEV y almacenamiento en Supabase | Sí |
| 25-Nov 22:07 | `52e8caa` | Derek Tórtola (destor01) | Despliegue unificado: un proyecto de Vercel y uno de Supabase con login | Sí |
| 25-Nov 22:21 | `3158e05` | Derek Tórtola (destor01) | supabase: permisos explícitos para service_role en seguridad.sql | Sí |
| 25-Nov 22:39 | `7eb6171` | Derek Tórtola (web de GitHub) | Merge pull request #7 from destor01/deploy-vercel-supabase |  |
| 25-Nov 23:13 | `b306682` | Derek Tórtola (destor01) | Desplegar en Vercel |  |
| 25-Nov 23:15 | `a86aacf` | Derek Tórtola (destor01) | vercel.json: acortar excludeFiles (máximo 256 caracteres) | Sí |
| 25-Nov 23:18 | `63b3ab4` | Derek Tórtola (destor01) | interfaz: mostrar el motivo real cuando falla el inicio de sesión | Sí |
| 26-Nov 01:22 | `51cdb83` | Derek Tórtola (destor01) | Survey Audit desde PDF y Quality Improvement con manual en PDF | Sí |
| 26-Nov 01:37 | `d252fb2` | Derek Tórtola (destor01) | Survey Audit: menos tokens en la lectura del PDF y la verificación | Sí |
| 26-Nov 01:51 | `d86fbea` | Derek Tórtola (destor01) | Usar Claude Haiku 5.5 en toda la plataforma | Sí |
| 26-Nov 01:59 | `22e9234` | Derek Tórtola (destor01) | Audio Audit: calibración de la evaluación JEV con las ediciones del supervisor | Sí |
| 26-Nov 02:31 | `a8ed82c` | Derek Tórtola (destor01) | Survey Audit: leer tablas grandes del PDF sin pasarse del límite | Sí |
| 26-Nov 02:48 | `70378b2` | Derek Tórtola (destor01) | Audio Audit: evaluación JEV y reporte de puntajes en la interfaz común | Sí |
| 26-Nov 03:05 | `def8d15` | Derek Tórtola (destor01) | Data Audit: historial de bases, bandeja de correcciones y correcciones guardadas | Sí |

Tras estos commits se agrega la documentación de entrega (este documento y los demás de `documentation/`).
