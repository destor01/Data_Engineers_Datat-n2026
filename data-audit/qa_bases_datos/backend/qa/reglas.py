"""Reglas específicas de cada base y la regla de llave única.

Las reglas genéricas (espacios, nulos, catálogo, rango, formato...) viven en motor.py
porque se aplican columna por columna a partir de la definición. Aquí van las que
miran varias columnas a la vez o agrupan registros.

Cada función recibe el Contexto y llama a ctx.hallazgo(...) o ctx.excluir(...).
Si una regla no tiene las columnas que necesita, no hace nada.
"""
from __future__ import annotations

from collections import Counter

import pandas as pd

from .texto import normalizar
from .transformaciones import _entero, _fecha

MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto",
         "septiembre", "octubre", "noviembre", "diciembre"]


def _num(s: pd.Series) -> pd.Series:
    return pd.to_numeric(s, errors="coerce")


# ------------------------------ Calidad del aire ------------------------------
def aire_mes_representativo(ctx, regla):
    o = ctx.out
    if not {"estación", "pm", "fehca", "valor"} <= set(o.columns):
        return
    p = regla.parametros
    max_horas, max_dias = int(p.get("max_horas_faltantes_dia", 4)), int(p.get("max_dias_invalidos_mes", 2))
    fecha = _fecha(o["fehca"]).dt.normalize()
    base = pd.DataFrame({"est": o["estación"], "pm": o["pm"], "fecha": fecha,
                         "falta": _num(o["valor"]).isna()}, index=o.index)
    base["mes"] = base["fecha"].dt.month
    # Horas sin dato por día (cada fila es una hora)
    por_dia = base.groupby(["est", "pm", "fecha"]).agg(falta=("falta", "sum"), horas=("falta", "size")).reset_index()
    por_dia["horas_sin_dato"] = por_dia["falta"] + (24 - por_dia["horas"]).clip(lower=0)
    por_dia["invalido"] = por_dia["horas_sin_dato"] > max_horas
    por_dia["mes"] = por_dia["fecha"].dt.month
    por_mes = por_dia.groupby(["est", "pm", "mes"])["invalido"].sum().reset_index()
    malos = por_mes[por_mes["invalido"] > max_dias]

    est_cat = ctx.d.catalogos.get("AIRE_ESTACION")
    pm_cat = ctx.d.catalogos.get("AIRE_PM")
    for _, m in malos.iterrows():
        idx = base.index[(base["est"] == m["est"]) & (base["pm"] == m["pm"]) & (base["mes"] == m["mes"])]
        nombre = est_cat.valores[m["est"]].etiqueta if est_cat and m["est"] in est_cat.valores else m["est"]
        pm = pm_cat.valores[m["pm"]].etiqueta if pm_cat and m["pm"] in pm_cat.valores else m["pm"]
        ctx.excluir(regla, idx, f"{nombre} {pm}, {MESES[int(m['mes']) - 1]}: {int(m['invalido'])} días con "
                                f"más de {max_horas} horas sin dato (máximo permitido {max_dias})")
    if len(malos):
        grupos = [e for e in ctx.excluidos if e["regla"] == regla.codigo]
        n = sum(len(e["indices"]) for e in grupos)
        ctx.hallazgo(regla, n, detalle=f"{len(grupos)} combinaciones de estación, PM y mes no son representativas")


def aire_rango_pm(ctx, regla):
    if "valor" not in ctx.out:
        return
    tope = float(regla.parametros.get("max", 500))
    v = _num(ctx.out["valor"])
    ctx.hallazgo(regla, v > tope, columna="valor", detalle=f"{tope:g}", valores=ctx.out["valor"])


