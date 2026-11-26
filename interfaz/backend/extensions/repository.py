"""Repositorio JSONB PostgreSQL; archivo local únicamente en demo explícita."""
import json
import os
from pathlib import Path
from threading import RLock
from contextlib import contextmanager
from fastapi import HTTPException

LOCK = RLock()
DDL = '''CREATE SCHEMA IF NOT EXISTS quality_extensions;
CREATE TABLE IF NOT EXISTS quality_extensions.state (
 id integer PRIMARY KEY CHECK (id = 1), data jsonb NOT NULL, revision bigint NOT NULL DEFAULT 0
);
INSERT INTO quality_extensions.state (id, data) VALUES (1, '{"templates":{},"interviews":{},"manuals":{},"recommendations":{},"documents":{}}'::jsonb)
ON CONFLICT (id) DO NOTHING;'''


def empty():
    return {key: {} for key in ('templates', 'interviews', 'manuals', 'recommendations', 'documents')}


@contextmanager
def transaction():
    """Una transacción por operación. MVP serializado; interfaz aislada para migrar a tablas normalizadas."""
    with LOCK:
        if os.environ.get('QA_STORAGE') == 'demo':
            path = Path(os.environ.get('QA_DEMO_STORE', str(Path(__file__).parents[1] / 'almacen/extensions.demo.json')))
            path.parent.mkdir(parents=True, exist_ok=True)
            state = json.loads(path.read_text(encoding='utf-8')) if path.exists() else empty()
            yield state
            temp = path.with_suffix('.tmp')
            temp.write_text(json.dumps(state, ensure_ascii=False, allow_nan=False), encoding='utf-8')
            temp.replace(path)
            return
        dsn = os.environ.get('DATABASE_URL')
        if not dsn:
            raise HTTPException(503, 'Configura DATABASE_URL para PostgreSQL o QA_STORAGE=demo para datos sintéticos locales.')
        import psycopg
        from psycopg.types.json import Jsonb
        try:
            # prepare_threshold=None: compatible con el pooler de Supabase (modo transacción).
            with psycopg.connect(dsn, prepare_threshold=None) as con, con.cursor() as cur:
                cur.execute('SELECT data FROM quality_extensions.state WHERE id=1 FOR UPDATE')
                row = cur.fetchone()
                if not row:
                    raise HTTPException(503, 'Ejecuta la migración 001_extensions.sql.')
                state = row[0]
                yield state
                cur.execute('UPDATE quality_extensions.state SET data=%s, revision=revision+1 WHERE id=1', (Jsonb(state),))
        except psycopg.Error:
            raise HTTPException(503, 'PostgreSQL no disponible o migración pendiente. Revisa la conexión localmente.') from None
