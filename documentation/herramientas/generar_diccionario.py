"""Genera documentation/diccionario-datos.md a partir de la configuración de Data Audit.

Lee data-audit/qa_bases_datos/backend/config (bases/*.yaml, catalogos.yaml y reglas.yaml),
la misma configuración que el motor carga en PostgreSQL. Así el diccionario no puede
desviarse de lo que el sistema valida.

    python documentation/herramientas/generar_diccionario.py
"""
from __future__ import annotations

import glob
from pathlib import Path

import yaml

RAIZ = Path(__file__).resolve().parents[2]
CONFIG = RAIZ / "data-audit/qa_bases_datos/backend/config"
SALIDA = RAIZ / "documentation/diccionario-datos.md"

DICC = {
    "dicc_defunciones": "Diccionario de defunciones 2018-2022 (INE)",
    "dicc_nacimientos": "Diccionario de nacimientos 2018-2022 (INE)",
    "dicc_pnc": "Diccionario de datos de Detenidos, PNC (INE)",
}
TIPOS = {"entero": "Entero", "decimal": "Decimal", "texto": "Texto", "codigo": "Código de catálogo",
         "fecha": "Fecha", "fecha_hora": "Fecha y hora", "hora": "Hora"}
INSTITUCION = {"DEFUNCIONES": "RENAP", "NACIMIENTOS": "RENAP", "DETENIDOS": "PNC",
               "CALIDAD_AIRE": "INSIVUMEH", "EMERGENCIAS": "SECONRED"}
PREFIJO_REGLAS = {"DEFUNCIONES": "DEF_", "NACIMIENTOS": "NAC_", "DETENIDOS": "PNC_",
                  "CALIDAD_AIRE": "AIRE_", "EMERGENCIAS": "EMERG_"}


def md(x) -> str:
    return str(x).replace("|", "\\|").replace("\n", " ")


def transformacion(t: dict | None) -> str:
    if not t:
        return "Se copia de la columna del crudo (por nombre o alias)."
    tipo = t.get("tipo")
    campo = t.get("campo") or ", ".join(t.get("campos", []) or [])
    textos = {
        "municipio_compuesto": f"Une departamento y municipio en el código DDMM ({campo}).",
        "parte_fecha": f"Extrae {t.get('parte')} de la fecha {campo}.",
        "parte_hora": f"Extrae la hora (0-23) de {campo}.",
        "agrupar_hora": f"Agrupa la hora de {campo} con cortes {t.get('cortes')}.",
        "agrupar_edad": f"Agrupa la edad de {campo} según los rangos del catálogo {t.get('catalogo')}.",
        "depto_de_municipio": f"Deriva el departamento de los dos primeros dígitos del municipio ({campo}).",
        "rellenar_ceros": f"Rellena con ceros a la izquierda hasta {t.get('largo')} dígitos ({campo}).",
        "padre_catalogo": f"Toma el grupo (código padre) de {campo} en el catálogo {t.get('catalogo')}.",
        "etiqueta_catalogo": f"Escribe la etiqueta oficial del código de {campo}.",
        "mapa": f"Traduce valores de {campo}: {t.get('valores')}.",
        "constante": f"Valor fijo: {t.get('valor')}.",
        "vacio_como": f"Si viene vacío se registra como {t.get('valor')!r}.",
        "codificar_texto": f"Convierte el texto de {campo} al código del catálogo {t.get('catalogo')} por equivalencias y similitud.",
        "codificar_ia": f"Codifica el texto libre de {campo} al catálogo {t.get('catalogo')} con similitud de texto e IA; queda como sugerencia pendiente de aprobación.",
    }
    return textos.get(tipo, f"{tipo}: {t}")


def valores_permitidos(v: dict, catalogos: dict) -> str:
    cat = v.get("catalogo")
    if not cat:
        partes = []
        if "min" in v or "max" in v:
            partes.append(f"{v.get('min', '−∞')} a {v.get('max', '∞')}")
        if v.get("regex"):
            partes.append(f"patrón `{v['regex']}`")
        return "; ".join(partes) or "Libre"
    c = catalogos.get(cat, {})
    if "valores" in c:
        codigos = [f"{x['codigo']}={x['etiqueta']}" for x in c["valores"]]
        lista = ", ".join(codigos[:12]) + (f" y {len(codigos) - 12} más" if len(codigos) > 12 else "")
        return f"Catálogo **{cat}** ({md(c.get('nombre', ''))}): {md(lista)}"
    if "cie10" in c:
        return f"Catálogo **{cat}**: CIE-10 completa (hoja «CIE-10» del diccionario de defunciones)"
    fuentes = "; ".join(f"{DICC.get(a, a)}, variable «{b}»" for a, b in c.get("diccionario", []))
    return f"Catálogo **{cat}** ({md(c.get('nombre', ''))}), códigos de: {md(fuentes)}"


