# Dependencias y licencias

Inventario de todo el software, modelos y servicios de terceros que usa Quality Audit, con versión probada, función, licencia, repositorio oficial y dónde se ejecuta. Las versiones de Python son las resueltas en la [instalación limpia](installation.md) del 26-nov-2026.

## Licencia del repositorio

El código propio se entrega bajo los términos de la Nota Conceptual del Datatón: licencia institucional **no exclusiva, gratuita, perpetua e irrevocable** a favor del INE, conservando la autoría de los participantes. No se agregó una licencia general distinta (MIT, Apache, GPL…) para no contradecir esas condiciones.

Lo que sí es seguro: todas las dependencias tienen licencias de software libre compatibles con uso institucional. Dos de ellas son **LGPL-3.0** (`psycopg` y `fpdf2`): se usan como bibliotecas sin modificarlas, lo que permite distribuir el sistema bajo cualquier licencia siempre que se respeten los términos de la LGPL para esas bibliotecas (incluir su aviso de licencia y permitir sustituirlas).

## Plataforma base

| Herramienta | Versión probada | Función | Licencia | Repositorio oficial | Ejecución |
|---|---|---|---|---|---|
| Python | 3.13.18 (prueba) / 3.12 (Vercel) | Lenguaje de la API y los motores | PSF-2.0 | https://github.com/python/cpython | Local / Vercel |
| Node.js / npm | 22.23.5 / 10.9.9 | Compilar la interfaz | MIT / Artistic-2.0 | https://github.com/nodejs/node | Local (solo compilación) |
| PostgreSQL | 16.15 (local), 16 (Supabase) | Base de datos | PostgreSQL License | https://github.com/postgres/postgres | Local / Supabase |
| FFmpeg | 6.1.1 | Conversión de audio (modo local) | LGPL-2.1+ (GPL según compilación) | https://github.com/FFmpeg/FFmpeg | Local |
| Git | — | Control de versiones | GPL-2.0 | https://github.com/git/git | Local |

## Python

Instaladas con `pip install -r requirements.txt` (43 paquetes; «Dependencia indirecta» = la requiere otro paquete). Todas se ejecutan localmente o en la función de Vercel.

