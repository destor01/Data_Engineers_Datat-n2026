# Quality Audit — backend

Plataforma de auditoría de calidad de datos para el Datatón INE Guatemala 2026.

## Estructura

```
quality-audit/
├── schema.sql                  # Esquema PostgreSQL (19 tablas)
└── backend/
    ├── config/
    │   ├── catalogos.yaml      # 31 catálogos + equivalencias de texto conocidas
    │   ├── reglas.yaml         # 28 reglas de calidad (umbrales, severidad, acción, mensaje)
    │   └── bases/              # Una definición por base del INE
    │       ├── defunciones.yaml
    │       ├── nacimientos.yaml
    │       ├── detenidos.yaml
    │       ├── calidad_aire.yaml
    │       └── emergencias.yaml
    ├── qa/                     # Motor de validación y API
    │   ├── api.py              # Endpoints /api/qa/... (FastAPI APIRouter)
    │   ├── servidor.py         # App FastAPI independiente (puerto 8001)
    │   ├── cli.py              # python -m qa.cli procesar ...
    │   ├── definicion.py       # Lee de PostgreSQL la definición de una base
    │   ├── lector.py           # Abre el crudo: tabla, hojas mensuales, ancho a largo, CSV
    │   ├── transformaciones.py # Las 13 recetas para calcular columnas del INE
    │   ├── codificador.py      # Sugiere códigos (similitud de texto; aquí se enchufa la IA)
    │   ├── reglas.py           # Reglas de varias columnas y llave única
    │   ├── motor.py            # Orquesta todo y calcula el puntaje
    │   ├── salidas.py          # Archivos de salida y guardado en la base de datos
    │   └── texto.py            # Normalización de texto
    ├── scripts/
    │   ├── cargar_config.py    # Diccionarios + YAML -> PostgreSQL
    │   └── comparar_con_ine.py # Compara la salida del motor con lo publicado por el INE
    └── requirements.txt
```

## Puesta en marcha

Requiere PostgreSQL 15 o superior (usa `UNIQUE NULLS NOT DISTINCT`) y Python 3.11+.

```bash
pip install -r backend/requirements.txt

createdb quality_audit
psql -d quality_audit -f schema.sql

cd backend
python -m scripts.cargar_config \
  --db postgresql://usuario:clave@localhost:5432/quality_audit \
  --dicc-defunciones ruta/diccionario-defunciones-2018-2022.xlsx \
  --dicc-nacimientos ruta/diccionario-nacimientos-2018-2022.xlsx \
  --dicc-pnc         ruta/diccionario-detenidos-pnc.xlsx
```

El script se puede correr las veces que haga falta: actualiza lo que ya existe.
Resultado esperado:

| Tabla | Filas |
| --- | ---: |
| catalogo | 31 |
| catalogo_valor | 15,086 |
| equivalencia | 761 |
| version_esquema (activas) | 5 |
| variable | 235 |
| alias_columna | 340 |
| regla | 33 |

## Cómo se definen las bases

Cada YAML de `config/bases/` tiene cuatro listas:

| Lista | Qué es | Se publica |
| --- | --- | --- |
| `variables` | Columnas de la base publicada por el INE, con su catálogo, rango y alias | Sí (salvo `publica: false`) |
| `auxiliares` | Columnas del crudo que sirven para validar (fechas completas, llaves) | No |
| `pii` | Datos personales (CUI, nombres, direcciones) | Nunca: se eliminan |
| `llave` | Columnas que identifican un registro único | Genera la regla `<BASE>_LLAVE_UNICA` |

Columnas publicadas por base (coinciden con las bases del INE):
defunciones 26, nacimientos 40, detenidos 19, calidad del aire 12, emergencias 26.

### Transformaciones

Cuando una columna del INE no se copia tal cual del crudo, `transformacion` dice cómo se calcula.
El motor implementa estos tipos:

