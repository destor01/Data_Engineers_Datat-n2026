"""Compara la salida del motor con lo que publicó el INE.

    python -m scripts.comparar_con_ine defunciones --crudo "Defunciones Julio_renap_2026.xlsx"
    python -m scripts.comparar_con_ine aire --crudo "Datos de Calidad del aire_INSIVUMEH_2025.xlsx" \
                                            --publicado "base-monitoreo_aire_2025_insivumeh.xlsx"

defunciones: el archivo de RENAP trae dos hojas, la cruda y la que dejó el INE. Se
             comparan los registros conservados uno por uno (MOVIMIENTO + SEDE + FECHA).
aire:        se comparan los meses que conserva cada estación y PM.
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import pandas as pd
import psycopg

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from qa.definicion import cargar_definicion  # noqa: E402
from qa.motor import procesar  # noqa: E402
from qa.texto import normalizar  # noqa: E402


def defunciones(cur, crudo: Path, anio: int, mes: int):
    d = cargar_definicion(cur, "DEFUNCIONES")
    r = procesar(crudo, d, anio, mes)
    raw = pd.read_excel(crudo, sheet_name=0)
    ine = pd.read_excel(crudo, sheet_name=1)
    excluidas = {f for e in r.excluidos for f in e["filas"]}
    raw["_fila"] = raw.index + 2
    nuestro = raw[~raw["_fila"].isin(excluidas)]
    k = ["MOVIMIENTO", "SEDE_EVENTO", "FECHA_DEFUNCION"]
    a = set(map(tuple, nuestro[k].astype(str).values))
    b = set(map(tuple, ine[k].astype(str).values))
    print(f"Registros recibidos:        {len(raw):>6,}")
    print(f"Conservados por el motor:   {len(a):>6,}")
    print(f"Conservados por el INE:     {len(b):>6,}")
    print(f"En ambos:                   {len(a & b):>6,}")
    print(f"Solo el motor / solo el INE: {len(a - b)} / {len(b - a)}")
    for e in sorted({e['regla'] for e in r.excluidos}):
        n = sum(len(x["filas"]) for x in r.excluidos if x["regla"] == e)
        print(f"  excluidos por {e}: {n:,}")
    print("COINCIDENCIA EXACTA" if a == b else "HAY DIFERENCIAS")


def aire(cur, crudo: Path, publicado: Path, anio: int):
    d = cargar_definicion(cur, "CALIDAD_AIRE")
    r = procesar(crudo, d, anio)
    o = r.salida.copy()
    o["m"] = pd.to_datetime(o["fehca"]).dt.month
    nos = o.groupby(["estación", "pm"])["m"].apply(lambda s: sorted(int(x) for x in s.unique())).to_dict()
    pub = pd.read_excel(publicado)
    pub["e"] = pub["estación"].map(lambda x: normalizar(x).replace(" ", "_"))
    pp = pub.groupby(["e", "pm"])["cod_mes"].apply(lambda s: sorted(int(x) for x in s.unique())).to_dict()
    # En la publicación, dos estaciones cambian de nombre a mitad de año
    renombres = {"INSIVUMEH": ["INSIVUMEH", "GUATEMALA"], "LOS_ALTOS": ["LOS_ALTOS", "QUETZALTENANGO"]}
    iguales = 0
    print(f"{'Estación':12} {'PM':5} {'Motor':38} {'INE':38}")
    for (e, pm), meses in sorted(nos.items()):
        ine = sorted({m for a in renombres.get(e, [e]) for m in pp.get((a, float(pm)), [])})
        igual = meses == ine
        iguales += igual
        print(f"{e:12} {str(pm):5} {str(meses):38} {str(ine):38} {'=' if igual else '≠'}")
    print(f"\n{iguales} de {len(nos)} combinaciones de estación y PM conservan exactamente los mismos meses.")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=os.environ.get("DATABASE_URL"))
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("defunciones")
    p.add_argument("--crudo", type=Path, required=True)
    p.add_argument("--anio", type=int, default=2026)
    p.add_argument("--mes", type=int, default=7)
    p = sub.add_parser("aire")
    p.add_argument("--crudo", type=Path, required=True)
    p.add_argument("--publicado", type=Path, required=True)
    p.add_argument("--anio", type=int, default=2025)
    a = ap.parse_args()
    with psycopg.connect(a.db) as con, con.cursor() as cur:
        if a.cmd == "defunciones":
            defunciones(cur, a.crudo, a.anio, a.mes)
        else:
            aire(cur, a.crudo, a.publicado, a.anio)


if __name__ == "__main__":
    main()