| Paquete | Versión | Función | Licencia | Repositorio |
|---|---|---|---|---|
| annotated-doc | 0.0.7 | Dependencia indirecta | MIT | https://github.com/fastapi/annotated-doc |
| annotated-types | 0.8.0 | Dependencia indirecta | MIT | https://github.com/annotated-types/annotated-types |
| anthropic | 2.14.0 | Cliente de la API de Claude | Apache Software License | https://github.com/anthropics/anthropic-sdk-python |
| anyio | 4.16.0 | Dependencia indirecta | MIT | https://github.com/agronholm/anyio |
| certifi | 2026.11.20 | Dependencia indirecta | Mozilla Public License 2.0 (MPL 2.0) | https://github.com/certifi/python-certifi |
| charset-normalizer | 3.5.3 | Dependencia indirecta |  | https://github.com/jawah/charset_normalizer |
| click | 8.5.1 | Dependencia indirecta | BSD-3-Clause | https://github.com/pallets/click/ |
| docstring_parser | 0.18.0 | Dependencia indirecta | MIT License | https://github.com/rr-/docstring_parser |
| et_xmlfile | 2.0.0 | Dependencia indirecta | MIT License | https://foss.heptapod.net/openpyxl/et_xmlfile |
| fastapi | 0.165.0 | Framework de la API | MIT | https://github.com/fastapi/fastapi |
| fonttools | 4.69.1 | Fuentes (fpdf2) |  | https://github.com/fonttools/fonttools |
| fpdf2 | 2.9.0 | Manual institucional en PDF | LGPL-3.0-only | https://github.com/py-pdf/fpdf2 |
| h11 | 0.16.0 | Dependencia indirecta | MIT License | https://github.com/python-hyper/h11 |
| httpcore2 | 2.16.2 | Dependencia indirecta | BSD-3-Clause | https://github.com/pydantic/httpx2 |
| httpx2 | 2.16.2 | Dependencia indirecta | BSD-3-Clause | https://github.com/pydantic/httpx2 |
| idna | 3.20 | Dependencia indirecta | BSD-3-Clause | https://github.com/kjd/idna |
| jiter | 0.19.0 | Dependencia indirecta | MIT | https://github.com/pydantic/jiter/ |
| numpy | 2.5.5 | Cálculo numérico (pandas) | BSD-3-Clause AND 0BSD AND MIT AND Zlib AND CC0-1.0 | https://numpy.org |
| openpyxl | 3.1.5 | Leer y escribir Excel | MIT License | https://openpyxl.readthedocs.io |
| opentelemetry-api | 1.45.2 | Dependencia indirecta | Apache-2.0 | https://github.com/open-telemetry/opentelemetry-python |
| pandas | 3.1.1 | Tablas en memoria | BSD-3-Clause | https://pandas.pydata.org |
| pillow | 13.0.0 | Imágenes (fpdf2) | MIT-CMU | https://github.com/python-pillow/Pillow |
| psycopg | 3.3.9 | Conexión a PostgreSQL | LGPL-3.0-only | https://psycopg.org/ |
| psycopg-binary | 3.3.9 | Binario de psycopg | LGPL-3.0-only | https://psycopg.org/ |
| pydantic | 2.14.4 | Validación de peticiones | MIT | https://github.com/pydantic/pydantic |
| pydantic_core | 2.50.5 | Núcleo de pydantic | MIT | https://github.com/pydantic/pydantic |
| pypdf | 7.1.1 | Dividir el PDF del cuestionario | BSD-3-Clause | https://github.com/py-pdf/pypdf |
| python-calamine | 0.9.1 | Lectura rápida de Excel | MIT | https://github.com/dimastbk/python-calamine |
| python-dateutil | 4.0.0 | Dependencia indirecta | BSD-3-Clause | https://github.com/dateutil/dateutil |
| python-dotenv | 1.2.4 | Lectura de .env |  | https://github.com/theskumar/python-dotenv |
| python-multipart | 0.0.34 | Subida de archivos | Apache-2.0 | https://github.com/Kludex/python-multipart |
| PyYAML | 6.0.4 | Reglas y definiciones YAML | MIT License | https://pyyaml.org/ |
| RapidFuzz | 3.14.6 | Similitud de texto | MIT | https://github.com/rapidfuzz/RapidFuzz |
| requests | 2.34.2 | HTTP a Supabase y proveedores de transcripción | Apache Software License | https://github.com/psf/requests |
| sniffio | 1.3.1 | Dependencia indirecta | MIT License, Apache Software License | https://github.com/python-trio/sniffio |
| starlette | 1.10.0 | Base de FastAPI | BSD-3-Clause | https://github.com/Kludex/starlette |
| truststore | 0.10.5 | Dependencia indirecta | MIT | https://github.com/sethmlarson/truststore |
| typing-inspection | 0.4.5 | Dependencia indirecta | MIT | https://github.com/pydantic/typing-inspection |
| typing_extensions | 4.16.0 | Dependencia indirecta | PSF-2.0 | https://github.com/python/typing_extensions |
| tzdata | 2026.6 | Dependencia indirecta |  | https://github.com/python/tzdata |
| urllib3 | 2.8.0 | Dependencia indirecta | MIT | https://github.com/urllib3/urllib3 |
| uvicorn | 0.54.0 | Servidor ASGI | BSD-3-Clause | https://www.uvicorn.org |
| xlsxwriter | 3.3.4 | Base corregida y bitácora en Excel | BSD-2-Clause | https://github.com/jmcnamara/XlsxWriter |


### Solo modo local con GPU (`audio-audit/requirements-local.txt`)

