"""Genera documentation/api-referencia.md desde el esquema OpenAPI de la API unificada.

La lista de rutas, parámetros y cuerpos sale de la propia aplicación FastAPI
(plataforma/app.py), así que coincide con lo desplegado.

    python documentation/herramientas/generar_api.py
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ))
for var in ("SUPABASE_URL", "SUPABASE_ANON_KEY", "SUPABASE_SERVICE_ROLE_KEY"):
    os.environ.pop(var, None)

from plataforma.app import app  # noqa: E402

SALIDA = RAIZ / "documentation/api-referencia.md"
MODULOS = [
    ("/api/qa", "Data Audit"),
    ("/api/surveys", "Survey Audit"),
    ("/api/improvement", "Quality Improvement"),
    ("/api", "Audio Audit y plataforma"),
]
ESTADOS = {"200": "OK", "201": "Creado", "204": "Sin contenido", "307": "Redirección",
           "422": "Datos no válidos"}


def md(x) -> str:
    return str(x).replace("|", "\\|").replace("\n", " ").strip()


def resolver(esquema: dict, spec: dict) -> dict:
    while "$ref" in esquema:
        nombre = esquema["$ref"].split("/")[-1]
        esquema = spec["components"]["schemas"][nombre]
    return esquema


def tipo(esquema: dict, spec: dict) -> str:
    esquema = resolver(esquema, spec)
    if "anyOf" in esquema:
        return " o ".join(sorted({tipo(x, spec) for x in esquema["anyOf"]}))
    t = esquema.get("type", "objeto")
    if t == "array":
        return f"lista de {tipo(esquema.get('items', {}), spec)}"
    if "enum" in esquema:
        return f"{t} ({' / '.join(map(str, esquema['enum']))})"
    return {"string": "texto", "integer": "entero", "number": "número", "boolean": "sí/no",
            "object": "objeto", "null": "nulo"}.get(t, t)


def restricciones(esquema: dict) -> str:
    partes = []
    for k, n in (("minLength", "mín. caracteres"), ("maxLength", "máx. caracteres"), ("minimum", "mín."),
                 ("maximum", "máx."), ("exclusiveMinimum", "mayor que"), ("pattern", "patrón")):
        if k in esquema:
            partes.append(f"{n} {esquema[k]}")
    for x in esquema.get("anyOf", []):
        partes += [p for p in restricciones(x).split("; ") if p]
    if "default" in esquema:
        partes.append(f"por defecto {esquema['default']!r}")
    return "; ".join(dict.fromkeys(partes))


def tabla_campos(esquema: dict, spec: dict) -> list[str]:
    esquema = resolver(esquema, spec)
    props = esquema.get("properties", {})
    if not props:
        return [f"Cuerpo: {tipo(esquema, spec)}."]
    req = set(esquema.get("required", []))
    filas = ["| Campo | Tipo | Obligatorio | Validación |", "|---|---|---|---|"]
    for k, v in props.items():
        filas.append(f"| `{k}` | {md(tipo(v, spec))} | {'sí' if k in req else 'no'} | {md(restricciones(resolver(v, spec)) or '—')} |")
    return filas


def modulo(ruta: str) -> str:
    for prefijo, nombre in MODULOS:
        if ruta.startswith(prefijo):
            return nombre
    return "Otros"


def main() -> None:
    spec = app.openapi()
    grupos: dict[str, list] = {}
    for ruta, ops in spec["paths"].items():
        for metodo, op in ops.items():
            grupos.setdefault(modulo(ruta), []).append((ruta, metodo.upper(), op))
    out = ["# Referencia de la API", "",
           "> Generado con `python documentation/herramientas/generar_api.py` desde el esquema OpenAPI de",
           "> `plataforma/app.py`. Las convenciones (autenticación, errores, ejemplos) están en",
           "> [integration-api.md](integration-api.md).", "",
           f"Total: **{sum(len(v) for v in grupos.values())} operaciones** en {len(spec['paths'])} rutas.", ""]
    orden = [n for _, n in MODULOS] + ["Otros"]
    out += ["## Índice", ""] + [f"- [{n}](#{n.lower().replace(' ', '-')}) ({len(grupos[n])})" for n in orden if n in grupos] + [""]
    for nombre in orden:
        if nombre not in grupos:
            continue
        out += [f"## {nombre}", "", "| Método | Ruta | Función |", "|---|---|---|"]
        lista = sorted(grupos[nombre], key=lambda x: (x[0], x[1]))
        for ruta, metodo, op in lista:
            resumen = (op.get("description") or op.get("summary") or "").strip().split("\n")[0]
            out.append(f"| {metodo} | `{ruta}` | {md(resumen)} |")
        out.append("")
        for ruta, metodo, op in lista:
            out += [f"### {metodo} `{ruta}`", ""]
            desc = (op.get("description") or op.get("summary") or "").strip()
            if desc:
                out += [desc, ""]
            params = op.get("parameters", [])
            if params:
                out += ["| Parámetro | En | Tipo | Obligatorio | Validación |", "|---|---|---|---|---|"]
                for p in params:
                    esq = p.get("schema", {})
                    lugar = {"path": "ruta", "query": "consulta", "header": "encabezado"}.get(p["in"], p["in"])
                    out.append(f"| `{p['name']}` | {lugar} | {md(tipo(esq, spec))} | {'sí' if p.get('required') else 'no'} | {md(restricciones(esq) or '—')} |")
                out.append("")
            cuerpo = op.get("requestBody", {}).get("content", {})
            for formato, c in cuerpo.items():
                out += [f"Solicitud (`{formato}`):", ""] + tabla_campos(c.get("schema", {}), spec) + [""]
            codigos = ", ".join(f"{k} {ESTADOS.get(k, '')}".strip() for k in op.get("responses", {}))
            out += [f"Respuestas documentadas: {codigos}. Errores comunes: 401 sin sesión, 404 no existe, 409 estado no permite la acción, 422 datos no válidos, 503 servicio externo ocupado.", ""]
    SALIDA.write_text("\n".join(out), encoding="utf-8")
    print("escrito", SALIDA, sum(len(v) for v in grupos.values()), "operaciones")


if __name__ == "__main__":
    main()
