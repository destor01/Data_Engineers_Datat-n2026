"""Codificador con IA: propone el código oficial para texto libre.

Casos que resuelve:
  PNC_CAUSA         MOTIVO de PNC ("LESIONES CULPOSAS EN HECHO DE TRANSITO") -> 61 causas del INE
  CIE10             causa de muerte escrita por el médico ("Choque séptico") -> código CIE-10
  DEF_SITIO         lugar de la defunción ("Hospital Roosevelt", "Aldea Xesuc") -> 9 tipos de sitio
  OCUPACION_CIUO08  ocupación ("AGRICULTOR") -> subgrupo CIUO-08

Cómo trabaja:
  1. Lo que la similitud de texto resuelve casi seguro (>= 95 %) no se manda a la IA.
  2. El resto va en lotes, con el catálogo (o, para CIE-10, los candidatos más parecidos)
     y un esquema JSON: la respuesta siempre se puede leer.
  3. Cada código se valida contra el catálogo. Un código que no existe se descarta.
  4. Si la IA falla (sin red, sin clave, error), ese lote usa la similitud de texto.

Privacidad: solo se envían los textos distintos de la columna, nunca filas, nombres ni CUI;
las cadenas de 6 o más dígitos se enmascaran. QUIEN_CERTIFICA (trae nombres de médicos)
no está en los catálogos permitidos por defecto.

Toda sugerencia queda pendiente hasta que un analista la aprueba.
"""
from __future__ import annotations

import json
import logging
import os
import re
import urllib.request
from concurrent.futures import ThreadPoolExecutor

from rapidfuzz import fuzz, process

from .codificador import CodificadorSimilitud, Sugerencia
from .definicion import Catalogo
from .texto import normalizar

logger = logging.getLogger("quality_audit.ia")

CATALOGOS_IA = ("PNC_CAUSA", "CIE10", "DEF_SITIO", "OCUPACION_CIUO08")
MAX_LISTA_COMPLETA = 150          # catálogos más grandes se mandan como candidatos por texto
CANDIDATOS_CIE10 = 15

SISTEMA = """Eres codificador estadístico del Instituto Nacional de Estadística (INE) de Guatemala.
Recibes textos libres tal como los escriben las instituciones (con faltas de ortografía, abreviaturas
y mayúsculas) y asignas a cada uno un código del catálogo oficial indicado.

Reglas:
- Usa solo códigos que existan en el catálogo. Nunca inventes un código.
- Si el texto no permite decidir con razonable seguridad, devuelve "codigo": null.
- "confianza" entre 0 y 1, calibrada: 0.95 o más solo si no hay duda; 0.6 a 0.8 si hay que
  interpretar; menos de 0.6 si es una suposición.
- "justificacion": una frase corta en español (máximo 20 palabras) que explique la decisión.
- Devuelve un resultado por cada id recibido, con el mismo id."""

PISTAS = {
    "PNC_CAUSA": """Catálogo: causas de detención de la Policía Nacional Civil.
- Si el texto menciona varios delitos, codifica el más grave y baja la confianza.
- Las variantes de redacción cuentan como la misma causa ("LESIONES CON ARMA BLANCA" = Lesiones por arma blanca).
- Usa 68 "Otras causas (motivo)" para faltas o delitos reales que no tienen causa propia en la lista
  (por ejemplo, responsabilidad de conductores o lesiones culposas de tránsito).""",
    "CIE10": """Catálogo: CIE-10 (OMS). El texto es la causa de muerte escrita por el médico.
- Devuelve el código de 4 caracteres sin punto (R572, I219). Si la categoría no tiene subcategorías,
  agrega X al final, como lo hace el INE (I10X, I64X).
- Prefiere los candidatos que se te dan; puedes usar otro código CIE-10 si es claramente mejor.
- Los paros cardiorrespiratorios y síntomas mal definidos van en el capítulo R (por ejemplo R092, I469).""",
    "DEF_SITIO": """Catálogo: sitio donde ocurrió la defunción.
- Hospitales nacionales, regionales, departamentales o "Roosevelt", "San Juan de Dios" = Hospital público.
- IGSS = Seguro social. Sanatorios y hospitales privados = Hospital privado.
- Aldeas, caseríos, cantones, colonias y direcciones suelen ser el domicilio: usa Domicilio con confianza media.
- Carreteras, kilómetros, calles sin número = Vía pública.""",
    "OCUPACION_CIUO08": """Catálogo: subgrupos principales de la CIUO-08 (2 dígitos).
- "Ama de casa", "estudiante", "jubilado" no son ocupaciones: devuelve null.""",
}


def _enmascarar(texto: str) -> str:
    return re.sub(r"\d{6,}", "######", texto)


