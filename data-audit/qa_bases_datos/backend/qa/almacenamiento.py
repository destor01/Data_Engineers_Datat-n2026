"""Dónde viven los archivos de las cargas: Supabase Storage (despliegue) o una carpeta local.

Supabase (si hay SUPABASE_URL y SUPABASE_SERVICE_ROLE_KEY):
    bucket privado QA_STORAGE_BUCKET (por defecto "qa-cargas"), objetos cargas/<carga_id>/<archivo>.
    El navegador sube el original directo con una URL firmada (Vercel no acepta más de 4.5 MB
    por petición) y descarga los resultados con URLs firmadas de corta duración.
Local (sin Supabase, o QA_ALMACENAMIENTO=local):
    carpeta QA_ALMACEN (por defecto qa_bases_datos/almacen), igual que antes.

En la tabla `archivo`, la columna `ruta` guarda "supabase://<bucket>/<objeto>" o la ruta local.
"""
from __future__ import annotations

import os
import shutil
from pathlib import Path
from urllib.parse import quote

import requests

PREFIJO = "supabase://"
TIPOS = {".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
         ".xls": "application/vnd.ms-excel", ".csv": "text/csv", ".txt": "text/plain",
         ".json": "application/json"}
_sesion = requests.Session()


def _credenciales() -> tuple[str, str]:
    url = (os.environ.get("SUPABASE_URL") or "").strip().rstrip("/")
    llave = (os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or os.environ.get("SUPABASE_SECRET_KEY") or "").strip()
    return url, llave


def usa_supabase() -> bool:
    modo = (os.environ.get("QA_ALMACENAMIENTO") or "").strip().lower()
    if modo == "local":
        return False
    url, llave = _credenciales()
    if modo == "supabase" and not (url and llave):
        raise RuntimeError("QA_ALMACENAMIENTO=supabase requiere SUPABASE_URL y SUPABASE_SERVICE_ROLE_KEY.")
    return bool(url and llave)


def bucket() -> str:
    return (os.environ.get("QA_STORAGE_BUCKET") or "qa-cargas").strip()


def objeto(carga_id: str, nombre: str) -> str:
    return f"cargas/{carga_id}/{nombre}"


def ruta_supabase(nombre_objeto: str) -> str:
    return f"{PREFIJO}{bucket()}/{nombre_objeto}"


def es_supabase(ruta: str) -> bool:
    return ruta.startswith(PREFIJO)


def _partir(ruta: str) -> tuple[str, str]:
    cubeta, _, nombre = ruta[len(PREFIJO):].partition("/")
    return cubeta, nombre


def _url(*partes: str) -> str:
    base, _ = _credenciales()
    limpio = "/".join(quote(p, safe="") for parte in partes for p in parte.strip("/").split("/"))
    return f"{base}/storage/v1/{limpio}"


def _cabeceras(extra: dict[str, str] | None = None) -> dict[str, str]:
    _, llave = _credenciales()
    # Con las llaves nuevas (sb_secret_) Supabase solo acepta Authorization si es igual a apikey.
    return {"apikey": llave, "Authorization": f"Bearer {llave}", **(extra or {})}


def _revisar(resp: requests.Response, accion: str) -> None:
    if resp.status_code >= 300:
        raise RuntimeError(f"Supabase Storage rechazó {accion} ({resp.status_code}): {resp.text[:300]}")


def url_subida(nombre_objeto: str) -> str:
    """URL firmada para que el navegador suba el archivo con PUT (expira en 2 horas)."""
    resp = _sesion.post(_url("object/upload/sign", bucket(), nombre_objeto), headers=_cabeceras(), json={},
                        timeout=15)
    _revisar(resp, "crear la URL de carga")
    rel = str(resp.json().get("url") or "")
    base, _ = _credenciales()
    if rel.startswith("http"):
        return rel
    return f"{base}{rel}" if rel.startswith("/storage/v1") else f"{base}/storage/v1/{rel.lstrip('/')}"


def url_descarga(ruta: str, nombre_archivo: str, expira: int = 300) -> str:
    cubeta, nombre = _partir(ruta)
    resp = _sesion.post(_url("object/sign", cubeta, nombre), headers=_cabeceras(), json={"expiresIn": expira},
                        timeout=15)
    _revisar(resp, "firmar la descarga")
    rel = str(resp.json().get("signedURL") or resp.json().get("signedUrl") or "")
    base, _ = _credenciales()
    url = rel if rel.startswith("http") else (f"{base}{rel}" if rel.startswith("/storage/v1")
                                              else f"{base}/storage/v1/{rel.lstrip('/')}")
    return f"{url}{'&' if '?' in url else '?'}download={quote(nombre_archivo)}"


def descargar(ruta: str, destino: Path) -> Path:
    """Copia el objeto a un archivo local (para procesarlo)."""
    cubeta, nombre = _partir(ruta)
    destino.parent.mkdir(parents=True, exist_ok=True)
    with _sesion.get(_url("object", cubeta, nombre), headers=_cabeceras(), stream=True, timeout=120) as resp:
        if resp.status_code == 404 or (resp.status_code == 400 and "not found" in resp.text.lower()):
            raise FileNotFoundError(ruta)
        _revisar(resp, "entregar el archivo")
        with destino.open("wb") as salida:
            shutil.copyfileobj(resp.raw, salida)
    return destino


def subir(origen: Path, nombre_objeto: str) -> str:
    """Sube (o reemplaza) un archivo local y devuelve su ruta supabase://."""
    with origen.open("rb") as datos:
        resp = _sesion.post(_url("object", bucket(), nombre_objeto), data=datos, timeout=300,
                            headers=_cabeceras({"Content-Type": TIPOS.get(origen.suffix.lower(), "application/octet-stream"),
                                                "x-upsert": "true"}))
    _revisar(resp, "guardar el archivo")
    return ruta_supabase(nombre_objeto)
