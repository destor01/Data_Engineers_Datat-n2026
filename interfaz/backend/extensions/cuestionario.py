"""Convierte un cuestionario en PDF en un formulario digital (Survey Audit).

1. El PDF se divide en bloques de pocas páginas (SURVEY_PAGINAS_BLOQUE, 2 por defecto) para que cada
   lectura termine dentro del límite de tiempo de Vercel.
2. Claude lee cada bloque como PDF: recibe el texto y la imagen de cada página, así que también
   reconoce páginas escaneadas (OCR). Devuelve secciones, preguntas, opciones con sus códigos,
   instrucciones y saltos ("Pase a…") tal como aparecen impresos.
3. `armar_formulario` une los bloques: secciones repetidas, preguntas cortadas entre páginas,
   catálogos de códigos impresos en otras páginas, y resuelve cada salto a una pregunta o sección.
   Los saltos que no se pueden resolver quedan marcados para revisión.
"""
from __future__ import annotations

import io
import os
import re
import unicodedata

from . import ia

TIPOS = {'texto': 'text', 'entero': 'integer', 'decimal': 'decimal', 'fecha': 'date',
         'opcion_unica': 'single_select', 'opcion_multiple': 'multi_select'}

_PASE = {"type": "object", "additionalProperties": False, "required": ["tipo", "referencia"],
         "properties": {"tipo": {"type": "string", "enum": ["ninguno", "pregunta", "seccion", "fin"]},
                        "referencia": {"type": "string"}}}
ESQUEMA = {
    "type": "object", "additionalProperties": False, "required": ["secciones", "preguntas", "catalogos"],
    "properties": {
        "secciones": {"type": "array", "items": {
            "type": "object", "additionalProperties": False,
            "required": ["titulo", "alcance", "informante", "instrucciones"],
            "properties": {"titulo": {"type": "string"}, "alcance": {"type": "string", "enum": ["hogar", "persona"]},
                           "informante": {"type": "string"}, "instrucciones": {"type": "string"}}}},
        "preguntas": {"type": "array", "items": {
            "type": "object", "additionalProperties": False,
            "required": ["codigo", "seccion", "texto", "tipo", "obligatoria", "opciones", "pase_a", "instrucciones",
                         "minimo", "maximo", "catalogo", "pagina"],
            "properties": {
                "codigo": {"type": "string"}, "seccion": {"type": "string"}, "texto": {"type": "string"},
                "tipo": {"type": "string", "enum": list(TIPOS)}, "obligatoria": {"type": "boolean"},
                "opciones": {"type": "array", "items": {
                    "type": "object", "additionalProperties": False, "required": ["codigo", "texto", "pase_a"],
                    "properties": {"codigo": {"type": "string"}, "texto": {"type": "string"}, "pase_a": _PASE}}},
                "pase_a": _PASE, "instrucciones": {"type": "string"}, "minimo": {"type": "string"},
                "maximo": {"type": "string"}, "catalogo": {"type": "string"}, "pagina": {"type": "integer"}}}},
        "catalogos": {"type": "array", "items": {
            "type": "object", "additionalProperties": False, "required": ["titulo", "opciones"],
            "properties": {"titulo": {"type": "string"}, "opciones": {"type": "array", "items": {
                "type": "object", "additionalProperties": False, "required": ["codigo", "texto"],
                "properties": {"codigo": {"type": "string"}, "texto": {"type": "string"}}}}}}},
    }}

