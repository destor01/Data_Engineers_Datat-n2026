"""Carga la configuración de Quality Audit en PostgreSQL.

Lee los diccionarios oficiales del INE (.xlsx) y los YAML de config/ y llena:
catalogo, catalogo_valor, equivalencia, version_esquema, variable,
alias_columna y las reglas de llave única.

Se puede correr las veces que sea necesario: actualiza lo que ya existe.

Uso:
    python -m scripts.cargar_config \
        --db postgresql://usuario:clave@localhost:5432/quality_audit \
        --dicc-defunciones diccionario-defunciones-2018-2022.xlsx \
        --dicc-nacimientos diccionario-nacimientos-2018-2022.xlsx \
        --dicc-pnc diccionario-detenidos-pnc.xlsx

Si no se pasa --db se usa la variable de entorno DATABASE_URL.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

import openpyxl
import psycopg
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from qa.texto import codigo_texto, es_ignorado, normalizar  # noqa: E402

CONFIG = Path(__file__).resolve().parents[1] / "config"
TIPOS_VALIDOS = {"entero", "decimal", "texto", "fecha", "hora", "fecha_hora", "codigo", "booleano"}


# ---------------------------------------------------------------------------
# Lectura de diccionarios
# ---------------------------------------------------------------------------
def leer_diccionario(ruta: Path) -> dict[str, list[tuple[str, str]]]:
    """Devuelve {etiqueta de variable: [(código, etiqueta), ...]} de la primera hoja.

    Los diccionarios del INE tienen tres columnas: Valor | Código | Etiqueta, con
    "Valor" escrito solo en la primera fila de cada variable. La fila de
    encabezado no siempre es la misma (PNC la tiene en la fila 4), así que se busca.
    """
    hoja = openpyxl.load_workbook(ruta, read_only=True, data_only=True).worksheets[0]
    filas = list(hoja.iter_rows(values_only=True))
    for i, fila in enumerate(filas[:15]):
        celdas = [normalizar(c) for c in fila]
        if "VALOR" in celdas and "ETIQUETA" in celdas:
            c_valor = celdas.index("VALOR")
            c_codigo = next(j for j, c in enumerate(celdas) if c.startswith("CODIGO"))
            c_etiqueta = celdas.index("ETIQUETA")
            break
    else:
        raise ValueError(f"{ruta.name}: no encontré la fila Valor | Código | Etiqueta")

    resultado: dict[str, list[tuple[str, str]]] = defaultdict(list)
    actual = None
    for fila in filas[i + 1:]:
        if c_valor < len(fila) and fila[c_valor] not in (None, ""):
            actual = str(fila[c_valor]).strip()
        codigo = codigo_texto(fila[c_codigo]) if c_codigo < len(fila) else None
        etiqueta = fila[c_etiqueta] if c_etiqueta < len(fila) else None
        if actual and codigo is not None and etiqueta not in (None, ""):
            resultado[actual].append((codigo, str(etiqueta).strip()))
    return dict(resultado)


def leer_cie10(ruta: Path, nombre_hoja: str) -> list[tuple[str, str]]:
    hoja = openpyxl.load_workbook(ruta, read_only=True, data_only=True)[nombre_hoja]
    salida, en_datos = [], False
    for fila in hoja.iter_rows(values_only=True):
        if not en_datos:
            en_datos = normalizar(fila[0]).startswith("CODIGO CIE")
            continue
        codigo, desc = codigo_texto(fila[0]), fila[1]
        if codigo and desc:
            salida.append((codigo.upper(), str(desc).strip()))
    return salida


# ---------------------------------------------------------------------------
# Construcción de catálogos en memoria
# ---------------------------------------------------------------------------
@dataclass
class Catalogo:
    codigo: str
    nombre: str
    fuente: str
    valores: dict[str, dict] = field(default_factory=dict)       # código -> {etiqueta, padre, ignorado}
    equivalencias: dict[str, tuple[str, str]] = field(default_factory=dict)  # texto -> (código, fuente)


def buscar_variable(dicc: dict, etiqueta: str, archivo: str) -> list[tuple[str, str]]:
    if etiqueta in dicc:
        return dicc[etiqueta]
    objetivo = normalizar(etiqueta)
    for k, v in dicc.items():
        if normalizar(k) == objetivo:
            return v
    raise KeyError(f"La variable '{etiqueta}' no está en {archivo}")


def armar_catalogos(cfg: dict, diccs: dict, rutas: dict, avisos: list[str]) -> dict[str, Catalogo]:
    catalogos: dict[str, Catalogo] = {}
    for codigo, c in cfg["catalogos"].items():
        cat = Catalogo(codigo, c["nombre"], "")
        ceros = c.get("rellenar_ceros")

        if "diccionario" in c:
            fuentes = []
            for archivo, etiqueta_var in c["diccionario"]:
                fuentes.append(f"{Path(rutas[archivo]).name} / {etiqueta_var}")
                for cod, etq in buscar_variable(diccs[archivo], etiqueta_var, archivo):
                    cod = codigo_texto(cod, ceros) or cod
                    if codigo == "MUNICIPIO" and cod.isdigit():
                        cod = cod.zfill(4)
                    if cod not in cat.valores:
                        cat.valores[cod] = {"etiqueta": etq, "padre": None, "ignorado": es_ignorado(etq)}
                    elif normalizar(cat.valores[cod]["etiqueta"]) != normalizar(etq):
                        # Misma clave, otra etiqueta ("Soltero" / "Soltera"): queda como equivalencia
                        cat.equivalencias.setdefault(normalizar(etq), (cod, "diccionario"))
            cat.fuente = "; ".join(fuentes)

        elif "cie10" in c:
            archivo, hoja = c["cie10"]
            for cod, desc in leer_cie10(Path(rutas[archivo]), hoja):
                cat.valores[cod] = {"etiqueta": desc, "padre": None, "ignorado": False}
            cat.fuente = f"{Path(rutas[archivo]).name} / hoja {hoja}"

        elif "valores" in c:
            for v in c["valores"]:
                cat.valores[str(v["codigo"])] = {
                    "etiqueta": str(v["etiqueta"]),
                    "padre": str(v["padre"]) if v.get("padre") is not None else None,
                    "ignorado": False,
                }
            cat.fuente = "config/catalogos.yaml"

        # Códigos de "sin dato" que el diccionario no trae
        for ign in c.get("ignorado", []):
            ign = str(ign)
            if ign in cat.valores:
                cat.valores[ign]["ignorado"] = True
            else:
                cat.valores[ign] = {"etiqueta": "Ignorado", "padre": None, "ignorado": True}

        # Jerarquías
        padre = c.get("padre")
        if padre == "departamento_por_prefijo":
            for cod, v in cat.valores.items():
                if len(cod) == 4 and cod.isdigit():
                    v["padre"] = "99" if cod == "9999" else str(int(cod[:2]))
        elif padre == "cie10_categoria":
            for cod, v in cat.valores.items():
                if len(cod) > 3:
                    v["padre"] = cod[:3]
        for padre_cod, hijos in (c.get("padres") or {}).items():
            for h in hijos:
                if str(h) in cat.valores:
                    cat.valores[str(h)]["padre"] = str(padre_cod)
                else:
                    avisos.append(f"{codigo}: el código {h} de 'padres' no existe en el catálogo")

        for texto, cod in (c.get("equivalencias") or {}).items():
            cat.equivalencias[normalizar(texto)] = (str(cod), "manual")

        catalogos[codigo] = cat

    # Equivalencias observadas en los crudos
    for codigo, mapa in (cfg.get("equivalencias") or {}).items():
        if codigo not in catalogos:
            avisos.append(f"equivalencias: el catálogo {codigo} no existe")
            continue
        for texto, cod in mapa.items():
            cod = str(cod)
            if cod not in catalogos[codigo].valores:
                avisos.append(f"equivalencias {codigo}: '{texto}' apunta a {cod}, que no existe")
                continue
            catalogos[codigo].equivalencias[normalizar(texto)] = (cod, "manual")
    return catalogos


# ---------------------------------------------------------------------------
# Escritura en PostgreSQL
# ---------------------------------------------------------------------------
def guardar_catalogos(cur, catalogos: dict[str, Catalogo]) -> dict[str, int]:
    ids = {}
    for cat in catalogos.values():
        cur.execute(
            """INSERT INTO catalogo (codigo, nombre, fuente) VALUES (%s, %s, %s)
               ON CONFLICT (codigo) DO UPDATE SET nombre = EXCLUDED.nombre, fuente = EXCLUDED.fuente
               RETURNING id""",
            (cat.codigo, cat.nombre, cat.fuente),
        )
        cid = cur.fetchone()[0]
        ids[cat.codigo] = cid
        cur.executemany(
            """INSERT INTO catalogo_valor (catalogo_id, codigo, etiqueta, padre_codigo, es_ignorado)
               VALUES (%s, %s, %s, %s, %s)
               ON CONFLICT (catalogo_id, codigo) DO UPDATE SET
                 etiqueta = EXCLUDED.etiqueta, padre_codigo = EXCLUDED.padre_codigo,
                 es_ignorado = EXCLUDED.es_ignorado, activo = TRUE""",
            [(cid, cod, v["etiqueta"], v["padre"], v["ignorado"]) for cod, v in cat.valores.items()],
        )

        # Cada etiqueta oficial es también una equivalencia aprobada: "MASCULINO" no,
        # pero "HOMBRE" -> 1 sí sale del diccionario. Las de YAML pisan a estas.
        equiv = {normalizar(v["etiqueta"]): (cod, "diccionario") for cod, v in cat.valores.items()}
        if cat.codigo == "CIE10":
            equiv = {}  # 14 mil descripciones largas: el CIE-10 se codifica con IA, no por texto exacto
        equiv.update(cat.equivalencias)
        cur.executemany(
            """INSERT INTO equivalencia (catalogo_id, institucion_id, texto_origen, codigo, fuente, aprobada)
               VALUES (%s, NULL, %s, %s, %s, TRUE)
               ON CONFLICT (catalogo_id, institucion_id, texto_origen) DO UPDATE SET
                 codigo = EXCLUDED.codigo, fuente = EXCLUDED.fuente, aprobada = TRUE
               WHERE equivalencia.fuente <> 'ia'""",
            [(cid, texto, cod, fuente) for texto, (cod, fuente) in equiv.items() if texto],
        )
    return ids


def rango_desde_diccionario(diccs, archivo, etiqueta) -> tuple[float | None, float | None, str | None]:
    numeros, ignorado = [], None
    for cod, etq in buscar_variable(diccs[archivo], etiqueta, archivo):
        if es_ignorado(etq):
            ignorado = cod
        elif cod.lstrip("-").isdigit():
            numeros.append(int(cod))
    return (min(numeros) if numeros else None, max(numeros) if numeros else None, ignorado)


def guardar_base(cur, ruta_yaml: Path, diccs, cat_ids, avisos) -> tuple[str, int]:
    b = yaml.safe_load(ruta_yaml.read_text(encoding="utf-8"))
    cur.execute("SELECT id FROM tipo_base WHERE codigo = %s", (b["base"],))
    fila = cur.fetchone()
    if not fila:
        raise ValueError(f"{ruta_yaml.name}: el tipo_base {b['base']} no existe (¿corriste schema.sql?)")
    tipo_base_id = fila[0]

    cur.execute("UPDATE version_esquema SET activa = FALSE WHERE tipo_base_id = %s AND version <> %s",
                (tipo_base_id, str(b["version"])))
    cur.execute(
        """INSERT INTO version_esquema (tipo_base_id, version, vigente_desde, activa, fuente, formato_crudo)
           VALUES (%s, %s, %s, TRUE, %s, %s)
           ON CONFLICT (tipo_base_id, version) DO UPDATE SET
             vigente_desde = EXCLUDED.vigente_desde, activa = TRUE,
             fuente = EXCLUDED.fuente, formato_crudo = EXCLUDED.formato_crudo
           RETURNING id""",
        (tipo_base_id, str(b["version"]), b.get("vigente_desde"), b.get("fuente"),
         json.dumps(b.get("formato_crudo"), ensure_ascii=False) if b.get("formato_crudo") else None),
    )
    version_id = cur.fetchone()[0]
    # Las variables de una versión se reescriben completas (borra alias y reglas ligadas en cascada)
    cur.execute("DELETE FROM variable WHERE version_esquema_id = %s", (version_id,))

    filas = []
    for v in b.get("variables", []):
        filas.append({**v, "publica": v.get("publica", True), "pii": False})
    for v in b.get("auxiliares", []):
        filas.append({**v, "publica": False, "pii": False, "alias": [v["nombre"]]})
    for nombre in b.get("pii", []):
        filas.append({"nombre": nombre, "etiqueta": "Dato personal: se elimina al publicar", "tipo": "texto",
                      "publica": False, "pii": True, "alias": [nombre]})

    alias_vistos: dict[str, str] = {}
    for orden, v in enumerate(filas, start=1):
        tipo = v.get("tipo", "texto")
        if tipo not in TIPOS_VALIDOS:
            raise ValueError(f"{ruta_yaml.name}: {v['nombre']} tiene tipo inválido '{tipo}'")
        catalogo_id = None
        if v.get("catalogo"):
            if v["catalogo"] not in cat_ids:
                raise ValueError(f"{ruta_yaml.name}: {v['nombre']} usa el catálogo {v['catalogo']}, que no existe")
            catalogo_id = cat_ids[v["catalogo"]]
        vmin, vmax, ign = v.get("min"), v.get("max"), v.get("ignorado")
        if v.get("rango_de"):
            dmin, dmax, dign = rango_desde_diccionario(diccs, *v["rango_de"])
            vmin = vmin if vmin is not None else dmin
            vmax = vmax if vmax is not None else dmax
            ign = ign if ign is not None else dign

        cur.execute(
            """INSERT INTO variable (version_esquema_id, nombre_ine, etiqueta, tipo, catalogo_id, requerida,
                                     valor_min, valor_max, patron_regex, codigo_ignorado, es_pii, se_publica,
                                     transformacion, orden)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING id""",
            (version_id, v["nombre"], v.get("etiqueta") or v["nombre"], tipo, catalogo_id,
             bool(v.get("requerida")), vmin, vmax, v.get("regex"),
             str(ign) if ign is not None else None, v["pii"], v["publica"],
             json.dumps(v["transformacion"], ensure_ascii=False) if v.get("transformacion") else None, orden),
        )
        var_id = cur.fetchone()[0]

        # El propio nombre del INE también es alias: un archivo ya en formato INE se reconoce solo
        alias = {normalizar(a) for a in (v.get("alias") or [])} | {normalizar(v["nombre"])}
        for a in sorted(alias):
            if not a:
                continue
            if a in alias_vistos and alias_vistos[a] != v["nombre"]:
                avisos.append(f"{b['base']}: el alias '{a}' está en {alias_vistos[a]} y en {v['nombre']}")
                continue
            alias_vistos[a] = v["nombre"]
            cur.execute("INSERT INTO alias_columna (variable_id, alias) VALUES (%s, %s) ON CONFLICT DO NOTHING",
                        (var_id, a))

    # Regla de llave única de la base
    if b.get("llave"):
        cur.execute(
            """INSERT INTO regla (tipo_base_id, codigo, nombre, descripcion, dimension, severidad, accion, parametros)
               VALUES (%s, %s, %s, %s, 'unicidad', 'error', 'reportar', %s)
               ON CONFLICT (codigo) DO UPDATE SET parametros = EXCLUDED.parametros""",
            (tipo_base_id, f"{b['base']}_LLAVE_UNICA", "Registro duplicado",
             "{n} registros repiten la llave " + ", ".join(b["llave"]) + " ({detalle}).",
             json.dumps({"columnas": b["llave"]}, ensure_ascii=False)),
        )
    return b["base"], len(filas)


def guardar_reglas(cur, ruta: Path) -> int:
    """Crea o actualiza las reglas de reglas.yaml. 'descripcion' guarda la plantilla del mensaje."""
    reglas = yaml.safe_load(ruta.read_text(encoding="utf-8"))["reglas"]
    for codigo, r in reglas.items():
        tipo_base_id = None
        if r.get("base"):
            cur.execute("SELECT id FROM tipo_base WHERE codigo = %s", (r["base"],))
            fila = cur.fetchone()
            if not fila:
                raise ValueError(f"reglas.yaml: {codigo} usa la base {r['base']}, que no existe")
            tipo_base_id = fila[0]
        cur.execute(
            """INSERT INTO regla (tipo_base_id, codigo, nombre, descripcion, dimension, severidad, accion, parametros)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
               ON CONFLICT (codigo) DO UPDATE SET
                 tipo_base_id = EXCLUDED.tipo_base_id, nombre = EXCLUDED.nombre,
                 descripcion = EXCLUDED.descripcion, dimension = EXCLUDED.dimension,
                 severidad = EXCLUDED.severidad, accion = EXCLUDED.accion, parametros = EXCLUDED.parametros""",
            (tipo_base_id, codigo, r["nombre"], r.get("mensaje"), r["dimension"], r["severidad"], r["accion"],
             json.dumps(r.get("parametros") or {}, ensure_ascii=False)),
        )
    return len(reglas)


# ---------------------------------------------------------------------------
def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--db", default=os.environ.get("DATABASE_URL"))
    ap.add_argument("--dicc-defunciones", required=True, type=Path)
    ap.add_argument("--dicc-nacimientos", required=True, type=Path)
    ap.add_argument("--dicc-pnc", required=True, type=Path)
    ap.add_argument("--config", type=Path, default=CONFIG)
    args = ap.parse_args()
    if not args.db:
        ap.error("falta --db o la variable DATABASE_URL")

    rutas = {"dicc_defunciones": args.dicc_defunciones,
             "dicc_nacimientos": args.dicc_nacimientos,
             "dicc_pnc": args.dicc_pnc}
    print("Leyendo diccionarios...")
    diccs = {k: leer_diccionario(p) for k, p in rutas.items()}
    for k, d in diccs.items():
        print(f"  {k}: {len(d)} variables")

    avisos: list[str] = []
    cfg = yaml.safe_load((args.config / "catalogos.yaml").read_text(encoding="utf-8"))
    catalogos = armar_catalogos(cfg, diccs, rutas, avisos)

    with psycopg.connect(args.db, prepare_threshold=None) as con, con.cursor() as cur:
        cat_ids = guardar_catalogos(cur, catalogos)
        print(f"Catálogos: {len(cat_ids)}")
        n_reglas = guardar_reglas(cur, args.config / "reglas.yaml")
        print(f"Reglas: {n_reglas}")
        for ruta in sorted((args.config / "bases").glob("*.yaml")):
            base, n = guardar_base(cur, ruta, diccs, cat_ids, avisos)
            print(f"  {base}: {n} variables")
        con.commit()

        cur.execute("""SELECT
            (SELECT count(*) FROM catalogo), (SELECT count(*) FROM catalogo_valor),
            (SELECT count(*) FROM equivalencia), (SELECT count(*) FROM version_esquema WHERE activa),
            (SELECT count(*) FROM variable), (SELECT count(*) FROM alias_columna), (SELECT count(*) FROM regla)""")
        r = cur.fetchone()
        print("\nEn la base de datos:")
        for nombre, n in zip(["catalogo", "catalogo_valor", "equivalencia", "version_esquema (activas)",
                              "variable", "alias_columna", "regla"], r):
            print(f"  {nombre:28} {n:>7,}")

    if avisos:
        print(f"\n{len(avisos)} avisos:")
        for a in avisos:
            print("  -", a)


if __name__ == "__main__":
    main()
