"""Motor de validación de Quality Audit.

    resultado = procesar("crudo.xlsx", definicion, anio=2026, mes=10)

Pasos:
 1. Leer el crudo (lector.py) y registrar problemas de estructura.
 2. Emparejar cada columna con una variable del INE por sus alias.
 3. Limpiar: espacios sobrantes y textos usados como "sin dato".
 4. Calcular las columnas del INE (copia directa o transformación).
 5. Codificar contra catálogo: código válido, equivalencia aprobada o sugerencia.
 6. Validar tipo, dato faltante, rango y formato.
 7. Reglas específicas de la base y llave única (reglas.py).
 8. Quitar los registros excluidos y calcular el puntaje.

No escribe nada: devuelve un Resultado que salidas.py convierte en archivos y en
filas de la base de datos.
"""
from __future__ import annotations

import re
import time
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

from . import transformaciones as T
from .codificador import Codificador, CodificadorSimilitud, Sugerencia
from .definicion import Catalogo, DefinicionBase, Regla
from .lector import leer
from .reglas import ESPECIFICAS, llave_unica
from .texto import normalizar

PESO = {"error": 1.0, "advertencia": 0.5, "info": 0.0}
DIMENSIONES = ["estructura", "completitud", "validez", "consistencia", "unicidad", "oportunidad", "representatividad"]
MAX_EJEMPLOS = 20
MAX_CAMBIOS_POR_COLUMNA = 500
# Columnas del crudo que leen las reglas específicas (reglas.py)
COLUMNAS_DE_REGLAS = ["FECHA", "FECHA_DEFUNCION", "MAYOR", "DIA"]
# Transformaciones que derivan de otra columna ya validada: su dato faltante se reporta en el origen
DERIVADAS = {"padre_catalogo", "etiqueta_catalogo", "depto_de_municipio", "agrupar_edad", "agrupar_hora"}


@dataclass
class Resultado:
    base: str
    version: str
    anio: int | None
    mes: int | None
    total_registros: int
    registros_validos: int
    registros_excluidos: int
    salida: pd.DataFrame                       # base corregida, ya sin excluidos ni datos personales
    hallazgos: list[dict] = field(default_factory=list)
    cambios: list[dict] = field(default_factory=list)
    excluidos: list[dict] = field(default_factory=list)
    mapeo_columnas: dict = field(default_factory=dict)
    hojas: list[dict] = field(default_factory=list)
    puntajes: dict = field(default_factory=dict)
    puntaje: float = 0.0
    segundos: float = 0.0

    @property
    def pendientes(self) -> list[dict]:
        return [c for c in self.cambios if c["estado"] == "pendiente"]


