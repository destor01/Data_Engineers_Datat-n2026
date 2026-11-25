"""Normalización de texto compartida por el cargador de configuración y el motor.

Los encabezados de columnas, las etiquetas de catálogo y los textos libres
se comparan siempre ya normalizados, así "Cobán", "COBAN " y "coban"
son el mismo texto.
"""
from __future__ import annotations

import re
import unicodedata

_ESPACIOS = re.compile(r"\s+")


def normalizar(texto: object) -> str:
    """Mayúsculas, sin tildes, sin espacios extra. La Ñ se conserva."""
    if texto is None:
        return ""
    s = str(texto).strip()
    # Proteger la Ñ antes de quitar diacríticos
    s = s.replace("ñ", "\0").replace("Ñ", "\0")
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = s.replace("\0", "Ñ")
    return _ESPACIOS.sub(" ", s).upper().strip()


def codigo_texto(valor: object, ceros: int | None = None) -> str | None:
    """Convierte un código leído de Excel a texto: 1.0 -> '1', 101 -> '0101' (ceros=4)."""
    if valor is None:
        return None
    if isinstance(valor, float):
        if valor != valor:  # NaN
            return None
        if valor.is_integer():
            valor = int(valor)
    s = str(valor).strip()
    if not s:
        return None
    if ceros and s.isdigit():
        s = s.zfill(ceros)
    return s


def es_ignorado(etiqueta: object) -> bool:
    return normalizar(etiqueta).startswith("IGNORAD")
