"""API de Quality Audit para el front (FastAPI).

Es un APIRouter con prefijo /api/qa. Sigue el mismo patrón que el transcriptor:
el archivo se guarda, el trabajo corre en segundo plano y el front consulta el
avance con GET /api/qa/cargas/{id} hasta que el estado deja de ser "procesando".

Dos formas de usarla:
  - Sola:      uvicorn qa.servidor:app --app-dir backend --port 8001
  - Integrada: app.include_router(router) en la app principal (ver README).

Flujo recomendado (sirve en Vercel y en local):
  1. POST /api/qa/cargas/subida        registra la carga y devuelve dónde subir el archivo
  2. PUT  <url de subida>              el navegador sube el original (URL firmada de Supabase
                                       Storage, o /api/qa/cargas/{id}/archivo en local)
  3. POST /api/qa/cargas/{id}/procesar valida la base en la misma petición y devuelve el reporte

Variables de entorno:
  DATABASE_URL       conexión a PostgreSQL (en Supabase: la del pooler)
  QA_ALMACEN         carpeta de archivos en modo local (por defecto qa_bases_datos/almacen)
  QA_ALMACENAMIENTO  supabase | local (por defecto supabase si hay SUPABASE_URL y SUPABASE_SERVICE_ROLE_KEY)
  QA_PROCESAMIENTO   sincrono | segundo_plano para POST /cargas y /reprocesar (en Vercel siempre sincrono)
  QA_MAX_MB          tamaño máximo del archivo (por defecto 50, el límite del plan gratis de Supabase)
"""
from __future__ import annotations

import json
import logging
import os
import re
import shutil
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Callable

import psycopg
from fastapi import APIRouter, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from psycopg.rows import dict_row
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool

from . import almacenamiento

from .definicion import cargar_definicion
from .codificador_ia import crear_codificador
from .motor import procesar
from .salidas import escribir_archivos, guardar_en_bd, usuario_sistema
from .texto import normalizar

logger = logging.getLogger("quality_audit")

RAIZ = Path(__file__).resolve().parents[2]                 # .../qa_bases_datos
EXTENSIONES = {".xlsx", ".xls", ".csv", ".txt"}
DESCARGABLES = {"corregido", "bitacora", "reporte"}        # el original trae datos personales: no se descarga aquí
UUID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")
IS_VERCEL = bool(os.environ.get("VERCEL") or os.environ.get("VERCEL_ENV"))

# La plataforma unificada lo reemplaza por el correo de la sesión de Supabase Auth.
usuario_autenticado: Callable[[], str | None] = lambda: None  # noqa: E731

router = APIRouter(prefix="/api/qa", tags=["QA de bases de datos"])
executor = ThreadPoolExecutor(max_workers=1)
progreso_lock = threading.Lock()
progreso: dict[str, dict[str, Any]] = {}                   # avance en memoria de las cargas en proceso


def _db_url() -> str:
    url = (os.environ.get("DATABASE_URL") or "").strip()
    if not url:
        raise HTTPException(status_code=500, detail="Falta configurar DATABASE_URL para el módulo de QA.")
    return url


def _almacen() -> Path:
    # En Vercel solo /tmp es escribible.
    ruta = Path(os.environ.get("QA_ALMACEN") or (Path(tempfile.gettempdir()) / "qa_almacen" if IS_VERCEL
                                                 else RAIZ / "almacen"))
    ruta.mkdir(parents=True, exist_ok=True)
    return ruta


def _max_bytes() -> int:
    return int(float(os.environ.get("QA_MAX_MB") or 50) * 1024 * 1024)


def _sincrono() -> bool:
    return IS_VERCEL or (os.environ.get("QA_PROCESAMIENTO") or "").strip().lower() == "sincrono"


def _conexion(**opciones):
    # prepare_threshold=None: el pooler de Supabase en modo transacción no admite sentencias preparadas.
    return psycopg.connect(_db_url(), prepare_threshold=None, **opciones)


def _conectar():
    return _conexion(row_factory=dict_row)


def _nombre_seguro(nombre: str) -> str:
    base = Path(nombre or "archivo.xlsx").name
    return re.sub(r"[^\w.\- ()áéíóúÁÉÍÓÚñÑ]", "_", base).strip() or "archivo.xlsx"


def _avance(carga_id: str, **datos: Any) -> None:
    with progreso_lock:
        progreso.setdefault(carga_id, {}).update(datos)


def _usuario_id(cur, email: str | None) -> int:
    if email:
        cur.execute("SELECT id FROM usuario WHERE email = %s AND activo", (email,))
        fila = cur.fetchone()
        if not fila:
            raise HTTPException(status_code=400, detail=f"No existe el usuario {email}.")
        return fila["id"]
    sesion = usuario_autenticado()
    if sesion:
        # Usuario que inició sesión con Supabase Auth: se registra la primera vez como analista del INE.
        cur.execute("""INSERT INTO usuario (nombre, email, password_hash, rol)
                       VALUES (%s, %s, '!supabase-auth', 'analista_ine')
                       ON CONFLICT (email) DO UPDATE SET email = EXCLUDED.email RETURNING id, activo""",
                    (sesion.split("@")[0][:150], sesion[:150]))
        fila = cur.fetchone()
        if not fila["activo"]:
            raise HTTPException(status_code=403, detail="Tu usuario está desactivado en Data Audit.")
        return fila["id"]
    cur.execute("SELECT id FROM usuario WHERE email = 'motor@quality-audit.local'")
    fila = cur.fetchone()
    if fila:
        return fila["id"]
    with _conexion() as con, con.cursor() as c2:
        uid = usuario_sistema(c2)
        con.commit()
    return uid


