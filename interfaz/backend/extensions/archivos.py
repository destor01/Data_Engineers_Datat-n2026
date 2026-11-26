"""Archivos de Survey Audit (cuestionarios en PDF): Supabase Storage en el despliegue, disco en local.

Bucket privado SURVEY_STORAGE_BUCKET (por defecto "encuestas"); se crea solo si no existe.
El navegador sube el PDF con una URL firmada, así no pasa por el límite de 4.5 MB de Vercel.
"""
from __future__ import annotations

import os
import tempfile
from pathlib import Path
from urllib.parse import quote

import requests

_sesion = requests.Session()
_cubetas_listas: set[str] = set()
IS_VERCEL = bool(os.environ.get('VERCEL') or os.environ.get('VERCEL_ENV'))


def _credenciales() -> tuple[str, str]:
    url = (os.environ.get('SUPABASE_URL') or '').strip().rstrip('/')
    llave = (os.environ.get('SUPABASE_SERVICE_ROLE_KEY') or os.environ.get('SUPABASE_SECRET_KEY') or '').strip()
    return url, llave


def usa_supabase() -> bool:
    url, llave = _credenciales()
    return bool(url and llave)


def cubeta() -> str:
    return (os.environ.get('SURVEY_STORAGE_BUCKET') or 'encuestas').strip()


def _local() -> Path:
    raiz = Path(tempfile.gettempdir()) / 'encuestas' if IS_VERCEL else Path(__file__).resolve().parents[1] / 'almacen' / 'encuestas'
    raiz.mkdir(parents=True, exist_ok=True)
    return raiz


def _url(*partes: str) -> str:
    base, _ = _credenciales()
    limpio = '/'.join(quote(p, safe='') for parte in partes for p in parte.strip('/').split('/'))
    return f'{base}/storage/v1/{limpio}'


def _cabeceras(extra: dict | None = None) -> dict:
    _, llave = _credenciales()
    return {'apikey': llave, 'Authorization': f'Bearer {llave}', **(extra or {})}


def _asegurar_cubeta() -> None:
    nombre = cubeta()
    if nombre in _cubetas_listas:
        return
    r = _sesion.get(_url('bucket', nombre), headers=_cabeceras(), timeout=10)
    if r.status_code != 200:
        _sesion.post(_url('bucket'), headers=_cabeceras(), json={'id': nombre, 'name': nombre, 'public': False}, timeout=10)
    _cubetas_listas.add(nombre)


def url_subida(nombre: str) -> dict:
    """Dónde sube el navegador el archivo: URL firmada (Supabase) o la propia API (local)."""
    if not usa_supabase():
        return {'directa': False}
    _asegurar_cubeta()
    r = _sesion.post(_url('object/upload/sign', cubeta(), nombre), headers=_cabeceras(), json={}, timeout=15)
    if r.status_code >= 300:
        raise RuntimeError(f'No se pudo preparar la subida ({r.status_code}).')
    rel = str(r.json().get('url') or '')
    base, _ = _credenciales()
    url = rel if rel.startswith('http') else (f'{base}{rel}' if rel.startswith('/storage/v1') else f'{base}/storage/v1/{rel.lstrip("/")}')
    return {'directa': True, 'url': url}


def guardar_local(nombre: str, datos: bytes) -> None:
    destino = _local() / nombre
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_bytes(datos)


def leer(nombre: str) -> bytes | None:
    """Contenido del archivo, o None si todavía no se subió."""
    cache = Path(tempfile.gettempdir()) / 'encuestas-cache' / nombre
    if cache.is_file():
        return cache.read_bytes()
    if usa_supabase():
        r = _sesion.get(_url('object', cubeta(), nombre), headers=_cabeceras(), timeout=120)
        if r.status_code >= 300:
            return None
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_bytes(r.content)
        return r.content
    ruta = _local() / nombre
    return ruta.read_bytes() if ruta.is_file() else None