SISTEMA = """Conviertes páginas de un cuestionario de encuesta (boleta) en un formulario digital.
Recibes algunas páginas de un documento más largo; extrae TODO lo que aparece en ellas, en el orden de lectura.

Reglas:
- Incluye cada pregunta que se le hace al informante. No resumas, no omitas y no inventes preguntas.
- Tablas y matrices: convierte cada fila y cada columna que pide un dato distinto en preguntas separadas.
  Ejemplo: una tabla de artículos del hogar con columnas "¿posee?", "¿cuántos?" y "¿cuánto pagó?" genera
  esas tres preguntas para cada artículo, con el nombre del artículo en el texto.
- "codigo": el número o código impreso de la pregunta (p. ej. "1", "2a", "P15"). En filas de una tabla,
  combina el código de la pregunta con el de la fila (p. ej. "J1-03"). Vacío si no hay.
- "seccion": capítulo y sección como aparecen impresos, p. ej.
  "Capítulo I. La vivienda y el hogar - Sección A: Características de la vivienda". Usa exactamente el
  mismo texto en "secciones" y en cada pregunta. Si la página dice "continuación", usa el título original.
- "alcance": "persona" si la sección se pregunta a cada miembro del hogar (listados con una columna o fila
  por persona, "para personas de X años o más", informante directo); si no, "hogar".
- "tipo": opcion_unica cuando hay opciones con código; opcion_multiple si indica "marque todas las que
  apliquen"; entero para cantidades y números; decimal para montos en quetzales o medidas; fecha para
  fechas; texto para respuestas abiertas, "Otro, especifique" y nombres.
- "opciones": código exactamente como está impreso (respeta ceros a la izquierda: "01") y texto sin los
  puntos de relleno. Si las opciones están en una lista de códigos de otra página ("ver códigos de
  ocupación"), deja "opciones" vacío y escribe el nombre de esa lista en "catalogo".
- "pase_a": saltos impresos ("Pase a la pregunta 8", "Pase a sección B", "Pase a capítulo XV",
  "Fin de la entrevista"). En la opción que lo provoca o, si aplica a cualquier respuesta, en la pregunta.
  "referencia" es lo impreso (p. ej. "8", "Sección B", "Capítulo XV"). Si no hay salto: tipo "ninguno".
- "instrucciones": indicaciones para el encuestador cerca de la pregunta ("Lea las opciones", "Si tiene
  más de uno refiérase al más nuevo"). "informante": quién responde la sección, si está impreso.
- "obligatoria": true salvo que la pregunta sea opcional o de observaciones.
- "minimo"/"maximo": solo si el cuestionario indica un rango; si no, texto vacío.
- "catalogos": listas de códigos impresas en estas páginas (p. ej. "Códigos de organizaciones").
- "pagina": número de página del documento original (se indica abajo).
- Ignora portadas, encabezados, pies de página, cuadros de control y texto legal."""


def paginas_por_bloque() -> int:
    try:
        return max(1, min(10, int(os.environ.get('SURVEY_PAGINAS_BLOQUE') or 2)))
    except ValueError:
        return 2


def contar_paginas(datos: bytes) -> int:
    from pypdf import PdfReader
    lector = PdfReader(io.BytesIO(datos))
    if lector.is_encrypted:
        raise ValueError('El PDF está protegido con contraseña. Guárdalo sin protección y vuelve a subirlo.')
    return len(lector.pages)


def extraer_paginas(datos: bytes, desde: int, hasta: int) -> bytes:
    from pypdf import PdfReader, PdfWriter
    lector = PdfReader(io.BytesIO(datos))
    escritor = PdfWriter()
    for i in range(desde - 1, hasta):
        escritor.add_page(lector.pages[i])
    salida = io.BytesIO()
    escritor.write(salida)
    return salida.getvalue()


def leer_bloque(datos: bytes, desde: int, hasta: int, total: int, nombre: str) -> dict:
    parte = extraer_paginas(datos, desde, hasta)
    instruccion = (f'Documento: «{nombre}» ({total} páginas). Estas son las páginas {desde} a {hasta}; '
                   f'la primera página adjunta es la página {desde} del documento. Extrae su contenido.')
    r = ia.generar('SURVEY_IA_MODELO', SISTEMA, [ia.pdf(parte), {"type": "text", "text": instruccion}], ESQUEMA,
                   max_tokens=32000)
    for p in r.get('preguntas', []):
        if not isinstance(p.get('pagina'), int) or not desde <= p['pagina'] <= hasta:
            p['pagina'] = desde
    return r