# ---------------------------------------------------------------------------
# Trabajo en segundo plano
# ---------------------------------------------------------------------------
def _procesar_carga(carga_id: str, base: str, ruta: Path, anio: int, mes: int | None, usuario_id: int,
                    ubicar=None) -> None:
    inicio = time.time()
    _avance(carga_id, estado="procesando", etapa="Cargando la definición de la base…", porcentaje=5,
            inicio=inicio, error=None)
    try:
        with _conexion() as con, con.cursor() as cur:
            cur.execute("UPDATE carga SET estado = 'procesando', actualizado_en = now() WHERE id = %s", (carga_id,))
            con.commit()
            d = cargar_definicion(cur, base)
            r = procesar(ruta, d, anio, mes, codificador=crear_codificador(),
                         progreso=lambda etapa, pct: _avance(carga_id, etapa=etapa, porcentaje=pct))
            _avance(carga_id, etapa="Generando archivo corregido y bitácora…", porcentaje=90)
            rutas = escribir_archivos(d, r, ruta, ruta.parent)
            _avance(carga_id, etapa="Guardando resultados…", porcentaje=95)
            guardar_en_bd(cur, d, r, carga_id, rutas, usuario_id, ubicar=ubicar)
            con.commit()
        _avance(carga_id, estado="terminado", etapa="¡Validación completada!", porcentaje=100,
                segundos=round(time.time() - inicio, 1))
    except Exception as exc:  # noqa: BLE001 - el front necesita el mensaje
        logger.exception("Error procesando la carga %s", carga_id)
        _avance(carga_id, estado="error", etapa="Error", error=str(exc), segundos=round(time.time() - inicio, 1))
        try:
            with _conexion() as con, con.cursor() as cur:
                cur.execute("UPDATE carga SET estado = 'error', notas = %s, actualizado_en = now() WHERE id = %s",
                            (str(exc)[:2000], carga_id))
                con.commit()
        except Exception:  # noqa: BLE001
            logger.exception("No se pudo marcar el error de la carga %s", carga_id)


def _encolar(carga_id: str, base: str, ruta: Path, anio: int, mes: int | None, usuario_id: int,
             ubicar=None) -> None:
    """En segundo plano en un servidor propio; en la misma petición en Vercel (los hilos no sobreviven)."""
    _avance(carga_id, estado="en_cola", etapa="En cola para procesar…", porcentaje=2, error=None)
    if _sincrono():
        _procesar_carga(carga_id, base, ruta, anio, mes, usuario_id, ubicar)
    else:
        executor.submit(_procesar_carga, carga_id, base, ruta, anio, mes, usuario_id, ubicar)


def _ubicador(carga_id: str, ruta_original: str | None = None):
    """Con Supabase Storage, sube cada salida y guarda su ruta supabase:// en la tabla archivo."""
    if not almacenamiento.usa_supabase():
        return None

    def ubicar(rol: str, ruta: Path) -> str:
        if rol == "original" and ruta_original:
            return ruta_original
        return almacenamiento.subir(ruta, almacenamiento.objeto(carga_id, ruta.name))
    return ubicar


def _carpeta_trabajo(carga_id: str) -> Path:
    return Path(tempfile.gettempdir()) / "qa_cargas" / carga_id


def _estado(carga_id: str) -> dict[str, Any]:
    with progreso_lock:
        return dict(progreso.get(carga_id) or {})


# ---------------------------------------------------------------------------
# Catálogo de bases
# ---------------------------------------------------------------------------
@router.get("/estado")
def estado() -> dict[str, Any]:
    try:
        with _conectar() as con, con.cursor() as cur:
            cur.execute("SELECT count(*) AS n FROM version_esquema WHERE activa")
            n = cur.fetchone()["n"]
        return {"ok": True, "base_de_datos": "conectada", "bases_configuradas": n}
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "base_de_datos": "sin conexión", "error": str(exc)}


@router.get("/bases")
def listar_bases() -> list[dict[str, Any]]:
    with _conectar() as con, con.cursor() as cur:
        cur.execute(
            """SELECT t.codigo, t.nombre, i.siglas AS institucion, t.periodicidad, ve.version,
                      count(v.id) FILTER (WHERE v.se_publica) AS columnas_publicadas
               FROM tipo_base t
               JOIN institucion i ON i.id = t.institucion_id
               LEFT JOIN version_esquema ve ON ve.tipo_base_id = t.id AND ve.activa
               LEFT JOIN variable v ON v.version_esquema_id = ve.id
               GROUP BY t.codigo, t.nombre, i.siglas, t.periodicidad, ve.version ORDER BY t.codigo""")
        return cur.fetchall()


@router.get("/bases/{codigo}")
def detalle_base(codigo: str) -> dict[str, Any]:
    with _conectar() as con, con.cursor() as cur:
        cur.execute("""SELECT t.codigo, t.nombre, i.siglas AS institucion, t.periodicidad, ve.id AS version_id, ve.version
                       FROM tipo_base t JOIN institucion i ON i.id = t.institucion_id
                       JOIN version_esquema ve ON ve.tipo_base_id = t.id AND ve.activa WHERE t.codigo = %s""",
                    (codigo.upper(),))
        base = cur.fetchone()
        if not base:
            raise HTTPException(status_code=404, detail="Base no encontrada.")
        cur.execute("""SELECT v.nombre_ine AS nombre, v.etiqueta, v.tipo, c.codigo AS catalogo, v.requerida,
                              v.valor_min, v.valor_max, v.codigo_ignorado, v.transformacion,
                              coalesce(array_agg(a.alias) FILTER (WHERE a.alias IS NOT NULL), '{}') AS alias
                       FROM variable v LEFT JOIN catalogo c ON c.id = v.catalogo_id
                       LEFT JOIN alias_columna a ON a.variable_id = v.id
                       WHERE v.version_esquema_id = %s AND v.se_publica
                       GROUP BY v.id, c.codigo ORDER BY v.orden""", (base["version_id"],))
        base["variables"] = cur.fetchall()
        cur.execute("""SELECT codigo, nombre, dimension, severidad, accion, parametros
                       FROM regla WHERE activa AND (tipo_base_id IS NULL OR
                         tipo_base_id = (SELECT id FROM tipo_base WHERE codigo = %s)) ORDER BY codigo""",
                    (codigo.upper(),))
        base["reglas"] = cur.fetchall()
        return base


