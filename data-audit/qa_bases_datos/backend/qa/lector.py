"""Lector universal: abre el archivo crudo tal como lo manda la institución.

Devuelve una tabla "larga y plana" con los encabezados originales, más dos
columnas de rastreo: `_hoja` y `_fila` (número de fila en el Excel original),
para que cada hallazgo apunte a la celda exacta.

Formatos (version_esquema.formato_crudo):
  - sin formato / "tabla":     una hoja, encabezado en la fila 1 (o `fila_encabezado`).
  - "hojas_mensuales":         una hoja por mes con la misma estructura; se unen.
  - "ancho_a_largo":           encabezado en dos filas (estación / PM) y una columna
                               por combinación; se pasa a una fila por lectura.
CSV: se detecta el separador y la codificación.
"""
from __future__ import annotations

import csv
import io
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

from .texto import normalizar


@dataclass
class Lectura:
    df: pd.DataFrame                                    # columnas originales + _hoja + _fila
    eventos: list[dict] = field(default_factory=list)   # hallazgos de estructura detectados al leer
    hojas: list[dict] = field(default_factory=list)     # [{"nombre", "filas", "columnas"}]


# ---------------------------------------------------------------------------
def _vacio(v) -> bool:
    return v is None or (isinstance(v, float) and v != v) or (isinstance(v, str) and not v.strip())


def _leer_hoja_cruda(ruta: Path, hoja) -> pd.DataFrame:
    return pd.read_excel(ruta, sheet_name=hoja, header=None, dtype=object, engine="calamine")


def _leer_csv(ruta: Path) -> pd.DataFrame:
    crudo = ruta.read_bytes()
    for codif in ("utf-8-sig", "latin-1"):
        try:
            texto = crudo.decode(codif)
            break
        except UnicodeDecodeError:
            continue
    try:
        sep = csv.Sniffer().sniff(texto[:5000], delimiters=";,|\t").delimiter
    except csv.Error:
        sep = ","
    return pd.read_csv(io.StringIO(texto), sep=sep, header=None, dtype=object, keep_default_na=False)


def _encabezados(crudo: pd.DataFrame, fila_enc: int) -> list[str]:
    """Nombres de columna de la fila `fila_enc` (base 0). Si una celda está vacía
    (encabezados combinados), toma el primer texto que encuentre hacia arriba."""
    nombres = []
    for j in range(crudo.shape[1]):
        nombre = None
        for i in range(fila_enc, -1, -1):
            v = crudo.iat[i, j]
            if not _vacio(v) and not str(v).startswith("="):
                nombre = str(v).strip()
                break
        nombres.append(nombre if nombre is not None else f"Unnamed: {j}")
    return nombres


def _tabla(crudo: pd.DataFrame, fila_enc: int, hoja: str) -> tuple[pd.DataFrame, list[dict]]:
    eventos = []
    nombres = _encabezados(crudo, fila_enc)
    datos = crudo.iloc[fila_enc + 1:].copy()
    datos.columns = range(datos.shape[1])
    datos["_fila"] = datos.index + 1          # índice 0 = fila 1 del Excel
    datos = datos[~datos.drop(columns="_fila").map(_vacio).all(axis=1)]

    # Columnas vacías y sin nombre
    quitar = []
    for j, n in enumerate(nombres):
        if n.startswith("Unnamed:") and datos[j].map(_vacio).all():
            quitar.append(j)
            eventos.append({"regla": "GEN_COLUMNA_VACIA", "columna": f"columna {j + 1} (sin nombre)", "hoja": hoja})

    # Encabezados repetidos: el segundo queda como NOMBRE.1 (igual que pandas)
    conteo, finales = Counter(), []
    repetidos = {k: c for k, c in Counter(normalizar(n) for n in nombres).items() if c > 1}
    for n in nombres:
        k = normalizar(n)
        finales.append(n if conteo[k] == 0 else f"{n}.{conteo[k]}")
        conteo[k] += 1
    for k, c in repetidos.items():
        if not k.startswith("UNNAMED"):
            eventos.append({"regla": "GEN_COLUMNA_DUPLICADA", "columna": k, "detalle": c, "hoja": hoja})

    datos.columns = finales + ["_fila"]
    datos = datos.drop(columns=[finales[j] for j in quitar])
    datos.insert(0, "_hoja", hoja)
    return datos.reset_index(drop=True), eventos


