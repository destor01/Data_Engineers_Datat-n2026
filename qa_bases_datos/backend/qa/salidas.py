"""Salidas del motor: archivos para la institución y filas en la base de datos.

Archivos (una carpeta por carga):
  original.<ext>          copia del archivo recibido (contiene datos personales: proteger)
  corregido.xlsx          base en formato INE, sin excluidos ni datos personales
  bitacora.xlsx           Resumen, Hallazgos, Cambios, Sugerencias y Excluidos
  reporte.json            lo mismo en JSON, para el front
"""
from __future__ import annotations

import hashlib
import json
import shutil
from datetime import date, datetime, time
from pathlib import Path

import pandas as pd

from .definicion import DefinicionBase
from .motor import Resultado
from .texto import normalizar

NOMBRE_DIMENSION = {
    "estructura": "Estructura", "completitud": "Completitud", "validez": "Validez",
    "consistencia": "Consistencia", "unicidad": "Unicidad", "oportunidad": "Oportunidad",
    "representatividad": "Representatividad",
}
ORDEN_SEVERIDAD = {"error": 0, "advertencia": 1, "info": 2}


def _json(v):
    if isinstance(v, (datetime, date, time, pd.Timestamp)):
        return v.isoformat()
    if hasattr(v, "item"):
        return v.item()
    return str(v)


def mensaje(d: DefinicionBase, h: dict) -> str:
    regla = d.reglas[h["regla"]]
    plantilla = regla.mensaje or regla.nombre
    try:
        return plantilla.format(n=f"{h['n']:,}", columna=h.get("columna") or "", detalle=h.get("detalle") or "")
    except (KeyError, IndexError, ValueError):
        return plantilla


def hallazgos_ordenados(d: DefinicionBase, r: Resultado) -> list[dict]:
    salida = []
    for h in r.hallazgos:
        regla = d.reglas[h["regla"]]
        salida.append({**h, "nombre": regla.nombre, "dimension": regla.dimension, "severidad": regla.severidad,
                       "accion": regla.accion, "mensaje": mensaje(d, h),
                       "porcentaje": round(100 * h["n"] / r.total_registros, 3) if r.total_registros else None})
    return sorted(salida, key=lambda h: (ORDEN_SEVERIDAD[h["severidad"]], -h["n"]))


def reporte(d: DefinicionBase, r: Resultado) -> dict:
    hs = hallazgos_ordenados(d, r)
    return {
        "base": r.base, "version": r.version, "anio": r.anio, "mes": r.mes,
        "total_registros": r.total_registros, "registros_validos": r.registros_validos,
        "registros_excluidos": r.registros_excluidos, "puntaje": r.puntaje, "puntajes": r.puntajes,
        "segundos": r.segundos, "hojas": r.hojas, "mapeo_columnas": r.mapeo_columnas,
        "resumen": {s: sum(1 for h in hs if h["severidad"] == s) for s in ("error", "advertencia", "info")},
        "sugerencias_pendientes": len(r.pendientes),
        "hallazgos": hs,
        "excluidos": [{k: v for k, v in e.items() if k != "filas"} | {"registros": len(e["filas"])}
                      for e in r.excluidos],
    }