class Contexto:
    """Lo que ven las reglas: el crudo limpio, la salida y cómo reportar."""

    def __init__(self, d: DefinicionBase, raw: pd.DataFrame, anio, mes):
        self.d, self.raw, self.anio, self.mes = d, raw, anio, mes
        self.raw_norm = {normalizar(c): c for c in raw.columns if not c.startswith("_")}
        self.out = pd.DataFrame(index=raw.index)
        self.hallazgos: list[dict] = []
        self.cambios: list[dict] = []
        self.excluidos: list[dict] = []

    # -- columnas --
    def raw_col(self, nombre: str) -> pd.Series:
        return self.raw[self.raw_norm[normalizar(nombre)]]

    # -- reporte --
    def _ejemplos(self, mascara: pd.Series, valores: pd.Series | None) -> list[dict]:
        idx = mascara[mascara].index[:MAX_EJEMPLOS]
        ej = []
        for i in idx:
            e = {"fila": int(self.raw.at[i, "_fila"]), "hoja": self.raw.at[i, "_hoja"]}
            if valores is not None:
                v = valores.get(i)
                e["valor"] = None if v is None or (isinstance(v, float) and v != v) else str(v)
            ej.append(e)
        return ej

    def hallazgo(self, regla: Regla | None, cuantos, columna=None, detalle=None, valores=None, hoja=None):
        if regla is None:
            return
        if isinstance(cuantos, pd.Series):
            mascara = cuantos.fillna(False).astype(bool)
            n = int(mascara.sum())
            ejemplos = self._ejemplos(mascara, valores)
        else:
            n, ejemplos = int(cuantos), []
        if n == 0:
            return
        self.hallazgos.append({"regla": regla.codigo, "columna": columna, "hoja": hoja, "n": n,
                               "detalle": detalle, "ejemplos": ejemplos})

    def cambio(self, regla: Regla | None, columna, antes, despues, n, primera, origen="regla",
               estado="aplicada", confianza=None, justificacion=None, equivalencia_id=None):
        if regla is None:
            return
        self.cambios.append({"regla": regla.codigo, "columna": columna, "antes": antes, "despues": despues,
                             "n": int(n), "fila": int(self.raw.at[primera, "_fila"]),
                             "hoja": self.raw.at[primera, "_hoja"], "origen": origen, "estado": estado,
                             "confianza": confianza, "justificacion": justificacion,
                             "equivalencia_id": equivalencia_id})

    def excluir(self, regla: Regla, indices, motivo: str):
        indices = list(indices)
        if not indices:
            return
        self.excluidos.append({"regla": regla.codigo, "motivo": motivo, "indices": indices,
                               "filas": [int(f) for f in self.raw.loc[indices, "_fila"]],
                               "hoja": self.raw.at[indices[0], "_hoja"]})


def _codigo_salida(x):
    if isinstance(x, str):
        if x.isdigit() and not (len(x) > 1 and x[0] == "0"):
            return int(x)
        if re.fullmatch(r"\d+\.\d+", x):
            return float(x)
    return x


def _vacio(v) -> bool:
    return v is None or (isinstance(v, float) and v != v) or (isinstance(v, str) and not v.strip()) or v is pd.NaT


# ---------------------------------------------------------------------------
def _limpiar(ctx: Contexto, columnas: list[str]):
    """Espacios sobrantes y textos de 'sin dato' en las columnas que se usan."""
    r = ctx.d.reglas
    nulos = {normalizar(x) for x in r["GEN_NULO_TEXTUAL"].parametros.get("valores", [])} if "GEN_NULO_TEXTUAL" in r else set()
    for c in columnas:
        s = ctx.raw[c]
        # Espacios
        es_txt = s.map(lambda v: isinstance(v, str))
        if es_txt.any():
            limpio = s[es_txt].map(lambda v: " ".join(v.split()))
            cambio = limpio != s[es_txt]
            if cambio.any():
                ctx.hallazgo(r.get("GEN_ESPACIOS"), cambio.reindex(s.index, fill_value=False), columna=c,
                             valores=s.map(repr))
                grupos = s[es_txt][cambio].groupby(s[es_txt][cambio]).groups
                for k, (antes, grupo) in enumerate(grupos.items()):
                    if k >= MAX_CAMBIOS_POR_COLUMNA:
                        break
                    ctx.cambio(r.get("GEN_ESPACIOS"), c, antes, " ".join(antes.split()), len(grupo), grupo[0])
                s = s.copy()
                s.loc[limpio.index] = limpio
        # Textos de "sin dato"
        if nulos:
            marca = s.map(lambda v: not _vacio(v) and normalizar(v) in nulos)
            if marca.any():
                tokens = Counter(str(v) for v in s[marca])
                ctx.hallazgo(r.get("GEN_NULO_TEXTUAL"), marca, columna=c,
                             detalle=", ".join(f"\"{t}\"" for t, _ in tokens.most_common(3)), valores=s)
                for t, cnt in tokens.items():
                    primera = s[marca & (s.astype(str) == t)].index[0]
                    ctx.cambio(r.get("GEN_NULO_TEXTUAL"), c, t, None, cnt, primera)
                s = s.where(~marca, None)
        ctx.raw[c] = s


