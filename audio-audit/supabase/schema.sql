-- =====================================================================
-- Esquema Supabase para Audio Audit (ENCOVI - INE Guatemala)
-- Ejecuta este script en el SQL Editor de tu proyecto en Supabase.
-- =====================================================================

-- 1. Bucket privado en Supabase Storage para grabaciones largas (30 min - 2 h)
--    Permite carga directa desde el frontend TypeScript mediante URLs firmadas
--    sin pasar por el límite de 4.5 MB de funciones serverless en Vercel.
INSERT INTO storage.buckets (id, name, public)
VALUES ('audio-interviews', 'audio-interviews', false)
ON CONFLICT (id) DO NOTHING;

-- 2. Tabla principal de entrevistas, transcripciones y reportes JEV
CREATE TABLE IF NOT EXISTS public.audio_audit_jobs (
    id                      TEXT PRIMARY KEY,
    filename                TEXT NOT NULL,
    source                  TEXT NOT NULL DEFAULT 'audio',
    stt_provider            TEXT,
    external_job_id         TEXT,
    storage_path            TEXT,
    has_audio               BOOLEAN NOT NULL DEFAULT FALSE,
    status                  TEXT NOT NULL DEFAULT 'queued',
    stage                   TEXT NOT NULL DEFAULT '',
    progress                REAL NOT NULL DEFAULT 0,
    duration_seconds        DOUBLE PRECISION,
    elapsed_seconds         DOUBLE PRECISION NOT NULL DEFAULT 0,
    result                  JSONB,
    error                   TEXT,
    eval_status             TEXT NOT NULL DEFAULT 'idle',
    eval_elapsed_seconds    DOUBLE PRECISION NOT NULL DEFAULT 0,
    evaluation              JSONB,
    eval_error              TEXT,
    created_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at              TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_audio_audit_jobs_created_at
    ON public.audio_audit_jobs (created_at DESC);

-- 3. Criterios JEV reescritos por auditores (aplican a todas las próximas transcripciones)
CREATE TABLE IF NOT EXISTS public.audio_audit_rule_overrides (
    rule_id                 TEXT PRIMARY KEY,
    section                 TEXT NOT NULL,
    custom_text             TEXT,
    weight                  INT CHECK (weight IN (1, 2, 3)),
    enabled                 BOOLEAN NOT NULL DEFAULT TRUE,
    auditor_guidance        TEXT,
    questions_override      JSONB NOT NULL DEFAULT '{}'::jsonb,
    updated_at              TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- 4. Bitácora de ediciones humanas por entrevista (trazabilidad y calibración futura)
CREATE TABLE IF NOT EXISTS public.audio_audit_evaluation_edits (
    id                      BIGSERIAL PRIMARY KEY,
    job_id                  TEXT NOT NULL REFERENCES public.audio_audit_jobs(id) ON DELETE CASCADE,
    rule_id                 TEXT NOT NULL,
    previous_outcome        JSONB,
    override_status         TEXT NOT NULL,
    new_outcome             JSONB,
    auditor_comment         TEXT,
    propagate_to_future     BOOLEAN NOT NULL DEFAULT FALSE,
    created_at              TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_audio_audit_eval_edits_job
    ON public.audio_audit_evaluation_edits (job_id, created_at DESC);

-- Activar RLS (el backend FastAPI se conecta con SUPABASE_SERVICE_ROLE_KEY)
ALTER TABLE public.audio_audit_jobs ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.audio_audit_rule_overrides ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.audio_audit_evaluation_edits ENABLE ROW LEVEL SECURITY;
