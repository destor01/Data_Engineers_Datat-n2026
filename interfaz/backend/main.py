"""Adaptador local del motor Data Audit existente; no modifica su código."""
from __future__ import annotations

import json
import logging
import os
from pathlib import Path
import re
import shutil
import sys
import threading
import uuid

from dotenv import load_dotenv
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from starlette.concurrency import run_in_threadpool

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / '.env')
ENGINE = Path(os.environ.get('DATA_ENGINE_PATH', str(ROOT.parent / 'data-audit' / 'qa_bases_datos' / 'backend'))).resolve()
if not (ENGINE / 'qa' / 'motor.py').is_file():
    raise RuntimeError('No se encontró Data Audit. Coloca interfaz-integrada junto a data-audit o configura DATA_ENGINE_PATH.')
sys.path.insert(0, str(ENGINE))
import psycopg
from qa.definicion import cargar_definicion
from qa.motor import procesar
from qa.salidas import escribir_archivos

app = FastAPI(title='Data Audit · adaptador local')
from extensions.api import router as surveys_router
from extensions.improvement import router as improvement_router
app.include_router(surveys_router)
app.include_router(improvement_router)
STORE = ROOT / 'backend' / 'almacen'
LOCK = threading.Lock()
MAX_BYTES = 100 * 1024 * 1024


def connection():
    dsn = os.environ.get('DATABASE_URL')
    if not dsn:
        raise HTTPException(503, 'Configura DATABASE_URL en .env y carga el esquema y los catálogos del motor.')
    return psycopg.connect(dsn)


@app.get('/data-api/bases')
def bases():
    try:
        with connection() as con, con.cursor() as cur:
            cur.execute('''SELECT DISTINCT t.codigo, t.nombre FROM tipo_base t
                JOIN version_esquema v ON v.tipo_base_id = t.id AND v.activa ORDER BY t.codigo''')
            return [{'codigo': c, 'nombre': n} for c, n in cur.fetchall()]
    except HTTPException:
        raise
    except Exception:
        logging.exception('No se pudo consultar el catálogo')
        raise HTTPException(503, 'No se pudo consultar PostgreSQL. Revisa la conexión, el esquema y los catálogos.')


def execute(source: Path, base: str, year: int, month: int, folder: Path):
    if not LOCK.acquire(blocking=False):
        raise HTTPException(409, 'Ya hay una auditoría en curso. Intenta cuando termine.')
    try:
        with connection() as con, con.cursor() as cur:
            cur.execute('''SELECT 1 FROM tipo_base t JOIN version_esquema v
                ON v.tipo_base_id = t.id AND v.activa WHERE t.codigo = %s''', (base,))
            if not cur.fetchone():
                raise HTTPException(400, 'La base no tiene una versión activa configurada.')
            definition = cargar_definicion(cur, base)
        result = procesar(source, definition, year, month)
        paths = escribir_archivos(definition, result, source, folder)
        report = json.loads(paths['reporte'].read_text(encoding='utf-8'))
        return {'reporte': report, 'descargas': {
            role: f'/data-api/descargas/{folder.name}/{role}'
            for role in ('corregido', 'bitacora', 'reporte')
        }}
    finally:
        LOCK.release()


@app.post('/data-api/procesar')
async def audit(file: UploadFile = File(...), base: str = Form(...),
                anio: int = Form(..., ge=1900, le=2100), mes: int = Form(..., ge=1, le=12)):
    suffix = Path(file.filename or '').suffix.lower()
    if suffix not in {'.csv', '.xls', '.xlsx'}:
        await file.close()
        raise HTTPException(400, 'Selecciona un archivo CSV, XLS o XLSX.')
    folder = STORE / uuid.uuid4().hex
    folder.mkdir(parents=True)
    source = folder / f'original{suffix}'
    try:
        size = 0
        with source.open('wb') as output:
            while chunk := await file.read(1024 * 1024):
                size += len(chunk)
                if size > MAX_BYTES:
                    raise HTTPException(413, 'El archivo supera 100 MB.')
                output.write(chunk)
        if not size:
            raise HTTPException(400, 'El archivo está vacío.')
        return await run_in_threadpool(execute, source, base, anio, mes, folder)
    except HTTPException:
        shutil.rmtree(folder, ignore_errors=True)
        raise
    except Exception:
        logging.exception('Falló la auditoría')
        shutil.rmtree(folder, ignore_errors=True)
        raise HTTPException(500, 'No se pudo auditar el archivo. Revisa el formato, los catálogos y el registro del servidor.')
    finally:
        await file.close()


@app.get('/data-api/descargas/{job_id}/{role}')
def download(job_id: str, role: str):
    names = {'corregido': 'corregido.xlsx', 'bitacora': 'bitacora.xlsx', 'reporte': 'reporte.json'}
    if not re.fullmatch(r'[0-9a-f]{32}', job_id) or role not in names:
        raise HTTPException(404, 'Archivo no encontrado.')
    path = STORE / job_id / names[role]
    if not path.is_file():
        raise HTTPException(404, 'Archivo no encontrado.')
    return FileResponse(path, filename=path.name)
