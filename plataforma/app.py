"""API unificada de Quality Audit: un solo FastAPI con los tres backends.

    /api/salud                 estado del servicio (público)
    /api/sesion                usuario de la sesión actual
    /api/qa/...                Data Audit (data-audit/qa_bases_datos)
    /api/transcribe, /api/jobs, /api/rules, /api/storage, /api/status ...   Audio Audit (audio-audit)
    /api/surveys/..., /api/improvement/..., /api/extensions/...            Survey Audit y Quality Improvement

En Vercel la sirve api/index.py. En local:
    uvicorn api.index:app --port 8000 --reload
"""
from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

RAIZ = Path(__file__).resolve().parents[1]
load_dotenv(RAIZ / ".env", override=False)

for carpeta in ("audio-audit", "data-audit/qa_bases_datos/backend", "interfaz/backend"):
    ruta = str(RAIZ / carpeta)
    if ruta not in sys.path:
        sys.path.insert(0, ruta)

from fastapi import APIRouter, FastAPI  # noqa: E402
from fastapi.exceptions import RequestValidationError  # noqa: E402
from fastapi.responses import JSONResponse  # noqa: E402
from fastapi.routing import APIRoute  # noqa: E402

from app.main import app as audio_app  # noqa: E402  (audio-audit)
from extensions import api as encuestas_mod  # noqa: E402  (interfaz/backend)
from extensions.api import router as encuestas_router  # noqa: E402
from extensions import improvement as mejora_mod  # noqa: E402
from extensions.improvement import router as mejora_router  # noqa: E402
from qa import api as qa_api  # noqa: E402  (data-audit)

from .auth import AccesoMiddleware, IS_VERCEL, auth_configurado, usuario_actual  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")

app = FastAPI(title="Quality Audit · Data Engineers", docs_url=None if IS_VERCEL else "/docs",
              redoc_url=None, openapi_url=None if IS_VERCEL else "/openapi.json")

# Audio Audit: se toman solo sus rutas /api/*. Su guardia propia (APP_PASSWORD) no aplica aquí:
# el acceso lo controla AccesoMiddleware con Supabase Auth.
audio_router = APIRouter()
audio_router.routes.extend(r for r in audio_app.router.routes
                           if isinstance(r, APIRoute) and r.path.startswith("/api/") and not r.path.startswith("/api/config/"))
app.include_router(audio_router)
app.include_router(qa_api.router)
app.include_router(encuestas_router)
app.include_router(mejora_router)

# Las acciones de Data Audit quedan registradas a nombre del usuario que inició sesión.
qa_api.usuario_autenticado = lambda: (usuario_actual.get() or {}).get("email")
mejora_mod.usuario_autenticado = lambda: (usuario_actual.get() or {}).get("email")
encuestas_mod.usuario_autenticado = lambda: (usuario_actual.get() or {}).get("email")


CAMPOS = {"nombre": "el nombre", "archivo": "el archivo", "cargo": "el cargo", "justificacion": "la justificación",
          "titulo": "el título", "acciones": "las acciones de mejora", "anio": "el año", "mes": "el mes", "base": "la base",
          "institucion_nombre": "el nombre de la institución", "introduccion": "la presentación", "hablante": "el hablante"}


@app.exception_handler(RequestValidationError)
async def datos_no_validos(request, exc: RequestValidationError):
    """Errores de formato explicados en lenguaje claro, sin detalles técnicos."""
    partes = []
    for e in exc.errors()[:4]:
        campo = next((CAMPOS.get(str(x), None) for x in reversed(e.get("loc", [])) if CAMPOS.get(str(x))), "un dato")
        tipo = e.get("type", "")
        motivo = ("es demasiado corto" if "too_short" in tipo else "es demasiado largo" if "too_long" in tipo
                  else "falta" if tipo == "missing" else "tiene un valor fuera del rango permitido" if "than" in tipo
                  else "no tiene el formato esperado")
        partes.append(f"falta {campo}" if motivo == "falta" else f"{campo} {motivo}")
    texto = "Revisa los datos: " + "; ".join(dict.fromkeys(partes)) + "."
    return JSONResponse(status_code=422, content={"detail": texto[0].upper() + texto[1:]})


@app.get("/api/salud")
def salud() -> dict:
    return {"ok": True, "login": auth_configurado(), "entorno": "vercel" if IS_VERCEL else "local"}


@app.get("/api/sesion")
def sesion() -> dict:
    usuario = usuario_actual.get()
    return {"email": usuario.get("email") if usuario else None, "login": auth_configurado()}


app.add_middleware(AccesoMiddleware)

if os.environ.get("QA_CORS"):
    from fastapi.middleware.cors import CORSMiddleware

    app.add_middleware(CORSMiddleware, allow_origins=[o.strip() for o in os.environ["QA_CORS"].split(",") if o.strip()],
                       allow_methods=["*"], allow_headers=["*"])