# ---------------------------------------------------------------------------
# Cargas
# ---------------------------------------------------------------------------
@router.post("/cargas")
async def crear_carga(
    file: UploadFile = File(...),
    base: str = Form(...),
    anio: int = Form(...),
    mes: int | None = Form(None),
    usuario: str | None = Form(None),
) -> dict[str, Any]:
    if not file.filename:
        raise HTTPException(status_code=400, detail="Debes seleccionar un archivo.")
    carga_id, base, usuario_id, previas = _registrar_carga(base, anio, mes, file.filename, usuario)

    carpeta = _almacen() / carga_id
    carpeta.mkdir(parents=True, exist_ok=True)
    destino = carpeta / f"original{Path(file.filename).suffix.lower()}"
    total = 0
    try:
        with destino.open("wb") as out:
            while chunk := await file.read(1024 * 1024):
                out.write(chunk)
                total += len(chunk)
    finally:
        await file.close()
    if total == 0:
        raise HTTPException(status_code=400, detail="El archivo está vacío.")

    ubicar = None
    if almacenamiento.usa_supabase():
        ruta = await run_in_threadpool(almacenamiento.subir, destino, almacenamiento.objeto(carga_id, destino.name))
        ubicar = _ubicador(carga_id, ruta)
    # En modo síncrono valida aquí mismo: fuera del event loop para no bloquear otras peticiones.
    await run_in_threadpool(_encolar, carga_id, base, destino, anio, mes, usuario_id, ubicar)
    respuesta = {"carga_id": carga_id, "estado": _estado(carga_id).get("estado", "en_cola"),
                 "archivo": _nombre_seguro(file.filename)}
    if previas:
        respuesta["aviso"] = f"Ya hay {len(previas)} carga(s) de esta base para el mismo período."
        respuesta["cargas_previas"] = previas
    return respuesta


def _registrar_carga(base: str, anio: int, mes: int | None, archivo: str,
                     usuario: str | None = None) -> tuple[str, str, int, list[str]]:
    """Valida la base y el período, crea la carga en estado 'recibida' y registra el evento."""
    if Path(archivo).suffix.lower() not in EXTENSIONES:
        raise HTTPException(status_code=400, detail="Formato no soportado. Sube un Excel (.xlsx, .xls) o un CSV.")
    if mes is not None and not 1 <= mes <= 12:
        raise HTTPException(status_code=400, detail="El mes debe estar entre 1 y 12.")
    if not 1900 <= anio <= 2100:
        raise HTTPException(status_code=400, detail="El año debe estar entre 1900 y 2100.")
    base = base.upper()
    with _conectar() as con, con.cursor() as cur:
        cur.execute("""SELECT t.id, t.institucion_id, t.periodicidad FROM tipo_base t
                       JOIN version_esquema ve ON ve.tipo_base_id = t.id AND ve.activa WHERE t.codigo = %s""", (base,))
        tb = cur.fetchone()
        if not tb:
            raise HTTPException(status_code=400, detail=f"La base {base} no existe o no tiene configuración activa.")
        if tb["periodicidad"] == "mensual" and mes is None:
            raise HTTPException(status_code=400, detail="Esta base es mensual: indica el mes del envío.")
        usuario_id = _usuario_id(cur, usuario)
        cur.execute("""INSERT INTO carga (institucion_id, tipo_base_id, usuario_id, periodo_anio, periodo_mes, estado)
                       VALUES (%s, %s, %s, %s, %s, 'recibida') RETURNING id""",
                    (tb["institucion_id"], tb["id"], usuario_id, anio, mes))
        carga_id = str(cur.fetchone()["id"])
        cur.execute("""SELECT id FROM carga WHERE tipo_base_id = %s AND periodo_anio = %s
                       AND periodo_mes IS NOT DISTINCT FROM %s AND id <> %s AND estado <> 'error'""",
                    (tb["id"], anio, mes, carga_id))
        previas = [str(x["id"]) for x in cur.fetchall()]
        cur.execute("""INSERT INTO evento_auditoria (usuario_id, accion, entidad, entidad_id, detalle)
                       VALUES (%s, 'subir_archivo', 'carga', %s, %s)""",
                    (usuario_id, carga_id, json.dumps({"archivo": _nombre_seguro(archivo), "base": base},
                                                       ensure_ascii=False)))
        con.commit()
    return carga_id, base, usuario_id, previas


# ---------------------------------------------------------------------------
# Flujo en tres pasos: preparar subida → subir el archivo → procesar
# ---------------------------------------------------------------------------
class NuevaCarga(BaseModel):
    base: str = Field(min_length=1, max_length=50)
    anio: int = Field(ge=1900, le=2100)
    mes: int | None = Field(default=None, ge=1, le=12)
    archivo: str = Field(min_length=1, max_length=300)
    tamano: int | None = Field(default=None, ge=0)


@router.post("/cargas/subida")
def preparar_subida(datos: NuevaCarga) -> dict[str, Any]:
    """Registra la carga y devuelve a dónde subir el archivo original con PUT."""
    if datos.tamano is not None and datos.tamano > _max_bytes():
        raise HTTPException(status_code=413, detail=f"El archivo supera el límite de {_max_bytes() // (1024 * 1024)} MB.")
    if datos.tamano == 0:
        raise HTTPException(status_code=400, detail="El archivo está vacío.")
    carga_id, base, _, previas = _registrar_carga(datos.base, datos.anio, datos.mes, datos.archivo)
    nombre = f"original{Path(datos.archivo).suffix.lower()}"
    if almacenamiento.usa_supabase():
        subida = {"url": almacenamiento.url_subida(almacenamiento.objeto(carga_id, nombre)), "metodo": "PUT",
                  "directa": True}
    else:
        subida = {"url": f"/api/qa/cargas/{carga_id}/archivo", "metodo": "PUT", "directa": False}
    respuesta = {"carga_id": carga_id, "base": base, "subida": subida, "max_bytes": _max_bytes()}
    if previas:
        respuesta["aviso"] = f"Ya hay {len(previas)} carga(s) de esta base para el mismo período."
    return respuesta


def _carga_pendiente(cur, carga_id: str) -> dict[str, Any]:
    """Datos de una carga creada con /cargas/subida, con la extensión del archivo que se anunció."""
    if not UUID.fullmatch(carga_id):
        raise HTTPException(status_code=404, detail="Carga no encontrada.")
    cur.execute("""SELECT c.id::text AS carga_id, t.codigo AS base, c.periodo_anio AS anio, c.periodo_mes AS mes,
                          c.estado::text AS estado,
                          (SELECT e.detalle->>'archivo' FROM evento_auditoria e
                           WHERE e.entidad = 'carga' AND e.entidad_id = c.id::text AND e.accion = 'subir_archivo'
                           ORDER BY e.id LIMIT 1) AS archivo
                   FROM carga c JOIN tipo_base t ON t.id = c.tipo_base_id WHERE c.id::text = %s""", (carga_id,))
    c = cur.fetchone()
    if not c:
        raise HTTPException(status_code=404, detail="Carga no encontrada.")
    c["original"] = f"original{Path(c['archivo'] or '').suffix.lower()}"
    return c