def nulos(v: dict, catalogos: dict, t: dict | None) -> str:
    ign = v.get("ignorado") or (catalogos.get(v.get("catalogo"), {}).get("ignorado") or [None])[0]
    if t and t.get("tipo") == "vacio_como":
        return f"Vacío → {t.get('valor')!r}"
    base = "Obligatorio: vacío es error" if v.get("requerida") else "Vacío permitido (advertencia)"
    return base + (f"; código «sin dato»: {ign}" if ign else "")


def reglas_variable(v: dict) -> str:
    r = []
    if v.get("requerida"):
        r.append("GEN_REQUERIDA")
    if v.get("tipo") in ("entero", "decimal", "fecha", "fecha_hora") and not v.get("catalogo"):
        r.append("GEN_TIPO")
    if v.get("catalogo"):
        ia = (v.get("transformacion") or {}).get("tipo") == "codificar_ia"
        r.append("GEN_CODIFICACION_IA" if ia else "GEN_CATALOGO, GEN_CODIFICACION")
    if "min" in v or "max" in v:
        r.append("GEN_RANGO")
    if v.get("regex"):
        r.append("GEN_FORMATO")
    r.append("GEN_SIN_DATO")
    return ", ".join(r)


def main() -> None:
    catalogos = yaml.safe_load((CONFIG / "catalogos.yaml").read_text(encoding="utf-8"))["catalogos"]
    reglas = yaml.safe_load((CONFIG / "reglas.yaml").read_text(encoding="utf-8"))["reglas"]
    out = [
        "# Diccionario de datos",
        "",
        "> Generado con `python documentation/herramientas/generar_diccionario.py` a partir de la configuración",
        "> que el motor de Data Audit carga en PostgreSQL (`data-audit/qa_bases_datos/backend/config`).",
        "> No edites este archivo a mano: cambia el YAML y vuelve a generarlo.",
        "",
        "Las variables, etiquetas y códigos son los de los diccionarios y bases publicadas del INE. Quality Audit",
        "no redefine ningún código: cuando una institución envía texto («MASCULINO») o un código propio, el",
        "sistema lo convierte al código oficial solo por una equivalencia aprobada o una sugerencia que un",
        "analista aprueba. Las fuentes de cada base están en [Fuentes de datos](data-sources.md).",
        "",
        "## Cómo leer las tablas",
        "",
        "| Atributo | Significado |",
        "|---|---|",
        "| Variable | Nombre oficial publicado por el INE (columna de la base corregida) |",
        "| Descripción | Etiqueta oficial de la variable |",
        "| Tipo | Tipo de dato que valida el motor |",
        "| Valores permitidos | Catálogo oficial o rango / patrón |",
        "| Nulos | Tratamiento del dato faltante |",
        "| Transformación | Cómo se obtiene desde el crudo de la institución |",
        "| Reglas | Validaciones que se aplican (ver [catálogo de reglas](#catálogo-de-reglas)) |",
        "",
        "Además de las reglas de cada fila, a todas las columnas se aplican `GEN_NULO_TEXTUAL` (textos como «N.D.»",
        "o «-1» que significan sin dato) y `GEN_ESPACIOS`, y a la tabla completa las reglas de estructura y la llave única.",
        "",
    ]
    for f in sorted(glob.glob(str(CONFIG / "bases/*.yaml"))):
        d = yaml.safe_load(Path(f).read_text(encoding="utf-8"))
        base = d["base"]
        out += [f"## {base} — {INSTITUCION.get(base, '')}", "",
                f"- **Fuente de la estructura y códigos:** {md(d.get('fuente', ''))}",
                f"- **Versión de la definición:** {d.get('version')} (vigente desde {d.get('vigente_desde')})",
                f"- **Llave para detectar duplicados:** {', '.join(map(str, d.get('llave', [])))}"]
        if d.get("formato_crudo"):
            out.append(f"- **Formato del crudo:** `{d['formato_crudo']}`")
        out += [f"- **Variables publicadas:** {len(d['variables'])}", "",
                "| Variable | Descripción | Tipo | Valores permitidos | Nulos | Transformación | Reglas |",
                "|---|---|---|---|---|---|---|"]
        for v in d["variables"]:
            t = v.get("transformacion")
            alias = f" Alias en el crudo: {', '.join(map(str, v['alias']))}." if v.get("alias") else ""
            out.append("| " + " | ".join([
                f"`{md(v['nombre'])}`", md(v.get("etiqueta", "")), TIPOS.get(v.get("tipo"), v.get("tipo")),
                valores_permitidos(v, catalogos), nulos(v, catalogos, t), md(transformacion(t) + alias), reglas_variable(v),
            ]) + " |")
        propias = [(k, r) for k, r in reglas.items() if k.startswith(PREFIJO_REGLAS.get(base, "#"))]
        if propias:
            out += ["", "Reglas propias de la base: " + "; ".join(f"`{k}` ({md(r['nombre'])})" for k, r in propias) + f"; `{base}_LLAVE_UNICA` (registro duplicado)."]
        if d.get("auxiliares"):
            out += ["", "Columnas auxiliares del crudo (se usan para calcular o validar y **no se publican**): "
                    + ", ".join(f"`{md(a['nombre'])}`" for a in d["auxiliares"]) + "."]
        if d.get("pii"):
            out += ["", f"Columnas con datos personales que se **eliminan** del archivo corregido ({len(d['pii'])}): "
                    + ", ".join(f"`{md(p)}`" for p in d["pii"]) + "."]
        out.append("")
    out += ["## Catálogos", "", "| Catálogo | Nombre | Origen de los códigos | Código «sin dato» |", "|---|---|---|---|"]
    for k, c in catalogos.items():
        if "valores" in c:
            origen = f"Definido en `catalogos.yaml` desde la base publicada ({len(c['valores'])} códigos)"
        elif "cie10" in c:
            origen = "Hoja CIE-10 del diccionario de defunciones"
        else:
            origen = "; ".join(f"{DICC.get(a, a)} — «{b}»" for a, b in c.get("diccionario", []))
        out.append(f"| `{k}` | {md(c.get('nombre', ''))} | {md(origen)} | {', '.join(c.get('ignorado') or []) or '—'} |")
    out += ["", "## Catálogo de reglas", "",
            "Severidad: `error` pesa 1, `advertencia` 0.5 e `info` 0 en el puntaje. Acción: `auto_corregir` cambia el valor y lo anota;",
            "`sugerir` propone un código pendiente de aprobación; `reportar` solo avisa; `excluir` saca el registro de la base publicable.",
            "", "| Regla | Nombre | Dimensión | Severidad | Acción |", "|---|---|---|---|---|"]
    for k, r in reglas.items():
        out.append(f"| `{k}` | {md(r['nombre'])} | {r['dimension']} | {r['severidad']} | {r['accion']} |")
    out.append("| `<BASE>_LLAVE_UNICA` | Registro duplicado por la llave de la base (una regla por base) | unicidad | error | reportar |")
    out += ["", "## Variables de Survey Audit y Audio Audit", "",
            "Survey Audit no usa un diccionario fijo: las variables (preguntas) se generan del cuestionario PDF que se sube",
            "y se revisan en el editor; su estructura está en [Metodología](methodology.md#survey-audit-captura-validada). Audio Audit evalúa",
            "51 reglas del Manual del Encuestador ENCOVI 2023 (`audio-audit/encovi_jev/rules_a1_a2.py`, guía en",
            "`audio-audit/encovi_jev/GUIDE_JEV_QUESTIONS.md`).",
            "",
            "**No implementado:** el proyecto no carga los diccionarios de hogares y personas de ENCOVI para validar",
            "respuestas contra catálogos externos; las opciones válidas de cada pregunta salen del propio cuestionario.", ""]
    SALIDA.write_text("\n".join(out), encoding="utf-8")
    print("escrito", SALIDA, len(out), "líneas")


if __name__ == "__main__":
    main()