def _ancho_a_largo(crudo: pd.DataFrame, fmt: dict, hoja: str) -> pd.DataFrame:
    nfilas = int(fmt.get("filas_encabezado", 2))
    nivel1 = crudo.iloc[0].copy()
    nivel1 = nivel1.where(~nivel1.map(_vacio)).ffill()
    nivel2 = crudo.iloc[nfilas - 1]
    fijas_norm = {normalizar(c) for c in fmt.get("columnas_fijas", [])}
    fijas = {j: str(nivel2.iat[j]).strip() for j in range(crudo.shape[1]) if normalizar(nivel2.iat[j]) in fijas_norm}

    datos = crudo.iloc[nfilas:].copy()
    datos["_fila"] = datos.index + 1
    partes = []
    for j in range(crudo.shape[1]):
        if j in fijas or _vacio(nivel2.iat[j]):
            continue
        p = pd.DataFrame({nombre: datos[k].values for k, nombre in fijas.items()})
        p[str(fmt.get("nivel_1", "nivel_1")).upper()] = str(nivel1.iat[j]).strip()
        p[str(fmt.get("nivel_2", "nivel_2")).upper()] = str(nivel2.iat[j]).strip()
        p[str(fmt.get("columna_valor", "valor")).upper()] = datos[j].values
        p["_fila"] = datos["_fila"].values
        partes.append(p)
    largo = pd.concat(partes, ignore_index=True)
    largo.insert(0, "_hoja", hoja)
    return largo


def _fila_encabezado(crudo: pd.DataFrame, configurada: int, conocidos: set[str] | None) -> int:
    """Fila del encabezado. Se usa la configurada, salvo que otra de las primeras filas tenga
    claramente más nombres de columna de la base (p. ej. un CSV con el encabezado en la fila 1
    cuando la institución suele enviar un Excel con títulos encima)."""
    if not conocidos or crudo.empty:
        return configurada

    def puntaje(i: int) -> int:
        if not 0 <= i < crudo.shape[0]:
            return -1
        return len({normalizar(v) for v in crudo.iloc[i] if not _vacio(v)} & conocidos)

    candidatas = range(min(25, crudo.shape[0]))
    mejor = max(candidatas, key=lambda i: (puntaje(i), -i))
    return mejor if puntaje(mejor) >= 2 and puntaje(mejor) > puntaje(configurada) else configurada


# ---------------------------------------------------------------------------
def leer(ruta: str | Path, formato: dict | None = None, conocidos: set[str] | None = None) -> Lectura:
    """`conocidos`: nombres normalizados de las columnas de la base (y sus alias), para ubicar el encabezado."""
    ruta = Path(ruta)
    fmt = formato or {}
    tipo = fmt.get("tipo", "tabla")
    fila_enc = int(fmt.get("fila_encabezado", 1)) - 1

    if ruta.suffix.lower() in (".csv", ".txt"):
        crudo = _leer_csv(ruta)
        df, ev = _tabla(crudo, _fila_encabezado(crudo, fila_enc, conocidos), ruta.name)
        return Lectura(df, ev, [{"nombre": ruta.name, "filas": len(df), "columnas": df.shape[1] - 2}])

    libro = pd.ExcelFile(ruta, engine="calamine")
    nombres_hojas = libro.sheet_names

    if tipo == "ancho_a_largo":
        hoja = nombres_hojas[fmt.get("hoja", 0)] if isinstance(fmt.get("hoja", 0), int) else fmt["hoja"]
        crudo = _leer_hoja_cruda(ruta, hoja)
        df = _ancho_a_largo(crudo, fmt, hoja)
        return Lectura(df, [], [{"nombre": hoja, "filas": crudo.shape[0], "columnas": crudo.shape[1]}])

    if tipo == "hojas_mensuales":
        partes, eventos, hojas, referencia = [], [], [], None
        for hoja in nombres_hojas:
            crudo = _leer_hoja_cruda(ruta, hoja)
            if crudo.empty:
                continue
            df, ev = _tabla(crudo, _fila_encabezado(crudo, fila_enc, conocidos), hoja)
            eventos += ev
            hojas.append({"nombre": hoja, "filas": len(df), "columnas": df.shape[1] - 2})
            cols = [normalizar(c) for c in df.columns if not c.startswith("_")]
            if referencia is None:
                referencia = (hoja, cols)
            elif cols != referencia[1]:
                faltan = [c for c in referencia[1] if c not in cols]
                sobran = [c for c in cols if c not in referencia[1]]
                eventos.append({"regla": "GEN_HOJAS_DISTINTAS", "hoja": hoja, "columna": None,
                                "detalle": f"'{hoja}' frente a '{referencia[0]}': "
                                           f"faltan {faltan or 'ninguna'}, sobran {sobran or 'ninguna'}"})
            partes.append(df)
        return Lectura(pd.concat(partes, ignore_index=True), eventos, hojas)

    hoja = fmt.get("hoja", 0)
    hoja = nombres_hojas[hoja] if isinstance(hoja, int) else hoja
    crudo = _leer_hoja_cruda(ruta, hoja)
    df, ev = _tabla(crudo, _fila_encabezado(crudo, fila_enc, conocidos), hoja)
    hojas = [{"nombre": h, "filas": None, "columnas": None} for h in nombres_hojas]
    for h in hojas:
        if h["nombre"] == hoja:
            h.update(filas=len(df), columnas=df.shape[1] - 2)
    return Lectura(df, ev, hojas)
