"""Prepara la base de datos de Supabase para Quality Audit (se puede correr varias veces).

    pip install "psycopg[binary]" python-dotenv
    python supabase/configurar.py

Usa DATABASE_URL (del entorno o del archivo .env de la raíz). Para este script conviene la
cadena "Session pooler" de Supabase (Connect → Session pooler), que funciona con IPv4.

Aplica, en orden:
  1. data-audit/qa_bases_datos/schema.sql       tablas de Data Audit (solo si no existen)
  2. audio-audit/supabase/schema.sql            tablas y bucket de Audio Audit
  3. interfaz/backend/migrations/001_extensions.sql   Survey Audit y Quality Improvement
  4. supabase/seguridad.sql                     buckets privados y RLS en todas las tablas

Después hay que cargar los catálogos del INE con data-audit/qa_bases_datos/backend/scripts/cargar_config.py.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]

try:
    import psycopg
except ImportError:
    sys.exit('Falta psycopg: pip install "psycopg[binary]" python-dotenv')
try:
    from dotenv import load_dotenv
    load_dotenv(RAIZ / ".env", override=False)
except ImportError:
    pass

PASOS = [
    ("Data Audit", RAIZ / "data-audit/qa_bases_datos/schema.sql", "public.carga"),
    ("Audio Audit", RAIZ / "audio-audit/supabase/schema.sql", None),
    ("Survey Audit y Quality Improvement", RAIZ / "interfaz/backend/migrations/001_extensions.sql", None),
    ("Seguridad y buckets", RAIZ / "supabase/seguridad.sql", None),
]


def main() -> None:
    url = (sys.argv[1] if len(sys.argv) > 1 else os.environ.get("DATABASE_URL") or "").strip()
    if not url:
        sys.exit("Falta DATABASE_URL (en .env o como argumento).")
    with psycopg.connect(url, autocommit=True, prepare_threshold=None) as con:
        for nombre, archivo, existe in PASOS:
            if existe and con.execute("SELECT to_regclass(%s)", (existe,)).fetchone()[0]:
                print(f"= {nombre}: ya existe, se omite ({archivo.relative_to(RAIZ)})")
                continue
            sql = archivo.read_text(encoding="utf-8")
            if existe:
                # El esquema de Data Audit no es idempotente: se aplica completo o nada.
                with con.transaction():
                    con.execute(sql)
            else:
                con.execute(sql)
            print(f"✓ {nombre} ({archivo.relative_to(RAIZ)})")
        tablas = con.execute("""SELECT count(*), count(*) FILTER (WHERE c.relrowsecurity)
                                FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
                                WHERE n.nspname = 'public' AND c.relkind = 'r'""").fetchone()
        print(f"\nTablas en public: {tablas[0]} · con RLS: {tablas[1]}")
        cubetas = con.execute("SELECT string_agg(id, ', ' ORDER BY id) FROM storage.buckets").fetchone()[0]
        print(f"Buckets: {cubetas}")
        bases = con.execute("SELECT count(*) FROM version_esquema WHERE activa").fetchone()[0]
        print(f"Bases con configuración activa: {bases}"
              + ("  ← falta correr scripts/cargar_config.py con los diccionarios del INE" if not bases else ""))


if __name__ == "__main__":
    main()