def _esquema(codigos: list[str] | None) -> dict:
    codigo = {"anyOf": [{"type": "string", "enum": codigos}, {"type": "null"}]} if codigos else \
             {"anyOf": [{"type": "string"}, {"type": "null"}]}
    return {
        "type": "object",
        "properties": {"resultados": {"type": "array", "items": {
            "type": "object",
            "properties": {"id": {"type": "integer"}, "codigo": codigo,
                           "confianza": {"type": "number"}, "justificacion": {"type": "string"}},
            "required": ["id", "codigo", "confianza", "justificacion"],
            "additionalProperties": False}}},
        "required": ["resultados"],
        "additionalProperties": False,
    }


# ---------------------------------------------------------------------------
# Proveedores: reciben (sistema, mensaje, esquema) y devuelven el JSON como dict
# ---------------------------------------------------------------------------
class ProveedorAnthropic:
    def __init__(self, modelo: str, api_key: str | None = None):
        import anthropic
        self.modelo = modelo
        self.cliente = anthropic.Anthropic(api_key=api_key) if api_key else anthropic.Anthropic()

    def __call__(self, sistema: str, mensaje: str, esquema: dict) -> dict:
        r = self.cliente.messages.create(
            model=self.modelo, max_tokens=8000, system=sistema,
            messages=[{"role": "user", "content": mensaje}],
            output_config={"format": {"type": "json_schema", "schema": esquema}},
        )
        texto = next(b.text for b in r.content if b.type == "text")
        return json.loads(texto)


class ProveedorOllama:
    """Modelo local con Ollama (https://ollama.com): nada sale de la computadora."""

    def __init__(self, modelo: str, url: str = "http://localhost:11434"):
        self.modelo, self.url = modelo, url.rstrip("/")

    def __call__(self, sistema: str, mensaje: str, esquema: dict) -> dict:
        cuerpo = json.dumps({"model": self.modelo, "stream": False, "format": esquema,
                             "options": {"temperature": 0},
                             "messages": [{"role": "system", "content": sistema},
                                          {"role": "user", "content": mensaje}]}).encode()
        req = urllib.request.Request(f"{self.url}/api/chat", data=cuerpo,
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=300) as resp:
            return json.loads(json.loads(resp.read())["message"]["content"])


# ---------------------------------------------------------------------------
class CodificadorIA:
    nombre = "ia"

    def __init__(self, proveedor, catalogos=CATALOGOS_IA, lote: int = 40, paralelo: int = 4,
                 respaldo: CodificadorSimilitud | None = None, umbral_directo: float = 0.95):
        self.proveedor = proveedor
        self.catalogos = set(catalogos)
        self.lote = lote
        self.paralelo = paralelo
        self.respaldo = respaldo or CodificadorSimilitud(minimo=0.8)
        self.umbral_directo = umbral_directo
        self.estadisticas = {"directas": 0, "ia": 0, "sin_codigo": 0, "invalidas": 0, "lotes_fallidos": 0}

    # -- validación de códigos --
    @staticmethod
    def _normalizar_codigo(catalogo: Catalogo, codigo) -> str | None:
        if codigo is None:
            return None
        c = str(codigo).strip().upper().replace(".", "")
        if c in catalogo.valores:
            return c
        if c.isdigit():
            for cand in (c.lstrip("0") or "0", c.zfill(2), c.zfill(4)):
                if cand in catalogo.valores:
                    return cand
        if catalogo.codigo == "CIE10":
            # El INE escribe las categorías sin subcategoría con X al final: I10 -> I10X
            if len(c) == 3 and c + "X" in catalogo.valores:
                return c + "X"
            if len(c) == 4 and c.endswith("X") and c[:3] in catalogo.valores:
                return c[:3]
        return None

    def _mensaje(self, catalogo: Catalogo, items: list[tuple[int, str]]) -> tuple[str, list[str] | None]:
        partes = [PISTAS.get(catalogo.codigo, f"Catálogo: {catalogo.codigo}.")]
        validos = {c: v for c, v in catalogo.valores.items() if not v.ignorado}
        if len(validos) <= MAX_LISTA_COMPLETA:
            partes.append("Códigos permitidos:\n" + "\n".join(f"{c}: {v.etiqueta}" for c, v in validos.items()))
            datos = [{"id": i, "texto": _enmascarar(t)} for i, t in items]
            # Los códigos van en las instrucciones, no como enum en el esquema: con enum el modelo
            # respondió mal (un solo resultado "placeholder"). La validación posterior basta.
            enum = None
        else:
            etiquetas = {normalizar(v.etiqueta): c for c, v in validos.items()}
            claves = list(etiquetas)
            datos = []
            for i, t in items:
                top = process.extract(normalizar(t), claves, scorer=fuzz.token_set_ratio, limit=CANDIDATOS_CIE10)
                datos.append({"id": i, "texto": _enmascarar(t),
                              "candidatos": [f"{etiquetas[k]}: {validos[etiquetas[k]].etiqueta}" for k, _, _ in top]})
            enum = None
        partes.append("Textos a codificar (JSON):\n" + json.dumps(datos, ensure_ascii=False))
        return "\n\n".join(partes), enum

    def _lote(self, catalogo: Catalogo, items: list[tuple[int, str]], intento: int = 1) -> dict[str, Sugerencia]:
        mensaje, enum = self._mensaje(catalogo, items)
        try:
            resp = self.proveedor(SISTEMA, mensaje, _esquema(enum))
        except Exception as exc:  # noqa: BLE001 - un lote fallido no detiene la carga
            logger.warning("Lote de IA fallido (%s): %s. Se usa similitud de texto.", catalogo.codigo, exc)
            self.estadisticas["lotes_fallidos"] += 1
            return self.respaldo.sugerir(catalogo, [t for _, t in items])
        por_id = dict(items)
        salida, respondidos = {}, set()
        for r in resp.get("resultados", []):
            texto = por_id.get(r.get("id"))
            if texto is None:
                continue
            respondidos.add(r["id"])
            justif = (r.get("justificacion") or "").strip()
            if r.get("codigo") is None or not justif or justif.lower() == "placeholder":
                self.estadisticas["sin_codigo"] += 1
                continue
            codigo = self._normalizar_codigo(catalogo, r["codigo"])
            if codigo is None:
                self.estadisticas["invalidas"] += 1
                continue
            conf = max(0.0, min(1.0, float(r.get("confianza") or 0)))
            etq = catalogo.valores[codigo].etiqueta
            salida[texto] = Sugerencia(codigo, round(conf, 3), f"IA: {justif} ({codigo} {etq})")
            self.estadisticas["ia"] += 1
        # Textos que la respuesta omitió: se piden de nuevo una vez
        faltan = [(i, t) for i, t in items if i not in respondidos]
        if faltan:
            self.estadisticas.setdefault("omitidos", 0)
            self.estadisticas["omitidos"] += len(faltan)
            if intento == 1:
                salida.update(self._lote(catalogo, faltan, intento=2))
        return salida

    def sugerir(self, catalogo: Catalogo, textos: list[str], contexto=None) -> dict[str, Sugerencia]:
        if catalogo.codigo not in self.catalogos or not textos:
            return self.respaldo.sugerir(catalogo, textos)
        salida: dict[str, Sugerencia] = {}
        # 1. Casi idénticos a una etiqueta o a un texto aprobado: no hace falta la IA
        for t, s in self.respaldo.sugerir(catalogo, textos).items():
            if s.confianza >= self.umbral_directo:
                salida[t] = s
                self.estadisticas["directas"] += 1
        faltan = [t for t in textos if t not in salida]
        # 2. El resto, por lotes en paralelo
        items = list(enumerate(faltan))
        lotes = [items[i:i + self.lote] for i in range(0, len(items), self.lote)]
        with ThreadPoolExecutor(max_workers=self.paralelo) as ex:
            for parcial in ex.map(lambda lt: self._lote(catalogo, lt), lotes):
                salida.update(parcial)
        logger.info("Codificación IA %s: %s", catalogo.codigo, self.estadisticas)
        return salida