class _Columnas:
    """Busca una columna: primero entre las ya calculadas del INE, luego en el crudo."""

    def __init__(self, ctx: Contexto):
        self.ctx = ctx
        self.indice = ctx.raw.index

    def __call__(self, nombre: str) -> pd.Series:
        if nombre in self.ctx.out.columns:
            return self.ctx.out[nombre]
        k = normalizar(nombre)
        if k in self.ctx.raw_norm:
            return self.ctx.raw[self.ctx.raw_norm[k]]
        raise T.FaltaColumna(nombre)


def _construir(ctx: Contexto, fuentes: dict[str, list[str]]):
    """Calcula cada variable publicada, respetando dependencias entre transformaciones."""
    d, col = ctx.d, _Columnas(ctx)
    pendientes = list(d.publicadas())
    faltantes: dict[str, str] = {}
    for _ in range(4):
        siguiente = []
        for v in pendientes:
            if v.transformacion:
                try:
                    ctx.out[v.nombre] = T.aplicar(v.transformacion, col, d).values
                    faltantes.pop(v.nombre, None)
                except T.FaltaColumna as e:
                    faltantes[v.nombre] = str(e)
                    siguiente.append(v)
            elif fuentes.get(v.nombre):
                s = ctx.raw[fuentes[v.nombre][0]]
                for otra in fuentes[v.nombre][1:]:          # mismo dato con dos nombres (No. / #)
                    s = s.where(~s.map(_vacio), ctx.raw[otra])
                ctx.out[v.nombre] = s.values
            else:
                faltantes[v.nombre] = "ninguna columna del archivo corresponde"
                ctx.out[v.nombre] = None
        if not siguiente or len(siguiente) == len(pendientes):
            pendientes = siguiente
            break
        pendientes = siguiente
    for v in pendientes:
        ctx.out[v.nombre] = None
    regla = d.reglas.get("GEN_COLUMNA_FALTANTE")
    for v in d.publicadas():
        if v.nombre in faltantes and v.requerida:
            ctx.hallazgo(regla, len(ctx.raw), columna=v.nombre, detalle=faltantes[v.nombre])
    # Reordenar como en la publicación del INE
    ctx.out = ctx.out[[v.nombre for v in d.publicadas()]]


