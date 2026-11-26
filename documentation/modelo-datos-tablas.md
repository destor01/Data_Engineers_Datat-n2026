# Modelo de datos: detalle de tablas

> Generado con `documentation/herramientas/generar_modelo_datos.py` desde una base PostgreSQL con los
> esquemas del proyecto. La explicación del modelo está en [modelo-datos.md](modelo-datos.md).

## Data Audit

### `public.alias_columna`

| Columna | Tipo | Nulo | Por defecto | Nota |
|---|---|---|---|---|
| `id` | integer | no | nextval('alias_columna_id_seq'::regclass) |  |
| `variable_id` | integer | no | — |  |
| `alias` | character varying(150) | no | — |  |

Restricciones:

- Llave foránea: `FOREIGN KEY (variable_id) REFERENCES variable(id) ON DELETE CASCADE`
- Llave primaria: `PRIMARY KEY (id)`
- Única: `UNIQUE (variable_id, alias)`

### `public.archivo`

| Columna | Tipo | Nulo | Por defecto | Nota |
|---|---|---|---|---|
| `id` | uuid | no | gen_random_uuid() |  |
| `carga_id` | uuid | no | — |  |
| `rol` | rol_archivo | no | — |  |
| `nombre` | character varying(300) | no | — |  |
| `formato` | character varying(10) | no | — |  |
| `tamano_bytes` | bigint | sí | — |  |
| `sha256` | character(64) | no | — |  |
| `ruta` | text | no | — |  |
| `hojas` | jsonb | sí | — |  |
| `creado_en` | timestamp with time zone | no | now() |  |

Restricciones:

- Llave foránea: `FOREIGN KEY (carga_id) REFERENCES carga(id) ON DELETE CASCADE`
- Llave primaria: `PRIMARY KEY (id)`

### `public.carga`

| Columna | Tipo | Nulo | Por defecto | Nota |
|---|---|---|---|---|
| `id` | uuid | no | gen_random_uuid() |  |
| `institucion_id` | integer | no | — |  |
| `tipo_base_id` | integer | no | — |  |
| `usuario_id` | integer | no | — |  |
| `periodo_anio` | smallint | no | — |  |
| `periodo_mes` | smallint | sí | — |  |
| `estado` | estado_carga | no | 'recibida'::estado_carga |  |
| `puntaje_calidad` | numeric(5,2) | sí | — |  |
| `notas` | text | sí | — |  |
| `creado_en` | timestamp with time zone | no | now() |  |
| `actualizado_en` | timestamp with time zone | no | now() |  |

Restricciones:

- Verificación: `CHECK (((periodo_mes >= 1) AND (periodo_mes <= 12)))`
- Llave foránea: `FOREIGN KEY (institucion_id) REFERENCES institucion(id)`
- Llave foránea: `FOREIGN KEY (tipo_base_id) REFERENCES tipo_base(id)`
- Llave foránea: `FOREIGN KEY (usuario_id) REFERENCES usuario(id)`
- Llave primaria: `PRIMARY KEY (id)`

Índices adicionales:

- `CREATE INDEX ix_carga_inst_periodo ON public.carga USING btree (institucion_id, tipo_base_id, periodo_anio, periodo_mes)`

### `public.catalogo`

| Columna | Tipo | Nulo | Por defecto | Nota |
|---|---|---|---|---|
| `id` | integer | no | nextval('catalogo_id_seq'::regclass) |  |
| `codigo` | character varying(40) | no | — |  |
| `nombre` | character varying(150) | no | — |  |
| `fuente` | text | sí | — |  |

Restricciones:

- Llave primaria: `PRIMARY KEY (id)`
- Única: `UNIQUE (codigo)`

### `public.catalogo_valor`