def crear_codificador():
    """Arma el codificador según el entorno:
    QA_IA_PROVEEDOR   anthropic | ollama | ninguno (por defecto: anthropic si hay ANTHROPIC_API_KEY)
    QA_IA_MODELO      claude-haiku-5-5 (anthropic) o el modelo de Ollama, p. ej. qwen2.5:14b
    QA_IA_CATALOGOS   catálogos que se mandan a la IA (por defecto PNC_CAUSA,CIE10,DEF_SITIO,OCUPACION_CIUO08)
    QA_IA_LOTE, QA_IA_PARALELO, OLLAMA_URL
    """
    proveedor = (os.environ.get("QA_IA_PROVEEDOR") or ("anthropic" if os.environ.get("ANTHROPIC_API_KEY") else
                                                        "ninguno")).lower()
    if proveedor == "ninguno":
        return CodificadorSimilitud(minimo=0.8)
    catalogos = [c.strip() for c in (os.environ.get("QA_IA_CATALOGOS") or ",".join(CATALOGOS_IA)).split(",") if c.strip()]
    lote = int(os.environ.get("QA_IA_LOTE") or 40)
    paralelo = int(os.environ.get("QA_IA_PARALELO") or 4)
    if proveedor == "anthropic":
        if not os.environ.get("ANTHROPIC_API_KEY"):
            logger.warning("QA_IA_PROVEEDOR=anthropic sin ANTHROPIC_API_KEY: se usa similitud de texto.")
            return CodificadorSimilitud(minimo=0.8)
        p = ProveedorAnthropic(os.environ.get("QA_IA_MODELO") or "claude-haiku-5-5")
    elif proveedor == "ollama":
        p = ProveedorOllama(os.environ.get("QA_IA_MODELO") or "qwen2.5:14b",
                            os.environ.get("OLLAMA_URL") or "http://localhost:11434")
        paralelo = 1
    else:
        raise ValueError(f"QA_IA_PROVEEDOR desconocido: {proveedor}")
    return CodificadorIA(p, catalogos=catalogos, lote=lote, paralelo=paralelo)