@router.put("/cargas/{carga_id}/archivo")
async def recibir_archivo(carga_id: str, request: Request) -> dict[str, Any]:
    """Solo en modo local: recibe el original (con Supabase el navegador sube directo a Storage)."""
    if almacenamiento.usa_supabase():
        raise HTTPException(status_code=409, detail="Con Supabase Storage el archivo se sube a la URL firmada.")
    with _conectar() as con, con.cursor() as cur:
        c = _carga_pendiente(cur, carga_id)
    if c["estado"] != "recibida":
        raise HTTPException(status_code=409, detail="La carga ya tiene un archivo procesado.")
    destino = _almacen() / carga_id / c["original"]
    destino.parent.mkdir(parents=True, exist_ok=True)
    total = 0
    with destino.open("wb") as out:
        async for bloque in request.stream():
            total += len(bloque)
            if total > _max_bytes():
                out.close()
                destino.unlink(missing_ok=True)
                raise HTTPException(status_code=413, detail="El archivo supera el límite permitido.")
            out.write(bloque)
    if not total:
        destino.unlink(missing_ok=True)
        raise HTTPException(status_code=400, detail="El archivo está vacío.")
    return {"carga_id": carga_id, "bytes": total}


def _descargas(carga_id: str) -> dict[str, str]:
    return {rol: f"/api/qa/cargas/{carga_id}/descargar/{rol}" for rol in ("corregido", "bitacora", "reporte")}


@router.post("/cargas/{carga_id}/procesar")
def procesar_carga(carga_id: str) -> dict[str, Any]:
    """Valida el archivo ya subido en esta misma petición y devuelve el reporte."""
    with _conectar() as con, con.cursor() as cur:
        c = _carga_pendiente(cur, carga_id)
        usuario_id = _usuario_id(cur, None)
        # Se toma la carga de forma atómica: dos peticiones simultáneas no la validan dos veces.
        # Una carga que quedó "procesando" más de 6 minutos (p. ej. Vercel cortó la función a los
        # 300 s) se puede volver a intentar.
        cur.execute("""UPDATE carga SET estado = 'procesando', actualizado_en = now()
                       WHERE id::text = %s AND (estado IN ('recibida', 'error')
                             OR (estado = 'procesando' AND actualizado_en < now() - interval '6 minutes'))
                       RETURNING id""", (carga_id,))
        tomada = cur.fetchone()
        con.commit()
    if not tomada:
        if c["estado"] == "procesando":
            raise HTTPException(status_code=409, detail="La carga ya se está procesando.")
        raise HTTPException(status_code=409, detail="La carga ya se procesó. Usa /reprocesar para repetirla.")

    trabajo = None
    if almacenamiento.usa_supabase():
        trabajo = _carpeta_trabajo(carga_id)
        original = trabajo / c["original"]
        ruta_original = almacenamiento.ruta_supabase(almacenamiento.objeto(carga_id, c["original"]))
        try:
            almacenamiento.descargar(ruta_original, original)
        except FileNotFoundError:
            shutil.rmtree(trabajo, ignore_errors=True)
            _liberar(carga_id, c["estado"])
            raise HTTPException(status_code=400, detail="El archivo todavía no se ha subido.") from None
        except Exception:
            shutil.rmtree(trabajo, ignore_errors=True)
            _liberar(carga_id, c["estado"])
            raise
        ubicar = _ubicador(carga_id, ruta_original)
    else:
        original = _almacen() / carga_id / c["original"]
        if not original.is_file():
            _liberar(carga_id, c["estado"])
            raise HTTPException(status_code=400, detail="El archivo todavía no se ha subido.")
        ubicar = None
    if original.stat().st_size > _max_bytes():
        if trabajo:
            shutil.rmtree(trabajo, ignore_errors=True)
        _liberar(carga_id, c["estado"])
        raise HTTPException(status_code=413, detail="El archivo supera el límite permitido.")

    try:
        _avance(carga_id, estado="en_cola", etapa="Procesando…", porcentaje=2, error=None)
        _procesar_carga(carga_id, c["base"], original, c["anio"], c["mes"], usuario_id, ubicar)
        estado = _estado(carga_id)
        if estado.get("estado") == "error":
            raise HTTPException(status_code=422, detail=f"No se pudo validar la base: {estado.get('error')}")
        reporte = json.loads((original.parent / "reporte.json").read_text(encoding="utf-8"))
    finally:
        if trabajo:
            shutil.rmtree(trabajo, ignore_errors=True)
    return {"carga_id": carga_id, "estado": "terminado", "segundos": estado.get("segundos"),
            "reporte": reporte, "descargas": _descargas(carga_id)}


def _liberar(carga_id: str, estado_previo: str) -> None:
    """Devuelve la carga a su estado anterior cuando no se llegó a procesar."""
    with _conexion() as con, con.cursor() as cur:
        cur.execute("UPDATE carga SET estado = %s, actualizado_en = now() WHERE id::text = %s AND estado = 'procesando'",
                    (estado_previo if estado_previo in ("recibida", "error") else "recibida", carga_id))
        con.commit()


@router.get("/cargas/{carga_id}/reporte")
def reporte_carga(carga_id: str) -> dict[str, Any]:
    """Reporte JSON de la última ejecución (el mismo formato que devuelve /procesar)."""
    a = _ultimo_archivo(carga_id, "reporte")
    ruta = a["ruta"]
    if almacenamiento.es_supabase(ruta):
        with tempfile.TemporaryDirectory() as tmp:
            texto = almacenamiento.descargar(ruta, Path(tmp) / "reporte.json").read_text(encoding="utf-8")
    elif Path(ruta).is_file():
        texto = Path(ruta).read_text(encoding="utf-8")
    else:
        raise HTTPException(status_code=404, detail="Archivo no disponible.")
    return {"carga_id": carga_id, "reporte": json.loads(texto), "descargas": _descargas(carga_id)}


def _ultimo_archivo(carga_id: str, rol: str) -> dict[str, Any]:
    with _conectar() as con, con.cursor() as cur:
        cur.execute("""SELECT a.ruta, t.codigo AS base, c.periodo_anio, c.periodo_mes FROM archivo a
                       JOIN carga c ON c.id = a.carga_id JOIN tipo_base t ON t.id = c.tipo_base_id
                       WHERE a.carga_id::text = %s AND a.rol = %s ORDER BY a.creado_en DESC LIMIT 1""", (carga_id, rol))
        a = cur.fetchone()
    if not a:
        raise HTTPException(status_code=404, detail="Archivo no disponible.")
    return a