| Tipo | Ejemplo |
| --- | --- |
| `municipio_compuesto` | RENAP manda depto `1` y munic `14` → `0114` |
| `parte_fecha` | `FECHA_NACIMIENTO` → día, mes o año |
| `parte_hora`, `agrupar_hora` | `02:00` → 2 → grupo "00:00 a 05:59" |
| `agrupar_edad` | 37 → grupo "35-39" según el catálogo |
| `depto_de_municipio` | `0101` → `1` |
| `rellenar_ceros` | `101` → `0101` |
| `padre_catalogo` | Causa 20 → grupo 3 (Contra el patrimonio) |
| `etiqueta_catalogo` | Código de mes 7 → "Julio" |
| `mapa` | `SI` → Urbano |
| `constante` | `ug/m3` |
| `vacio_como` | Conteo vacío → 0 (afectación en emergencias) |
| `codificar_texto` | "Quiche" → departamento 14, por equivalencia exacta |
| `codificar_ia` | Texto libre → código, propuesto por IA y aprobado por un analista |

## Motor de validación

```bash
export DATABASE_URL=postgresql://usuario:clave@localhost:5432/quality_audit
cd backend
python -m qa.cli bases
python -m qa.cli procesar --base DETENIDOS --archivo detenidos_octubre.xlsx --anio 2026 --mes 10
```

Opciones: `--almacen` (carpeta de salida, por defecto `./almacen`), `--sin-guardar` (no escribe
en la base de datos), `--usuario` (email de quien sube), `--todo` (muestra los informativos).

### Qué hace, en orden

1. **Lee** el crudo como venga y registra problemas de estructura (encabezados repetidos,
   columnas vacías, hojas con encabezados distintos).
2. **Empareja** cada columna con una variable del INE por sus alias. Las columnas con datos
   personales se descartan y las desconocidas se reportan.
3. **Limpia** espacios sobrantes y textos de "sin dato" ("N.D.", "-1", "IGNORADO"...).
4. **Calcula** cada columna del INE: copia directa o transformación.
5. **Codifica** contra el catálogo. Si el valor ya es un código válido, lo deja; si existe una
   equivalencia aprobada, lo traduce; si no, lo reporta y pide una sugerencia al codificador.
6. **Valida** tipo de dato, dato faltante (asigna el código de ignorado del INE), rango y formato.
7. Corre las **reglas específicas** y la de **llave única**.
8. Quita los registros **excluidos** y calcula el **puntaje**.

### Qué produce

| Salida | Contenido |
| --- | --- |
| `almacen/<carga>/original.*` | Copia del archivo recibido. Trae datos personales: proteger |
| `almacen/<carga>/corregido.xlsx` | Base en formato INE, sin excluidos ni datos personales |
| `almacen/<carga>/bitacora.xlsx` | Hojas Resumen, Hallazgos, Cambios aplicados, Sugerencias y Excluidos |
| `almacen/<carga>/reporte.json` | Lo mismo en JSON, para el front |
| Base de datos | `carga`, `archivo`, `ejecucion`, `puntaje_dimension`, `hallazgo`, `correccion`, `registro_excluido`, `evento_auditoria` |

### Acciones y bitácora

- `auto_corregir`: cambia el valor y lo anota como cambio **aplicado**.
- `sugerir`: deja el valor original en la salida y anota un cambio **pendiente** con el código
  propuesto, su confianza y la justificación. Un cambio pendiente cubre todas las filas con el
  mismo texto (`registros_afectados`).
- `reportar`: solo hallazgo.
- `excluir`: saca los registros de la salida y los guarda agrupados por motivo en `registro_excluido`.

La estandarización masiva (texto → código por equivalencia, nulos textuales) se registra
agregada: una fila por valor distinto, no una por celda.

### Puntaje (0 a 100)

Por dimensión. Error pesa 1, advertencia 0.5, informativo 0.

- **Estructura:** 100 menos 15 por cada error y 5 por cada advertencia.
- **Reglas de columna** (genéricas): celdas afectadas ÷ (registros × columnas publicadas).
- **Reglas de registro** (específicas y llave única): registros afectados ÷ total.

El puntaje global es el promedio de las dimensiones que aplican a la base.

### Codificador

`qa/codificador.py` define la interfaz `sugerir(catalogo, textos) -> {texto: Sugerencia}`.
Hoy usa similitud de texto (`rapidfuzz`, distancia de edición): corrige errores de escritura
y variantes cercanas ("TENECIA DE DROGA" → 42 Tenencia de droga). Para municipios solo
busca dentro del departamento del registro. El codificador con IA tendrá la misma firma.

