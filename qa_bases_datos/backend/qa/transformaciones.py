"""Transformaciones: calculan una columna del INE a partir de las columnas del crudo.

Cada función recibe la receta (variable.transformacion), una función `col(nombre)`
que busca la columna primero entre las ya calculadas y luego en el crudo, y la
definición de la base. Devuelve una Serie con el valor ANTES de codificar:
la codificación contra catálogo la hace el motor en un solo lugar.
"""
from __future__ import annotations

import re
from datetime import date, datetime, time

import pandas as pd

from .definicion import DefinicionBase
from .texto import normalizar


class FaltaColumna(Exception):
    """La transformación necesita una columna que todavía no existe (o no vino en el crudo)."""


def _entero(v):
    if v is None or (isinstance(v, float) and v != v):
        return None
    try:
        return int(float(str(v).strip()))
    except (TypeError, ValueError):
        return None


def _fecha(serie: pd.Series) -> pd.Series:
    def conv(v):
        if isinstance(v, (datetime, pd.Timestamp)):
            return pd.Timestamp(v)
        if isinstance(v, date):
            return pd.Timestamp(v)
        if v is None or (isinstance(v, float) and v != v):
            return pd.NaT
        return pd.to_datetime(str(v).strip(), dayfirst=True, errors="coerce")
    return serie.map(conv)


def _hora(v):
    if isinstance(v, (datetime, pd.Timestamp, time)):
        return v.hour
    if v is None or (isinstance(v, float) and v != v):
        return None
    s = str(v).strip()
    m = re.match(r"^(\d{1,2})(?::\d{2})?", s)
    if m and 0 <= int(m.group(1)) <= 23:
        return int(m.group(1))
    return None


# ---------------------------------------------------------------------------
def municipio_compuesto(tf, col, d):
    dep, mun = col(tf["depto"]), col(tf["munic"])

    def unir(a, b):
        a, b = _entero(a), _entero(b)
        if a is None or b is None or a <= 0 or b <= 0:
            return None
        if b >= 100:                      # ya viene completo (0101 o 101)
            return f"{b:04d}"
        return f"{a:02d}{b:02d}"
    return pd.Series([unir(a, b) for a, b in zip(dep, mun)], index=dep.index, dtype=object)


def parte_fecha(tf, col, d):
    f = _fecha(col(tf["campo"]))
    parte = tf["parte"]
    attr = {"dia": "day", "mes": "month", "anio": "year"}[parte]
    return f.map(lambda x: getattr(x, attr) if pd.notna(x) else None).astype(object)


def parte_hora(tf, col, d):
    return col(tf["campo"]).map(_hora).astype(object)


def agrupar_hora(tf, col, d):
    cortes = tf["cortes"]

    def grupo(v):
        h = _hora(v)
        if h is None:
            return None
        for i in range(len(cortes) - 1):
            if cortes[i] <= h < cortes[i + 1]:
                return str(i + 1)
        return None
    return col(tf["campo"]).map(grupo).astype(object)


def _rangos_edad(catalogo) -> list[tuple[int, int, str]]:
    rangos = []
    for cod, v in catalogo.valores.items():
        e = normalizar(v.etiqueta)
        if m := re.match(r"^(\d+)\s*-\s*(\d+)$", e):
            rangos.append((int(m.group(1)), int(m.group(2)), cod))
        elif m := re.match(r"^MENOR DE (\d+)$", e):
            rangos.append((0, int(m.group(1)) - 1, cod))
        elif m := re.match(r"^(\d+) Y MAS$", e):
            rangos.append((int(m.group(1)), 200, cod))
    return rangos


def agrupar_edad(tf, col, d):
    rangos = _rangos_edad(d.catalogos[tf["catalogo"]])
    ultimo = max(rangos, key=lambda r: r[1]) if rangos else None

    def grupo(v):
        e = _entero(v)
        if e is None or e < 0:
            return None
        for lo, hi, cod in rangos:
            if lo <= e <= hi:
                return cod
        # Catálogos que terminan en "60-64" sin "y más": las edades mayores van al último grupo
        return ultimo[2] if ultimo and e > ultimo[1] else None
    return col(tf["campo"]).map(grupo).astype(object)