@router.get("/cargas")
def listar_cargas(base: str | None = None, estado: str | None = None, institucion: str | None = None,
                  limite: int = Query(50, le=500)) -> list[dict[str, Any]]:
    filtros, params = [], []
    if base:
        filtros.append("t.codigo = %s")
        params.append(base.upper())
    if estado:
        filtros.append("c.estado = %s")
        params.append(estado)
    if institucion:
        filtros.append("i.siglas = %s")
        params.append(institucion.upper())
    where = ("WHERE " + " AND ".join(filtros)) if filtros else ""
    with _conectar() as con, con.cursor() as cur:
        cur.execute(f"""
            SELECT c.id::text AS carga_id, t.codigo AS base, i.siglas AS institucion, c.periodo_anio AS anio,
                   c.periodo_mes AS mes, c.estado, c.puntaje_calidad AS puntaje, c.creado_en, c.actualizado_en,
                   e.total_registros, e.registros_validos, e.registros_excluidos,
                   (e.resumen->>'sugerencias_pendientes')::int AS sugerencias_pendientes
            FROM carga c JOIN tipo_base t ON t.id = c.tipo_base_id JOIN institucion i ON i.id = c.institucion_id
            LEFT JOIN LATERAL (SELECT * FROM ejecucion x WHERE x.carga_id = c.id
                               ORDER BY x.iniciada_en DESC LIMIT 1) e ON TRUE
            {where} ORDER BY c.creado_en DESC LIMIT %s""", (*params, limite))
        filas = cur.fetchall()
    for f in filas:
        with progreso_lock:
            p = progreso.get(f["carga_id"])
        if p and p.get("estado") in ("en_cola", "procesando"):
            f["avance"] = {"etapa": p.get("etapa"), "porcentaje": p.get("porcentaje")}
    return filas


def _ultima_ejecucion(cur, carga_id: str) -> dict | None:
    cur.execute("""SELECT id::text AS ejecucion_id, iniciada_en, finalizada_en, total_registros, registros_validos,
                          registros_excluidos, puntaje, mapeo_columnas, resumen
                   FROM ejecucion WHERE carga_id = %s ORDER BY iniciada_en DESC LIMIT 1""", (carga_id,))
    return cur.fetchone()


@router.get("/cargas/{carga_id}")
def detalle_carga(carga_id: str) -> dict[str, Any]:
    with _conectar() as con, con.cursor() as cur:
        cur.execute("""SELECT c.id::text AS carga_id, t.codigo AS base, t.nombre AS nombre_base, i.siglas AS institucion,
                              c.periodo_anio AS anio, c.periodo_mes AS mes, c.estado, c.puntaje_calidad AS puntaje,
                              c.notas, c.creado_en, c.actualizado_en, u.email AS usuario
                       FROM carga c JOIN tipo_base t ON t.id = c.tipo_base_id
                       JOIN institucion i ON i.id = c.institucion_id JOIN usuario u ON u.id = c.usuario_id
                       WHERE c.id::text = %s""", (carga_id,))
        carga = cur.fetchone()
        if not carga:
            raise HTTPException(status_code=404, detail="Carga no encontrada.")
        ej = _ultima_ejecucion(cur, carga_id)
        carga["ejecucion"] = ej
        if ej:
            cur.execute("SELECT dimension, puntaje FROM puntaje_dimension WHERE ejecucion_id = %s ORDER BY dimension",
                        (ej["ejecucion_id"],))
            carga["puntajes"] = {r["dimension"]: float(r["puntaje"]) for r in cur.fetchall()}
            cur.execute("""SELECT severidad, count(*) AS n FROM hallazgo WHERE ejecucion_id = %s GROUP BY severidad""",
                        (ej["ejecucion_id"],))
            carga["hallazgos_por_severidad"] = {r["severidad"]: r["n"] for r in cur.fetchall()}
            cur.execute("SELECT count(*) AS n FROM correccion WHERE ejecucion_id = %s AND estado = 'pendiente'",
                        (ej["ejecucion_id"],))
            carga["sugerencias_pendientes"] = cur.fetchone()["n"]
            cur.execute("""SELECT DISTINCT ON (rol) rol, nombre, tamano_bytes, creado_en FROM archivo
                           WHERE carga_id = %s ORDER BY rol, creado_en DESC""", (carga_id,))
            carga["archivos"] = [a for a in cur.fetchall() if a["rol"] in DESCARGABLES | {"original"}]
    with progreso_lock:
        p = dict(progreso.get(carga_id) or {})
    if p:
        carga["avance"] = {k: p.get(k) for k in ("estado", "etapa", "porcentaje", "error", "segundos")}
        if p.get("estado") == "procesando" and p.get("inicio"):
            carga["avance"]["segundos"] = round(time.time() - p["inicio"], 1)
    return carga


@router.get("/cargas/{carga_id}/hallazgos")
def hallazgos(carga_id: str, severidad: str | None = None, dimension: str | None = None,
              incluir_info: bool = True) -> list[dict[str, Any]]:
    with _conectar() as con, con.cursor() as cur:
        ej = _ultima_ejecucion(cur, carga_id)
        if not ej:
            raise HTTPException(status_code=404, detail="La carga todavía no tiene resultados.")
        filtros, params = ["h.ejecucion_id = %s"], [ej["ejecucion_id"]]
        if severidad:
            filtros.append("h.severidad = %s")
            params.append(severidad)
        if dimension:
            filtros.append("r.dimension = %s")
            params.append(dimension)
        if not incluir_info:
            filtros.append("h.severidad <> 'info'")
        cur.execute(f"""SELECT h.id, r.codigo AS regla, r.nombre, r.dimension, r.accion, h.severidad, h.columna, h.hoja,
                               h.registros_afectados, h.porcentaje, h.mensaje, h.ejemplos, h.estado
                        FROM hallazgo h JOIN regla r ON r.id = h.regla_id
                        WHERE {' AND '.join(filtros)}
                        ORDER BY array_position(ARRAY['error','advertencia','info']::severidad[], h.severidad),
                                 h.registros_afectados DESC""", params)
        return cur.fetchall()


