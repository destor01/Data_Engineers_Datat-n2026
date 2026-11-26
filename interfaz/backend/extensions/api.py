"""Flujos locales de instrumentos, captura, evidencia y mejora institucional."""
from datetime import datetime, timezone
import hashlib
import io
import json
from pathlib import Path
import sys
import uuid

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field
from .repository import transaction

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / 'survey-audit/backend'))
from survey_audit.validation import check_template, validate

router = APIRouter(prefix='/api', tags=['Quality extensions'])


def now():
    return datetime.now(timezone.utc).isoformat()


def identifier():
    return str(uuid.uuid4())


def find(state, table, key):
    item = state[table].get(key)
    if not item:
        raise HTTPException(404, 'Recurso no encontrado')
    return item


def event(item, action, actor='operador local'):
    item.setdefault('events', []).append(dict(action=action, actor=actor, at=now()))


class TemplatePayload(BaseModel):
    schema_data: dict


class Answers(BaseModel):
    responses: dict
    revision: int = Field(ge=1)


class CreateInterview(BaseModel):
    template_id: str


class Evidence(BaseModel):
    question_id: str
    turn_ids: list[int]
    observed_value: str | int | float | list[str] | None = None
    interviewer: str = Field(min_length=1, max_length=100)


class Review(BaseModel):
    state: str
    justification: str = Field(min_length=3, max_length=1000)


@router.get('/extensions/status')
def status():
    import os
    with transaction() as state:
        counts = {key: len(value) for key, value in state.items()}
    return dict(storage='demo' if os.environ.get('QA_STORAGE') == 'demo' else 'postgres', counts=counts,
                authentication='local_only', at=now())


@router.get('/surveys/templates')
def templates():
    with transaction() as state:
        return list(state['templates'].values())


@router.post('/surveys/templates')
def create_template(body: TemplatePayload):
    schema = body.schema_data
    try:
        errors = check_template(schema)
    except (TypeError, KeyError, AttributeError, ValueError):
        raise HTTPException(422, 'Estructura de instrumento inválida') from None
    if errors:
        raise HTTPException(422, errors)
    item = dict(id=identifier(), schema=schema, status='draft', created_at=now(), revision=1)
    item['schema']['status'] = 'draft'
    with transaction() as state:
        for existing in state['templates'].values():
            if (existing['schema']['template_code'], existing['schema']['version']) == (schema['template_code'], schema['version']):
                raise HTTPException(409, 'Ya existe ese código y versión. Crea una versión siguiente.')
        event(item, 'created')
        state['templates'][item['id']] = item
    return item


@router.patch('/surveys/templates/{key}')
def edit_template(key: str, body: TemplatePayload):
    try:
        errors = check_template(body.schema_data)
    except (TypeError, KeyError, AttributeError, ValueError):
        raise HTTPException(422, 'Estructura inválida') from None
    if errors:
        raise HTTPException(422, errors)
    with transaction() as state:
        item = find(state, 'templates', key)
        if item['status'] != 'draft':
            raise HTTPException(409, 'La versión publicada es inmutable. Crea una versión nueva.')
        if any(other['id'] != key and (other['schema']['template_code'], other['schema']['version']) == (body.schema_data['template_code'], body.schema_data['version']) for other in state['templates'].values()):
            raise HTTPException(409, 'Código y versión duplicados')
        item['schema'] = body.schema_data
        item['schema']['status'] = 'draft'
        item['revision'] += 1
        event(item, 'edited')
        return item


@router.post('/surveys/templates/{key}/publish')
def publish(key: str):
    with transaction() as state:
        item = find(state, 'templates', key)
        if item['status'] == 'published':
            return item
        item['status'] = item['schema']['status'] = 'published'
        item['hash'] = hashlib.sha256(json.dumps(item['schema'], sort_keys=True).encode()).hexdigest()
        event(item, 'published')
        return item


@router.post('/surveys/import')
async def import_pdf(file: UploadFile = File(...)):
    data = await file.read(20 * 1024 * 1024 + 1)
    await file.close()
    if len(data) > 20 * 1024 * 1024:
        raise HTTPException(413, 'Máximo 20 MB')
    if not data.startswith(b'%PDF-'):
        raise HTTPException(422, 'Se requiere contenido PDF válido')
    digest = hashlib.sha256(data).hexdigest()
    with transaction() as state:
        existing = next((d for d in state['documents'].values() if d['hash'] == digest), None)
        if existing:
            return existing
    from pypdf import PdfReader
    try:
        reader = PdfReader(io.BytesIO(data))
        if reader.is_encrypted or len(reader.pages) > 600:
            raise ValueError()
        pages = [dict(page=i+1, text=p.extract_text(extraction_mode='layout')[:24000]) for i, p in enumerate(reader.pages)]
    except Exception:
        raise HTTPException(422, 'No se pudo extraer el PDF. Comprueba cifrado y formato; OCR aún no disponible.') from None
    item = dict(id=identifier(), hash=digest, pages=pages, status='needs_review', created_at=now(),
                warning='Extracción por página. Revisa columnas, matrices y saltos visualmente antes de crear preguntas.')
    with transaction() as state:
        state['documents'][item['id']] = item
    return item


@router.get('/surveys/interviews')
def interviews():
    with transaction() as state:
        return list(state['interviews'].values())


