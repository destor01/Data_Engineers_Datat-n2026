# Quality Audit | Datatón INE Guatemala 2026

## Plataforma integrada

La [interfaz](interfaz/README.md) y una **API unificada** (`api/index.py`) reúnen Audio Audit, Data Audit, Survey Audit y Quality Improvement. Se publican en **un proyecto de Vercel y uno de Supabase** (base de datos, archivos privados y login): ver [despliegue](documentation/deployment.md) y [accesos](documentation/accesos.md). Inicio local de todo junto: [interfaz integrada](documentation/interfaz.md#procesamiento-real-api-unificada).

**Equipo:** Data Engineers

Quality Audit es un prototipo modular para apoyar la auditoría de calidad de información estadística mediante procesamiento local de entrevistas y validación de registros administrativos. Busca reducir tareas repetitivas y mejorar la trazabilidad de las decisiones de calidad, sin sustituir la revisión técnica del INE.

## Módulos

| Módulo | Funcionalidad documentada | Estado |
|---|---|---|
| [Audio Audit](audio-audit/README.md) | Transcripción en español, reducción de ruido, marcas temporales, diarización y exportación TXT | Código revisado; ejecución pendiente de verificar tras la reorganización |
| [Data Audit](data-audit/qa_bases_datos/backend/README.md) | Validación, estandarización, sugerencias, exclusiones, puntuación y bitácora | Resultados reportados por el equipo; reproducción pendiente |

La auditoría automática del cumplimiento de preguntas de una boleta y la identificación del rol del encuestador no están confirmadas en la versión revisada. Cada módulo también se puede ejecutar por separado, como se describe abajo.

## Puesta en marcha

**Audio Audit (Windows):** instalar Python compatible con las dependencias, FFmpeg y FFprobe accesibles desde PATH. Se recomienda GPU NVIDIA compatible con los paquetes CUDA 12.8 incluidos. Desde la raíz del repositorio, en PowerShell:

```powershell
cd audio-audit
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Abrir http://127.0.0.1:8000. Para diarización, aceptar las condiciones del [modelo Pyannote](https://huggingface.co/pyannote/speaker-diarization-community-1) y configurar un [token de lectura](https://huggingface.co/settings/tokens) en la interfaz local. No compartir el token.

**Data Audit:** requiere PostgreSQL 15+ y Python 3.11+. Desde la raíz, en PowerShell, con PostgreSQL instalado, en ejecución y sus herramientas en PATH:

```powershell
cd data-audit/qa_bases_datos
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r backend/requirements.txt
createdb -U usuario quality_audit
psql -U usuario -d quality_audit -f schema.sql
cd backend
```

Cargar la configuración y los diccionarios autorizados antes de procesar archivos. Los comandos completos, configuración de credenciales y ejemplos se encuentran en la [guía de instalación](documentation/installation.md). Los crudos y diccionarios institucionales no se incluyen en el repositorio. No se ha verificado todavía una instalación limpia desde esta estructura.

## Documentación

- [Arquitectura](documentation/architecture.md)
- [Metodología](documentation/methodology.md)
- [Instalación](documentation/installation.md)
- [Despliegue en Vercel y Supabase](documentation/deployment.md)
- [Pruebas y resultados](documentation/testing.md)
- [Fuentes de datos](documentation/data-sources.md)
- [Manual de usuario](documentation/user-guide.md)
- [Seguridad y confidencialidad](documentation/security.md)

## Datos y tecnologías

Fuente institucional: [INE Guatemala](https://www.ine.gob.gt/). Ver [fuentes y condiciones de uso](documentation/data-sources.md). Las tecnologías declaradas incluyen Python, PostgreSQL, FFmpeg, WhisperX, PyTorch, Pyannote, FastAPI, Uvicorn, pandas y RapidFuzz. Deben verificarse las licencias de las versiones instaladas y de los pesos de modelos antes de la entrega; no se declara una licencia propia sin autorización del equipo y del INE.

**Estado:** documentación de trabajo basada en el código y README facilitados por el equipo. No acredita una prueba integral ni una certificación institucional.
