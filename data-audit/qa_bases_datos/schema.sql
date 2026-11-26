-- =====================================================================
-- Quality Audit · Datatón INE Guatemala 2026
-- Esquema PostgreSQL (16+) de la plataforma de auditoría de calidad
--
-- Los registros de cada base NO se guardan fila por fila en la BD:
-- los archivos van a almacenamiento de objetos (disco/S3) y en la BD
-- solo quedan metadatos, hallazgos y la bitácora de correcciones.
-- =====================================================================

CREATE EXTENSION IF NOT EXISTS pgcrypto;   -- gen_random_uuid()

-- ---------------------------------------------------------------------
-- Tipos enumerados
-- ---------------------------------------------------------------------
CREATE TYPE rol_usuario      AS ENUM ('institucion', 'analista_ine', 'admin');
CREATE TYPE tipo_dato        AS ENUM ('entero', 'decimal', 'texto', 'fecha', 'hora', 'fecha_hora', 'codigo', 'booleano');
CREATE TYPE dimension_calidad AS ENUM ('estructura', 'completitud', 'validez', 'consistencia', 'unicidad', 'oportunidad', 'representatividad');
CREATE TYPE severidad        AS ENUM ('error', 'advertencia', 'info');
CREATE TYPE accion_regla     AS ENUM ('auto_corregir', 'sugerir', 'reportar', 'excluir');
CREATE TYPE estado_carga     AS ENUM ('recibida', 'procesando', 'con_observaciones', 'aprobada', 'rechazada', 'error');
CREATE TYPE rol_archivo      AS ENUM ('original', 'corregido', 'reporte', 'bitacora');
CREATE TYPE estado_hallazgo  AS ENUM ('abierto', 'corregido', 'aceptado', 'descartado');
CREATE TYPE origen_correccion AS ENUM ('regla', 'ia', 'usuario');
CREATE TYPE estado_correccion AS ENUM ('pendiente', 'aplicada', 'rechazada');
CREATE TYPE fuente_equivalencia AS ENUM ('diccionario', 'manual', 'ia');

-- =====================================================================
-- 1. ACTORES
-- =====================================================================
CREATE TABLE institucion (
    id          SERIAL PRIMARY KEY,
    siglas      VARCHAR(20)  NOT NULL UNIQUE,        -- RENAP, PNC, INSIVUMEH, SECONRED
    nombre      VARCHAR(200) NOT NULL,
    contacto    VARCHAR(200),
    activa      BOOLEAN      NOT NULL DEFAULT TRUE,
    creado_en   TIMESTAMPTZ  NOT NULL DEFAULT now()
);

CREATE TABLE usuario (
    id              SERIAL PRIMARY KEY,
    institucion_id  INT REFERENCES institucion(id),  -- NULL para personal del INE
    nombre          VARCHAR(150) NOT NULL,
    email           VARCHAR(150) NOT NULL UNIQUE,
    password_hash   TEXT         NOT NULL,
    rol             rol_usuario  NOT NULL,
    activo          BOOLEAN      NOT NULL DEFAULT TRUE,
    creado_en       TIMESTAMPTZ  NOT NULL DEFAULT now(),
    CHECK (rol <> 'institucion' OR institucion_id IS NOT NULL)
);

-- =====================================================================
-- 2. DEFINICIÓN DE LAS BASES (lo que sale de los diccionarios)
-- =====================================================================
CREATE TABLE tipo_base (
    id              SERIAL PRIMARY KEY,
    codigo          VARCHAR(40)  NOT NULL UNIQUE,    -- DEFUNCIONES, NACIMIENTOS, DETENIDOS, CALIDAD_AIRE, EMERGENCIAS
    nombre          VARCHAR(150) NOT NULL,
    institucion_id  INT NOT NULL REFERENCES institucion(id),
    periodicidad    VARCHAR(20)  NOT NULL DEFAULT 'mensual',
    descripcion     TEXT
);

-- Versión del diccionario de variables (ej. "Diccionario defunciones 2018-2022")
CREATE TABLE version_esquema (
    id              SERIAL PRIMARY KEY,
    tipo_base_id    INT NOT NULL REFERENCES tipo_base(id),
    version         VARCHAR(40) NOT NULL,            -- '2018-2022', '2025'
    vigente_desde   DATE,
    activa          BOOLEAN NOT NULL DEFAULT TRUE,
    fuente          TEXT,                            -- archivo/URL del diccionario
    formato_crudo   JSONB,                           -- cómo leer el crudo: {"tipo":"ancho_a_largo",...}
    UNIQUE (tipo_base_id, version)
);
-- Solo una versión activa por tipo de base
CREATE UNIQUE INDEX ux_version_activa ON version_esquema(tipo_base_id) WHERE activa;

