"""Función de Vercel: toda ruta /api/* llega aquí (ver vercel.json)."""
from __future__ import annotations

import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

from plataforma.app import app  # noqa: E402, F401
