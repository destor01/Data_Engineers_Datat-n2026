# Despliegue: un proyecto de Vercel y uno de Supabase

Toda la plataforma se publica desde este repositorio con **un solo proyecto de Vercel** (interfaz + API) y **un solo proyecto de Supabase** (base de datos, archivos y usuarios).

| Pieza | Dónde vive | Qué hace |
|---|---|---|
| Interfaz (`interfaz/`) | Vercel, sitio estático | Login, Audio Audit, Data Audit, Survey Audit y Quality Improvement |
| API unificada (`api/index.py` → `plataforma/`) | Vercel, una función Python | Todas las rutas `/api/*`: audio, QA de bases y extensiones |
| PostgreSQL | Supabase | Tablas de Data Audit, Audio Audit y extensiones (todas con RLS) |
| Storage | Supabase | Buckets privados `audio-interviews` y `qa-cargas` |
| Auth | Supabase | Cuentas de correo y contraseña; sin registro público |

```text
Navegador ──login──▶ Supabase Auth
    │
    ├──▶ Vercel  /            interfaz (estático)
    ├──▶ Vercel  /api/*       API unificada ──▶ Supabase Postgres (DATABASE_URL)
    │                                       └─▶ Supabase Storage (llave secreta)
    └──PUT──▶ Supabase Storage (URL firmada: audios y bases, sin pasar por Vercel)
```

La plataforma del equipo está publicada en https://dataton-six.vercel.app.

Cada petición a `/api/*` lleva el token de la sesión y la API lo verifica con Supabase. Sin sesión responde 401; sin Supabase configurado, en Vercel responde 503 (la API nunca queda abierta por olvido). `/api/salud` es la única ruta pública.

## 1. Supabase