def _codificar(ctx: Contexto, v, codificador: Codificador):
    d, r = ctx.d, ctx.d.reglas
    cat = d.catalogos[v.catalogo]
    s = ctx.out[v.nombre]
    es_ia = bool(v.transformacion and v.transformacion.get("tipo") == "codificar_ia")
    regla_desc = r.get("GEN_CODIFICACION_IA") if es_ia else r.get("GEN_CATALOGO")

    presentes = s[~s.map(_vacio)]
    if presentes.empty:
        return
    clave = presentes.map(lambda x: str(x).strip())
    resueltos, como = {}, {}
    for valor in clave.unique():
        cod, modo = cat.resolver(valor)
        resueltos[valor], como[valor] = cod, modo

    nueva = s.copy()
    grupos = presentes.groupby(clave).groups
    traducidos = Counter()
    desconocidos: dict[str, list] = {}
    registrados = 0
    for valor, idx in grupos.items():
        cod, modo = resueltos[valor], como[valor]
        if modo == "codigo":
            nueva.loc[idx] = cod
        elif modo == "equivalencia":
            nueva.loc[idx] = cod
            traducidos[valor] += len(idx)
            eq = cat.equivalencias.get(normalizar(valor))
            registrados += 1
            if registrados <= MAX_CAMBIOS_POR_COLUMNA:
                ctx.cambio(r.get("GEN_CODIFICACION"), v.nombre, valor, cod, len(idx), idx[0],
                           justificacion="Equivalencia aprobada", equivalencia_id=eq[1] if eq else None)
        else:
            desconocidos[valor] = list(idx)

    if traducidos:
        ctx.hallazgo(r.get("GEN_CODIFICACION"), pd.Series(s.index.isin(
            [i for val in traducidos for i in grupos[val]]), index=s.index), columna=v.nombre,
            detalle=", ".join(f"\"{t}\" → {resueltos[t]}" for t, _ in traducidos.most_common(3)), valores=s)

    if desconocidos:
        # Sugerencias: primero las pendientes de corridas anteriores, luego el codificador
        minimo = (regla_desc.parametros.get("confianza_minima") if es_ia
                  else regla_desc.parametros.get("similitud_minima")) if regla_desc else 0.85
        dentro_de = (v.transformacion or {}).get("dentro_de")
        if dentro_de and dentro_de in ctx.out:
            # Municipios: sugerir solo entre los del departamento de cada registro
            # (hay "La Democracia" en Escuintla y en Huehuetenango)
            sugeridas = {}
            for t in desconocidos:
                deptos = ctx.out.loc[desconocidos[t], dentro_de].map(lambda x: str(x) if not _vacio(x) else None)
                padre = deptos.mode().iat[0] if deptos.notna().any() else None
                sub = Catalogo(cat.codigo, {c: x for c, x in cat.valores.items() if x.padre == padre},
                               {k: e for k, e in cat.equivalencias.items()
                                if e[0] in cat.valores and cat.valores[e[0]].padre == padre}, {})
                sug = codificador.sugerir(sub, [t]).get(t) if padre and sub.valores else None
                if sug:
                    etq_dep = d.catalogos["DEPARTAMENTO"].valores.get(padre)
                    sug.justificacion += f", dentro de {etq_dep.etiqueta if etq_dep else padre}"
                    sugeridas[t] = sug
        else:
            textos = [t for t in desconocidos if normalizar(t) not in cat.pendientes]
            sugeridas = codificador.sugerir(cat, textos) if textos else {}
        for t in desconocidos:
            if normalizar(t) in cat.pendientes:
                cod, eid, conf = cat.pendientes[normalizar(t)]
                sugeridas[t] = Sugerencia(cod, conf, "Sugerida en una carga anterior; pendiente de aprobar")
        mascara = pd.Series(s.index.isin([i for idx in desconocidos.values() for i in idx]), index=s.index)
        orden = sorted(desconocidos, key=lambda t: -len(desconocidos[t]))
        if es_ia:
            detalle = len(desconocidos)
        else:
            detalle = ", ".join(f"\"{t}\"" for t in orden[:5]) + (" y otros" if len(orden) > 5 else "")
        ctx.hallazgo(regla_desc, mascara, columna=v.nombre, detalle=detalle, valores=s)
        for t in orden:
            sug = sugeridas.get(t)
            if sug and (minimo is None or sug.confianza >= float(minimo)):
                ctx.cambio(regla_desc, v.nombre, t, sug.codigo, len(desconocidos[t]), desconocidos[t][0],
                           origen="ia" if es_ia else "regla", estado="pendiente",
                           confianza=sug.confianza, justificacion=sug.justificacion)
    ctx.out[v.nombre] = nueva