# ------------------------------ Periodo de ocurrencia ------------------------------
def periodo_ocurrencia(ctx, regla):
    col = regla.parametros.get("columna_anio")
    if col not in ctx.out or ctx.anio is None:
        return
    anio = _num(ctx.out[col])
    fuera = anio.notna() & (anio != ctx.anio)
    if not fuera.any():
        return
    conteo = Counter(int(a) for a in anio[fuera])
    for a, _ in sorted(conteo.items()):
        idx = ctx.out.index[fuera & (anio == a)]
        ctx.excluir(regla, idx, f"Ocurrió en {a}, la carga es de {ctx.anio}")
    top = ", ".join(f"{a}: {c}" for a, c in conteo.most_common(5))
    ctx.hallazgo(regla, fuera, columna=col, detalle=top, valores=ctx.out[col])


def fuera_de_alcance(ctx, regla):
    """Excluye registros cuyo valor en una columna del crudo no es el esperado (p. ej. país 320)."""
    p = regla.parametros
    if normalizar(p.get("columna", "")) not in ctx.raw_norm:
        return
    s = ctx.raw_col(p["columna"])
    esperado = str(p["valor"])
    norm = s.map(lambda v: str(_entero(v)) if _entero(v) is not None else (str(v).strip() if v is not None else None))
    fuera = s.notna() & (norm != esperado)
    if not fuera.any():
        return
    conteo = Counter(norm[fuera])
    for valor, _ in conteo.most_common():
        ctx.excluir(regla, ctx.raw.index[fuera & (norm == valor)], f"{p['columna']} = {valor}")
    ctx.hallazgo(regla, fuera, columna=p["columna"],
                 detalle=", ".join(f"{v}: {c}" for v, c in conteo.most_common(4)), valores=s)


def def_fecha_coherencia(ctx, regla):
    if "FECHA_DEFUNCION" not in ctx.raw_norm or not {"Diaocu", "Mesocu", "Añoocu"} <= set(ctx.out.columns):
        return
    f = _fecha(ctx.raw_col("FECHA_DEFUNCION"))
    o = ctx.out
    malo = f.notna() & ((_num(o["Diaocu"]) != f.dt.day) | (_num(o["Mesocu"]) != f.dt.month) |
                        (_num(o["Añoocu"]) != f.dt.year))
    ctx.hallazgo(regla, malo, columna="FECHA_DEFUNCION", valores=ctx.raw_col("FECHA_DEFUNCION"))


# ------------------------------ Nacimientos ------------------------------
def nac_hijos_coherencia(ctx, regla):
    o = ctx.out
    if not {"Tohite", "Tohinm", "Tohivi"} <= set(o.columns):
        return
    t, m, v = _num(o["Tohite"]), _num(o["Tohinm"]), _num(o["Tohivi"])
    validos = t.notna() & m.notna() & v.notna() & (t != 99) & (m != 99) & (v != 99)
    malo = validos & (t != m + v)
    ejemplo = t.astype("Int64").astype(str) + " ≠ " + m.astype("Int64").astype(str) + " + " + v.astype("Int64").astype(str)
    ctx.hallazgo(regla, malo, columna="Tohite", valores=ejemplo)


# ------------------------------ PNC ------------------------------
def pnc_mayor_edad(ctx, regla):
    if "MAYOR" not in ctx.raw_norm or "edad_per" not in ctx.out:
        return
    marca = ctx.raw_col("MAYOR").astype(str).str.upper().str.strip()
    edad = _num(ctx.out["edad_per"])
    edad = edad.where(edad != 999)
    malo = edad.notna() & (((marca == "MAYOR") & (edad < 18)) | ((marca == "MENOR") & (edad >= 18)))
    ctx.hallazgo(regla, malo, columna="MAYOR", valores=marca + " con edad " + edad.astype("Int64").astype(str))


def pnc_dia_semana(ctx, regla):
    if "FECHA" not in ctx.raw_norm or "día_sem_ocu" not in ctx.out:
        return
    f = _fecha(ctx.raw_col("FECHA"))
    dia = _num(ctx.out["día_sem_ocu"])
    malo = f.notna() & dia.notna() & (dia != 9) & (dia != f.dt.dayofweek + 1)
    ctx.hallazgo(regla, malo, columna="DIA", valores=ctx.raw_col("DIA"))