@router.get("/cargas/{carga_id}/sugerencias")
def sugerencias(carga_id: str, estado: str = "pendiente", columna: str | None = None) -> list[dict[str, Any]]:
    with _conectar() as con, con.cursor() as cur:
        ej = _ultima_ejecucion(cur, carga_id)
        if not ej:
            raise HTTPException(status_code=404, detail="La carga todavía no tiene resultados.")
        filtros, params = ["x.ejecucion_id = %s", "r.accion = 'sugerir'"], [ej["ejecucion_id"]]
        if estado != "todas":
            filtros.append("x.estado = %s")
            params.append(estado)
        if columna:
            filtros.append("x.columna = %s")
            params.append(columna)
        cur.execute(f"""SELECT x.id, x.columna, x.valor_antes, x.valor_despues AS valor_sugerido, x.registros_afectados,
                               x.fila AS primera_fila, x.hoja, x.origen, x.confianza, x.justificacion, x.estado,
                               r.codigo AS regla
                        FROM correccion x JOIN hallazgo h ON h.id = x.hallazgo_id JOIN regla r ON r.id = h.regla_id
                        WHERE {' AND '.join(filtros)}
                        ORDER BY x.registros_afectados DESC""", params)
        filas = cur.fetchall()
        # Etiqueta del código sugerido, para mostrarla en la bandeja
        for f in filas:
            cat = _catalogo_de_columna(cur, ej["ejecucion_id"], f["columna"])
            f["catalogo"] = cat
            f["etiqueta_sugerida"] = _etiqueta(cur, cat, f["valor_sugerido"]) if cat else None
        return filas


@router.get("/cargas/{carga_id}/excluidos")
def excluidos(carga_id: str) -> list[dict[str, Any]]:
    with _conectar() as con, con.cursor() as cur:
        ej = _ultima_ejecucion(cur, carga_id)
        if not ej:
            raise HTTPException(status_code=404, detail="La carga todavía no tiene resultados.")
        cur.execute("""SELECT x.id, r.codigo AS regla, r.nombre, x.motivo, x.hoja, x.registros_afectados,
                              x.fila AS primera_fila, x.filas
                       FROM registro_excluido x JOIN regla r ON r.id = x.regla_id
                       WHERE x.ejecucion_id = %s ORDER BY x.registros_afectados DESC""", (ej["ejecucion_id"],))
        return cur.fetchall()


@router.get("/cargas/{carga_id}/descargar/{rol}", response_model=None)
def descargar(carga_id: str, rol: str) -> FileResponse | JSONResponse:
    """Archivo local: lo entrega directo. En Supabase Storage: {"url": ...} firmada por 5 minutos."""
    if rol not in DESCARGABLES and rol != "original":
        raise HTTPException(status_code=400, detail="Solo se pueden descargar: original, corregido, bitacora o reporte.")
    if rol == "original":
        # El original trae datos personales: la plataforma exige sesión (middleware) y la descarga queda en la bitácora.
        with _conectar() as con, con.cursor() as cur:
            cur.execute("""INSERT INTO evento_auditoria (usuario_id, accion, entidad, entidad_id)
                           VALUES (%s, 'descargar_original', 'carga', %s)""", (_usuario_id(cur, None), carga_id))
            con.commit()
    a = _ultimo_archivo(carga_id, rol)
    periodo = f"{a['periodo_anio']}" + (f"_{a['periodo_mes']:02d}" if a["periodo_mes"] else "")
    nombre = f"{a['base'].lower()}_{periodo}_{rol}{Path(a['ruta']).suffix}"
    if almacenamiento.es_supabase(a["ruta"]):
        return JSONResponse({"url": almacenamiento.url_descarga(a["ruta"], nombre), "nombre": nombre})
    ruta = Path(a["ruta"])
    if not ruta.exists():
        raise HTTPException(status_code=404, detail="Archivo no disponible.")
    return FileResponse(ruta, filename=nombre)


@router.post("/cargas/{carga_id}/reprocesar")
def reprocesar(carga_id: str, usuario: str | None = Form(None)) -> dict[str, Any]:
    """Vuelve a correr el motor con el mismo archivo: aplica las sugerencias ya aprobadas."""
    with _conectar() as con, con.cursor() as cur:
        cur.execute("""SELECT t.codigo AS base, c.periodo_anio, c.periodo_mes, c.estado FROM carga c
                       JOIN tipo_base t ON t.id = c.tipo_base_id WHERE c.id::text = %s""", (carga_id,))
        c = cur.fetchone()
        if not c:
            raise HTTPException(status_code=404, detail="Carga no encontrada.")
        with progreso_lock:
            if (progreso.get(carga_id) or {}).get("estado") in ("en_cola", "procesando"):
                raise HTTPException(status_code=409, detail="La carga ya se está procesando.")
        cur.execute("SELECT ruta FROM archivo WHERE carga_id::text = %s AND rol = 'original' ORDER BY creado_en LIMIT 1",
                    (carga_id,))
        a = cur.fetchone()
        usuario_id = _usuario_id(cur, usuario)
        cur.execute("""INSERT INTO evento_auditoria (usuario_id, accion, entidad, entidad_id)
                       VALUES (%s, 'reprocesar_carga', 'carga', %s)""", (usuario_id, carga_id))
        con.commit()
    trabajo, ubicar = None, None
    if a and almacenamiento.es_supabase(a["ruta"]):
        # Se trae el original a una carpeta temporal (en un servidor propio, al almacén local).
        carpeta = _carpeta_trabajo(carga_id) if _sincrono() else _almacen() / carga_id
        trabajo = carpeta if _sincrono() else None
        nombre = a["ruta"].rsplit("/", 1)[-1]
        try:
            original = almacenamiento.descargar(a["ruta"], carpeta / nombre)
        except FileNotFoundError:
            raise HTTPException(status_code=404, detail="No se encontró el archivo original de la carga.") from None
        ubicar = _ubicador(carga_id, a["ruta"])
    else:
        original = Path(a["ruta"]) if a else next((_almacen() / carga_id).glob("original.*"), None)
        if not original or not original.exists():
            raise HTTPException(status_code=404, detail="No se encontró el archivo original de la carga.")
    try:
        _encolar(carga_id, c["base"], original, c["periodo_anio"], c["periodo_mes"], usuario_id, ubicar)
    finally:
        if trabajo:
            shutil.rmtree(trabajo, ignore_errors=True)
    estado = _estado(carga_id)
    if _sincrono() and estado.get("estado") == "error":
        raise HTTPException(status_code=422, detail=f"No se pudo validar la base: {estado.get('error')}")
    return {"carga_id": carga_id, "estado": estado.get("estado", "en_cola")}