def _validar(ctx: Contexto, v):
    d, r = ctx.d, ctx.d.reglas
    s = ctx.out[v.nombre]
    cat = d.catalogos.get(v.catalogo) if v.catalogo else None

    # Tipo de dato
    if v.tipo in ("entero", "decimal") and not v.catalogo:
        vacio = s.map(_vacio)
        num = pd.to_numeric(s, errors="coerce")
        malo = ~vacio & num.isna()
        ctx.hallazgo(r.get("GEN_TIPO"), malo, columna=v.nombre,
                     detalle="números enteros" if v.tipo == "entero" else "números", valores=s)
        s = num.where(~malo, s)
        if v.tipo == "entero":
            s = s.map(lambda x: int(x) if isinstance(x, float) and x == x and x.is_integer() else x)
    elif v.tipo in ("fecha", "fecha_hora"):
        vacio = s.map(_vacio)
        f = T._fecha(s)
        malo = ~vacio & f.isna()
        ctx.hallazgo(r.get("GEN_TIPO"), malo, columna=v.nombre, detalle="fechas válidas", valores=s)
        s = f.where(~malo, s)
        if v.tipo == "fecha":
            s = s.map(lambda x: x.date() if isinstance(x, pd.Timestamp) else x)

    # Dato faltante -> código de ignorado, o error si es obligatorio
    ign = v.ignorado
    if ign is None and cat:
        ign = next((c for c, x in cat.valores.items() if x.ignorado), None)
    vacio = s.map(_vacio)
    if vacio.any():
        derivada = bool(v.transformacion and v.transformacion.get("tipo") in DERIVADAS)
        if v.requerida and not derivada:
            ctx.hallazgo(r.get("GEN_REQUERIDA"), vacio, columna=v.nombre)
        elif not derivada:
            ctx.hallazgo(r.get("GEN_SIN_DATO"), vacio, columna=v.nombre,
                         detalle=f"se asignó el código de ignorado {ign}" if ign is not None else "quedan vacíos")
        if ign is not None:
            valor_ign = int(ign) if v.tipo == "entero" and str(ign).isdigit() else ign
            ctx.cambio(r.get("GEN_SIN_DATO"), v.nombre, None, str(ign), int(vacio.sum()), vacio[vacio].index[0])
            s = s.where(~vacio, valor_ign)

    # Rango (sin contar el código de ignorado)
    if (v.vmin is not None or v.vmax is not None) and not v.catalogo:
        num = pd.to_numeric(s, errors="coerce")
        if ign is not None:
            num = num.where(num != float(ign))
        fuera = pd.Series(False, index=s.index)
        if v.vmin is not None:
            fuera |= num < v.vmin
        if v.vmax is not None:
            fuera |= num > v.vmax
        rango = f"{v.vmin:g} a {v.vmax:g}" if v.vmin is not None and v.vmax is not None else (
            f"mínimo {v.vmin:g}" if v.vmin is not None else f"máximo {v.vmax:g}")
        ctx.hallazgo(r.get("GEN_RANGO"), fuera, columna=v.nombre, detalle=rango, valores=s)

    # Formato
    if v.regex:
        patron = re.compile(v.regex)
        no_vacio = ~s.map(_vacio)
        malo = no_vacio & ~s.astype(str).map(lambda x: bool(patron.match(x)))
        if ign is not None:
            malo &= s.astype(str) != str(ign)
        ctx.hallazgo(r.get("GEN_FORMATO"), malo, columna=v.nombre, detalle=v.regex, valores=s)

    ctx.out[v.nombre] = s


def _puntaje(d: DefinicionBase, hallazgos: list[dict], total: int, n_columnas: int) -> tuple[dict, float]:
    """Puntaje 0-100 por dimensión.
    - Estructura: 100 menos 15 por error y 5 por advertencia.
    - Hallazgos de una columna: celdas afectadas / (registros x columnas publicadas).
    - Hallazgos de registro (sin columna o de reglas de varias columnas): registros afectados / total.
    """
    aplica = {r.dimension for r in d.reglas.values()}
    penal = defaultdict(float)
    for h in hallazgos:
        regla = d.reglas[h["regla"]]
        w = PESO[regla.severidad]
        if w == 0:
            continue
        if regla.dimension == "estructura":
            penal["estructura"] += 15 if regla.severidad == "error" else 5
        elif regla.codigo.startswith("GEN_"):
            penal[regla.dimension] += 100 * w * h["n"] / max(total * n_columnas, 1)
        else:
            penal[regla.dimension] += 100 * w * h["n"] / max(total, 1)
    puntajes = {dim: round(max(0.0, 100 - penal[dim]), 1) for dim in DIMENSIONES if dim in aplica}
    return puntajes, round(sum(puntajes.values()) / len(puntajes), 1) if puntajes else 0.0