-- Catálogos de códigos: DEPARTAMENTO, MUNICIPIO, PAIS, CIE10, CAUSA_PNC, SEXO, PUEBLO...
CREATE TABLE catalogo (
    id          SERIAL PRIMARY KEY,
    codigo      VARCHAR(40)  NOT NULL UNIQUE,
    nombre      VARCHAR(150) NOT NULL,
    fuente      TEXT
);

CREATE TABLE catalogo_valor (
    id              SERIAL PRIMARY KEY,
    catalogo_id     INT NOT NULL REFERENCES catalogo(id) ON DELETE CASCADE,
    codigo          VARCHAR(40)  NOT NULL,           -- '0101', 'P229', '47', 'MATERIALES_PELIGROSOS'
    etiqueta        VARCHAR(300) NOT NULL,           -- 'Guatemala', 'Orden de captura'
    padre_codigo    VARCHAR(40),                     -- municipio -> depto, CIE10 subcat -> cat
    es_ignorado     BOOLEAN NOT NULL DEFAULT FALSE,  -- 9, 99, 9999 = "Ignorado"
    activo          BOOLEAN NOT NULL DEFAULT TRUE,
    UNIQUE (catalogo_id, codigo)
);
CREATE INDEX ix_catval_etiqueta ON catalogo_valor (catalogo_id, lower(etiqueta));

-- Variables de cada versión de esquema
CREATE TABLE variable (
    id                  SERIAL PRIMARY KEY,
    version_esquema_id  INT NOT NULL REFERENCES version_esquema(id) ON DELETE CASCADE,
    nombre_ine          VARCHAR(60)  NOT NULL,       -- nombre en la base publicada: Depreg, Caudef
    etiqueta            VARCHAR(200) NOT NULL,       -- 'Departamento de registro'
    tipo                tipo_dato    NOT NULL,
    catalogo_id         INT REFERENCES catalogo(id), -- si el valor debe existir en un catálogo
    requerida           BOOLEAN NOT NULL DEFAULT FALSE,
    valor_min           NUMERIC,
    valor_max           NUMERIC,
    patron_regex        TEXT,
    codigo_ignorado     VARCHAR(20),                 -- '9', '99', '9999'
    es_pii              BOOLEAN NOT NULL DEFAULT FALSE, -- CUI, nombres: se eliminan al publicar
    se_publica          BOOLEAN NOT NULL DEFAULT TRUE,
    transformacion      JSONB,                       -- cómo se calcula desde el crudo: {"tipo":"municipio_compuesto","depto":"DEPTO_REGISTRO","munic":"MUNIC_REGISTRO"}
    orden               INT NOT NULL,
    UNIQUE (version_esquema_id, nombre_ine)
);

-- Nombres con que las instituciones mandan cada columna (DEPTO_REGISTRO -> Depreg)
CREATE TABLE alias_columna (
    id           SERIAL PRIMARY KEY,
    variable_id  INT NOT NULL REFERENCES variable(id) ON DELETE CASCADE,
    alias        VARCHAR(150) NOT NULL,              -- guardar normalizado: mayúsculas, sin tildes
    UNIQUE (variable_id, alias)
);

-- Memoria de equivalencias texto -> código (MOTIVO de PNC, CAUSA_A -> CIE-10, "Coban" -> 1601)
-- Crece con cada aprobación: la próxima vez se corrige sola.
CREATE TABLE equivalencia (
    id              SERIAL PRIMARY KEY,
    catalogo_id     INT NOT NULL REFERENCES catalogo(id),
    institucion_id  INT REFERENCES institucion(id),  -- NULL = aplica a todas
    texto_origen    VARCHAR(500) NOT NULL,           -- normalizado
    codigo          VARCHAR(40)  NOT NULL,
    fuente          fuente_equivalencia NOT NULL,
    confianza       NUMERIC(4,3),                    -- 0.000 - 1.000 si viene de IA
    aprobada        BOOLEAN NOT NULL DEFAULT FALSE,
    aprobada_por    INT REFERENCES usuario(id),
    veces_usada     INT NOT NULL DEFAULT 0,
    creado_en       TIMESTAMPTZ NOT NULL DEFAULT now(),
    -- NULLS NOT DISTINCT: dos equivalencias "para todas" (institucion_id NULL) con el
    -- mismo texto chocan entre sí (PostgreSQL 15+)
    UNIQUE NULLS NOT DISTINCT (catalogo_id, institucion_id, texto_origen)
);