No se instalaron en la prueba limpia; las versiones de whisperx y pyannote.audio son las publicadas al 26-nov-2026 (whisperx no está fijado en el archivo).

| Paquete | Versión | Función | Licencia | Repositorio |
|---|---|---|---|---|
| torch / torchvision / torchaudio | 2.8.0+cu128 / 0.23.0 / 2.8.0 | Inferencia en GPU | BSD-3-Clause | https://github.com/pytorch/pytorch |
| whisperx | 3.8.6 | Transcripción y alineación | BSD-2-Clause | https://github.com/m-bain/whisperX |
| pyannote.audio | 4.1.1 | Diarización | MIT | https://github.com/pyannote/pyannote-audio |

### Solo pruebas

| Paquete | Versión | Licencia | Repositorio |
|---|---|---|---|
| pytest | 9.2.0 | MIT | https://github.com/pytest-dev/pytest |
| playwright | 1.65.2 | Apache-2.0 | https://github.com/microsoft/playwright-python |

## JavaScript (interfaz)

| Paquete | Versión | Función | Licencia | Repositorio | Ejecución |
|---|---|---|---|---|---|
| @supabase/supabase-js | 2.119.2 | Inicio de sesión desde el navegador | MIT | https://github.com/supabase/supabase-js | Navegador |
| typescript | 5.9.3 | Verificación de tipos | Apache-2.0 | https://github.com/microsoft/TypeScript | Compilación |
| vite | 6.4.6 | Servidor de desarrollo y compilación | MIT | https://github.com/vitejs/vite | Compilación |

`npm ci` instala 24 paquetes en total (incluidas dependencias indirectas como esbuild y rollup): 20 MIT, 1 ISC, 1 BSD-3-Clause, 1 0BSD y 1 Apache-2.0. La interfaz React original de `audio-audit/` (react 18.3.1, vite 5.4.21, @vitejs/plugin-react 4.7.0, todas MIT) se conserva como referencia y no se publica.

## Fuentes, modelos y datos de terceros

| Recurso | Uso | Licencia | Origen | Ejecución |
|---|---|---|---|---|
| Fuentes DejaVu | Manual PDF de Quality Improvement | Licencia libre de DejaVu (Bitstream Vera + dominio público); copia en `interfaz/backend/extensions/fuentes/LICENCIA.txt` | https://dejavu-fonts.github.io | Local |
| Pyannote `speaker-diarization-community-1` | Diarización local | CC-BY-4.0 (acceso condicionado en Hugging Face) | https://huggingface.co/pyannote/speaker-diarization-community-1 | Local |
| Pesos de Whisper | Transcripción local | MIT (OpenAI) | https://github.com/openai/whisper | Local |
| Diccionarios y bases públicas del INE | Catálogos y reglas | Condiciones de uso del INE; compartidos por la organización del Datatón | https://www.ine.gob.gt | Local |

## Servicios comerciales y en la nube

| Servicio | Función | Licencia / términos | Costo y restricciones | Ejecución |
|---|---|---|---|---|
| Vercel | Hospedaje de interfaz y API | Términos de servicio de Vercel | Plan Hobby gratuito; 300 s por petición | Externa |
| Supabase | PostgreSQL, Storage, Auth | Términos de Supabase (su software es Apache-2.0) | Plan gratuito; 50 MB por archivo; pausa por inactividad | Externa |
| Anthropic API (Claude Haiku 5.5) | IA de Survey, Data Audit y QI | Términos comerciales de Anthropic | Pago por uso | Externa |
| OpenRouter / TypeSafe JEV | Evaluación de entrevistas | Términos de OpenRouter y TypeSafe | Pago por uso | Externa |
| AssemblyAI / Deepgram | Transcripción y diarización | Términos de cada proveedor | Pago por uso | Externa |

Detalle de costos y datos que recibe cada servicio: [IA y servicios](ia-y-servicios.md) y [seguridad](security.md#9-servicios-externos-y-datos-que-reciben).
