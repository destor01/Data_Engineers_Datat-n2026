# Instalación y reproducibilidad

Esta guía permite instalar, ejecutar y verificar Quality Audit sin ayuda del equipo. Hay tres formas de usarlo:

| Forma | Para qué sirve | Qué se necesita |
|---|---|---|
| **A. Plataforma publicada** | Evaluar sin instalar nada | Navegador y una cuenta (ver [accesos](accesos.md)) |
| **B. Instalación local mínima** | Reproducir Data Audit, la API y la interfaz en una computadora | Python, Node.js y PostgreSQL |
| **C. Despliegue propio en la nube** | Publicar una copia institucional | Cuentas de Vercel y Supabase (ver [despliegue](deployment.md)) |

Las cifras de esta página (tiempos, versiones, conteos) salen de la **instalación limpia del 26-nov-2026** descrita en [Pruebas](testing.md#matriz-de-pruebas): se clonó el repositorio en una carpeta vacía (commit `def8d15`) y se siguieron estos pasos sin ningún archivo previo.

## 1. Requisitos

### Hardware

| Recurso | Probado | Observación |
|---|---|---|
| CPU | 2 vCPU (x86-64) | Suficiente para Data Audit con las 5 bases reales: la más grande (166 440 filas) tardó 7 s según el equipo. |
| RAM | 7 GB | No se midió el pico de memoria. La base de aire (166 440 filas × 12 columnas) se procesó sin problema en el equipo del equipo de desarrollo. |
| Disco | ~1 GB libre | Entorno Python ≈ 400 MB, `node_modules` ≈ 60 MB, catálogos en PostgreSQL < 20 MB. |
| GPU | **No necesaria** | La transcripción publicada usa AssemblyAI (nube). La GPU solo sirve para el modo opcional con WhisperX local; ese modo **no se midió** en esta versión. |
| Red | Necesaria para IA y transcripción | Data Audit, la validación de formularios y la interfaz funcionan sin internet si `QA_IA_PROVEEDOR=ninguno`. |

### Sistema operativo

| Sistema | Estado |
|---|---|
| Linux (Ubuntu 24.04.5) | **Verificado** con instalación limpia completa (todos los pasos de esta guía). |
| Windows 10/11 (PowerShell) | Usado por el equipo para desarrollar y para preparar Supabase (`supabase/configurar.py`, `cargar_config`). **No se hizo una instalación limpia documentada**; los comandos equivalentes de PowerShell se muestran en cada paso. |
| macOS | No probado. |
| Vercel (Linux, Python 3.12) | Verificado: es el entorno de producción. |

### Software y versiones probadas

| Componente | Versión probada | Requerido para |
|---|---|---|
| Python | 3.13.18 (instalación limpia) · 3.12 (Vercel, `.python-version`) | API y motores |
| Node.js / npm | 22.23.5 / 10.9.9 | Compilar la interfaz (Vite 6 exige Node 20.19+ o 22.12+) |
| PostgreSQL | 16.15 (local) · 16 (Supabase) | Catálogos, cargas, correcciones y estado de Survey/QI |
| Git | cualquiera reciente | Clonar el repositorio |
| FFmpeg | 6.1.1 | Solo transcripción local con WhisperX |
| Chrome for Testing + Playwright | 153 / 1.65.2 | Solo para repetir las pruebas de navegador |

Las 43 librerías de Python que instala `requirements.txt` y sus licencias están en [licencias](licencias.md). Las versiones exactas resueltas en la prueba fueron, entre otras: fastapi 0.165.0, uvicorn 0.54.0, pydantic 2.14.4, psycopg 3.3.9, pandas 3.1.1, openpyxl 3.1.5, python-calamine 0.9.1, rapidfuzz 3.14.6, XlsxWriter 3.3.4, anthropic 2.14.0, pypdf 7.1.1, fpdf2 2.9.0. `requirements.txt` fija mínimos (`>=`) y no topes, por lo que una instalación futura puede resolver versiones más nuevas; para repetir exactamente el entorno probado use `pip install fastapi==0.165.0 …` con la lista de [licencias](licencias.md#python).

## 2. Obtener el código

```bash
git clone https://github.com/destor01/Data_Engineers_Datat-n2026.git
cd Data_Engineers_Datat-n2026
```

La rama `main` contiene la versión entregada. El historial de ramas y contribuciones está en [historial](historial.md).

## 3. Configuración (`.env`)

Copiar la plantilla y llenar solo lo necesario. **Nunca subir `.env` al repositorio** (ya está en `.gitignore`).

```bash
cp .env.example .env                       # PowerShell: Copy-Item .env.example .env
cp interfaz/.env.example interfaz/.env.local
```

### Variables del servidor (`.env` en la raíz)

| Variable | Obligatoria | Secreta | Uso |
|---|---|---|---|
| `DATABASE_URL` | **Sí** | Sí | PostgreSQL. Local: `postgresql://usuario:clave@127.0.0.1:5432/quality_audit`. Vercel: cadena *Transaction pooler* (puerto 6543). |
| `SUPABASE_URL` | No | No | Activa login y almacenamiento en Supabase. Sin ella: sin login, la API solo atiende `localhost` y los archivos se guardan en disco. |
| `SUPABASE_ANON_KEY` | Con Supabase | No (pública) | Verificación de sesiones. |
| `SUPABASE_SERVICE_ROLE_KEY` | Con Supabase | **Sí** | Firma de URLs y acceso a buckets privados. |
| `SUPABASE_STORAGE_BUCKET` | No | No | Bucket de audios (`audio-interviews`). |
| `QA_STORAGE_BUCKET` | No | No | Bucket de Data Audit (`qa-cargas`). |
| `SURVEY_STORAGE_BUCKET` | No | No | Bucket de cuestionarios PDF (`encuestas`). |
| `QA_MAX_MB` | No | No | Tamaño máximo de una base (50). |
| `QA_IA_PROVEEDOR` | No | No | `anthropic`, `ollama` o `ninguno`. Por defecto `anthropic` si hay llave. |
| `QA_IA_MODELO`, `QA_IA_LOTE`, `QA_IA_PARALELO` | No | No | Modelo (por defecto `claude-haiku-5-5`), valores por lote (40) e hilos (4) del codificador con IA. |
| `ANTHROPIC_API_KEY` | Para IA | **Sí** | Lectura del PDF y verificación en Survey, redacción en QI, codificador de Data Audit. |
| `SURVEY_IA_MODELO`, `SURVEY_VERIF_MODELO`, `MEJORA_IA_MODELO` | No | No | Modelo por función (todos `claude-haiku-5-5` por defecto). |
| `SURVEY_PAGINAS_BLOQUE` | No | No | Páginas del PDF por petición (2). |
| `MEJORA_IA` | No | No | `0` para que QI use solo las plantillas, sin IA. |
| `ASSEMBLYAI_API_KEY` / `DEEPGRAM_API_KEY` | Para audio en la nube | **Sí** | Transcripción y diarización. |
| `OPENROUTER_API_KEY` | Para evaluación JEV | **Sí** | Evaluación del encuestador con JEV. |

### Variables de la interfaz (`interfaz/.env.local`)

| Variable | Valor | Nota |
|---|---|---|
| `VITE_APP_MODE` | `api` | `demo` muestra ejemplos sin backend. |
| `VITE_SUPABASE_URL`, `VITE_SUPABASE_ANON_KEY` | vacías en local | Si se llenan, la interfaz pide iniciar sesión. Son **públicas**: nunca poner aquí una llave secreta. |
| `VITE_MAX_AUDIO_MB`, `VITE_MAX_DATA_MB` | 50 | Límites mostrados y validados en el navegador. |
| `API_BACKEND_URL` | `http://127.0.0.1:8000` | Solo desarrollo: adónde reenvía Vite las rutas `/api/*`. |

## 4. Base de datos

### 4.1 Crear la base y aplicar los esquemas

```bash
createdb quality_audit
psql -d quality_audit -f data-audit/qa_bases_datos/schema.sql
psql -d quality_audit -f interfaz/backend/migrations/001_extensions.sql
```

En **Supabase** se usa en su lugar un solo script, que aplica en orden los cuatro archivos (Data Audit, Audio Audit, Survey/QI y seguridad) y se puede repetir sin dañar datos:

```bash
python supabase/configurar.py          # usa DATABASE_URL (cadena Session pooler)
```

`audio-audit/supabase/schema.sql` y `supabase/seguridad.sql` crean buckets y políticas de Supabase Storage (`storage.buckets`); en un PostgreSQL local sin Supabase no aplican y no son necesarios. El modelo resultante está en [modelo de datos](modelo-datos.md).

### 4.2 Cargar reglas y catálogos del INE

Data Audit necesita los diccionarios **públicos** del INE (ver [fuentes](data-sources.md#diccionarios-públicos-del-ine)). No se versionan en el repositorio; se descargan del portal del INE y se indican por ruta. Los tres argumentos son obligatorios:

```bash
cd data-audit/qa_bases_datos/backend
python -m scripts.cargar_config --db "$DATABASE_URL" \
  --dicc-defunciones /ruta/diccionario-defunciones-2018-2022.xlsx \
  --dicc-nacimientos /ruta/diccionario-nacimientos-2018-2022.xlsx \
  --dicc-pnc /ruta/diccionario-detenidos-pnc.xlsx
```

Resultado esperado (2.4 s en la prueba): 28 reglas de `reglas.yaml` + 5 de llave única = **33 reglas**; **5 bases** activas (CALIDAD_AIRE 12 variables, DEFUNCIONES 82, DETENIDOS 58, EMERGENCIAS 26, NACIMIENTOS 57); **31 catálogos**, **15 086 códigos**, **761 equivalencias**, 235 variables y 340 alias de columnas.

## 5. Instalación

Desde la raíz del repositorio:

```bash
python -m venv .venv
. .venv/bin/activate                      # PowerShell: .\.venv\Scripts\Activate.ps1
pip install -r requirements.txt           # 9.8 s en la prueba (43 paquetes)

cd interfaz
npm ci
npm run build                             # tsc + vite: 5.5 s en la prueba
cd ..
```

Opcional, transcripción local con GPU (no se usa en la plataforma publicada): `pip install -r audio-audit/requirements-local.txt` (torch 2.8.0+cu128, whisperx, pyannote), FFmpeg en el `PATH` y un token de Hugging Face con acceso aceptado a `pyannote/speaker-diarization-community-1`.

## 6. Ejecución

Dos procesos, cada uno en su terminal:

```bash
# 1. API unificada (todos los módulos en un proceso)
uvicorn api.index:app --port 8000 --reload

# 2. Interfaz en modo desarrollo
cd interfaz && npm run dev                # abre http://127.0.0.1:5173
```

Alternativa sin recarga (la usada en la prueba limpia): `npm run build` y `npx vite preview --port 4173` con `API_BACKEND_URL` apuntando a la API.

Data Audit también funciona sin interfaz, desde la línea de comandos:

```bash
cd data-audit/qa_bases_datos/backend
python -m qa.cli bases
python -m qa.cli procesar --base EMERGENCIAS --archivo ../../../documentation/ejemplos/emergencias_sintetica.csv \
  --anio 2025 --mes 3 --sin-guardar --almacen /tmp/salida
```

## 7. Verificación

| Paso | Comando o acción | Resultado esperado |
|---|---|---|
| API viva | `curl http://127.0.0.1:8000/api/salud` | `{"ok":true,"login":false,"entorno":"local"}` |
| Catálogo | `curl http://127.0.0.1:8000/api/qa/bases` | Lista de 5 bases |
| Protección | `curl -H "Host: otro.ejemplo" http://127.0.0.1:8000/api/qa/bases` | 403: sin Supabase la API solo atiende `localhost` |
| CLI | `qa.cli procesar` con el CSV sintético (paso 6) | 41 registros, puntaje 92.2, 23 hallazgos, 5 sugerencias pendientes, 4 archivos (0.67 s) |
| Interfaz | Abrir la interfaz → Data Audit → base Emergencias, 2025, marzo → subir `documentation/ejemplos/emergencias_sintetica.csv` | Auditoría terminada con puntaje 92.2 y descarga de `emergencias_2025_03_corregido.xlsx` |
| Pruebas automáticas | ver [Pruebas](testing.md#cómo-repetir-las-pruebas) | 40 pruebas en verde |

## 8. Solución de problemas

| Síntoma | Causa probable | Solución |
|---|---|---|
| `cargar_config` termina con error de argumentos | Falta uno de los tres diccionarios | Los tres `--dicc-*` son obligatorios. |
| Data Audit no muestra bases | Catálogos no cargados o `DATABASE_URL` distinta | Repetir 4.2 contra la misma base que usa la API. |
| `403 Sin Supabase Auth configurado…` | Se accede por IP o nombre que no es `localhost` sin Supabase | Usar `127.0.0.1`/`localhost` o configurar Supabase. |
| `401` en todas las rutas | Sesión vencida o token ausente | Volver a iniciar sesión. |
| `503` al leer un PDF o verificar | Falta `ANTHROPIC_API_KEY` en el servidor | Definirla (o usar solo la captura manual de formularios). |
| `429`/«IA ocupada» | Límite de peticiones del proveedor | La interfaz reintenta sola; esperar. |
| La interfaz sigue en modo demo | `VITE_APP_MODE` cambió con Vite encendido | Reiniciar `npm run dev` o recompilar. |
| `psycopg` no conecta a Supabase desde casa | Red sin IPv6 | Usar la cadena *Session pooler* (IPv4). |
| Una base se queda «procesando» en Vercel | Más de 300 s por petición (plan Hobby) | Dividir la base o desactivar el codificador con IA (`QA_IA_PROVEEDOR=ninguno`). |
| Transcripción local falla | Falta FFmpeg, token HF o memoria GPU | Usar transcripción en la nube o desactivar diarización. |

## 9. Despliegue

- **En línea (Vercel + Supabase):** pasos completos en [despliegue](deployment.md). Producción: https://dataton-six.vercel.app.
- **Local institucional:** los pasos 2–6 en un servidor interno; poner la API detrás de un proxy con HTTPS y configurar Supabase Auth (o restringir el acceso por red), porque sin Supabase la API no tiene usuarios.

## Reproducibilidad

- Todo el código, esquemas SQL, reglas (`reglas.yaml`), plantillas de QI y reglas JEV están versionados; los resultados dependen solo de ellos, de los diccionarios del INE y del archivo de entrada.
- Data Audit es determinista sin IA (`QA_IA_PROVEEDOR=ninguno`): el mismo archivo produce el mismo puntaje. Con IA, las sugerencias pueden variar entre ejecuciones, pero nunca se aplican sin aprobación humana.
- Los ejemplos sintéticos de `documentation/ejemplos/` permiten repetir cada módulo sin datos personales (ver [manual de usuario](user-guide.md)).
- La documentación técnica generada ([API](api-referencia.md), [diccionario](diccionario-datos.md), [tablas](modelo-datos-tablas.md)) se vuelve a producir con los scripts de `documentation/herramientas/`.