@router.post('/surveys/interviews')
def create_interview(body: CreateInterview):
    with transaction() as state:
        template = find(state, 'templates', body.template_id)
        if template['status'] != 'published':
            raise HTTPException(409, 'Publica el instrumento antes de capturar')
        item = dict(id=identifier(), template_id=template['id'], status='draft', responses={}, revision=1,
                    created_at=now(), findings=[], transcripts=[], schema=template['schema'])
        event(item, 'created')
        state['interviews'][item['id']] = item
        return item


@router.get('/surveys/interviews/{key}')
def get_interview(key: str):
    with transaction() as state:
        return find(state, 'interviews', key)


@router.patch('/surveys/interviews/{key}')
def save_interview(key: str, body: Answers):
    with transaction() as state:
        item = find(state, 'interviews', key)
        if item['status'] != 'draft' or body.revision != item['revision']:
            raise HTTPException(409, 'Entrevista finalizada o modificada en otra ventana. Recarga antes de guardar.')
        item['responses'] = body.responses
        item['revision'] += 1
        event(item, 'saved')
        return item


@router.post('/surveys/interviews/{key}/validate')
def validate_interview(key: str):
    with transaction() as state:
        item = find(state, 'interviews', key)
        return validate(item['schema'], item['responses'])


@router.post('/surveys/interviews/{key}/submit')
def submit_interview(key: str):
    with transaction() as state:
        item = find(state, 'interviews', key)
        result = validate(item['schema'], item['responses'])
        if not result['valid']:
            raise HTTPException(422, result['findings'])
        if item['status'] == 'submitted':
            return item
        item['status'] = 'submitted'
        item['validation'] = result
        event(item, 'submitted')
        return item


@router.post('/surveys/interviews/{key}/transcripts')
def transcript(key: str, body: dict):
    """Persistencia del resultado autorizado del motor existente, sin tokens ni rutas internas."""
    if body.get('consent') is not True:
        raise HTTPException(422, 'Confirma autorización para procesar el audio')
    result = body.get('result', {})
    turns = result.get('turns')
    if not isinstance(turns, list) or not turns or len(turns) > 10000:
        raise HTTPException(422, 'Transcripción sin intervenciones válidas')
    clean = []
    for i, t in enumerate(turns):
        try:
            start, end = float(t['start']), float(t['end'])
            if not 0 <= start <= end < 1e7:
                raise ValueError()
            clean.append(dict(id=i, speaker=str(t['speaker'])[:100], text=str(t['text'])[:5000],
                              start=start, end=end, has_overlap=bool(t.get('has_overlap'))))
        except (TypeError, ValueError, KeyError):
            raise HTTPException(422, 'Intervención inválida') from None
    digest = hashlib.sha256(json.dumps(clean, sort_keys=True).encode()).hexdigest()
    with transaction() as state:
        item = find(state, 'interviews', key)
        existing = next((t for t in item['transcripts'] if t['hash'] == digest), None)
        if existing:
            return existing
        record = dict(id=identifier(), hash=digest, turns=clean, engine_job_id=str(body.get('engine_job_id', ''))[:100],
                      synthetic=body.get('synthetic') is True, created_at=now())
        item['transcripts'].append(record)
        event(item, 'transcript_attached')
        return record


@router.post('/surveys/interviews/{key}/reconcile')
def reconcile(key: str, body: Evidence):
    with transaction() as state:
        item = find(state, 'interviews', key)
        q = next((q for q in item['schema']['questions'] if q['id'] == body.question_id), None)
        if not q or not item['transcripts']:
            raise HTTPException(422, 'Pregunta o transcripción no disponible')
        transcript = item['transcripts'][-1]
        if any(i < 0 or i >= len(transcript['turns']) for i in body.turn_ids):
            raise HTTPException(422, 'Intervención inexistente')
        turns = [transcript['turns'][i] for i in body.turn_ids]
        if body.interviewer not in {t['speaker'] for t in transcript['turns']}:
            raise HTTPException(422, 'Confirma un hablante existente como encuestador')
        applicable = validate(item['schema'], item['responses'])['applicability'][q['id']] == 'applicable'
        has_answer = any(t['speaker'] != body.interviewer and t['text'].strip() for t in turns)
        status = 'not_applicable' if not applicable else 'unverifiable' if not turns or not has_answer or any(t['has_overlap'] for t in turns) or body.observed_value is None else 'match' if item['responses'].get(q['id']) == body.observed_value else 'mismatch'
        finding = dict(id=identifier(), question_id=q['id'], status=status, registered=item['responses'].get(q['id']),
                       observed=body.observed_value, transcript_id=transcript['id'], evidence=turns, method='human_alignment_v1',
                       interviewer=body.interviewer, review_state='pending_review', created_at=now())
        previous = next((f for f in item['findings'] if f['question_id'] == q['id'] and f['transcript_id'] == transcript['id']), None)
        if previous:
            if previous['review_state'] != 'pending_review':
                raise HTTPException(409, 'Hallazgo ya revisado; conserva su decisión histórica')
            finding['id'] = previous['id']
            item['findings'].remove(previous)
        item['findings'].append(finding)
        event(item, 'reconciled')
        return finding


@router.patch('/surveys/interviews/{key}/findings/{finding_id}')
def review(key: str, finding_id: str, body: Review):
    if body.state not in {'confirmed', 'dismissed'}:
        raise HTTPException(422, 'Decisión inválida')
    with transaction() as state:
        item = find(state, 'interviews', key)
        finding = next((f for f in item['findings'] if f['id'] == finding_id), None)
        if not finding:
            raise HTTPException(404, 'Hallazgo no encontrado')
        finding.update(review_state=body.state, justification=body.justification)
        event(item, 'finding_reviewed')
        return finding
