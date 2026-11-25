"""Carga desde PostgreSQL todo lo que el motor necesita para validar una base.

El motor no lee YAML ni diccionarios: la base de datos es la fuente de verdad.
Así, un umbral o un alias que un analista cambia en el front se usa en la
siguiente ejecución sin tocar código.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .texto import normalizar


@dataclass
class Variable:
    id: int
    nombre: str
    etiqueta: str
    tipo: str
    catalogo: str | None
    requerida: bool
    vmin: float | None
    vmax: float | None
    regex: str | None
    ignorado: str | None
    es_pii: bool
    publica: bool
    transformacion: dict | None
    orden: int
    alias: list[str] = field(default_factory=list)


@dataclass
class ValorCatalogo:
    etiqueta: str
    padre: str | None
    ignorado: bool


@dataclass
class Catalogo:
    codigo: str
    valores: dict[str, ValorCatalogo]
    equivalencias: dict[str, tuple[str, int]]        # texto normalizado -> (código, id de equivalencia)
    pendientes: dict[str, tuple[str, int, float]]    # sugerencias de IA sin aprobar

    def resolver(self, valor: object) -> tuple[str | None, str]:
        """Devuelve (código, cómo): 'codigo' si ya era un código válido, 'equivalencia' si se tradujo."""
        if valor is None:
            return None, "vacio"
        s = str(valor).strip()
        if s.endswith(".0") and s[:-2].lstrip("-").isdigit():
            s = s[:-2]
        if s in self.valores:
            return s, "codigo"
        # Códigos numéricos con o sin ceros a la izquierda ("1" vs "01", "101" vs "0101")
        if s.isdigit():
            for largo in (2, 4):
                if s.zfill(largo) in self.valores:
                    return s.zfill(largo), "codigo"
            if s.lstrip("0") in self.valores:
                return s.lstrip("0"), "codigo"
        n = normalizar(s)
        if n in self.equivalencias:
            return self.equivalencias[n][0], "equivalencia"
        if n.upper() in self.valores:
            return n.upper(), "codigo"
        return None, "desconocido"


@dataclass
class Regla:
    id: int
    codigo: str
    nombre: str
    mensaje: str
    dimension: str
    severidad: str
    accion: str
    parametros: dict


@dataclass
class DefinicionBase:
    tipo_base_id: int
    codigo: str
    institucion_id: int
    version_id: int
    version: str
    formato_crudo: dict | None
    variables: list[Variable]
    catalogos: dict[str, Catalogo]
    reglas: dict[str, Regla]

    def alias(self) -> dict[str, Variable]:
        return {a: v for v in self.variables for a in v.alias}

    def publicadas(self) -> list[Variable]:
        return sorted((v for v in self.variables if v.publica), key=lambda v: v.orden)


def cargar_definicion(cur, codigo_base: str) -> DefinicionBase:
    cur.execute(
        """SELECT t.id, t.institucion_id, ve.id, ve.version, ve.formato_crudo
           FROM tipo_base t JOIN version_esquema ve ON ve.tipo_base_id = t.id AND ve.activa
           WHERE t.codigo = %s""",
        (codigo_base,),
    )
    fila = cur.fetchone()
    if not fila:
        raise ValueError(f"No hay versión activa para la base {codigo_base}. ¿Corriste cargar_config?")
    tipo_base_id, institucion_id, version_id, version, formato = fila

    cur.execute(
        """SELECT v.id, v.nombre_ine, v.etiqueta, v.tipo, c.codigo, v.requerida, v.valor_min, v.valor_max,
                  v.patron_regex, v.codigo_ignorado, v.es_pii, v.se_publica, v.transformacion, v.orden,
                  coalesce(array_agg(a.alias) FILTER (WHERE a.alias IS NOT NULL), '{}')
           FROM variable v
           LEFT JOIN catalogo c ON c.id = v.catalogo_id
           LEFT JOIN alias_columna a ON a.variable_id = v.id
           WHERE v.version_esquema_id = %s
           GROUP BY v.id, c.codigo ORDER BY v.orden""",
        (version_id,),
    )
    variables = [
        Variable(r[0], r[1], r[2], r[3], r[4], r[5],
                 float(r[6]) if r[6] is not None else None, float(r[7]) if r[7] is not None else None,
                 r[8], r[9], r[10], r[11], r[12], r[13], list(r[14]))
        for r in cur.fetchall()
    ]

    # Catálogos que usa la base: los de sus variables y los que nombran sus transformaciones
    usados = {v.catalogo for v in variables if v.catalogo}
    for v in variables:
        if v.transformacion and v.transformacion.get("catalogo"):
            usados.add(v.transformacion["catalogo"])
    usados |= {"DEPARTAMENTO", "MUNICIPIO"}
    catalogos = {}
    for cod in usados:
        cur.execute(
            """SELECT cv.codigo, cv.etiqueta, cv.padre_codigo, cv.es_ignorado
               FROM catalogo_valor cv JOIN catalogo c ON c.id = cv.catalogo_id
               WHERE c.codigo = %s AND cv.activo""",
            (cod,),
        )
        valores = {r[0]: ValorCatalogo(r[1], r[2], r[3]) for r in cur.fetchall()}
        cur.execute(
            """SELECT e.texto_origen, e.codigo, e.id, e.aprobada, coalesce(e.confianza, 0)
               FROM equivalencia e JOIN catalogo c ON c.id = e.catalogo_id
               WHERE c.codigo = %s AND (e.institucion_id IS NULL OR e.institucion_id = %s)
               ORDER BY e.institucion_id NULLS FIRST""",   # las de la institución pisan a las generales
            (cod, institucion_id),
        )
        equiv, pend = {}, {}
        for texto, codigo, eid, aprobada, conf in cur.fetchall():
            if aprobada:
                equiv[texto] = (codigo, eid)
            else:
                pend[texto] = (codigo, eid, float(conf))
        catalogos[cod] = Catalogo(cod, valores, equiv, pend)

    cur.execute(
        """SELECT id, codigo, nombre, coalesce(descripcion, nombre), dimension, severidad, accion, parametros
           FROM regla WHERE activa AND (tipo_base_id IS NULL OR tipo_base_id = %s)""",
        (tipo_base_id,),
    )
    reglas = {r[1]: Regla(r[0], r[1], r[2], r[3], r[4], r[5], r[6], r[7] or {}) for r in cur.fetchall()}

    return DefinicionBase(tipo_base_id, codigo_base, institucion_id, version_id, version, formato,
                          variables, catalogos, reglas)