def escribir_archivos(d: DefinicionBase, r: Resultado, original: Path, carpeta: Path) -> dict[str, Path]:
    carpeta.mkdir(parents=True, exist_ok=True)
    rutas = {"original": carpeta / f"original{original.suffix.lower()}",
             "corregido": carpeta / "corregido.xlsx",
             "bitacora": carpeta / "bitacora.xlsx",
             "reporte": carpeta / "reporte.json"}
    if original.resolve() != rutas["original"].resolve():
        shutil.copyfile(original, rutas["original"])

    # Base corregida
    with pd.ExcelWriter(rutas["corregido"], engine="xlsxwriter") as xw:
        r.salida.to_excel(xw, sheet_name=r.base[:31], index=False)

    # Bitácora
    hs = hallazgos_ordenados(d, r)
    resumen = pd.DataFrame(
        [("Base", r.base), ("Período", f"{r.mes or ''}/{r.anio or ''}".strip("/")),
         ("Registros recibidos", r.total_registros), ("Registros válidos", r.registros_validos),
         ("Registros excluidos", r.registros_excluidos), ("Puntaje global", r.puntaje)]
        + [(f"Puntaje {NOMBRE_DIMENSION[k]}", v) for k, v in r.puntajes.items()]
        + [("Errores", sum(1 for h in hs if h["severidad"] == "error")),
           ("Advertencias", sum(1 for h in hs if h["severidad"] == "advertencia")),
           ("Sugerencias pendientes", len(r.pendientes))],
        columns=["Indicador", "Valor"])
    hallazgos = pd.DataFrame([{
        "Severidad": h["severidad"], "Dimensión": NOMBRE_DIMENSION[h["dimension"]], "Regla": h["regla"],
        "Columna": h.get("columna"), "Hoja": h.get("hoja"), "Registros": h["n"], "%": h["porcentaje"],
        "Mensaje": h["mensaje"], "Acción": h["accion"],
        "Filas de ejemplo": ", ".join(str(e["fila"]) for e in h["ejemplos"][:10]),
    } for h in hs])
    cambios = pd.DataFrame([{
        "Regla": c["regla"], "Columna": c["columna"], "Antes": c["antes"], "Después": c["despues"],
        "Registros": c["n"], "Primera fila": c["fila"], "Hoja": c["hoja"], "Origen": c["origen"],
        "Estado": c["estado"], "Confianza": c["confianza"], "Justificación": c["justificacion"],
    } for c in r.cambios])
    sugerencias = cambios[cambios["Estado"] == "pendiente"] if not cambios.empty else cambios
    aplicados = cambios[cambios["Estado"] != "pendiente"] if not cambios.empty else cambios
    excluidos = pd.DataFrame([{
        "Regla": e["regla"], "Motivo": e["motivo"], "Hoja": e["hoja"], "Registros": len(e["filas"]),
        "Filas": ", ".join(map(str, e["filas"][:200])) + (" …" if len(e["filas"]) > 200 else ""),
    } for e in r.excluidos])
    with pd.ExcelWriter(rutas["bitacora"], engine="xlsxwriter") as xw:
        for nombre, df in [("Resumen", resumen), ("Hallazgos", hallazgos), ("Cambios aplicados", aplicados),
                           ("Sugerencias", sugerencias), ("Excluidos", excluidos)]:
            (df if not df.empty else pd.DataFrame({"": ["Sin registros"]})).to_excel(xw, sheet_name=nombre, index=False)
            hoja = xw.sheets[nombre]
            for j, col in enumerate(df.columns):
                ancho = min(80, max(10, int(df[col].map(lambda x: len(str(x))).quantile(0.9)) + 2 if len(df) else 10,
                                    len(str(col)) + 2))
                hoja.set_column(j, j, ancho)
            hoja.freeze_panes(1, 0)

    rutas["reporte"].write_text(json.dumps(reporte(d, r), ensure_ascii=False, indent=2, default=_json),
                                encoding="utf-8")
    return rutas


def _sha256(ruta: Path) -> str:
    h = hashlib.sha256()
    with open(ruta, "rb") as f:
        for bloque in iter(lambda: f.read(1 << 20), b""):
            h.update(bloque)
    return h.hexdigest()


def usuario_sistema(cur) -> int:
    cur.execute(
        """INSERT INTO usuario (nombre, email, password_hash, rol) VALUES
           ('Motor de validación', 'motor@quality-audit.local', '!', 'admin')
           ON CONFLICT (email) DO UPDATE SET nombre = EXCLUDED.nombre RETURNING id""")
    return cur.fetchone()[0]


def crear_carga(cur, d: DefinicionBase, usuario_id: int, anio: int, mes: int | None) -> str:
    cur.execute(
        """INSERT INTO carga (institucion_id, tipo_base_id, usuario_id, periodo_anio, periodo_mes, estado)
           VALUES (%s, %s, %s, %s, %s, 'procesando') RETURNING id""",
        (d.institucion_id, d.tipo_base_id, usuario_id, anio, mes))
    return str(cur.fetchone()[0])