class Decision(BaseModel):
    usuario: str | None = None
    comentario: str | None = None


@router.post("/cargas/{carga_id}/aprobar")
def aprobar_carga(carga_id: str, decision: Decision) -> dict[str, Any]:
    return _decidir_carga(carga_id, "aprobada", decision)


@router.post("/cargas/{carga_id}/rechazar")
def rechazar_carga(carga_id: str, decision: Decision) -> dict[str, Any]:
    return _decidir_carga(carga_id, "rechazada", decision)


def _decidir_carga(carga_id: str, estado: str, decision: Decision) -> dict[str, Any]:
    with _conectar() as con, con.cursor() as cur:
        usuario_id = _usuario_id(cur, decision.usuario)
        cur.execute("""UPDATE carga SET estado = %s, notas = coalesce(%s, notas), actualizado_en = now()
                       WHERE id::text = %s AND estado IN ('con_observaciones', 'aprobada', 'rechazada')
                       RETURNING id""", (estado, decision.comentario, carga_id))
        if not cur.fetchone():
            raise HTTPException(status_code=409, detail="La carga no existe o todavía se está procesando.")
        cur.execute("""INSERT INTO evento_auditoria (usuario_id, accion, entidad, entidad_id, detalle)
                       VALUES (%s, %s, 'carga', %s, %s)""",
                    (usuario_id, {"aprobada": "aprobar_carga", "rechazada": "rechazar_carga"}[estado], carga_id, json.dumps({"comentario": decision.comentario})))
        con.commit()
    return {"carga_id": carga_id, "estado": estado}


# ---------------------------------------------------------------------------
# Sugerencias: aprobar o rechazar
# ---------------------------------------------------------------------------
class Aprobacion(BaseModel):
    usuario: str | None = None
    codigo: str | None = None        # para corregir la sugerencia: aprobar con otro código


def _catalogo_de_columna(cur, ejecucion_id: str, columna: str) -> str | None:
    cur.execute("""SELECT c.codigo AS catalogo, v.transformacion FROM ejecucion e
                   JOIN variable v ON v.version_esquema_id = e.version_esquema_id AND v.nombre_ine = %s
                   LEFT JOIN catalogo c ON c.id = v.catalogo_id WHERE e.id::text = %s""", (columna, ejecucion_id))
    f = cur.fetchone()
    if not f:
        return None
    return f["catalogo"] or (f["transformacion"] or {}).get("catalogo")


def _etiqueta(cur, catalogo: str, codigo: str | None) -> str | None:
    if not codigo:
        return None
    cur.execute("""SELECT cv.etiqueta FROM catalogo_valor cv JOIN catalogo c ON c.id = cv.catalogo_id
                   WHERE c.codigo = %s AND cv.codigo = %s""", (catalogo, codigo))
    f = cur.fetchone()
    return f["etiqueta"] if f else None


@router.post("/sugerencias/{correccion_id}/aprobar")
def aprobar_sugerencia(correccion_id: int, aprobacion: Aprobacion) -> dict[str, Any]:
    """Aprueba una sugerencia. Queda como equivalencia aprobada de la institución: desde la
    siguiente ejecución, ese texto se codifica solo."""
    with _conectar() as con, con.cursor() as cur:
        cur.execute("""SELECT x.*, x.ejecucion_id::text AS ejec, c.institucion_id, c.id::text AS carga_id
                       FROM correccion x JOIN ejecucion e ON e.id = x.ejecucion_id JOIN carga c ON c.id = e.carga_id
                       WHERE x.id = %s""", (correccion_id,))
        x = cur.fetchone()
        if not x:
            raise HTTPException(status_code=404, detail="Sugerencia no encontrada.")
        if x["estado"] != "pendiente":
            raise HTTPException(status_code=409, detail=f"La sugerencia ya está {x['estado']}.")
        catalogo = _catalogo_de_columna(cur, x["ejec"], x["columna"])
        if not catalogo:
            raise HTTPException(status_code=400, detail="La columna no tiene catálogo asociado.")
        codigo = (aprobacion.codigo or x["valor_despues"] or "").strip()
        if not _etiqueta(cur, catalogo, codigo):
            raise HTTPException(status_code=400, detail=f"El código {codigo} no existe en el catálogo {catalogo}.")
        usuario_id = _usuario_id(cur, aprobacion.usuario)
        fuente = "ia" if x["origen"] == "ia" and not aprobacion.codigo else "manual"
        cur.execute("""INSERT INTO equivalencia (catalogo_id, institucion_id, texto_origen, codigo, fuente, confianza,
                                                 aprobada, aprobada_por)
                       SELECT id, %s, %s, %s, %s, %s, TRUE, %s FROM catalogo WHERE codigo = %s
                       ON CONFLICT (catalogo_id, institucion_id, texto_origen) DO UPDATE SET
                         codigo = EXCLUDED.codigo, fuente = EXCLUDED.fuente, aprobada = TRUE,
                         aprobada_por = EXCLUDED.aprobada_por
                       RETURNING id""",
                    (x["institucion_id"], normalizar(x["valor_antes"]), codigo, fuente, x["confianza"], usuario_id,
                     catalogo))
        eq_id = cur.fetchone()["id"]
        cur.execute("""UPDATE correccion SET estado = 'aplicada', valor_despues = %s, equivalencia_id = %s,
                         revisada_por = %s, revisada_en = now() WHERE id = %s""",
                    (codigo, eq_id, usuario_id, correccion_id))
        cur.execute("""INSERT INTO evento_auditoria (usuario_id, accion, entidad, entidad_id, detalle)
                       VALUES (%s, 'aprobar_sugerencia', 'correccion', %s, %s)""",
                    (usuario_id, str(correccion_id),
                     json.dumps({"texto": x["valor_antes"], "codigo": codigo, "corregida": bool(aprobacion.codigo)},
                                ensure_ascii=False)))
        con.commit()
    return {"id": correccion_id, "estado": "aplicada", "codigo": codigo, "equivalencia_id": eq_id,
            "registros_afectados": x["registros_afectados"],
            "mensaje": "Aprobada. Reprocesa la carga para aplicarla al archivo corregido."}