-- =====================================================================
-- 3. REGLAS DE CALIDAD
-- =====================================================================
CREATE TABLE regla (
    id              SERIAL PRIMARY KEY,
    tipo_base_id    INT REFERENCES tipo_base(id),    -- NULL = regla genérica (espacios, duplicados...)
    codigo          VARCHAR(60)  NOT NULL UNIQUE,    -- AIRE_MES_REPRESENTATIVO, NAC_HIJOS_COHERENCIA
    nombre          VARCHAR(200) NOT NULL,
    descripcion     TEXT,
    dimension       dimension_calidad NOT NULL,
    severidad       severidad    NOT NULL,
    accion          accion_regla NOT NULL,
    parametros      JSONB NOT NULL DEFAULT '{}',     -- {"max_horas_faltantes_dia":4,"max_dias_invalidos_mes":2}
    activa          BOOLEAN NOT NULL DEFAULT TRUE
);

-- Variables que revisa cada regla
CREATE TABLE regla_variable (
    regla_id     INT NOT NULL REFERENCES regla(id) ON DELETE CASCADE,
    variable_id  INT NOT NULL REFERENCES variable(id) ON DELETE CASCADE,
    PRIMARY KEY (regla_id, variable_id)
);

-- =====================================================================
-- 4. CARGAS Y PROCESAMIENTO
-- =====================================================================
CREATE TABLE carga (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    institucion_id  INT NOT NULL REFERENCES institucion(id),
    tipo_base_id    INT NOT NULL REFERENCES tipo_base(id),
    usuario_id      INT NOT NULL REFERENCES usuario(id),
    periodo_anio    SMALLINT NOT NULL,
    periodo_mes     SMALLINT CHECK (periodo_mes BETWEEN 1 AND 12), -- NULL si es anual
    estado          estado_carga NOT NULL DEFAULT 'recibida',
    puntaje_calidad NUMERIC(5,2),                    -- 0-100, de la última ejecución
    notas           TEXT,
    creado_en       TIMESTAMPTZ NOT NULL DEFAULT now(),
    actualizado_en  TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX ix_carga_inst_periodo ON carga (institucion_id, tipo_base_id, periodo_anio, periodo_mes);

CREATE TABLE archivo (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    carga_id        UUID NOT NULL REFERENCES carga(id) ON DELETE CASCADE,
    rol             rol_archivo NOT NULL,
    nombre          VARCHAR(300) NOT NULL,
    formato         VARCHAR(10)  NOT NULL,           -- xlsx, csv, sav
    tamano_bytes    BIGINT,
    sha256          CHAR(64) NOT NULL,               -- detecta re-envíos del mismo archivo
    ruta            TEXT NOT NULL,                   -- ruta en almacenamiento (originales cifrados: traen PII)
    hojas           JSONB,                           -- [{"nombre":"julio 2026","filas":8841,"columnas":76}]
    creado_en       TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Cada corrida del motor sobre una carga
CREATE TABLE ejecucion (
    id                   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    carga_id             UUID NOT NULL REFERENCES carga(id) ON DELETE CASCADE,
    version_esquema_id   INT NOT NULL REFERENCES version_esquema(id),
    iniciada_en          TIMESTAMPTZ NOT NULL DEFAULT now(),
    finalizada_en        TIMESTAMPTZ,
    total_registros      INT,
    registros_validos    INT,
    registros_excluidos  INT,
    puntaje              NUMERIC(5,2),
    mapeo_columnas       JSONB,                      -- {"DEPTO_REGISTRO":"Depreg", "MUNICIPIO.1": null}
    resumen              JSONB,                      -- conteos por regla/severidad para el dashboard
    error                TEXT
);

-- Puntaje por dimensión (para las gráficas del reporte)
CREATE TABLE puntaje_dimension (
    ejecucion_id  UUID NOT NULL REFERENCES ejecucion(id) ON DELETE CASCADE,
    dimension     dimension_calidad NOT NULL,
    puntaje       NUMERIC(5,2) NOT NULL,
    PRIMARY KEY (ejecucion_id, dimension)
);

-- =====================================================================
-- 5. RESULTADOS: HALLAZGOS Y BITÁCORA DE CORRECCIONES
-- =====================================================================
-- Hallazgos agregados: una fila por regla + columna, con ejemplos.
-- (Evita guardar 55,000 filas cuando hay 55,000 "N.D.")
CREATE TABLE hallazgo (
    id              BIGSERIAL PRIMARY KEY,
    ejecucion_id    UUID NOT NULL REFERENCES ejecucion(id) ON DELETE CASCADE,
    regla_id        INT  NOT NULL REFERENCES regla(id),
    hoja            VARCHAR(100),
    columna         VARCHAR(150),
    registros_afectados INT NOT NULL,
    porcentaje      NUMERIC(6,3),
    severidad       severidad NOT NULL,
    mensaje         TEXT NOT NULL,                   -- texto para la institución
    ejemplos        JSONB,                           -- [{"fila":12,"valor":"N.D."}, ...] máx. 20
    estado          estado_hallazgo NOT NULL DEFAULT 'abierto'
);
CREATE INDEX ix_hallazgo_ejecucion ON hallazgo (ejecucion_id, severidad);

-- Bitácora de cambios (trazabilidad: nada se cambia en silencio).
-- Una fila por cambio distinto: "AGRESION A FEMINA" -> "12" en 25 registros es UNA fila
-- con registros_afectados = 25; aprobarla aplica el cambio a los 25.
CREATE TABLE correccion (
    id              BIGSERIAL PRIMARY KEY,
    ejecucion_id    UUID NOT NULL REFERENCES ejecucion(id) ON DELETE CASCADE,
    hallazgo_id     BIGINT REFERENCES hallazgo(id) ON DELETE SET NULL,
    hoja            VARCHAR(100),
    fila            INT  NOT NULL,                   -- primera fila del archivo original con ese valor
    registros_afectados INT NOT NULL DEFAULT 1,      -- cuántas celdas tienen el mismo valor_antes
    columna         VARCHAR(150) NOT NULL,
    valor_antes     TEXT,
    valor_despues   TEXT,
    origen          origen_correccion NOT NULL,
    equivalencia_id INT REFERENCES equivalencia(id), -- si salió de la memoria de equivalencias
    confianza       NUMERIC(4,3),                    -- para sugerencias de IA
    justificacion   TEXT,                            -- explicación de la IA o de la regla
    estado          estado_correccion NOT NULL,      -- auto_corregir => 'aplicada'; sugerir => 'pendiente'
    revisada_por    INT REFERENCES usuario(id),
    revisada_en     TIMESTAMPTZ
);
CREATE INDEX ix_correccion_pendiente ON correccion (ejecucion_id) WHERE estado = 'pendiente';

-- Registros excluidos y por qué (fuera de período, mes no representativo...)
CREATE TABLE registro_excluido (
    id            BIGSERIAL PRIMARY KEY,
    ejecucion_id  UUID NOT NULL REFERENCES ejecucion(id) ON DELETE CASCADE,
    regla_id      INT  NOT NULL REFERENCES regla(id),
    hoja          VARCHAR(100),
    fila          INT NOT NULL,                      -- primera fila excluida del grupo
    registros_afectados INT NOT NULL DEFAULT 1,      -- filas excluidas por el mismo motivo
    filas         JSONB,                             -- todas las filas del grupo: [12, 13, 14, ...]
    motivo        TEXT NOT NULL                      -- "Mes 3 de Correos PM10: 5 días con más de 4 horas sin dato"
);

-- =====================================================================
-- 6. AUDITORÍA DEL SISTEMA
-- =====================================================================
CREATE TABLE evento_auditoria (
    id          BIGSERIAL PRIMARY KEY,
    usuario_id  INT REFERENCES usuario(id),
    accion      VARCHAR(60) NOT NULL,                -- subir_archivo, aprobar_correccion, descargar_original
    entidad     VARCHAR(60),
    entidad_id  TEXT,
    detalle     JSONB,
    ip          INET,
    creado_en   TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- =====================================================================
-- Datos semilla mínimos
-- =====================================================================
INSERT INTO institucion (siglas, nombre) VALUES
 ('RENAP',     'Registro Nacional de las Personas'),
 ('PNC',       'Policía Nacional Civil'),
 ('INSIVUMEH', 'Instituto Nacional de Sismología, Vulcanología, Meteorología e Hidrología'),
 ('SECONRED',  'Secretaría Ejecutiva de la Coordinadora Nacional para la Reducción de Desastres');

INSERT INTO tipo_base (codigo, nombre, institucion_id, periodicidad) VALUES
 ('DEFUNCIONES',  'Estadísticas vitales - Defunciones', (SELECT id FROM institucion WHERE siglas='RENAP'),     'mensual'),
 ('NACIMIENTOS',  'Estadísticas vitales - Nacimientos', (SELECT id FROM institucion WHERE siglas='RENAP'),     'mensual'),
 ('DETENIDOS',    'Hechos delictivos - Detenidos',      (SELECT id FROM institucion WHERE siglas='PNC'),       'mensual'),
 ('CALIDAD_AIRE', 'Monitoreo de calidad del aire',      (SELECT id FROM institucion WHERE siglas='INSIVUMEH'), 'anual'),
 ('EMERGENCIAS',  'Emergencias y desastres',            (SELECT id FROM institucion WHERE siglas='SECONRED'),  'anual');

-- Las reglas se cargan desde backend/config/reglas.yaml con scripts/cargar_config.py
