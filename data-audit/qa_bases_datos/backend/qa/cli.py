"""Línea de comandos del motor.

    python -m qa.cli bases
    python -m qa.cli procesar --base DETENIDOS --archivo detenidos_octubre.xlsx --anio 2026 --mes 10

La conexión sale de --db o de la variable DATABASE_URL. Los archivos de salida van a
--almacen/<id de la carga>/ (por defecto ./almacen). Con --sin-guardar no escribe en
la base de datos (útil para probar un archivo).
"""
from __future__ import annotations

import argparse
import os
import sys
import uuid
from pathlib import Path

import psycopg
from dotenv import load_dotenv

from .definicion import cargar_definicion
from .codificador_ia import crear_codificador
from .motor import procesar
from .salidas import crear_carga, escribir_archivos, guardar_en_bd, hallazgos_ordenados, usuario_sistema

ICONO = {"error": "ERROR", "advertencia": "AVISO", "info": "info "}


def cmd_bases(cur):
    cur.execute("""SELECT t.codigo, t.nombre, i.siglas, t.periodicidad, ve.version
                   FROM tipo_base t JOIN institucion i ON i.id = t.institucion_id
                   LEFT JOIN version_esquema ve ON ve.tipo_base_id = t.id AND ve.activa ORDER BY t.codigo""")
    for c, n, i, p, v in cur.fetchall():
        print(f"{c:14} {i:10} {p:8} versión {v or '-':6} {n}")


def cmd_procesar(con, args):
    ruta = Path(args.archivo)
    if not ruta.exists():
        sys.exit(f"No existe el archivo {ruta}")
    with con.cursor() as cur:
        d = cargar_definicion(cur, args.base)
        if d.codigo != "CALIDAD_AIRE" and args.mes is None and d.codigo in ("DEFUNCIONES", "NACIMIENTOS", "DETENIDOS"):
            print("Aviso: base mensual sin --mes; las reglas de período solo revisan el año.")
        print(f"Procesando {ruta.name} como {d.codigo} (versión {d.version})...")
        codificador = crear_codificador()
        print(f"Codificador: {getattr(codificador, 'nombre', 'similitud')}")
        r = procesar(ruta, d, args.anio, args.mes, codificador=codificador)
        if hasattr(codificador, 'estadisticas'):
            print(f"IA: {codificador.estadisticas}")

        if args.sin_guardar:
            carga_id = f"prueba-{uuid.uuid4().hex[:8]}"
            rutas = escribir_archivos(d, r, ruta, Path(args.almacen) / carga_id)
        else:
            if args.usuario:
                cur.execute("SELECT id FROM usuario WHERE email = %s", (args.usuario,))
                fila = cur.fetchone()
                if not fila:
                    sys.exit(f"No existe el usuario {args.usuario}")
                usuario_id = fila[0]
            else:
                usuario_id = usuario_sistema(cur)
            carga_id = crear_carga(cur, d, usuario_id, args.anio, args.mes)
            rutas = escribir_archivos(d, r, ruta, Path(args.almacen) / carga_id)
            guardar_en_bd(cur, d, r, carga_id, rutas, usuario_id)
            con.commit()

    print(f"\nCarga {carga_id}  ({r.segundos} s)")
    print(f"Registros: {r.total_registros:,} recibidos, {r.registros_validos:,} válidos, "
          f"{r.registros_excluidos:,} excluidos")
    print(f"Puntaje global: {r.puntaje}")
    for k, v in r.puntajes.items():
        print(f"  {k:18} {v:5.1f}")
    hs = [h for h in hallazgos_ordenados(d, r) if h["severidad"] != "info" or args.todo]
    print(f"\nHallazgos ({len(hs)}{'' if args.todo else ', sin los informativos'}):")
    for h in hs[: args.max]:
        print(f"  {ICONO[h['severidad']]}  {h['mensaje']}")
    if len(hs) > args.max:
        print(f"  … y {len(hs) - args.max} más en la bitácora")
    print(f"\nSugerencias pendientes de aprobar: {len(r.pendientes)}")
    print("Archivos:")
    for k, p in rutas.items():
        print(f"  {k:10} {p}")


def main():
    load_dotenv(Path(__file__).resolve().parents[2] / ".env", override=False)
    ap = argparse.ArgumentParser(prog="qa", description="Motor de validación Quality Audit")
    ap.add_argument("--db", default=os.environ.get("DATABASE_URL"))
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("bases", help="Lista las bases configuradas")
    p = sub.add_parser("procesar", help="Valida un archivo crudo")
    p.add_argument("--base", required=True, help="DEFUNCIONES, NACIMIENTOS, DETENIDOS, CALIDAD_AIRE, EMERGENCIAS")
    p.add_argument("--archivo", required=True)
    p.add_argument("--anio", type=int, required=True)
    p.add_argument("--mes", type=int)
    p.add_argument("--usuario", help="email del usuario que sube el archivo (por defecto, el usuario del motor)")
    p.add_argument("--almacen", default="almacen")
    p.add_argument("--sin-guardar", action="store_true", help="no escribe en la base de datos")
    p.add_argument("--todo", action="store_true", help="muestra también los hallazgos informativos")
    p.add_argument("--max", type=int, default=25, help="hallazgos a mostrar")
    args = ap.parse_args()
    if not args.db:
        ap.error("falta --db o la variable DATABASE_URL")
    with psycopg.connect(args.db) as con:
        if args.cmd == "bases":
            with con.cursor() as cur:
                cmd_bases(cur)
        else:
            cmd_procesar(con, args)


if __name__ == "__main__":
    main()