# ---------------------------------------------------------------------------
# Unión de bloques
# ---------------------------------------------------------------------------
def _norm(texto: str) -> str:
    t = unicodedata.normalize('NFKD', texto or '').encode('ascii', 'ignore').decode().lower()
    t = re.sub(r'\b(continuacion|continua|cont)\b\.*', ' ', t)
    t = re.sub(r'[^a-z0-9]+', ' ', t)
    return ' '.join(t.split())


def _codigo(texto: str) -> str:
    t = _norm(texto)
    t = re.sub(r'^(pregunta|preg|p|no|numero)\s+', '', t)
    return t.replace(' ', '')


def _entero(texto: str):
    try:
        v = float(str(texto).replace(',', '').strip())
        return int(v) if v.is_integer() else v
    except ValueError:
        return None


def armar_formulario(bloques: list[dict], nombre: str, codigo_plantilla: str, origen: dict) -> dict:
    secciones: list[dict] = []
    seccion_id: dict[str, str] = {}
    catalogos: dict[str, list[dict]] = {}
    crudas: list[tuple[dict, str]] = []

    for bloque in bloques:
        for s in bloque.get('secciones', []):
            clave = _norm(s.get('titulo', ''))
            if clave and clave not in seccion_id:
                seccion_id[clave] = f's{len(secciones) + 1:03d}'
                secciones.append(dict(id=seccion_id[clave], label=s['titulo'].strip()[:300],
                                      scope='person' if s.get('alcance') == 'persona' else 'household',
                                      informante=(s.get('informante') or '').strip()[:200],
                                      instrucciones=(s.get('instrucciones') or '').strip()[:1000]))
        for c in bloque.get('catalogos', []):
            ops = [o for o in c.get('opciones', []) if str(o.get('codigo', '')).strip()]
            if ops:
                catalogos.setdefault(_norm(c.get('titulo', '')), ops)
        anteriores = {(_norm(p['seccion']), _codigo(p['codigo']), _norm(p['texto'])) for p, _ in crudas[-15:]}
        for p in bloque.get('preguntas', []):
            if not (p.get('texto') or '').strip():
                continue
            if (_norm(p.get('seccion', '')), _codigo(p.get('codigo', '')), _norm(p['texto'])) in anteriores:
                continue  # pregunta cortada entre dos bloques
            clave = _norm(p.get('seccion', ''))
            if clave not in seccion_id:
                seccion_id[clave] = f's{len(secciones) + 1:03d}'
                secciones.append(dict(id=seccion_id[clave], label=(p.get('seccion') or 'Sin sección').strip()[:300],
                                      scope='household', informante='', instrucciones=''))
            crudas.append((p, seccion_id[clave]))

    if not crudas:
        raise ValueError('No se encontraron preguntas en el documento. Revisa que el PDF sea un cuestionario.')

    preguntas: list[dict] = []
    for i, (p, sid) in enumerate(crudas, 1):
        q = dict(id=f'q{i:04d}', codigo=(p.get('codigo') or '').strip()[:40], section_id=sid,
                 label=p['texto'].strip()[:1000], type=TIPOS.get(p.get('tipo'), 'text'),
                 required=bool(p.get('obligatoria', True)), instrucciones=(p.get('instrucciones') or '').strip()[:1000],
                 pagina=p.get('pagina'), alertas=[])
        opciones, vistos = [], set()
        for o in p.get('opciones', []):
            code = str(o.get('codigo', '')).strip()[:20]
            if code and code not in vistos:
                vistos.add(code)
                opciones.append(dict(code=code, label=(o.get('texto') or code).strip()[:300], _pase=o.get('pase_a')))
        if not opciones and (p.get('catalogo') or '').strip():
            ref = _norm(p['catalogo'])
            lista = next((v for k, v in catalogos.items() if ref and (ref in k or k in ref)), None)
            if lista:
                opciones = [dict(code=str(o['codigo']).strip()[:20], label=o['texto'].strip()[:300], _pase=None)
                            for o in lista]
                opciones = list({o['code']: o for o in opciones}.values())
            else:
                q['alertas'].append(f'Las opciones están en la lista «{p["catalogo"]}», que no se encontró en el documento. Agrégalas a mano.')
        if q['type'] in {'single_select', 'multi_select'} and not opciones:
            q['type'] = 'text'
        q['options'] = opciones
        minimo, maximo = _entero(p.get('minimo', '')), _entero(p.get('maximo', ''))
        if q['type'] in {'integer', 'decimal'} and (minimo is not None or maximo is not None):
            q['constraints'] = {k: v for k, v in (('min', minimo), ('max', maximo)) if v is not None}
        q['_pase'] = p.get('pase_a')
        preguntas.append(q)

    _resolver_saltos(preguntas, secciones)
    for q in preguntas:
        if not q['alertas']:
            del q['alertas']
    return {'schema_version': 2, 'template_code': codigo_plantilla, 'nombre': nombre, 'version': 1,
            'status': 'draft', 'origen': origen, 'sections': secciones, 'questions': preguntas}


