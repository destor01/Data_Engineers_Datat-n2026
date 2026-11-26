# Guía para el jurado

Ruta sugerida para entender, probar y evaluar Quality Audit sin ayuda del equipo.

## 1. Acceso

| Recurso | Dónde |
|---|---|
| Plataforma publicada | https://dataton-six.vercel.app |
| Cuentas de la plataforma | [accesos.md](accesos.md) |
| Repositorio | https://github.com/destor01/Data_Engineers_Datat-n2026 — privado; las cuentas de GitHub del jurado ya están invitadas y ven el historial completo ([historial](historial.md)) |
| Archivos de prueba sintéticos | `documentation/ejemplos/` |

> El plan gratuito de Supabase pausa el proyecto tras una semana sin uso. Si la plataforma no responde, avisar al equipo o instalarla localmente (sección 4).

## 2. Recorrido de 20 minutos por la plataforma

| Min. | Módulo | Qué hacer | Qué observar |
|---|---|---|---|
| 0–6 | **Data Audit** | Base *Emergencias · SECONRED*, 2025, marzo; subir `emergencias_sintetica.csv` | Puntaje por dimensión, hallazgos explicados, bandeja: aprobar «Mixcoo», elegir un código, rechazar otro; *Aplicar correcciones aprobadas*; descargar la bitácora |
| 6–10 | **Quality Improvement** | Subir el reporte JSON descargado | Recomendaciones agrupadas con cifras reales; aprobar una con cargo; crear el manual y ver el PDF |
| 10–15 | **Audio Audit** | *¿Ya tienes la transcripción?* → subir `entrevista_encovi_sintetica.json` → *Cargar transcripción* → asignar roles → *Evaluar con JEV* | Veredicto, riesgos con minuto y frase, 51 reglas; editar una regla y ver cómo cambia el puntaje |
| 15–20 | **Survey Audit** | Subir `cuestionario_sintetico.pdf`, revisar y finalizar el formulario, capturar con un error, vincular `transcripcion_sintetica.json` y validar | Errores de captura, pases que ocultan preguntas, discrepancia de «horas de agua» con evidencia |

Paso a paso con capturas: [manual de usuario](user-guide.md).

## 3. Dónde está cada criterio de evaluación

| Criterio | Documento |
|---|---|
| Problema, usuarios, propuesta de valor | [README](../README.md) |
| Funcionalidad y estado real de cada función | [README → Funcionalidades](../README.md), [limitaciones](limitaciones.md#funcionalidades-solicitadas-o-previstas-no-implementadas) |
| Aplicabilidad institucional (y fases de escalamiento) | [aplicabilidad-institucional.md](aplicabilidad-institucional.md) |
| Calidad técnica: arquitectura, API, modelo de datos | [architecture.md](architecture.md), [api-referencia.md](api-referencia.md), [modelo-datos.md](modelo-datos.md) |
| Rigor estadístico y metodología | [methodology.md](methodology.md), [diccionario-datos.md](diccionario-datos.md) |
| Innovación | [innovacion.md](innovacion.md) |
| Facilidad de uso | [user-guide.md](user-guide.md) |
| Evidencia de pruebas y resultados | [testing.md](testing.md) |
| Fuentes de datos | [data-sources.md](data-sources.md) |
| Secreto estadístico y seguridad | [security.md](security.md) |
| Reproducibilidad | [installation.md](installation.md) |
| IA, servicios de pago y nube | [ia-y-servicios.md](ia-y-servicios.md) |
| Licencias de terceros | [licencias.md](licencias.md) |

## 4. Instalarlo y verificarlo localmente

Resumen (detalle en [instalación](installation.md)); en Linux toma unos minutos:

```bash
git clone https://github.com/destor01/Data_Engineers_Datat-n2026.git && cd Data_Engineers_Datat-n2026
python -m venv .venv && . .venv/bin/activate && pip install -r requirements.txt
createdb quality_audit
psql -d quality_audit -f data-audit/qa_bases_datos/schema.sql
psql -d quality_audit -f interfaz/backend/migrations/001_extensions.sql
export DATABASE_URL=postgresql:///quality_audit
(cd data-audit/qa_bases_datos/backend && python -m scripts.cargar_config --db "$DATABASE_URL" \
   --dicc-defunciones <ruta> --dicc-nacimientos <ruta> --dicc-pnc <ruta>)
uvicorn api.index:app --port 8000 &
(cd interfaz && npm ci && npm run dev)
```

Los diccionarios oficiales del INE no están en el repositorio: la organización del Datatón los compartió con los equipos ([fuentes](data-sources.md#diccionarios-oficiales-del-ine)).

## 5. Cómo comprobar las afirmaciones principales

| Afirmación | Cómo comprobarla |
|---|---|
| 40 pruebas automáticas en verde | Comandos de [testing.md](testing.md#cómo-repetir-las-pruebas) |
| Base sintética: 41 registros, puntaje 92.2, 23 hallazgos, 5 sugerencias | `qa.cli procesar` con `emergencias_sintetica.csv` |
| 33 reglas, 31 catálogos, 15 086 códigos | Salida de `cargar_config` |
| 78 operaciones de API | `http://127.0.0.1:8000/docs` en local o [api-referencia.md](api-referencia.md) |
| Fórmulas del puntaje | `data-audit/qa_bases_datos/backend/qa/motor.py` y `audio-audit/encovi_jev/scoring.py` |
| Concordancia con el INE en defunciones y aire | `scripts/comparar_con_ine.py` (requiere los crudos proporcionados por el INE, que no se publican) |
| Sin llaves en el repositorio | `git log -p --all \| grep -iE "sk-ant-[a-z0-9]{10}"` (no devuelve llaves reales) |
| Control de acceso de la API de audio | `python audio-audit/tests/check_security.py` |