@router.post("/sugerencias/{correccion_id}/rechazar")
def rechazar_sugerencia(correccion_id: int, decision: Decision) -> dict[str, Any]:
    with _conectar() as con, con.cursor() as cur:
        cur.execute("""SELECT x.estado, x.valor_antes, x.columna, x.ejecucion_id::text AS ejec, c.institucion_id
                       FROM correccion x JOIN ejecucion e ON e.id = x.ejecucion_id JOIN carga c ON c.id = e.carga_id
                       WHERE x.id = %s""", (correccion_id,))
        x = cur.fetchone()
        if not x:
            raise HTTPException(status_code=404, detail="Sugerencia no encontrada.")
        if x["estado"] != "pendiente":
            raise HTTPException(status_code=409, detail=f"La sugerencia ya está {x['estado']}.")
        usuario_id = _usuario_id(cur, decision.usuario)
        cur.execute("""UPDATE correccion SET estado = 'rechazada', revisada_por = %s, revisada_en = now(),
                         justificacion = coalesce(justificacion, '') || coalesce(' | Rechazo: ' || %s, '')
                       WHERE id = %s""", (usuario_id, decision.comentario, correccion_id))
        # Si era una sugerencia de IA guardada en memoria, se descarta para no volver a proponerla igual
        catalogo = _catalogo_de_columna(cur, x["ejec"], x["columna"])
        if catalogo:
            cur.execute("""DELETE FROM equivalencia WHERE NOT aprobada AND institucion_id = %s AND texto_origen = %s
                           AND catalogo_id = (SELECT id FROM catalogo WHERE codigo = %s)""",
                        (x["institucion_id"], normalizar(x["valor_antes"]), catalogo))
        cur.execute("""INSERT INTO evento_auditoria (usuario_id, accion, entidad, entidad_id, detalle)
                       VALUES (%s, 'rechazar_sugerencia', 'correccion', %s, %s)""",
                    (usuario_id, str(correccion_id), json.dumps({"comentario": decision.comentario})))
        con.commit()
    return {"id": correccion_id, "estado": "rechazada"}


@router.get("/catalogos/{codigo}")
def buscar_en_catalogo(codigo: str, q: str | None = None, limite: int = Query(20, le=200)) -> list[dict[str, Any]]:
    """Para el selector del front cuando el analista corrige una sugerencia."""
    with _conectar() as con, con.cursor() as cur:
        cur.execute("""SELECT cv.codigo, cv.etiqueta FROM catalogo_valor cv JOIN catalogo c ON c.id = cv.catalogo_id
                       WHERE c.codigo = %s AND cv.activo ORDER BY cv.codigo""", (codigo.upper(),))
        filas = cur.fetchall()
    if not filas:
        raise HTTPException(status_code=404, detail="Catálogo no encontrado.")
    if q:
        n = normalizar(q)
        filas = [f for f in filas if f["codigo"].upper().startswith(n) or n in normalizar(f["etiqueta"])]
        filas.sort(key=lambda f: (not f["codigo"].upper().startswith(n), len(f["etiqueta"])))
    return filas[:limite]


# ---------------------------------------------------------------------------
# Correcciones guardadas (equivalencias aprobadas por institución)
# ---------------------------------------------------------------------------
@router.get("/equivalencias")
def listar_equivalencias(institucion: str | None = None, catalogo: str | None = None, q: str | None = None,
                         limite: int = Query(200, le=1000)) -> list[dict[str, Any]]:
    """Correcciones aprobadas: cada texto de origen con el código que se le asignó. Desde la siguiente
    validación, ese texto se corrige solo para la institución."""
    filtros, params = ["e.aprobada"], []
    if institucion:
        filtros.append("i.siglas = %s")
        params.append(institucion.upper())
    if catalogo:
        filtros.append("c.codigo = %s")
        params.append(catalogo.upper())
    with _conectar() as con, con.cursor() as cur:
        cur.execute(f"""SELECT e.id, coalesce(i.siglas, 'TODAS') AS institucion, c.codigo AS catalogo, c.nombre AS nombre_catalogo,
                               e.texto_origen, e.codigo, cv.etiqueta, e.fuente::text AS fuente, e.veces_usada, e.creado_en,
                               u.email AS aprobada_por
                        FROM equivalencia e JOIN catalogo c ON c.id = e.catalogo_id
                        LEFT JOIN institucion i ON i.id = e.institucion_id
                        LEFT JOIN catalogo_valor cv ON cv.catalogo_id = c.id AND cv.codigo = e.codigo
                        LEFT JOIN usuario u ON u.id = e.aprobada_por
                        WHERE {' AND '.join(filtros)} ORDER BY e.creado_en DESC LIMIT %s""", (*params, limite))
        filas = cur.fetchall()
    if q:
        n = normalizar(q)
        filas = [f for f in filas if n in normalizar(f["texto_origen"]) or n in normalizar(f["etiqueta"] or "") or f["codigo"].upper().startswith(n)]
    return filas


@router.delete("/equivalencias/{equivalencia_id}")
def quitar_equivalencia(equivalencia_id: int) -> dict[str, Any]:
    """Deja de aplicar una corrección guardada. Las bases ya validadas no cambian hasta reprocesarlas."""
    with _conectar() as con, con.cursor() as cur:
        cur.execute("""SELECT e.texto_origen, e.codigo, c.codigo AS catalogo FROM equivalencia e
                       JOIN catalogo c ON c.id = e.catalogo_id WHERE e.id = %s""", (equivalencia_id,))
        e = cur.fetchone()
        if not e:
            raise HTTPException(status_code=404, detail="La corrección guardada no existe.")
        usuario_id = _usuario_id(cur, None)
        cur.execute("UPDATE correccion SET equivalencia_id = NULL WHERE equivalencia_id = %s", (equivalencia_id,))
        cur.execute("DELETE FROM equivalencia WHERE id = %s", (equivalencia_id,))
        cur.execute("""INSERT INTO evento_auditoria (usuario_id, accion, entidad, entidad_id, detalle)
                       VALUES (%s, 'quitar_equivalencia', 'equivalencia', %s, %s)""",
                    (usuario_id, str(equivalencia_id), json.dumps(e, ensure_ascii=False, default=str)))
        con.commit()
    return {"id": equivalencia_id, "eliminada": True}
