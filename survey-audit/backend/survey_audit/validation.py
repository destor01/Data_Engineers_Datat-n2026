"""Validación declarativa de formularios de entrevista. Nunca ejecuta expresiones del instrumento.

Versión 1: preguntas con `visible_when` (piloto original).
Versión 2: formularios generados desde un PDF. Además de `visible_when`, cada opción (o la pregunta
completa) puede tener `pase_a` = {"tipo": "pregunta"|"seccion"|"fin", "destino": id}: si se elige esa
respuesta, las preguntas entre el origen y el destino no aplican. Las secciones con scope "person" se
repiten por cada persona del hogar (`_personas` en las respuestas) y sus respuestas se guardan como
"<id_pregunta>#<n>".
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal

SUPPORTED_TYPES = {'text', 'integer', 'decimal', 'date', 'single_select', 'multi_select'}
OPERATORS = {'eq', 'ne', 'in'}
SCOPES = {'household', 'person'}
MAX_PERSONAS = 40
PERSONAS = '_personas'


def _destinos(template) -> tuple[set, set]:
    return {q.get('id') for q in template.get('questions', [])}, {s.get('id') for s in template.get('sections', [])}


def _check_pase(pase, preguntas: set, secciones: set) -> bool:
    if pase in (None, {}):
        return True
    if not isinstance(pase, dict) or pase.get('tipo') not in {'pregunta', 'seccion', 'fin'}:
        return False
    if pase['tipo'] == 'pregunta':
        return pase.get('destino') in preguntas
    if pase['tipo'] == 'seccion':
        return pase.get('destino') in secciones
    return True


def check_template(template):
    errors = []
    if template.get('schema_version') not in (1, 2):
        errors.append('schema_version debe ser 1 o 2')
    if not template.get('template_code') or type(template.get('version')) is not int or template['version'] < 1:
        errors.append('Código y versión positiva requeridos')
    questions = template.get('questions', [])
    ids = [q.get('id') for q in questions]
    if not questions or any(not isinstance(i, str) or not i or '#' in i for i in ids) or len(set(ids)) != len(ids):
        errors.append('Preguntas con identificadores únicos requeridas')
    section_list = template.get('sections', [])
    sections = {s.get('id') for s in section_list}
    if len(sections) != len(section_list) or any(s.get('scope', 'household') not in SCOPES for s in section_list):
        errors.append('Secciones con identificador único y alcance válido requeridas')
    preguntas, secciones = _destinos(template)
    for q in questions:
        if q.get('type') not in SUPPORTED_TYPES or q.get('section_id') not in sections:
            errors.append(f"{q.get('id')}: tipo o sección inválida")
        if not isinstance(q.get('label'), str) or not q['label'].strip():
            errors.append(f"{q.get('id')}: etiqueta requerida")
        options = q.get('options', [])
        codes = [o.get('code') for o in options]
        if any(not isinstance(c, str) or not c for c in codes) or len(codes) != len(set(codes)):
            errors.append(f"{q.get('id')}: códigos únicos de texto requeridos")
        if q.get('type') in {'single_select', 'multi_select'} and not options:
            errors.append(f"{q.get('id')}: catálogo requerido")
        condition = q.get('visible_when')
        if condition and (condition.get('operator') not in OPERATORS or condition.get('question_id') not in ids[:ids.index(q['id'])]):
            errors.append(f"{q.get('id')}: condición debe referir una pregunta anterior y operador permitido")
        if not _check_pase(q.get('pase_a'), preguntas, secciones) or not all(_check_pase(o.get('pase_a'), preguntas, secciones) for o in options):
            errors.append(f"{q.get('id')}: salto con destino inexistente")
    return errors


def saltos(template) -> dict[str, list[tuple[str, list[str] | None]]]:
    """Para cada pregunta, las condiciones que la hacen no aplicar: [(pregunta_origen, códigos|None)].
    None significa "cualquier respuesta" (salto incondicional después de responder)."""
    questions = template['questions']
    orden = {q['id']: i for i, q in enumerate(questions)}
    primera = {}
    for i, q in enumerate(questions):
        primera.setdefault(q['section_id'], i)
    seccion_de = {s['id']: s.get('scope', 'household') for s in template.get('sections', [])}
    ocultas: dict[str, list] = {}

    def marcar(origen: dict, pase: dict | None, codigos: list[str] | None):
        if not pase:
            return
        i = orden[origen['id']]
        if pase['tipo'] == 'pregunta':
            j = orden.get(pase['destino'], i)
        elif pase['tipo'] == 'seccion':
            j = primera.get(pase['destino'], i)
        else:
            j = len(questions)
        alcance = seccion_de.get(origen['section_id'], 'household')
        for k in range(i + 1, max(i + 1, j)):
            destino = questions[k]
            # Un salto dentro de las preguntas por persona no oculta preguntas del hogar, y viceversa.
            if seccion_de.get(destino['section_id'], 'household') != alcance:
                continue
            ocultas.setdefault(destino['id'], []).append((origen['id'], codigos))

    for q in questions:
        for o in q.get('options', []):
            marcar(q, o.get('pase_a'), [o['code']])
        marcar(q, q.get('pase_a'), None)
    return ocultas


def _instancias(template, responses):
    """Preguntas en orden de captura: (clave_respuesta, pregunta, persona|None)."""
    scope = {s['id']: s.get('scope', 'household') for s in template.get('sections', [])}
    personas = responses.get(PERSONAS)
    n = personas if type(personas) is int and 0 <= personas <= MAX_PERSONAS else 0
    por_seccion: dict[str, list] = {}
    for q in template['questions']:
        por_seccion.setdefault(q['section_id'], []).append(q)
    vistos = []
    for q in template['questions']:
        if q['section_id'] in vistos:
            continue
        vistos.append(q['section_id'])
        grupo = por_seccion[q['section_id']]
        if scope.get(q['section_id'], 'household') == 'person':
            for p in range(1, n + 1):
                for pq in grupo:
                    yield f"{pq['id']}#{p}", pq, p
        else:
            for pq in grupo:
                yield pq['id'], pq, None


def _texto_pregunta(q: dict, persona: int | None) -> str:
    etiqueta = q['label'].strip()
    if len(etiqueta) > 90:
        etiqueta = etiqueta[:87] + '…'
    codigo = f"{q['codigo']}. " if q.get('codigo') else ''
    return f"{'Persona ' + str(persona) + ' · ' if persona else ''}{codigo}{etiqueta}"


def validate(template, responses):
    """Retorna hallazgos y aplicabilidad; conserva respuestas inactivas para trazabilidad."""
    errors = check_template(template)
    if errors:
        raise ValueError('; '.join(errors))
    findings, applicability, active = [], {}, {}
    ocultas = saltos(template) if template.get('schema_version') == 2 else {}
    con_personas = any(s.get('scope') == 'person' for s in template.get('sections', []))

    def issue(key, rule, text, q=None, persona=None):
        findings.append(dict(question_id=key, rule_id=rule, severity='error', message=text,
                             pregunta=_texto_pregunta(q, persona) if q else None))

    if con_personas:
        n = responses.get(PERSONAS)
        if type(n) is not int or not 0 <= n <= MAX_PERSONAS:
            issue(PERSONAS, 'required', f'Indica cuántas personas viven en el hogar (un número entre 0 y {MAX_PERSONAS}).')
    claves = {clave for clave, _, _ in _instancias(template, responses)}
    for key in responses.keys() - claves - {PERSONAS}:
        base = key.split('#')[0]
        if base not in {q['id'] for q in template['questions']}:
            issue(key, 'unknown_question', 'Pregunta desconocida')
    for key, q, persona in _instancias(template, responses):
        qid = q['id']

        def valor_de(origen: str):
            return active.get(f'{origen}#{persona}' if persona and f'{origen}#{persona}' in claves else origen)

        visible = True
        c = q.get('visible_when')
        if c:
            parent = valor_de(c['question_id'])
            expected = c.get('value')
            visible = parent is not None and {'eq': lambda: parent == expected, 'ne': lambda: parent != expected,
                       'in': lambda: isinstance(expected, list) and parent in expected}[c['operator']]()
        for origen, codigos in ocultas.get(qid, []):
            elegido = valor_de(origen)
            if elegido is None:
                continue
            elegidos = elegido if isinstance(elegido, list) else [elegido]
            if codigos is None or any(v in codigos for v in elegidos):
                visible = False
        applicability[key] = 'applicable' if visible else 'not_applicable'
        if not visible:
            continue
        value = responses.get(key)
        if value is None or value == '' or value == []:
            if q.get('required'):
                issue(key, 'required', 'Falta la respuesta.' if template.get('schema_version') == 2 else 'Respuesta requerida', q, persona)
            continue
        kind = q['type']
        codes = {o['code'] for o in q.get('options', [])}
        if kind == 'integer' and type(value) is not int:
            issue(key, 'type', 'Escribe un número entero, sin decimales.' if template.get('schema_version') == 2 else 'Se requiere un entero', q, persona)
        elif kind == 'decimal' and (type(value) not in (int, float) or not Decimal(str(value)).is_finite()):
            issue(key, 'type', 'Escribe una cantidad numérica.', q, persona)
        elif kind == 'text' and not isinstance(value, str):
            issue(key, 'type', 'Escribe la respuesta como texto.', q, persona)
        elif kind == 'date':
            try:
                if not isinstance(value, str) or date.fromisoformat(value).isoformat() != value:
                    raise ValueError()
            except (ValueError, TypeError):
                issue(key, 'type', 'Escribe una fecha válida.', q, persona)
        elif kind == 'single_select' and (not isinstance(value, str) or value not in codes):
            issue(key, 'catalog', 'Elige una de las opciones de la lista.', q, persona)
        elif kind == 'multi_select' and (not isinstance(value, list) or any(not isinstance(v, str) or v not in codes for v in value) or len(value) != len(set(value))):
            issue(key, 'catalog', 'Elige solo opciones de la lista, sin repetir.', q, persona)
        if kind in {'integer', 'decimal'} and type(value) in (int, float):
            limits = q.get('constraints', {})
            if 'min' in limits and value < limits['min'] or 'max' in limits and value > limits['max']:
                rango = ' y '.join(t for t in (f"mayor o igual a {limits['min']}" if 'min' in limits else '',
                                               f"menor o igual a {limits['max']}" if 'max' in limits else '') if t)
                issue(key, 'range', f'El valor debe ser {rango}.', q, persona)
        if not any(f['question_id'] == key for f in findings):
            active[key] = value
    return dict(valid=not findings, findings=findings, applicability=applicability, active_responses=active)
