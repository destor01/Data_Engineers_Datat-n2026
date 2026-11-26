# Instalación y configuración

Los siguientes comandos están adaptados a la estructura reorganizada y a Windows PowerShell. No se han ejecutado en una instalación limpia. Trabajar con una copia clonada del repositorio y permisos de acceso vigentes.

## Plataforma completa (API unificada)

Para correr todos los módulos juntos, como en el despliegue, ver [interfaz integrada](interfaz.md#procesamiento-real-api-unificada); para publicarlos en Vercel y Supabase, ver [despliegue](deployment.md). Las secciones siguientes describen cada módulo por separado.

## Audio Audit

Instalar Python compatible con el entorno del equipo (versión exacta pendiente), FFmpeg/FFprobe en PATH y controlador NVIDIA compatible con los paquetes CUDA 12.8 si se usará GPU. Verificar:

```powershell
python --version
ffmpeg -version
ffprobe -version
```

Desde la raíz:

```powershell
cd audio-audit
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Alternativa tras preparar `.venv`: ejecutar `start.bat`. Abrir http://127.0.0.1:8000. El código contempla CPU; la instalación de los paquetes CUDA en equipos sin GPU y su funcionamiento deben probarse.

Dependencias declaradas: torch 2.8.0+cu128, torchvision 0.23.0+cu128, torchaudio 2.8.0+cu128, whisperx (sin fijar), fastapi>=0.115.0, uvicorn[standard]>=0.32.0, python-multipart>=0.0.12, python-dotenv>=1.0.1. El índice adicional es https://download.pytorch.org/whl/cu128.

Para diarización, aceptar el acceso al [modelo](https://huggingface.co/pyannote/speaker-diarization-community-1), crear un [token Read](https://huggingface.co/settings/tokens) y guardarlo localmente desde la interfaz o en `audio-audit/.env` como `HF_TOKEN=...`. La descarga inicial de modelos requiere conectividad. Confirmar la versión de WhisperX y Pyannote efectivamente utilizadas y sus licencias. Para probar sin token, desactivar diarización.

## Data Audit

Instalar Python 3.11+ y PostgreSQL 15+ con servicio iniciado y comandos `createdb`/`psql` en PATH. Usar un rol autorizado con permisos para crear la base o solicitar una base al administrador. Desde la raíz:

```powershell
cd data-audit/qa_bases_datos
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r backend/requirements.txt
createdb -U usuario quality_audit
psql -U usuario -d quality_audit -f schema.sql
cd backend
```

Reemplazar `usuario`, `clave` y las rutas por los valores locales autorizados. Si la contraseña tiene caracteres reservados de URI, codificarlos correctamente. No subir credenciales al repositorio. Ejemplo con variables temporales en la sesión (no usar contraseñas reales en documentación):

```powershell
$env:DATABASE_URL = 'postgresql://usuario:clave@localhost:5432/quality_audit'
..\.venv\Scripts\python.exe -m scripts.cargar_config --db $env:DATABASE_URL --dicc-defunciones 'C:/datos/diccionario-defunciones-2018-2022.xlsx' --dicc-nacimientos 'C:/datos/diccionario-nacimientos-2018-2022.xlsx' --dicc-pnc 'C:/datos/diccionario-detenidos-pnc.xlsx'
..\.venv\Scripts\python.exe -m qa.cli bases
..\.venv\Scripts\python.exe -m qa.cli procesar --base DETENIDOS --archivo 'C:/datos/detenidos_octubre.xlsx' --anio 2026 --mes 10
```

El usuario debe contar con los diccionarios compatibles y archivos de prueba autorizados; los nombres de ejemplo no garantizan disponibilidad. La CLI admite `--almacen`, `--sin-guardar`, `--usuario` y `--todo` según el README. `--sin-guardar` evita escritura en PostgreSQL, no necesariamente archivos locales. Usar un directorio de salida protegido. Para limpiar la variable al terminar: `Remove-Item Env:DATABASE_URL`.

Dependencias declaradas: psycopg[binary]>=3.2, openpyxl>=3.1, pandas>=2.2, PyYAML>=6.0, python-calamine>=0.3, rapidfuzz>=3.9, XlsxWriter>=3.2.

## Reproducibilidad pendiente

Registrar versiones exactas del entorno probado, comprobar ambos módulos después del traslado, preparar muestras autorizadas reproducibles para el jurado y documentar cómo obtener los diccionarios sin publicar material restringido.

## Interfaz común

La instalación completa de Node, modo demo/API, variables y tres servicios se encuentra en [Interfaz integrada](interfaz.md). La ubicación vigente es interfaz/, junto a los dos motores.
