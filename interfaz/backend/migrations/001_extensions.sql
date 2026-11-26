-- Aditiva. No altera ni reemplaza tablas de Data Audit.
-- MVP: agregado JSONB transaccional; normalizar por entidad antes de alta concurrencia.
BEGIN;
CREATE SCHEMA IF NOT EXISTS quality_extensions;
CREATE TABLE IF NOT EXISTS quality_extensions.state (
  id integer PRIMARY KEY CHECK (id = 1),
  data jsonb NOT NULL,
  revision bigint NOT NULL DEFAULT 0
);
INSERT INTO quality_extensions.state (id, data)
VALUES (1, '{"templates":{},"interviews":{},"manuals":{},"recommendations":{},"documents":{}}'::jsonb)
ON CONFLICT (id) DO NOTHING;
-- Backend exclusivamente: no exponer esta tabla por API pública de Supabase.
REVOKE ALL ON SCHEMA quality_extensions FROM PUBLIC;
REVOKE ALL ON quality_extensions.state FROM PUBLIC;
ALTER TABLE quality_extensions.state ENABLE ROW LEVEL SECURITY;
COMMIT;
