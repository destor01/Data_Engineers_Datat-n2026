"""Genera documentation/modelo-datos-tablas.md consultando un PostgreSQL con los esquemas cargados.

    python documentation/herramientas/generar_modelo_datos.py "postgresql://usuario@host:5432/base"

Lista, por tabla: columnas (tipo, nulos, valor por defecto), llave primaria, llaves foráneas,
restricciones UNIQUE y CHECK, e índices. Usa el catálogo de PostgreSQL, no el texto del SQL.
"""
from __future__ import annotations

import sys
from pathlib import Path

import psycopg

SALIDA = Path(__file__).resolve().parents[2] / "documentation/modelo-datos-tablas.md"
GRUPOS = [
    ("Data Audit", "public", lambda t: not t.startswith("audio_audit")),
    ("Audio Audit", "public", lambda t: t.startswith("audio_audit")),
    ("Survey Audit y Quality Improvement", "quality_extensions", lambda t: True),
]


def md(x) -> str:
    return str(x).replace("|", "\\|").replace("\n", " ")


def main(url: str) -> None:
    out = ["# Modelo de datos: detalle de tablas", "",
           "> Generado con `documentation/herramientas/generar_modelo_datos.py` desde una base PostgreSQL con los",
           "> esquemas del proyecto. La explicación del modelo está en [modelo-datos.md](modelo-datos.md).", ""]
    with psycopg.connect(url) as con, con.cursor() as cur:
        for titulo, esquema, filtro in GRUPOS:
            cur.execute("SELECT tablename FROM pg_tables WHERE schemaname = %s ORDER BY tablename", (esquema,))
            tablas = [t for (t,) in cur.fetchall() if filtro(t)]
            out += [f"## {titulo}", ""]
            for t in tablas:
                q = f"{esquema}.{t}"
                cur.execute("SELECT obj_description(%s::regclass)", (q,))
                comentario = cur.fetchone()[0]
                out += [f"### `{q}`", ""] + ([md(comentario), ""] if comentario else [])
                cur.execute("""SELECT a.attname, format_type(a.atttypid, a.atttypmod), a.attnotnull,
                                      pg_get_expr(d.adbin, d.adrelid), col_description(a.attrelid, a.attnum)
                               FROM pg_attribute a LEFT JOIN pg_attrdef d ON d.adrelid = a.attrelid AND d.adnum = a.attnum
                               WHERE a.attrelid = %s::regclass AND a.attnum > 0 AND NOT a.attisdropped ORDER BY a.attnum""", (q,))
                out += ["| Columna | Tipo | Nulo | Por defecto | Nota |", "|---|---|---|---|---|"]
                for nombre, tipo, notnull, defecto, nota in cur.fetchall():
                    out.append(f"| `{nombre}` | {md(tipo)} | {'no' if notnull else 'sí'} | {md(defecto or '—')} | {md(nota or '')} |")
                cur.execute("""SELECT contype, pg_get_constraintdef(oid) FROM pg_constraint
                               WHERE conrelid = %s::regclass ORDER BY contype, conname""", (q,))
                restr = cur.fetchall()
                nombres = {"p": "Llave primaria", "f": "Llave foránea", "u": "Única", "c": "Verificación"}
                if restr:
                    out += ["", "Restricciones:", ""] + [f"- {nombres.get(tp, tp)}: `{md(defi)}`" for tp, defi in restr]
                cur.execute("""SELECT indexdef FROM pg_indexes WHERE schemaname = %s AND tablename = %s
                               AND indexname NOT IN (SELECT conname FROM pg_constraint WHERE conrelid = %s::regclass)
                               ORDER BY indexname""", (esquema, t, q))
                idx = [r[0] for r in cur.fetchall()]
                if idx:
                    out += ["", "Índices adicionales:", ""] + [f"- `{md(i)}`" for i in idx]
                out.append("")
        cur.execute("""SELECT t.typname, string_agg(e.enumlabel, ', ' ORDER BY e.enumsortorder)
                       FROM pg_type t JOIN pg_enum e ON e.enumtypid = t.oid GROUP BY t.typname ORDER BY t.typname""")
        out += ["## Tipos enumerados", "", "| Tipo | Valores |", "|---|---|"] + [f"| `{n}` | {md(v)} |" for n, v in cur.fetchall()]
    SALIDA.write_text("\n".join(out) + "\n", encoding="utf-8")
    print("escrito", SALIDA)


if __name__ == "__main__":
    main(sys.argv[1])
