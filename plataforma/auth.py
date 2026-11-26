"""Acceso a la API unificada con sesiones de Supabase Auth.

Cada petición a /api/* debe traer `Authorization: Bearer <access_token>` de una sesión
iniciada en la interfaz. El token se valida contra Supabase (GET /auth/v1/user), así que
funciona con las llaves nuevas (sb_publishable / sb_secret) y con las heredadas (anon /
service_role), sin manejar secretos de firma en este servidor.

Sin Supabase configurado:
  - en Vercel la API responde 503 (nunca queda abierta por olvido);
  - en local solo atiende peticiones a localhost, para desarrollo.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import threading
import time
from contextvars import ContextVar
from typing import Any
from urllib.parse import urlsplit

import requests

logger = logging.getLogger("plataforma.auth")

IS_VERCEL = bool(os.environ.get("VERCEL") or os.environ.get("VERCEL_ENV"))
RUTAS_PUBLICAS = {"/api/salud"}
# En la plataforma unificada las llaves viven en las variables de entorno, no se cambian por HTTP.
RUTAS_BLOQUEADAS = ("/api/config/",)
HOSTS_LOCALES = {"127.0.0.1", "localhost", "::1"}
METODOS_SEGUROS = {"GET", "HEAD", "OPTIONS"}
CACHE_SEGUNDOS = 60
CACHE_MAXIMO = 500

usuario_actual: ContextVar[dict[str, Any] | None] = ContextVar("usuario_actual", default=None)

_cache: dict[str, tuple[float, dict[str, Any]]] = {}
_cache_lock = threading.Lock()
_sesion = requests.Session()


def credenciales() -> tuple[str, str]:
    """URL del proyecto y llave pública (publishable/anon) para consultar Auth."""
    url = (os.environ.get("SUPABASE_URL") or os.environ.get("VITE_SUPABASE_URL") or "").strip().rstrip("/")
    llave = (
        os.environ.get("SUPABASE_ANON_KEY")
        or os.environ.get("SUPABASE_PUBLISHABLE_KEY")
        or os.environ.get("VITE_SUPABASE_ANON_KEY")
        or os.environ.get("VITE_SUPABASE_PUBLISHABLE_KEY")
        or ""
    ).strip()
    return url, llave


def auth_configurado() -> bool:
    url, llave = credenciales()
    return bool(url and llave)


def verificar_token(token: str) -> dict[str, Any] | None:
    """Devuelve el usuario de Supabase si el token es válido; None si no lo es."""
    if not token:
        return None
    clave = hashlib.sha256(token.encode()).hexdigest()
    ahora = time.time()
    with _cache_lock:
        guardado = _cache.get(clave)
        if guardado and guardado[0] > ahora:
            return guardado[1]
    url, llave = credenciales()
    try:
        resp = _sesion.get(f"{url}/auth/v1/user",
                           headers={"apikey": llave, "Authorization": f"Bearer {token}"}, timeout=10)
    except requests.RequestException:
        logger.exception("No se pudo consultar Supabase Auth")
        raise
    if resp.status_code != 200:
        return None
    datos = resp.json()
    usuario = {"id": datos.get("id"), "email": (datos.get("email") or "").lower() or None}
    if not usuario["id"]:
        return None
    with _cache_lock:
        if len(_cache) >= CACHE_MAXIMO:
            _cache.clear()
        _cache[clave] = (ahora + CACHE_SEGUNDOS, usuario)
    return usuario


def _host(valor: str) -> str:
    return (urlsplit(valor if "//" in valor else f"//{valor}").hostname or "").lower()


class AccesoMiddleware:
    """Middleware ASGI: login obligatorio en /api/*, bloqueo de /api/config/* y control de origen."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or not scope["path"].startswith("/api/"):
            await self.app(scope, receive, send)
            return
        ruta: str = scope["path"]
        metodo: str = scope["method"]
        cabeceras = {k.decode("latin-1").lower(): v.decode("latin-1") for k, v in scope["headers"]}
        host = _host(cabeceras.get("host", ""))

        if ruta.startswith(RUTAS_BLOQUEADAS):
            await _responder(send, 403, "En esta plataforma las llaves se configuran en las variables de entorno del servidor.")
            return

        # Escrituras solo desde la misma página (o localhost en desarrollo).
        origen = cabeceras.get("origin")
        if metodo not in METODOS_SEGUROS and origen:
            permitidos = {host} | (set() if IS_VERCEL else HOSTS_LOCALES)
            if _host(origen) not in permitidos:
                await _responder(send, 403, "Origen no permitido.")
                return

        if ruta in RUTAS_PUBLICAS or metodo == "OPTIONS":
            await self.app(scope, receive, send)
            return

        if not auth_configurado():
            if IS_VERCEL:
                await _responder(send, 503, "Falta configurar Supabase Auth (SUPABASE_URL y SUPABASE_ANON_KEY) en Vercel.")
                return
            if host not in HOSTS_LOCALES:
                await _responder(send, 403, "Sin Supabase Auth configurado, la API solo atiende localhost.")
                return
            await self.app(scope, receive, send)
            return

        esquema, _, token = cabeceras.get("authorization", "").partition(" ")
        try:
            usuario = verificar_token(token.strip()) if esquema.lower() == "bearer" else None
        except requests.RequestException:
            await _responder(send, 503, "No se pudo verificar la sesión con Supabase. Intenta de nuevo.")
            return
        if not usuario:
            await _responder(send, 401, "Inicia sesión para usar la plataforma.",
                             {"www-authenticate": 'Bearer realm="Quality Audit"'})
            return

        marca = usuario_actual.set(usuario)
        try:
            await self.app(scope, receive, send)
        finally:
            usuario_actual.reset(marca)


async def _responder(send, estado: int, detalle: str, extra: dict[str, str] | None = None) -> None:
    cuerpo = json.dumps({"detail": detalle}, ensure_ascii=False).encode()
    cabeceras = [(b"content-type", b"application/json; charset=utf-8"), (b"content-length", str(len(cuerpo)).encode())]
    cabeceras += [(k.encode(), v.encode()) for k, v in (extra or {}).items()]
    await send({"type": "http.response.start", "status": estado, "headers": cabeceras})
    await send({"type": "http.response.body", "body": cuerpo})