def depto_de_municipio(tf, col, d):
    def dep(v):
        n = _entero(v)
        if n is None or n <= 0:
            return None
        s = f"{n:04d}" if n >= 100 else None
        return str(int(s[:2])) if s else None
    return col(tf["campo"]).map(dep).astype(object)


def rellenar_ceros(tf, col, d):
    largo = int(tf["largo"])
    return col(tf["campo"]).map(lambda v: f"{_entero(v):0{largo}d}" if _entero(v) is not None and _entero(v) > 0
                                else (None if _entero(v) is not None else v)).astype(object)


def padre_catalogo(tf, col, d):
    cat = d.catalogos[tf["catalogo"]]

    def padre(v):
        if v is None or (isinstance(v, float) and v != v):
            return None
        cod, _ = cat.resolver(v)
        return cat.valores[cod].padre if cod else None
    return col(tf["campo"]).map(padre).astype(object)


def etiqueta_catalogo(tf, col, d):
    cat = d.catalogos[tf["catalogo"]]

    def etq(v):
        cod, _ = cat.resolver(v)
        return cat.valores[cod].etiqueta if cod else None
    return col(tf["campo"]).map(etq).astype(object)


def mapa(tf, col, d):
    m = {normalizar(k): v for k, v in tf["valores"].items()}
    return col(tf["campo"]).map(lambda v: m.get(normalizar(v), v) if v is not None else None).astype(object)


def constante(tf, col, d):
    return pd.Series(tf["valor"], index=col.indice, dtype=object)


def vacio_como(tf, col, d):
    """Celda vacía = un valor fijo. En conteos (personas afectadas) vacío significa 0."""
    s = col(tf["campo"])
    vacio = s.map(lambda v: v is None or (isinstance(v, float) and v != v) or (isinstance(v, str) and not v.strip()))
    return s.where(~vacio, tf["valor"]).astype(object)


def codificar_texto(tf, col, d):
    """Texto -> código por coincidencia exacta de etiqueta. Con `dentro_de`, busca el
    municipio solo entre los del departamento indicado ("San Pedro" hay varios)."""
    serie = col(tf["campo"])
    if not tf.get("dentro_de"):
        return serie
    cat = d.catalogos[tf["catalogo"]]
    por_padre: dict[tuple[str, str], str] = {}
    for cod, v in cat.valores.items():
        por_padre.setdefault((v.padre, normalizar(v.etiqueta)), cod)
    padres = col(tf["dentro_de"])
    return pd.Series([por_padre.get((str(p) if p is not None else None, normalizar(t)), t)
                      for t, p in zip(serie, padres)], index=serie.index, dtype=object)


def codificar_ia(tf, col, d):
    """Devuelve el texto del primer campo; el motor lo resuelve con equivalencias aprobadas
    y, si no puede, pide sugerencias al codificador (similitud o IA)."""
    return col(tf["campos"][0])


TRANSFORMACIONES = {
    "municipio_compuesto": municipio_compuesto,
    "parte_fecha": parte_fecha,
    "parte_hora": parte_hora,
    "agrupar_hora": agrupar_hora,
    "agrupar_edad": agrupar_edad,
    "depto_de_municipio": depto_de_municipio,
    "rellenar_ceros": rellenar_ceros,
    "padre_catalogo": padre_catalogo,
    "etiqueta_catalogo": etiqueta_catalogo,
    "mapa": mapa,
    "constante": constante,
    "vacio_como": vacio_como,
    "codificar_texto": codificar_texto,
    "codificar_ia": codificar_ia,
}


def dependencias(tf: dict) -> list[str]:
    """Columnas que necesita una receta (para calcularlas en el orden correcto)."""
    deps = []
    for k in ("depto", "munic", "campo", "dentro_de"):
        if tf.get(k):
            deps.append(tf[k])
    if tf.get("tipo") == "codificar_ia":
        deps.append(tf["campos"][0])
    return deps


def aplicar(tf: dict, col, d: DefinicionBase) -> pd.Series:
    fn = TRANSFORMACIONES.get(tf.get("tipo"))
    if fn is None:
        raise ValueError(f"Transformación desconocida: {tf.get('tipo')}")
    return fn(tf, col, d)