| Columna | Tipo | Nulo | Por defecto | Nota |
|---|---|---|---|---|
| `id` | integer | no | nextval('catalogo_valor_id_seq'::regclass) |  |
| `catalogo_id` | integer | no | — |  |
| `codigo` | character varying(40) | no | — |  |
| `etiqueta` | character varying(300) | no | — |  |
| `padre_codigo` | character varying(40) | sí | — |  |
| `es_ignorado` | boolean | no | false |  |
| `activo` | boolean | no | true |  |

Restricciones:

- Llave foránea: `FOREIGN KEY (catalogo_id) REFERENCES catalogo(id) ON DELETE CASCADE`
- Llave primaria: `PRIMARY KEY (id)`
- Única: `UNIQUE (catalogo_id, codigo)`

Índices adicionales:

- `CREATE INDEX ix_catval_etiqueta ON public.catalogo_valor USING btree (catalogo_id, lower((etiqueta)::text))`

### `public.correccion`

| Columna | Tipo | Nulo | Por defecto | Nota |
|---|---|---|---|---|
| `id` | bigint | no | nextval('correccion_id_seq'::regclass) |  |
| `ejecucion_id` | uuid | no | — |  |
| `hallazgo_id` | bigint | sí | — |  |
| `hoja` | character varying(100) | sí | — |  |
| `fila` | integer | no | — |  |
| `registros_afectados` | integer | no | 1 |  |
| `columna` | character varying(150) | no | — |  |
| `valor_antes` | text | sí | — |  |
| `valor_despues` | text | sí | — |  |
| `origen` | origen_correccion | no | — |  |
| `equivalencia_id` | integer | sí | — |  |
| `confianza` | numeric(4,3) | sí | — |  |
| `justificacion` | text | sí | — |  |
| `estado` | estado_correccion | no | — |  |
| `revisada_por` | integer | sí | — |  |
| `revisada_en` | timestamp with time zone | sí | — |  |

Restricciones:

- Llave foránea: `FOREIGN KEY (ejecucion_id) REFERENCES ejecucion(id) ON DELETE CASCADE`
- Llave foránea: `FOREIGN KEY (equivalencia_id) REFERENCES equivalencia(id)`
- Llave foránea: `FOREIGN KEY (hallazgo_id) REFERENCES hallazgo(id) ON DELETE SET NULL`
- Llave foránea: `FOREIGN KEY (revisada_por) REFERENCES usuario(id)`
- Llave primaria: `PRIMARY KEY (id)`

Índices adicionales:

- `CREATE INDEX ix_correccion_pendiente ON public.correccion USING btree (ejecucion_id) WHERE (estado = 'pendiente'::estado_correccion)`

### `public.ejecucion`

| Columna | Tipo | Nulo | Por defecto | Nota |
|---|---|---|---|---|
| `id` | uuid | no | gen_random_uuid() |  |
| `carga_id` | uuid | no | — |  |
| `version_esquema_id` | integer | no | — |  |
| `iniciada_en` | timestamp with time zone | no | now() |  |
| `finalizada_en` | timestamp with time zone | sí | — |  |
| `total_registros` | integer | sí | — |  |
| `registros_validos` | integer | sí | — |  |
| `registros_excluidos` | integer | sí | — |  |
| `puntaje` | numeric(5,2) | sí | — |  |
| `mapeo_columnas` | jsonb | sí | — |  |
| `resumen` | jsonb | sí | — |  |
| `error` | text | sí | — |  |

Restricciones:

- Llave foránea: `FOREIGN KEY (carga_id) REFERENCES carga(id) ON DELETE CASCADE`
- Llave foránea: `FOREIGN KEY (version_esquema_id) REFERENCES version_esquema(id)`
- Llave primaria: `PRIMARY KEY (id)`

### `public.equivalencia`

| Columna | Tipo | Nulo | Por defecto | Nota |
|---|---|---|---|---|
| `id` | integer | no | nextval('equivalencia_id_seq'::regclass) |  |
| `catalogo_id` | integer | no | — |  |
| `institucion_id` | integer | sí | — |  |
| `texto_origen` | character varying(500) | no | — |  |
| `codigo` | character varying(40) | no | — |  |
| `fuente` | fuente_equivalencia | no | — |  |
| `confianza` | numeric(4,3) | sí | — |  |
| `aprobada` | boolean | no | false |  |
| `aprobada_por` | integer | sí | — |  |
| `veces_usada` | integer | no | 0 |  |
| `creado_en` | timestamp with time zone | no | now() |  |

