"""Adaptador de reportes y manuales sin copiar mensajes ni ejemplos con posibles datos personales."""
import hashlib
import json
from pathlib import Path
from fastapi import APIRouter, HTTPException
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field
from .api import find, identifier, now, event
from .repository import transaction

router = APIRouter(prefix='/api/improvement', tags=['Quality Improvement'])
INSTITUTIONS = json.loads((Path(__file__).resolve().parents[3] / 'quality-improvement/templates/institutions.json').read_text(encoding='utf-8'))


class Report(BaseModel):
    institution: str
    report: dict
    synthetic: bool = False
    source_run_ref: str = Field(min_length=1, max_length=150)
    source_run_at: str = Field(min_length=1, max_length=50)


class Manual(BaseModel):
    institution: str
    title: str = Field(min_length=3, max_length=200)
    content: str = Field(min_length=10, max_length=100000)
    source_ids: list[str] = []


class ManualEdit(BaseModel):
    title: str = Field(min_length=3, max_length=200)
    content: str = Field(min_length=10, max_length=100000)


@router.get('/institutions')
def institutions():
    return [dict(key=k, action=v) for k, v in INSTITUTIONS.items()]


@router.get('/recommendations')
def recommendations():
    with transaction() as state:
        return list(state['recommendations'].values())


@router.post('/reports')
def ingest(body: Report):
    if body.institution not in INSTITUTIONS:
        raise HTTPException(422, 'Institución no configurada')
    report = body.report
    if not isinstance(report.get('hallazgos'), list) or len(report['hallazgos']) > 10000:
        raise HTTPException(422, 'Se requiere reporte.json de Data Audit con hallazgos')
    total = report.get('total_registros')
    if total is not None and (type(total) is not int or total < 0):
        raise HTTPException(422, 'Denominador inválido')
    digest = hashlib.sha256(json.dumps(report, sort_keys=True).encode()).hexdigest()
    generated = []
    for h in report['hallazgos']:
        # No conservar ejemplos, detalle, mensajes ni valores crudos del reporte.
        if not isinstance(h, dict) or type(h.get('n')) is not int or h['n'] < 0 or h.get('severidad') not in {'error', 'advertencia', 'info'}:
            raise HTTPException(422, 'Hallazgo incompatible con contrato real de Data Audit')
        rule = h.get('regla')
        if not isinstance(rule, str) or len(rule) > 100 or not rule.replace('_', '').replace('-', '').replace('.', '').isalnum():
            raise HTTPException(422, 'Identificador de regla inválido')
        key = hashlib.sha256(f'{body.institution}:{body.source_run_ref}:{digest}:{rule}:{h.get("columna", "")}'.encode()).hexdigest()
        generated.append(dict(id=key, institution=body.institution, rule=rule, severity=h['severidad'], count=h['n'],
            denominator=total, rate=None, rate_reason='Unidad de conteo de la regla pendiente de confirmar; no se asume que hallazgos sean registros únicos.',
            source_hash=digest, source_run_ref=body.source_run_ref, source_run_at=body.source_run_at,
            synthetic=body.synthetic, action=INSTITUTIONS[body.institution],
            hypothesis='Posible falta de validación antes del envío; requiere comprobación institucional.',
            owner='Responsable de calidad propuesto', indicator='Conteo de hallazgos de la misma regla en el siguiente periodo comparable',
            priority='alta' if h['severidad'] == 'error' else 'media' if h['severidad'] == 'advertencia' else 'baja',
            status='pending_review', created_at=now()))
    with transaction() as state:
        for item in generated:
            if item['id'] not in state['recommendations']:
                state['recommendations'][item['id']] = item
        return [state['recommendations'][r['id']] for r in generated]


@router.get('/manuals')
def manuals():
    with transaction() as state:
        return list(state['manuals'].values())


@router.post('/manuals')
def create_manual(body: Manual):
    if body.institution not in INSTITUTIONS:
        raise HTTPException(422, 'Institución no configurada')
    with transaction() as state:
        for key in body.source_ids:
            source = find(state, 'recommendations', key)
            if source['institution'] != body.institution:
                raise HTTPException(422, 'Fuente de otra institución')
        item = dict(id=identifier(), institution=body.institution, title=body.title, content=body.content,
                    source_ids=body.source_ids, status='draft', created_at=now(),
                    version=1 + max((m['version'] for m in state['manuals'].values() if m['institution'] == body.institution), default=0))
        event(item, 'manual_created')
        state['manuals'][item['id']] = item
        return item


@router.patch('/manuals/{key}')
def edit_manual(key: str, body: ManualEdit):
    with transaction() as state:
        item = find(state, 'manuals', key)
        if item['status'] != 'draft':
            raise HTTPException(409, 'Manual aprobado inmutable; crea una versión nueva')
        item.update(title=body.title, content=body.content)
        event(item, 'manual_edited')
        return item


@router.post('/manuals/{key}/approve')
def approve(key: str):
    with transaction() as state:
        item = find(state, 'manuals', key)
        item['status'] = 'approved'
        event(item, 'technical_approval')
        return item


@router.get('/manuals/{key}/download', response_class=PlainTextResponse)
def download(key: str):
    with transaction() as state:
        item = find(state, 'manuals', key)
        text = ('Propuesta técnica de Quality Audit — pendiente de validación institucional\n\n'
                f"{item['title']}\nInstitución: {item['institution']} · Versión: {item['version']}\n\n{item['content']}\n")
        return PlainTextResponse(text, headers={'Content-Disposition': f'attachment; filename="manual-{item["id"]}.md"'})
