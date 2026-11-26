-- =====================================================================
-- Quality Audit · Seguridad y buckets en Supabase
-- Ejecutar DESPUÉS de los esquemas de Data Audit, Audio Audit y extensiones.
-- Se puede correr varias veces.
-- =====================================================================

-- 1. Buckets privados de Storage
--    audio-interviews: grabaciones (lo crea también audio-audit/supabase/schema.sql)
--    qa-cargas:        bases institucionales originales y sus resultados (Data Audit)
--    encuestas:        cuestionarios en PDF para generar formularios (Survey Audit)
INSERT INTO storage.buckets (id, name, public)
VALUES ('audio-interviews', 'audio-interviews', false),
       ('qa-cargas', 'qa-cargas', false),
       ('encuestas', 'encuestas', false)
ON CONFLICT (id) DO NOTHING;

-- 2. Row Level Security en TODAS las tablas del esquema public.
--    La llave pública (anon/publishable) viaja en el navegador; sin políticas, RLS impide que
--    alguien la use para leer o escribir tablas por la API REST de Supabase. El backend entra
--    como dueño de las tablas (DATABASE_URL) o con la llave secreta, que no pasan por RLS.
DO $$
DECLARE t record;
BEGIN
  FOR t IN SELECT tablename FROM pg_tables WHERE schemaname = 'public' LOOP
    EXECUTE format('ALTER TABLE public.%I ENABLE ROW LEVEL SECURITY', t.tablename);
  END LOOP;
END $$;

-- 3. Permisos: el backend (llave secreta = rol service_role) necesita acceso a las tablas para la
--    Data API (Audio Audit la usa), aunque el proyecto no otorgue permisos automáticos a tablas nuevas.
--    Los roles del navegador (anon, authenticated) no tienen ninguno.
DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'service_role') THEN
    GRANT USAGE ON SCHEMA public TO service_role;
    GRANT ALL ON ALL TABLES IN SCHEMA public TO service_role;
    GRANT ALL ON ALL SEQUENCES IN SCHEMA public TO service_role;
    ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO service_role;
    ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON SEQUENCES TO service_role;
  END IF;
END $$;

DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN
    REVOKE ALL ON ALL TABLES IN SCHEMA public FROM anon, authenticated;
    REVOKE ALL ON ALL SEQUENCES IN SCHEMA public FROM anon, authenticated;
    ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE ALL ON TABLES FROM anon, authenticated;
    ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE ALL ON SEQUENCES FROM anon, authenticated;
  END IF;
END $$;