def pnc_mes_periodo(ctx, regla):
    if "FECHA" not in ctx.raw_norm or ctx.anio is None:
        return
    f = _fecha(ctx.raw_col("FECHA"))
    malo = f.notna() & (f.dt.year != ctx.anio)
    if ctx.mes:
        malo |= f.notna() & (f.dt.month != ctx.mes)
    periodo = f"{MESES[ctx.mes - 1]} {ctx.anio}" if ctx.mes else str(ctx.anio)
    ctx.hallazgo(regla, malo, columna="FECHA", detalle=periodo, valores=ctx.raw_col("FECHA"))


# ------------------------------ Emergencias ------------------------------
def emerg_subtipo_amenaza(ctx, regla):
    o = ctx.out
    cat = ctx.d.catalogos.get("EMERG_SUBTIPO")
    if not cat or not {"amenaza", "subtipo_amenaza"} <= set(o.columns):
        return
    padre = o["subtipo_amenaza"].map(lambda s: cat.valores[s].padre if s in cat.valores else None)
    malo = padre.notna() & o["amenaza"].notna() & (padre != o["amenaza"])
    pares = Counter(zip(o.loc[malo, "amenaza"], o.loc[malo, "subtipo_amenaza"]))
    detalle = "; ".join(f"{a} con {s} ({c})" for (a, s), c in pares.most_common(4))
    ctx.hallazgo(regla, malo, columna="subtipo_amenaza", detalle=detalle,
                 valores=o["amenaza"].astype(str) + " / " + o["subtipo_amenaza"].astype(str))


def emerg_periodo(ctx, regla):
    if "fecha" not in ctx.out or ctx.anio is None:
        return
    f = _fecha(ctx.out["fecha"])
    ctx.hallazgo(regla, f.notna() & (f.dt.year != ctx.anio), columna="fecha", valores=ctx.out["fecha"])


# ------------------------------ Llave única ------------------------------
def llave_unica(ctx, regla):
    cols = regla.parametros.get("columnas") or []
    partes, completa = [], pd.Series(True, index=ctx.raw.index)
    for c in cols:
        if c in ctx.out:
            s = ctx.out[c]
        elif normalizar(c) in ctx.raw_norm:
            s = ctx.raw_col(c)
        else:
            return
        completa &= s.notna() & (s.astype(str).str.strip() != "")
        partes.append(s.astype(str))
    llave = partes[0]
    for p in partes[1:]:
        llave = llave + " | " + p
    # Una llave incompleta no cuenta como duplicado: eso ya lo reporta GEN_REQUERIDA
    dup = completa & llave.where(completa).duplicated(keep=False)
    if dup.any():
        grupos = llave[dup].nunique()
        ctx.hallazgo(regla, dup, detalle=f"{grupos} llaves repetidas", valores=llave)


ESPECIFICAS = {
    "AIRE_MES_REPRESENTATIVO": aire_mes_representativo,
    "AIRE_RANGO_PM": aire_rango_pm,
    "DEF_PERIODO_OCURRENCIA": periodo_ocurrencia,
    "NAC_PERIODO_OCURRENCIA": periodo_ocurrencia,
    "DEF_FECHA_COHERENCIA": def_fecha_coherencia,
    "DEF_OCURRIO_EXTRANJERO": fuera_de_alcance,
    "NAC_HIJOS_COHERENCIA": nac_hijos_coherencia,
    "PNC_MAYOR_EDAD_COHERENCIA": pnc_mayor_edad,
    "PNC_DIA_SEMANA_COHERENCIA": pnc_dia_semana,
    "PNC_MES_PERIODO": pnc_mes_periodo,
    "EMERG_SUBTIPO_AMENAZA": emerg_subtipo_amenaza,
    "EMERG_PERIODO": emerg_periodo,
}
