"""Validación declarativa del piloto. Nunca ejecuta expresiones del instrumento."""
from datetime import date
from decimal import Decimal, InvalidOperation

SUPPORTED_TYPES = {'text', 'integer', 'decimal', 'date', 'single_select', 'multi_select'}
OPERATORS = {'eq', 'ne', 'in'}


def check_template(template):
    errors = []
    if template.get('schema_version') != 1:
        errors.append('schema_version debe ser 1')
    if not template.get('template_code') or type(template.get('version')) is not int or template['version'] < 1:
        errors.append('Código y versión positiva requeridos')
    questions = template.get('questions', [])
    ids = [q.get('id') for q in questions]
    if not questions or any(not isinstance(i, str) or not i for i in ids) or len(set(ids)) != len(ids):
        errors.append('Preguntas con identificadores únicos requeridas')
    sections = {s['id'] for s in template.get('sections', [])}
    for q in questions:
        if q.get('type') not in SUPPORTED_TYPES or q.get('section_id') not in sections:
            errors.append(f"{q.get('id')}: tipo o sección inválida")
        if not isinstance(q.get('label'), str) or not q['label'].strip():
            errors.append(f"{q.get('id')}: etiqueta requerida")
        options = q.get('options', [])
        codes = [o.get('code') for o in options]
        if any(not isinstance(c, str) for c in codes) or len(codes) != len(set(codes)):
            errors.append(f"{q.get('id')}: códigos únicos de texto requeridos")
        if q.get('type') in {'single_select', 'multi_select'} and not options:
            errors.append(f"{q.get('id')}: catálogo requerido")
        condition = q.get('visible_when')
        if condition and (condition.get('operator') not in OPERATORS or condition.get('question_id') not in ids[:ids.index(q['id'])]):
            errors.append(f"{q.get('id')}: condición debe referir una pregunta anterior y operador permitido")
    return errors


def validate(template, responses):
    """Retorna hallazgos y aplicabilidad; conserva respuestas inactivas para trazabilidad."""
    errors = check_template(template)
    if errors:
        raise ValueError('; '.join(errors))
    findings, applicability, active = [], {}, {}
    def issue(qid, rule, text):
        findings.append(dict(question_id=qid, rule_id=rule, severity='error', message=text))
    known = {q['id'] for q in template['questions']}
    for qid in responses.keys() - known:
        issue(qid, 'unknown_question', 'Pregunta desconocida')
    for q in template['questions']:
        qid = q['id']
        c = q.get('visible_when')
        visible = True
        if c:
            parent = active.get(c['question_id'])
            expected = c.get('value')
            visible = parent is not None and {'eq': lambda: parent == expected, 'ne': lambda: parent != expected,
                       'in': lambda: isinstance(expected, list) and parent in expected}[c['operator']]()
        applicability[qid] = 'applicable' if visible else 'not_applicable'
        if not visible:
            continue
        value = responses.get(qid)
        if value is None or value == '' or value == []:
            if q.get('required'):
                issue(qid, 'required', 'Respuesta requerida')
            continue
        kind = q['type']
        codes = {o['code'] for o in q.get('options', [])}
        if kind == 'integer' and type(value) is not int:
            issue(qid, 'type', 'Se requiere un entero')
        elif kind == 'decimal' and (type(value) not in (int, float) or not Decimal(str(value)).is_finite()):
            issue(qid, 'type', 'Se requiere un decimal finito')
        elif kind == 'text' and not isinstance(value, str):
            issue(qid, 'type', 'Se requiere texto')
        elif kind == 'date':
            try:
                if not isinstance(value, str) or date.fromisoformat(value).isoformat() != value:
                    raise ValueError()
            except (ValueError, TypeError):
                issue(qid, 'type', 'Fecha inválida; usa AAAA-MM-DD')
        elif kind == 'single_select' and (not isinstance(value, str) or value not in codes):
            issue(qid, 'catalog', 'Código fuera del catálogo')
        elif kind == 'multi_select' and (not isinstance(value, list) or any(not isinstance(v, str) or v not in codes for v in value) or len(value) != len(set(value))):
            issue(qid, 'catalog', 'Selección múltiple inválida o duplicada')
        if kind in {'integer', 'decimal'} and type(value) in (int, float):
            limits = q.get('constraints', {})
            if 'min' in limits and value < limits['min'] or 'max' in limits and value > limits['max']:
                issue(qid, 'range', 'Respuesta fuera del rango aprobado')
        if not any(f['question_id'] == qid for f in findings):
            active[qid] = value
    return dict(valid=not findings, findings=findings, applicability=applicability, active_responses=active)