1. **Crear el proyecto** en [supabase.com](https://supabase.com) y guardar la contraseña de la base de datos.
2. **Desactivar el registro público:** en Authentication, en la configuración del proveedor Email, desactivar la opción que permite a cualquiera crear cuenta. Solo entrarán las cuentas que cree el equipo.
3. **Crear los usuarios:** Authentication → Users → Add user → Create new user, con *Auto Confirm User* marcado. Anotarlos en [accesos.md](accesos.md) (ver la advertencia de ese archivo).
4. **Preparar la base de datos** desde tu computadora, en la raíz del repositorio. Usa la cadena **Session pooler** (botón *Connect* del proyecto), que funciona con IPv4:

   ```powershell
   python -m venv .venv
   .\.venv\Scripts\python.exe -m pip install -r requirements.txt
   $env:DATABASE_URL = 'postgresql://postgres.<ref>:<contraseña>@aws-0-<región>.pooler.supabase.com:5432/postgres'
   .\.venv\Scripts\python.exe supabase\configurar.py
   ```

   El script se puede repetir. Aplica en orden `data-audit/qa_bases_datos/schema.sql`, `audio-audit/supabase/schema.sql`, `interfaz/backend/migrations/001_extensions.sql` y `supabase/seguridad.sql` (buckets privados `audio-interviews`, `qa-cargas` y `encuestas`, RLS en todas las tablas y sin permisos para los roles del navegador). Alternativa: pegar esos cuatro archivos, en ese orden, en el SQL Editor.

5. **Cargar los catálogos del INE** (necesarios para que aparezcan bases en Data Audit). Los diccionarios no están en el repositorio:

   ```powershell
   cd data-audit\qa_bases_datos\backend
   ..\..\..\.venv\Scripts\python.exe -m scripts.cargar_config --dicc-defunciones 'C:\ruta\diccionario-defunciones-2018-2022.xlsx' --dicc-nacimientos 'C:\ruta\diccionario-nacimientos-2018-2022.xlsx' --dicc-pnc 'C:\ruta\diccionario-detenidos-pnc.xlsx'
   ```

   Al terminar, `supabase\configurar.py` muestra cuántas bases quedaron activas.

6. **Llaves** (Project Settings → API Keys): la *publishable* (o *anon*) es pública por diseño; la *secret* (o *service_role*) nunca va al navegador ni al repositorio.

## 2. Vercel

1. Add New → Project → importar este repositorio de GitHub. **Root Directory: la raíz** (no `interfaz/`). El resto lo toma de `vercel.json`.
2. En Settings → Environment Variables, para Production y Preview:

   | Variable | Valor | Pública |
   |---|---|---|
   | `VITE_APP_MODE` | `api` | sí |
   | `VITE_SUPABASE_URL` | URL del proyecto (`https://<ref>.supabase.co`) | sí |
   | `VITE_SUPABASE_ANON_KEY` | llave publishable/anon | sí |
   | `SUPABASE_URL` | la misma URL | no |
   | `SUPABASE_SERVICE_ROLE_KEY` | llave secret/service_role | **secreta** |
   | `DATABASE_URL` | cadena **Transaction pooler** (puerto 6543) | **secreta** |
   | `ASSEMBLYAI_API_KEY` o `DEEPGRAM_API_KEY` | transcripción en la nube | **secreta** |
   | `ANTHROPIC_API_KEY` | Survey Audit (leer el PDF del cuestionario y verificar entrevistas) y redacción de Quality Improvement; también el codificador con IA de Data Audit | **secreta** |
   | `OPENROUTER_API_KEY` | opcional: evaluación JEV de entrevistas | **secreta** |

   Opcionales sin secreto: `SURVEY_IA_MODELO`, `SURVEY_VERIF_MODELO` (verificación de entrevistas; si no se define usa `SURVEY_IA_MODELO`), `MEJORA_IA_MODELO` (modelo de Claude; por defecto `claude-haiku-5-5` en toda la plataforma), `SURVEY_PAGINAS_BLOQUE` (páginas del PDF por petición, 2), `SURVEY_STORAGE_BUCKET` (`encuestas`) y `MEJORA_IA=0` para no usar IA en Quality Improvement.

   Las variables `VITE_*` quedan dentro del JavaScript que descarga el navegador: nunca pongas ahí una llave secreta.
3. Deploy. Comprobar `https://<tu-proyecto>.vercel.app/api/salud`: debe responder `{"ok": true, "login": true, "entorno": "vercel"}`.
4. Entrar con una de las cuentas creadas y probar Data Audit con `documentation/ejemplos/emergencias_sintetica.csv` (ver [manual de usuario](user-guide.md)).

Cada push a `main` publica producción; cada rama o PR genera una vista previa con su propia URL.

## 3. Desarrollo local

### 3.1 Requisitos

| Programa | Versión | Comprobar |
|---|---|---|
| Python | 3.12 o superior | `python --version` |
| Node.js y npm | Node 20.19+ o 22.12+ | `node --version` |
| PostgreSQL | 16 (con `psql` y `createdb` en el PATH) | `psql --version` |
| Git | cualquiera reciente | `git --version` |

Además necesitas los tres diccionarios oficiales del INE (defunciones 2018-2022, nacimientos 2018-2022 y detenidos PNC). No están en el repositorio.

### 3.2 Instalar dependencias de Python

Desde la raíz del repositorio:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

### 3.3 Configurar variables

```powershell
Copy-Item .env.example .env
Copy-Item interfaz\.env.example interfaz\.env.local
```

En `.env` llena como mínimo `DATABASE_URL`, por ejemplo `postgresql://postgres:clave@127.0.0.1:5432/quality_audit`. Las llaves de IA (`ANTHROPIC_API_KEY`, `ASSEMBLYAI_API_KEY`, `OPENROUTER_API_KEY`) son opcionales: sin ellas, los módulos funcionan sin las funciones de IA. Para trabajar sin IA en Data Audit, agrega `QA_IA_PROVEEDOR=ninguno`.

En `interfaz\.env.local` deja `VITE_APP_MODE=api` y `API_BACKEND_URL=http://127.0.0.1:8000`. Si dejas vacías `VITE_SUPABASE_URL` y `VITE_SUPABASE_ANON_KEY`, no se pide login.

### 3.4 Crear la base de datos

```powershell
createdb -U postgres quality_audit
psql -U postgres -d quality_audit -f data-audit\qa_bases_datos\schema.sql
psql -U postgres -d quality_audit -f interfaz\backend\migrations\001_extensions.sql
```

Si usas Supabase en lugar de un PostgreSQL local, ejecuta `.\.venv\Scripts\python.exe supabase\configurar.py` en lugar de estos dos `psql` (ver la sección 1).

### 3.5 Cargar reglas y catálogos del INE

```powershell
cd data-audit\qa_bases_datos\backend
..\..\..\.venv\Scripts\python.exe -m scripts.cargar_config --db "postgresql://postgres:clave@127.0.0.1:5432/quality_audit" `
  --dicc-defunciones "C:\ruta\diccionario-defunciones-2018-2022.xlsx" `
  --dicc-nacimientos "C:\ruta\diccionario-nacimientos-2018-2022.xlsx" `
  --dicc-pnc "C:\ruta\diccionario-detenidos-pnc.xlsx"
..\..\..\.venv\Scripts\python.exe -m qa.cli bases
cd ..\..\..
```

Los tres diccionarios son obligatorios. Al terminar se deben ver 33 reglas, 31 catálogos y 5 bases activas, y `qa.cli bases` lista las 5 bases.

### 3.6 Instalar la interfaz

```powershell
cd interfaz
npm ci
cd ..
```

### 3.7 Ejecutar

Terminal 1, desde la raíz (API):

```powershell
.\.venv\Scripts\python.exe -m uvicorn api.index:app --port 8000 --reload
```

Terminal 2, desde `interfaz\`:

```powershell
npm run dev
```

Abre http://127.0.0.1:5173. Vite envía `/api/*` al puerto 8000.

### 3.8 Verificar

- http://127.0.0.1:8000/api/salud responde `{"ok":true,"login":false,"entorno":"local"}`.
- http://127.0.0.1:8000/api/qa/bases lista las 5 bases.
- En la interfaz: Data Audit → base *Emergencias*, 2025, marzo → subir `documentation\ejemplos\emergencias_sintetica.csv`. Debe terminar con puntaje 92.2.

Si no defines las variables de Supabase, no se pide login, la API solo atiende `localhost` y Data Audit guarda los archivos en `data-audit/qa_bases_datos/almacen/`. Los módulos también se pueden ejecutar por separado, como indica el README de cada uno.

**Opcional, transcripción local con GPU:** `.\.venv\Scripts\python.exe -m pip install -r audio-audit\requirements-local.txt`, FFmpeg en el PATH y un token de Hugging Face con acceso al modelo `pyannote/speaker-diarization-community-1`.

## Límites conocidos

- **Tamaño de archivo:** el plan gratuito de Supabase admite hasta 50 MB por archivo, para audios y bases. La interfaz valida ese límite (`VITE_MAX_AUDIO_MB`, `VITE_MAX_DATA_MB`) y la API el de las bases (`QA_MAX_MB`).
- **Tiempo por validación:** Data Audit procesa cada base dentro de una petición de hasta 300 s (máximo del plan Hobby de Vercel). Una base que tarde más, por ejemplo con el codificador con IA sobre muchos registros, no termina.
- **Transcripción:** con AssemblyAI el trabajo es asíncrono y no tiene ese límite; Deepgram responde dentro de la misma petición.
- **Pausa de Supabase:** los proyectos gratuitos se pausan tras una semana sin actividad. Entra a la plataforma antes de una presentación.
- **Evaluación JEV:** necesita `OPENROUTER_API_KEY`; sin ella la interfaz avisa que falta la llave y no calcula el puntaje. La pantalla React original de `audio-audit/` no se publica: la evaluación, el reporte, la edición, la calibración y el editor de reglas están en la interfaz común.
- **Lectura de cuestionarios:** cada petición lee un bloque de páginas en menos de 300 s y la interfaz lanza varias a la vez. Un PDF de 72 páginas tarda varios minutos; si Anthropic limita las peticiones, la interfaz reintenta sola. La página debe quedar abierta mientras se lee (se puede continuar después).
- **Roles:** cualquier cuenta creada en Supabase tiene acceso a todo. Data Audit registra a cada usuario que entra como `analista_ine` para su bitácora.