Restricciones:

- Llave foránea: `FOREIGN KEY (aprobada_por) REFERENCES usuario(id)`
- Llave foránea: `FOREIGN KEY (catalogo_id) REFERENCES catalogo(id)`
- Llave foránea: `FOREIGN KEY (institucion_id) REFERENCES institucion(id)`
- Llave primaria: `PRIMARY KEY (id)`
- Única: `UNIQUE NULLS NOT DISTINCT (catalogo_id, institucion_id, texto_origen)`

### `public.evento_auditoria`

| Columna | Tipo | Nulo | Por defecto | Nota |
|---|---|---|---|---|
| `id` | bigint | no | nextval('evento_auditoria_id_seq'::regclass) |  |
| `usuario_id` | integer | sí | — |  |
| `accion` | character varying(60) | no | — |  |
| `entidad` | character varying(60) | sí | — |  |
| `entidad_id` | text | sí | — |  |
| `detalle` | jsonb | sí | — |  |
| `ip` | inet | sí | — |  |
| `creado_en` | timestamp with time zone | no | now() |  |

Restricciones:

- Llave foránea: `FOREIGN KEY (usuario_id) REFERENCES usuario(id)`
- Llave primaria: `PRIMARY KEY (id)`

### `public.hallazgo`

| Columna | Tipo | Nulo | Por defecto | Nota |
|---|---|---|---|---|
| `id` | bigint | no | nextval('hallazgo_id_seq'::regclass) |  |
| `ejecucion_id` | uuid | no | — |  |
| `regla_id` | integer | no | — |  |
| `hoja` | character varying(100) | sí | — |  |
| `columna` | character varying(150) | sí | — |  |
| `registros_afectados` | integer | no | — |  |
| `porcentaje` | numeric(6,3) | sí | — |  |
| `severidad` | severidad | no | — |  |
| `mensaje` | text | no | — |  |
| `ejemplos` | jsonb | sí | — |  |
| `estado` | estado_hallazgo | no | 'abierto'::estado_hallazgo |  |

Restricciones:

- Llave foránea: `FOREIGN KEY (ejecucion_id) REFERENCES ejecucion(id) ON DELETE CASCADE`
- Llave foránea: `FOREIGN KEY (regla_id) REFERENCES regla(id)`
- Llave primaria: `PRIMARY KEY (id)`

Índices adicionales:

- `CREATE INDEX ix_hallazgo_ejecucion ON public.hallazgo USING btree (ejecucion_id, severidad)`

### `public.institucion`

| Columna | Tipo | Nulo | Por defecto | Nota |
|---|---|---|---|---|
| `id` | integer | no | nextval('institucion_id_seq'::regclass) |  |
| `siglas` | character varying(20) | no | — |  |
| `nombre` | character varying(200) | no | — |  |
| `contacto` | character varying(200) | sí | — |  |
| `activa` | boolean | no | true |  |
| `creado_en` | timestamp with time zone | no | now() |  |

Restricciones:

- Llave primaria: `PRIMARY KEY (id)`
- Única: `UNIQUE (siglas)`

### `public.puntaje_dimension`

| Columna | Tipo | Nulo | Por defecto | Nota |
|---|---|---|---|---|
| `ejecucion_id` | uuid | no | — |  |
| `dimension` | dimension_calidad | no | — |  |
| `puntaje` | numeric(5,2) | no | — |  |

Restricciones:

- Llave foránea: `FOREIGN KEY (ejecucion_id) REFERENCES ejecucion(id) ON DELETE CASCADE`
- Llave primaria: `PRIMARY KEY (ejecucion_id, dimension)`

### `public.registro_excluido`