Las sugerencias de columnas `codificar_ia` se guardan en `equivalencia` sin aprobar, para
volver a mostrarlas en la siguiente carga.

## API para el front

### Levantarla sola

```bat
cd qa_bases_datos
copy .env.example .env        &REM y pon tu DATABASE_URL
pip install -r backend\requirements.txt
iniciar_api.bat
```

Queda en `http://localhost:8001`. En `http://localhost:8001/docs` está la documentación interactiva:
ahí se puede probar cada endpoint, subir un archivo y ver la respuesta, sin front.

### Integrarla a la app del transcriptor

Cuando el equipo lo decida, se agregan estas líneas en `app/main.py`, después de crear `app`,
y `DATABASE_URL` en el `.env` de la raíz. No cambia nada más de la app:

```python
import sys
sys.path.insert(0, str(BASE_DIR / "qa_bases_datos" / "backend"))
from qa.api import router as qa_router
app.include_router(qa_router)
```

Así el front del transcriptor y el de bases de datos usan el mismo servidor y el mismo puerto.

### Endpoints (`/api/qa`)

| Método | Ruta | Para qué |
| --- | --- | --- |
| GET | `/estado` | Si hay conexión a la base de datos |
| GET | `/bases` | Bases configuradas (para el selector al subir) |
| GET | `/bases/{codigo}` | Columnas y reglas de una base |
| POST | `/cargas` | Subir un archivo. Form: `file`, `base`, `anio`, `mes` (obligatorio si es mensual), `usuario` |
| GET | `/cargas` | Historial. Filtros: `base`, `estado`, `institucion`, `limite` |
| GET | `/cargas/{id}` | Estado, avance, puntajes y resumen. Se consulta cada segundo mientras procesa |
| GET | `/cargas/{id}/hallazgos` | Hallazgos. Filtros: `severidad`, `dimension`, `incluir_info` |
| GET | `/cargas/{id}/sugerencias` | Bandeja de sugerencias. `estado`: pendiente (por defecto), aplicada, rechazada, todas |
| GET | `/cargas/{id}/excluidos` | Registros excluidos, agrupados por motivo |
| GET | `/cargas/{id}/descargar/{rol}` | `corregido`, `bitacora` o `reporte`. El original no se descarga (trae datos personales) |
| POST | `/cargas/{id}/reprocesar` | Volver a validar con las sugerencias ya aprobadas |
| POST | `/cargas/{id}/aprobar` | El analista aprueba la carga. JSON: `{"usuario", "comentario"}` |
| POST | `/cargas/{id}/rechazar` | El analista la devuelve a la institución |
| POST | `/sugerencias/{id}/aprobar` | Aprobar. JSON: `{"usuario", "codigo"}`; `codigo` solo si se corrige la sugerencia |
| POST | `/sugerencias/{id}/rechazar` | Rechazar. JSON: `{"usuario", "comentario"}`. No se vuelve a proponer |
| GET | `/catalogos/{codigo}?q=` | Buscar en un catálogo (selector para corregir una sugerencia) |

### Flujo del front

1. `GET /bases` para el selector, luego `POST /cargas` con el archivo. Devuelve `carga_id`.
2. `GET /cargas/{id}` cada segundo. `avance.estado` pasa por `en_cola`, `procesando` (con `etapa` y
   `porcentaje` para la barra) y termina en `terminado` o `error`.
3. Con `terminado`: tarjetas con `puntaje`, `puntajes` por dimensión y `hallazgos_por_severidad`;
   tabla de `/hallazgos`; botones de descarga.
4. Bandeja `/sugerencias`: cada fila muestra el texto, el código y la etiqueta sugeridos, la confianza
   y cuántos registros cambian. Aprobar, corregir (con `/catalogos`) o rechazar.
5. `POST /reprocesar` aplica lo aprobado; el puntaje y los pendientes se actualizan.
6. El analista aprueba o rechaza la carga.

Lo aprobado queda como equivalencia de la institución: la siguiente carga de esa institución ya
viene codificada. Lo rechazado no se vuelve a sugerir.