# ---------------------------------------------------------------------------
def procesar(ruta: str | Path, d: DefinicionBase, anio: int | None = None, mes: int | None = None,
             codificador: Codificador | None = None) -> Resultado:
    t0 = time.time()
    codificador = codificador or CodificadorSimilitud()
    lectura = leer(ruta, d.formato_crudo)
    raw = lectura.df.reset_index(drop=True)
    ctx = Contexto(d, raw, anio, mes)
    r = d.reglas

    # 1. Estructura detectada al leer
    for e in lectura.eventos:
        ctx.hallazgo(r.get(e["regla"]), 1, columna=e.get("columna"), detalle=e.get("detalle"), hoja=e.get("hoja"))

    # 2. Emparejar columnas
    alias = d.alias()
    fuentes: dict[str, list[str]] = defaultdict(list)
    mapeo, usadas = {}, []
    for c in raw.columns:
        if c.startswith("_"):
            continue
        var = alias.get(normalizar(c))
        if var is None:
            mapeo[c] = None
            ctx.hallazgo(r.get("GEN_COLUMNA_DESCONOCIDA"), 1, columna=c)
            continue
        mapeo[c] = var.nombre
        if var.es_pii:
            ctx.hallazgo(r.get("GEN_PII"), 1, columna=c)
            continue
        fuentes[var.nombre].append(c)
        usadas.append(c)

    # 3. Limpieza de las columnas que alimentan la salida o las reglas (las demás no se tocan)
    relevantes = {c for v in d.publicadas() for c in fuentes.get(v.nombre, [])}
    for v in d.publicadas():
        for dep in T.dependencias(v.transformacion or {}):
            if normalizar(dep) in ctx.raw_norm:
                relevantes.add(ctx.raw_norm[normalizar(dep)])
    for regla in r.values():
        for c in (regla.parametros.get("columnas") or []) + COLUMNAS_DE_REGLAS:
            if normalizar(c) in ctx.raw_norm:
                relevantes.add(ctx.raw_norm[normalizar(c)])
    _limpiar(ctx, [c for c in usadas if c in relevantes])

    # 4. Construir las columnas del INE
    _construir(ctx, fuentes)

    # 5-6. Codificar y validar cada variable publicada
    for v in d.publicadas():
        if v.catalogo:
            _codificar(ctx, v, codificador)
        _validar(ctx, v)

    # 7. Reglas específicas y llave única
    for codigo, regla in r.items():
        if codigo in ESPECIFICAS:
            ESPECIFICAS[codigo](ctx, regla)
        elif codigo.endswith("_LLAVE_UNICA"):
            llave_unica(ctx, regla)

    # 8. Salida sin excluidos, con enteros como enteros
    excluir = {i for e in ctx.excluidos for i in e["indices"]}
    salida = ctx.out.drop(index=list(excluir))
    for v in d.publicadas():
        if v.catalogo:
            # Como en las bases del INE: 1 es número, "0101" y "P229" quedan como texto
            salida[v.nombre] = salida[v.nombre].map(_codigo_salida)
        if v.tipo == "entero" and not v.catalogo:
            num = pd.to_numeric(salida[v.nombre], errors="coerce")
            if num.notna().sum() == (~salida[v.nombre].map(_vacio)).sum():
                salida[v.nombre] = num.round().astype("Int64")
    puntajes, global_ = _puntaje(d, ctx.hallazgos, len(raw), len(d.publicadas()))

    return Resultado(
        base=d.codigo, version=d.version, anio=anio, mes=mes,
        total_registros=len(raw), registros_validos=len(salida), registros_excluidos=len(excluir),
        salida=salida.reset_index(drop=True), hallazgos=ctx.hallazgos, cambios=ctx.cambios,
        excluidos=[{k: v for k, v in e.items() if k != "indices"} for e in ctx.excluidos],
        mapeo_columnas=mapeo, hojas=lectura.hojas, puntajes=puntajes, puntaje=global_,
        segundos=round(time.time() - t0, 1),
    )