| Columna | Tipo | Nulo | Por defecto | Nota |
|---|---|---|---|---|
| `id` | bigint | no | nextval('registro_excluido_id_seq'::regclass) |  |
| `ejecucion_id` | uuid | no | — |  |
| `regla_id` | integer | no | — |  |
| `hoja` | character varying(100) | sí | — |  |
| `fila` | integer | no | — |  |
| `registros_afectados` | integer | no | 1 |  |
| `filas` | jsonb | sí | — |  |
| `motivo` | text | no | — |  |

Restricciones:

- Llave foránea: `FOREIGN KEY (ejecucion_id) REFERENCES ejecucion(id) ON DELETE CASCADE`
- Llave foránea: `FOREIGN KEY (regla_id) REFERENCES regla(id)`
- Llave primaria: `PRIMARY KEY (id)`

### `public.regla`

| Columna | Tipo | Nulo | Por defecto | Nota |
|---|---|---|---|---|
| `id` | integer | no | nextval('regla_id_seq'::regclass) |  |
| `tipo_base_id` | integer | sí | — |  |
| `codigo` | character varying(60) | no | — |  |
| `nombre` | character varying(200) | no | — |  |
| `descripcion` | text | sí | — |  |
| `dimension` | dimension_calidad | no | — |  |
| `severidad` | severidad | no | — |  |
| `accion` | accion_regla | no | — |  |
| `parametros` | jsonb | no | '{}'::jsonb |  |
| `activa` | boolean | no | true |  |

Restricciones:

- Llave foránea: `FOREIGN KEY (tipo_base_id) REFERENCES tipo_base(id)`
- Llave primaria: `PRIMARY KEY (id)`
- Única: `UNIQUE (codigo)`

### `public.regla_variable`

| Columna | Tipo | Nulo | Por defecto | Nota |
|---|---|---|---|---|
| `regla_id` | integer | no | — |  |
| `variable_id` | integer | no | — |  |

Restricciones:

- Llave foránea: `FOREIGN KEY (regla_id) REFERENCES regla(id) ON DELETE CASCADE`
- Llave foránea: `FOREIGN KEY (variable_id) REFERENCES variable(id) ON DELETE CASCADE`
- Llave primaria: `PRIMARY KEY (regla_id, variable_id)`

### `public.tipo_base`

| Columna | Tipo | Nulo | Por defecto | Nota |
|---|---|---|---|---|
| `id` | integer | no | nextval('tipo_base_id_seq'::regclass) |  |
| `codigo` | character varying(40) | no | — |  |
| `nombre` | character varying(150) | no | — |  |
| `institucion_id` | integer | no | — |  |
| `periodicidad` | character varying(20) | no | 'mensual'::character varying |  |
| `descripcion` | text | sí | — |  |

Restricciones:

- Llave foránea: `FOREIGN KEY (institucion_id) REFERENCES institucion(id)`
- Llave primaria: `PRIMARY KEY (id)`
- Única: `UNIQUE (codigo)`

### `public.usuario`

| Columna | Tipo | Nulo | Por defecto | Nota |
|---|---|---|---|---|
| `id` | integer | no | nextval('usuario_id_seq'::regclass) |  |
| `institucion_id` | integer | sí | — |  |
| `nombre` | character varying(150) | no | — |  |
| `email` | character varying(150) | no | — |  |
| `password_hash` | text | no | — |  |
| `rol` | rol_usuario | no | — |  |
| `activo` | boolean | no | true |  |
| `creado_en` | timestamp with time zone | no | now() |  |

Restricciones:

- Verificación: `CHECK (((rol <> 'institucion'::rol_usuario) OR (institucion_id IS NOT NULL)))`
- Llave foránea: `FOREIGN KEY (institucion_id) REFERENCES institucion(id)`
- Llave primaria: `PRIMARY KEY (id)`
- Única: `UNIQUE (email)`

### `public.variable`