**Pendiente:** autenticación. Por ahora `usuario` es un email opcional; sin él, las acciones quedan a
nombre del usuario del motor. Antes de producción hay que agregar login y permisos por rol.

## Resultados con los crudos reales

| Base | Recibidos | Válidos | Excluidos | Puntaje | Sugerencias | Tiempo |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Calidad del aire 2025 | 166,440 lecturas | 75,240 | 91,200 | 88.8 | 0 | 7 s |
| Defunciones julio 2026 | 10,034 | 8,841 | 1,193 | 97.8 | 751 | 7 s |
| Nacimientos junio 2026 | 30,093 | 22,515 | 7,578 | 96.9 | 0 | 5 s |
| Emergencias 2025 | 7,337 | 7,337 | 0 | 96.6 | 5 | 1 s |
| Detenidos octubre 2026 | 4,255 | 4,255 | 0 | 98.0 | 30 | 1 s |

### Comparación con lo publicado por el INE (`scripts/comparar_con_ine.py`)

- **Defunciones:** el motor conserva **exactamente los mismos 8,841 registros** que el INE
  (0 de diferencia). Excluye 1,098 defunciones ocurridas en otros años y 243 ocurridas fuera
  de Guatemala; esa segunda regla se dedujo de la comparación.
- **Calidad del aire:** en 11 de 19 combinaciones de estación y PM conserva los mismos meses.
  En las otras 8 la diferencia es de un mes y la decisión del INE no se explica con su propia
  regla: por ejemplo, excluyó mayo de Correos PM10 con solo 2 horas sin dato y conservó agosto
  de Salamá con 3 días inválidos. El motor aplica la regla igual en todos los casos.

### Hallazgos que vale la pena mostrar

- RENAP manda códigos de departamento y municipio que no existen ("0519", "0137", depto 43).
- 5,796 nacimientos (19 %) llegan sin departamento de ocurrencia (código -1).
- SECONRED: la columna de correlativo cambia de "No." a "#" desde septiembre y octubre llega vacía;
  valores "Todos" como municipio, "**" en conteos y caracteres dañados ("Vi±as" por "Viñas").
- PNC: 531 textos distintos de MOTIVO sin código; las sugerencias por similitud cubren las variantes
  cercanas y el resto queda para la IA.

## Configuración verificada con los crudos reales

- **Columnas reconocidas:** nacimientos 53/53, emergencias 24/24, detenidos 49/50
  (la que falta es `Unnamed: 49`, una columna sin nombre que se reporta) y defunciones 82/82.
- **Valores de texto cubiertos por equivalencias** (sin IA): sexo 100 %, escolaridad 100 %,
  sitio de nacimiento 100 %, día de la semana 100 %, estado civil 99.8–100 % (RENAP manda
  "N" en 75 nacimientos, un código que no está en el catálogo).
- **Lo que queda para la IA o para el INE:**
  - `MOTIVO` de PNC: solo 24.5 % de los registros coincide con una causa oficial; el resto
    son variantes ("LESIONES CULPOSAS EN HECHO DE TRANSITO", "PORTACION ILEGAL DE ARMA DE FUEGO").
  - Pueblo: "INDIGENA", "EXTRANJERO", "NEGRA" y "BLANCA" no tienen equivalente directo en el catálogo.
  - Tipo de inscripción: RENAP manda "Consular" (19 % de los nacimientos), un valor que el
    diccionario no tiene.

## Pendiente de confirmar con el INE

- Grupo de causa de 6 causas de PNC que no aparecen en la base publicada 2023:
  16 Autosecuestro, 34 Cobro ilegal de impuesto a buses, 37 Impuesto a negocios,
  38 En desalojos de fincas, 44 Siembra y cultivo de drogas, 63 Tenencia de licores clandestinos.
- Cómo codificar "Consular" en tipo de inscripción.
- Si existe un diccionario posterior a 2018-2022 (la publicación 2025 ya no trae ocupación).
- Cómo decide el INE los meses de calidad del aire que difieren de la regla de 4 horas y 2 días.
- Si "**" en los conteos de SECONRED significa "dato pendiente" o "confidencial".
