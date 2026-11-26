"""Servidor independiente del módulo de QA de bases de datos.

    cd qa_bases_datos
    python -m uvicorn qa.servidor:app --app-dir backend --port 8001 --reload

Documentación interactiva de los endpoints: http://localhost:8001/docs

Lee la configuración de qa_bases_datos/.env (DATABASE_URL, QA_ALMACEN, QA_CORS).
"""
from __future__ import annotations

import logging
import os
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

RAIZ = Path(__file__).resolve().parents[2]
load_dotenv(RAIZ / ".env", override=False)

from .api import router  # noqa: E402  (después de cargar .env)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")

app = FastAPI(title="Quality Audit — QA de bases de datos", version="0.1.0")
origenes = [o.strip() for o in os.environ.get("QA_CORS", "http://localhost:8000,http://127.0.0.1:8000,"
                                              "http://localhost:5173,http://localhost:3000").split(",") if o.strip()]
app.add_middleware(CORSMiddleware, allow_origins=origenes, allow_methods=["*"], allow_headers=["*"])
app.include_router(router)


@app.get("/")
def inicio() -> dict:
    return {"servicio": "Quality Audit — QA de bases de datos", "documentacion": "/docs", "api": "/api/qa"}