| Columna | Tipo | Nulo | Por defecto | Nota |
|---|---|---|---|---|
| `id` | integer | no | nextval('variable_id_seq'::regclass) |  |
| `version_esquema_id` | integer | no | — |  |
| `nombre_ine` | character varying(60) | no | — |  |
| `etiqueta` | character varying(200) | no | — |  |
| `tipo` | tipo_dato | no | — |  |
| `catalogo_id` | integer | sí | — |  |
| `requerida` | boolean | no | false |  |
| `valor_min` | numeric | sí | — |  |
| `valor_max` | numeric | sí | — |  |
| `patron_regex` | text | sí | — |  |
| `codigo_ignorado` | character varying(20) | sí | — |  |
| `es_pii` | boolean | no | false |  |
| `se_publica` | boolean | no | true |  |
| `transformacion` | jsonb | sí | — |  |
| `orden` | integer | no | — |  |

Restricciones:

- Llave foránea: `FOREIGN KEY (catalogo_id) REFERENCES catalogo(id)`
- Llave foránea: `FOREIGN KEY (version_esquema_id) REFERENCES version_esquema(id) ON DELETE CASCADE`
- Llave primaria: `PRIMARY KEY (id)`
- Única: `UNIQUE (version_esquema_id, nombre_ine)`

### `public.version_esquema`

| Columna | Tipo | Nulo | Por defecto | Nota |
|---|---|---|---|---|
| `id` | integer | no | nextval('version_esquema_id_seq'::regclass) |  |
| `tipo_base_id` | integer | no | — |  |
| `version` | character varying(40) | no | — |  |
| `vigente_desde` | date | sí | — |  |
| `activa` | boolean | no | true |  |
| `fuente` | text | sí | — |  |
| `formato_crudo` | jsonb | sí | — |  |

Restricciones:

- Llave foránea: `FOREIGN KEY (tipo_base_id) REFERENCES tipo_base(id)`
- Llave primaria: `PRIMARY KEY (id)`
- Única: `UNIQUE (tipo_base_id, version)`

Índices adicionales:

- `CREATE UNIQUE INDEX ux_version_activa ON public.version_esquema USING btree (tipo_base_id) WHERE activa`

## Audio Audit

### `public.audio_audit_calibration`

| Columna | Tipo | Nulo | Por defecto | Nota |
|---|---|---|---|---|
| `model_version` | text | no | — |  |
| `min_labels` | integer | no | 30 |  |
| `total_labels` | integer | no | 0 |  |
| `is_calibrated` | boolean | no | false |  |
| `calibrator` | jsonb | no | '{"noul_platt": {}, "choice_temperature": {}}'::jsonb |  |
| `groups` | jsonb | no | '{}'::jsonb |  |
| `updated_at` | timestamp with time zone | no | now() |  |

Restricciones:

- Llave primaria: `PRIMARY KEY (model_version)`

### `public.audio_audit_evaluation_edits`

| Columna | Tipo | Nulo | Por defecto | Nota |
|---|---|---|---|---|
| `id` | bigint | no | nextval('audio_audit_evaluation_edits_id_seq'::regclass) |  |
| `job_id` | text | no | — |  |
| `rule_id` | text | no | — |  |
| `previous_outcome` | jsonb | sí | — |  |
| `override_status` | text | no | — |  |
| `new_outcome` | jsonb | sí | — |  |
| `auditor_comment` | text | sí | — |  |
| `propagate_to_future` | boolean | no | false |  |
| `window_index` | integer | sí | — |  |
| `question_key` | text | sí | — |  |
| `question_type` | text | sí | — |  |
| `calibration_group` | text | sí | — |  |
| `raw_probability` | double precision | sí | — |  |
| `raw_probabilities` | jsonb | sí | — |  |
| `gold_label` | text | sí | — |  |
| `model_version` | text | sí | — |  |
| `is_mock` | boolean | no | false |  |
| `created_at` | timestamp with time zone | no | now() |  |

Restricciones:

- Llave foránea: `FOREIGN KEY (job_id) REFERENCES audio_audit_jobs(id) ON DELETE CASCADE`
- Llave primaria: `PRIMARY KEY (id)`

Índices adicionales:

- `CREATE INDEX ix_audio_audit_eval_edits_calibration ON public.audio_audit_evaluation_edits USING btree (model_version, calibration_group, created_at) WHERE ((is_mock = false) AND (question_key IS NOT NULL))`
- `CREATE INDEX ix_audio_audit_eval_edits_job ON public.audio_audit_evaluation_edits USING btree (job_id, created_at DESC)`

### `public.audio_audit_jobs`

| Columna | Tipo | Nulo | Por defecto | Nota |
|---|---|---|---|---|
| `id` | text | no | — |  |
| `filename` | text | no | — |  |
| `source` | text | no | 'audio'::text |  |
| `stt_provider` | text | sí | — |  |
| `external_job_id` | text | sí | — |  |
| `storage_path` | text | sí | — |  |
| `has_audio` | boolean | no | false |  |
| `status` | text | no | 'queued'::text |  |
| `stage` | text | no | ''::text |  |
| `progress` | real | no | 0 |  |
| `duration_seconds` | double precision | sí | — |  |
| `elapsed_seconds` | double precision | no | 0 |  |
| `result` | jsonb | sí | — |  |
| `error` | text | sí | — |  |
| `eval_status` | text | no | 'idle'::text |  |
| `eval_elapsed_seconds` | double precision | no | 0 |  |
| `evaluation` | jsonb | sí | — |  |
| `eval_error` | text | sí | — |  |
| `created_at` | timestamp with time zone | no | now() |  |
| `updated_at` | timestamp with time zone | no | now() |  |

Restricciones:

- Llave primaria: `PRIMARY KEY (id)`

Índices adicionales:

- `CREATE INDEX ix_audio_audit_jobs_created_at ON public.audio_audit_jobs USING btree (created_at DESC)`

### `public.audio_audit_rule_overrides`

| Columna | Tipo | Nulo | Por defecto | Nota |
|---|---|---|---|---|
| `rule_id` | text | no | — |  |
| `section` | text | no | — |  |
| `custom_text` | text | sí | — |  |
| `weight` | integer | sí | — |  |
| `enabled` | boolean | no | true |  |
| `auditor_guidance` | text | sí | — |  |
| `questions_override` | jsonb | no | '{}'::jsonb |  |
| `updated_at` | timestamp with time zone | no | now() |  |

Restricciones:

- Verificación: `CHECK ((weight = ANY (ARRAY[1, 2, 3])))`
- Llave primaria: `PRIMARY KEY (rule_id)`

## Survey Audit y Quality Improvement

### `quality_extensions.state`

| Columna | Tipo | Nulo | Por defecto | Nota |
|---|---|---|---|---|
| `id` | integer | no | — |  |
| `data` | jsonb | no | — |  |
| `revision` | bigint | no | 0 |  |

Restricciones:

- Verificación: `CHECK ((id = 1))`
- Llave primaria: `PRIMARY KEY (id)`

## Tipos enumerados

| Tipo | Valores |
|---|---|
| `accion_regla` | auto_corregir, sugerir, reportar, excluir |
| `dimension_calidad` | estructura, completitud, validez, consistencia, unicidad, oportunidad, representatividad |
| `estado_carga` | recibida, procesando, con_observaciones, aprobada, rechazada, error |
| `estado_correccion` | pendiente, aplicada, rechazada |
| `estado_hallazgo` | abierto, corregido, aceptado, descartado |
| `fuente_equivalencia` | diccionario, manual, ia |
| `origen_correccion` | regla, ia, usuario |
| `rol_archivo` | original, corregido, reporte, bitacora |
| `rol_usuario` | institucion, analista_ine, admin |
| `severidad` | error, advertencia, info |
| `tipo_dato` | entero, decimal, texto, fecha, hora, fecha_hora, codigo, booleano |