def guardar_en_bd(cur, d: DefinicionBase, r: Resultado, carga_id: str, rutas: dict[str, Path],
                  usuario_id: int) -> str:
    """Escribe ejecución, puntajes, hallazgos, cambios, excluidos y archivos. Devuelve el id de la ejecución."""
    for rol in ("original", "corregido", "reporte", "bitacora"):
        p = rutas[rol]
        cur.execute(
            """INSERT INTO archivo (carga_id, rol, nombre, formato, tamano_bytes, sha256, ruta, hojas)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s)""",
            (carga_id, rol, p.name, p.suffix.lstrip("."), p.stat().st_size, _sha256(p), str(p),
             json.dumps(r.hojas, ensure_ascii=False, default=_json) if rol == "original" else None))

    rep = reporte(d, r)
    cur.execute(
        """INSERT INTO ejecucion (carga_id, version_esquema_id, finalizada_en, total_registros, registros_validos,
                                  registros_excluidos, puntaje, mapeo_columnas, resumen)
           VALUES (%s, %s, now(), %s, %s, %s, %s, %s, %s) RETURNING id""",
        (carga_id, d.version_id, r.total_registros, r.registros_validos, r.registros_excluidos, r.puntaje,
         json.dumps(r.mapeo_columnas, ensure_ascii=False),
         json.dumps({"resumen": rep["resumen"], "puntajes": r.puntajes, "segundos": r.segundos,
                     "sugerencias_pendientes": len(r.pendientes)}, ensure_ascii=False)))
    ejecucion_id = str(cur.fetchone()[0])

    cur.executemany("INSERT INTO puntaje_dimension (ejecucion_id, dimension, puntaje) VALUES (%s, %s, %s)",
                    [(ejecucion_id, k, v) for k, v in r.puntajes.items()])

    ids_hallazgo = {}
    for h in hallazgos_ordenados(d, r):
        cur.execute(
            """INSERT INTO hallazgo (ejecucion_id, regla_id, hoja, columna, registros_afectados, porcentaje,
                                     severidad, mensaje, ejemplos, estado)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING id""",
            (ejecucion_id, d.reglas[h["regla"]].id, h.get("hoja"), h.get("columna"), h["n"], h["porcentaje"],
             h["severidad"], h["mensaje"], json.dumps(h["ejemplos"], ensure_ascii=False, default=_json),
             "corregido" if h["accion"] == "auto_corregir" else "abierto"))
        ids_hallazgo.setdefault((h["regla"], h.get("columna")), cur.fetchone()[0])

    cur.executemany(
        """INSERT INTO correccion (ejecucion_id, hallazgo_id, hoja, fila, registros_afectados, columna, valor_antes,
                                   valor_despues, origen, equivalencia_id, confianza, justificacion, estado)
           VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
        [(ejecucion_id, ids_hallazgo.get((c["regla"], c["columna"])), c["hoja"], c["fila"], c["n"], c["columna"],
          None if c["antes"] is None else str(c["antes"]), None if c["despues"] is None else str(c["despues"]),
          c["origen"], c["equivalencia_id"], c["confianza"], c["justificacion"], c["estado"])
         for c in r.cambios])

    # Sugerencias de IA: quedan en la memoria de equivalencias sin aprobar
    for c in r.pendientes:
        if c["origen"] != "ia":
            continue
        var = next(v for v in d.variables if v.nombre == c["columna"])
        cat = var.catalogo or (var.transformacion or {}).get("catalogo")
        cur.execute(
            """INSERT INTO equivalencia (catalogo_id, institucion_id, texto_origen, codigo, fuente, confianza, aprobada)
               SELECT id, %s, %s, %s, 'ia', %s, FALSE FROM catalogo WHERE codigo = %s
               ON CONFLICT (catalogo_id, institucion_id, texto_origen) DO NOTHING""",
            (d.institucion_id, normalizar(c["antes"]), c["despues"], c["confianza"], cat))

    cur.executemany(
        """INSERT INTO registro_excluido (ejecucion_id, regla_id, hoja, fila, registros_afectados, filas, motivo)
           VALUES (%s, %s, %s, %s, %s, %s, %s)""",
        [(ejecucion_id, d.reglas[e["regla"]].id, e["hoja"], e["filas"][0], len(e["filas"]),
          json.dumps(e["filas"]), e["motivo"]) for e in r.excluidos])

    hay_problemas = any(d.reglas[h["regla"]].severidad in ("error", "advertencia") for h in r.hallazgos)
    estado = "con_observaciones" if hay_problemas or r.pendientes else "aprobada"
    cur.execute("UPDATE carga SET estado = %s, puntaje_calidad = %s, actualizado_en = now() WHERE id = %s",
                (estado, r.puntaje, carga_id))
    cur.execute(
        """INSERT INTO evento_auditoria (usuario_id, accion, entidad, entidad_id, detalle)
           VALUES (%s, 'procesar_carga', 'carga', %s, %s)""",
        (usuario_id, carga_id, json.dumps({"ejecucion": ejecucion_id, "puntaje": r.puntaje,
                                           "registros": r.total_registros})))
    return ejecucion_id