def _resolver_saltos(preguntas: list[dict], secciones: list[dict]) -> None:
    orden_seccion = {s['id']: i for i, s in enumerate(secciones)}
    titulo = {s['id']: _norm(s['label']) for s in secciones}

    def capitulo(sid: str) -> str:
        m = re.match(r'(capitulo [ivxlcdm0-9]+)', titulo[sid])
        return m.group(1) if m else ''

    def resolver(i: int, pase: dict | None, origen_texto: str):
        if not isinstance(pase, dict) or pase.get('tipo') in (None, 'ninguno'):
            return None
        ref = (pase.get('referencia') or '').strip()
        q = preguntas[i]
        if pase['tipo'] == 'fin':
            return {'tipo': 'fin'}
        if pase['tipo'] == 'pregunta':
            buscado = _codigo(ref)
            candidatos = [j for j in range(i + 1, len(preguntas)) if buscado and _codigo(preguntas[j]['codigo']) in
                          (buscado, ) or (buscado and _codigo(preguntas[j]['codigo']).split('-')[0] == buscado)]
            misma = [j for j in candidatos if preguntas[j]['section_id'] == q['section_id']]
            mismo_cap = [j for j in candidatos if capitulo(preguntas[j]['section_id']) == capitulo(q['section_id'])]
            j = (misma or mismo_cap or candidatos or [None])[0]
            if j is not None:
                return {'tipo': 'pregunta', 'destino': preguntas[j]['id']}
        if pase['tipo'] in ('seccion', 'pregunta'):
            r = _norm(ref)
            letra = re.search(r'seccion ([a-z0-9]+)\b', r)
            cap = re.search(r'capitulo ([ivxlcdm0-9]+)\b', r)
            posteriores = [s for s in secciones if orden_seccion[s['id']] > orden_seccion[q['section_id']]]
            for s in posteriores:
                t = titulo[s['id']]
                if (cap and re.search(rf'capitulo {cap.group(1)}\b', t) and not letra) or \
                   (letra and re.search(rf'seccion {letra.group(1)}\b', t) and (not cap or f'capitulo {cap.group(1)}' in t
                                                                              or capitulo(s['id']) == capitulo(q['section_id']))) or \
                   (not cap and not letra and r and r in t):
                    return {'tipo': 'seccion', 'destino': s['id']}
        q['alertas'].append(f'No se encontró a dónde lleva el salto «Pase a {ref or "…"}»{origen_texto}. Revísalo.')
        return None

    for i, q in enumerate(preguntas):
        for o in q['options']:
            destino = resolver(i, o.pop('_pase', None), f' de la opción {o["code"]}')
            if destino:
                o['pase_a'] = destino
        destino = resolver(i, q.pop('_pase', None), '')
        if destino:
            q['pase_a'] = destino
