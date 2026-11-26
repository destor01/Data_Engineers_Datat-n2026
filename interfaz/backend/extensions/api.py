"""Survey Audit: del cuestionario en PDF a la entrevista digital verificada contra la grabación.

Formularios
  POST  /surveys/documents                 registra el PDF y devuelve dónde subirlo
  PUT   /surveys/documents/{id}/archivo    (solo local) recibe el PDF
  POST  /surveys/documents/{id}/preparar   cuenta páginas y arma los bloques de lectura
  POST  /surveys/documents/{id}/leer       lee un rango de páginas con Claude (OCR incluido)
  POST  /surveys/documents/{id}/formulario une los bloques y crea el formulario en borrador
  GET/PATCH /surveys/templates[/{id}]      revisar y editar; POST /surveys/templates/{id}/publish lo finaliza
Entrevistas
  POST  /surveys/interviews                nueva entrevista (nombre + código único ENT-0001)
  PATCH /surveys/interviews/{id}           guardar respuestas; POST .../submit finaliza (valida en el servidor)
  POST  /surveys/interviews/{id}/transcripts   vincula el JSON de Audio Audit a ESA entrevista
  PATCH /surveys/interviews/{id}/encuestador   hablante que corresponde al encuestador
  POST  /surveys/interviews/{id}/verificacion[/{n}]  validación cruzada respuestas ↔ transcripción
  PATCH /surveys/interviews/{id}/findings/{fid}     revisión humana con justificación

Las respuestas oficiales son las del formulario; la transcripción solo se usa como evidencia.
"""
from datetime import datetime, timezone
import hashlib
import json
import logging
import re
import sys
import uuid
from pathlib import Path
from typing import Any, Callable

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from .repository import transaction
from . import archivos, ia

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / 'survey-audit/backend'))
from survey_audit.validation import PERSONAS, check_template, validate  # noqa: E402

router = APIRouter(prefix='/api', tags=['Survey Audit'])
logger = logging.getLogger('quality_audit.encuestas')
MAX_PDF = 50 * 1024 * 1024

# La plataforma unificada lo reemplaza por el correo de la sesión.
usuario_autenticado: Callable[[], str | None] = lambda: None  # noqa: E731


def now():
    return datetime.now(timezone.utc).isoformat()


def identifier():
    return str(uuid.uuid4())


def find(state, table, key):
    item = state.setdefault(table, {}).get(key)
    if not item:
        raise HTTPException(404, 'No se encontró lo que buscas. Actualiza la página e inténtalo de nuevo.')
    return item


def event(item, action, actor=None):
    item.setdefault('events', []).append(dict(action=action, actor=actor or usuario_autenticado() or 'usuario local', at=now()))


def _ocupada(exc: ia.IANoDisponible) -> JSONResponse:
    return JSONResponse({'detail': str(exc), 'reintentar': isinstance(exc, ia.IAOcupada)},
                        status_code=503 if isinstance(exc, ia.IAOcupada) else 422)


@router.get('/extensions/status')
def status():
    import os
    with transaction() as state:
        counts = {key: len(value) for key, value in state.items() if isinstance(value, dict)}
    return dict(storage='demo' if os.environ.get('QA_STORAGE') == 'demo' else 'postgres', counts=counts,
                ia=ia.disponible(), archivos='supabase' if archivos.usa_supabase() else 'local', at=now())


# ---------------------------------------------------------------------------
# Del PDF al formulario
# ---------------------------------------------------------------------------
class NuevoDocumento(BaseModel):
    nombre: str = Field(min_length=2, max_length=150)
    archivo: str = Field(min_length=1, max_length=300)
    tamano: int = Field(ge=1)


def _docs(state) -> dict:
    return state.setdefault('encuestas_documentos', {})


def _objeto(doc_id: str) -> str:
    return f'cuestionarios/{doc_id}.pdf'


@router.post('/surveys/documents')
def nuevo_documento(body: NuevoDocumento):
    if not body.archivo.lower().endswith('.pdf'):
        raise HTTPException(422, 'Selecciona la entrevista en formato PDF.')
    if body.tamano > MAX_PDF:
        raise HTTPException(413, 'El PDF supera 50 MB. Reduce su tamaño (por ejemplo, guardándolo con menor resolución) y vuelve a subirlo.')
    if not ia.disponible() and ia.responder is ia._llamar:
        raise HTTPException(503, 'Para generar formularios desde un PDF hace falta configurar la llave de Claude (ANTHROPIC_API_KEY) en el servidor.')
    doc = dict(id=identifier(), nombre=body.nombre.strip(), archivo=Path(body.archivo).name[:300], tamano=body.tamano,
               estado='esperando_archivo', creado_en=now(), lecturas={}, paginas=None, bloques=[])
    with transaction() as state:
        _docs(state)[doc['id']] = doc
    subida = archivos.url_subida(_objeto(doc['id']))
    if not subida['directa']:
        subida['url'] = f"/api/surveys/documents/{doc['id']}/archivo"
    return dict(documento=doc, subida=subida)


@router.put('/surveys/documents/{key}/archivo')
async def recibir_documento(key: str, request: Request):
    if archivos.usa_supabase():
        raise HTTPException(409, 'El PDF se sube directamente al almacenamiento.')
    with transaction() as state:
        find(state, 'encuestas_documentos', key)
    datos = bytearray()
    async for parte in request.stream():
        datos += parte
        if len(datos) > MAX_PDF:
            raise HTTPException(413, 'El PDF supera 50 MB.')
    archivos.guardar_local(_objeto(key), bytes(datos))
    return dict(ok=True, bytes=len(datos))


def _pdf(key: str) -> bytes:
    datos = archivos.leer(_objeto(key))
    if not datos:
        raise HTTPException(409, 'El PDF todavía no termina de subirse. Espera un momento y vuelve a intentarlo.')
    if not datos.startswith(b'%PDF-'):
        raise HTTPException(422, 'El archivo no es un PDF válido. Vuelve a guardarlo como PDF y súbelo de nuevo.')
    return datos


@router.post('/surveys/documents/{key}/preparar')
def preparar_documento(key: str):
    from .cuestionario import contar_paginas, paginas_por_bloque
    datos = _pdf(key)
    try:
        paginas = contar_paginas(datos)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from None
    except Exception:
        raise HTTPException(422, 'No se pudo abrir el PDF. Revisa que no esté dañado y vuelve a subirlo.') from None
    if not 1 <= paginas <= 600:
        raise HTTPException(422, 'El PDF debe tener entre 1 y 600 páginas.')
    tam = paginas_por_bloque()
    bloques = [dict(desde=i, hasta=min(i + tam - 1, paginas)) for i in range(1, paginas + 1, tam)]
    with transaction() as state:
        doc = find(state, 'encuestas_documentos', key)
        doc.update(paginas=paginas, bloques=bloques, estado='leyendo')
        return doc


class Rango(BaseModel):
    desde: int = Field(ge=1)
    hasta: int = Field(ge=1)


@router.post('/surveys/documents/{key}/leer')
def leer_paginas(key: str, body: Rango):
    from .cuestionario import leer_bloque
    with transaction() as state:
        doc = dict(find(state, 'encuestas_documentos', key))
    if not doc.get('paginas') or not 1 <= body.desde <= body.hasta <= doc['paginas']:
        raise HTTPException(422, 'Rango de páginas inválido.')
    try:
        resultado = leer_bloque(_pdf(key), body.desde, body.hasta, doc['paginas'], doc['nombre'])
    except ia.IARespuestaLarga as exc:
        if body.hasta > body.desde:
            return JSONResponse({'detail': 'Estas páginas tienen demasiado contenido; se leerán una por una.', 'dividir': True}, status_code=422)
        raise HTTPException(422, f'La página {body.desde} tiene demasiado contenido para leerse completa. Revísala a mano en el editor.') from exc
    except ia.IANoDisponible as exc:
        return _ocupada(exc)
    with transaction() as state:
        doc = find(state, 'encuestas_documentos', key)
        doc['lecturas'][f'{body.desde}-{body.hasta}'] = dict(desde=body.desde, hasta=body.hasta, **resultado)
    return dict(desde=body.desde, hasta=body.hasta, preguntas=len(resultado.get('preguntas', [])),
                secciones=len(resultado.get('secciones', [])))


@router.post('/surveys/documents/{key}/formulario')
def crear_formulario(key: str):
    from .cuestionario import armar_formulario
    with transaction() as state:
        doc = find(state, 'encuestas_documentos', key)
        lecturas = sorted(doc['lecturas'].values(), key=lambda r: r['desde'])
        cubiertas = {p for r in lecturas for p in range(r['desde'], r['hasta'] + 1)}
        faltan = sorted(set(range(1, (doc.get('paginas') or 0) + 1)) - cubiertas)
        if faltan:
            raise HTTPException(409, f'Faltan páginas por leer ({len(faltan)}). Continúa la lectura antes de generar el formulario.')
        # Si una página se leyó dos veces (bloque y luego página por página), se usa la lectura más fina.
        usadas, elegidas = set(), []
        for r in sorted(lecturas, key=lambda r: (r['hasta'] - r['desde'], r['desde'])):
            paginas = set(range(r['desde'], r['hasta'] + 1))
            if not paginas & usadas:
                usadas |= paginas
                elegidas.append(r)
        elegidas.sort(key=lambda r: r['desde'])
        codigo = re.sub(r'[^A-Z0-9]+', '-', doc['nombre'].upper()).strip('-')[:40] or 'ENTREVISTA'
        version = 1 + sum(1 for t in state.setdefault('templates', {}).values() if t['schema'].get('template_code') == codigo)
        try:
            schema = armar_formulario(elegidas, doc['nombre'], codigo,
                                      dict(documento_id=doc['id'], archivo=doc['archivo'], paginas=doc['paginas']))
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from None
        schema['version'] = version
        errores = check_template(schema)
        if errores:
            logger.warning('Formulario generado con problemas: %s', errores[:5])
            raise HTTPException(422, 'El formulario generado tiene problemas de estructura. Vuelve a generarlo.')
        item = dict(id=identifier(), schema=schema, status='draft', created_at=now(), revision=1, documento_id=doc['id'])
        event(item, 'Formulario generado desde el PDF')
        state['templates'][item['id']] = item
        doc.update(estado='listo', template_id=item['id'])
        return item


@router.get('/surveys/documents')
def documentos():
    with transaction() as state:
        return sorted(({k: v for k, v in d.items() if k != 'lecturas'} | {'rangos': [[r['desde'], r['hasta']] for r in d['lecturas'].values()]}
                       for d in _docs(state).values()), key=lambda d: d['creado_en'], reverse=True)


# ---------------------------------------------------------------------------
# Formularios
# ---------------------------------------------------------------------------
class TemplatePayload(BaseModel):
    schema_data: dict
    revision: int | None = None


def _resumen_formulario(t: dict) -> dict:
    s = t['schema']
    alertas = sum(1 for q in s['questions'] if q.get('alertas'))
    return dict(id=t['id'], status=t['status'], revision=t['revision'], created_at=t['created_at'],
                nombre=s.get('nombre') or s['template_code'], version=s['version'], preguntas=len(s['questions']),
                secciones=len(s.get('sections', [])), alertas=alertas, origen=s.get('origen'))


@router.get('/surveys/templates')
def templates():
    with transaction() as state:
        return sorted((_resumen_formulario(t) for t in state.setdefault('templates', {}).values()),
                      key=lambda t: t['created_at'], reverse=True)


@router.get('/surveys/templates/{key}')
def template(key: str):
    with transaction() as state:
        return find(state, 'templates', key)


@router.post('/surveys/templates')
def create_template(body: TemplatePayload):
    schema = body.schema_data
    try:
        errors = check_template(schema)
    except (TypeError, KeyError, AttributeError, ValueError):
        raise HTTPException(422, 'El formulario no tiene una estructura válida.') from None
    if errors:
        raise HTTPException(422, errors)
    item = dict(id=identifier(), schema=schema, status='draft', created_at=now(), revision=1)
    item['schema']['status'] = 'draft'
    with transaction() as state:
        for existing in state.setdefault('templates', {}).values():
            if (existing['schema']['template_code'], existing['schema']['version']) == (schema['template_code'], schema['version']):
                raise HTTPException(409, 'Ya existe un formulario con ese nombre y versión.')
        event(item, 'created')
        state['templates'][item['id']] = item
    return item


def _explicar(errores: list[str], schema: dict) -> str:
    etiquetas = {q.get('id'): q.get('label', '') for q in schema.get('questions', [])}
    partes = []
    for e in errores[:5]:
        qid, _, motivo = e.partition(': ')
        texto = {'tipo o sección inválida': 'elige un tipo de respuesta y una sección',
                 'etiqueta requerida': 'escribe el texto de la pregunta',
                 'códigos únicos de texto requeridos': 'cada opción necesita un código distinto',
                 'catálogo requerido': 'agrega al menos una opción de respuesta',
                 'salto con destino inexistente': 'el salto apunta a una pregunta o sección que ya no existe'}.get(motivo)
        partes.append(f'«{etiquetas.get(qid, qid)[:60]}»: {texto}' if texto else e)
    return 'Revisa estas preguntas: ' + '; '.join(partes) + ('.' if len(errores) <= 5 else f'; y {len(errores) - 5} más.')


@router.patch('/surveys/templates/{key}')
def edit_template(key: str, body: TemplatePayload):
    try:
        errors = check_template(body.schema_data)
    except (TypeError, KeyError, AttributeError, ValueError):
        raise HTTPException(422, 'El formulario no tiene una estructura válida. Recarga la página.') from None
    if errors:
        raise HTTPException(422, _explicar(errors, body.schema_data))
    with transaction() as state:
        item = find(state, 'templates', key)
        if item['status'] != 'draft':
            raise HTTPException(409, 'Este formulario ya está finalizado y no se puede modificar.')
        if body.revision is not None and body.revision != item['revision']:
            raise HTTPException(409, 'El formulario cambió en otra ventana. Recarga la página antes de guardar.')
        if any(other['id'] != key and (other['schema']['template_code'], other['schema']['version']) == (body.schema_data['template_code'], body.schema_data['version']) for other in state['templates'].values()):
            raise HTTPException(409, 'Ya existe otro formulario con ese nombre y versión.')
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
        pendientes = [q for q in item['schema']['questions'] if q.get('alertas')]
        if pendientes:
            raise HTTPException(409, f'Hay {len(pendientes)} preguntas marcadas para revisión. Corrígelas (o quita la marca) antes de finalizar el formulario.')
        item['status'] = item['schema']['status'] = 'published'
        item['hash'] = hashlib.sha256(json.dumps(item['schema'], sort_keys=True).encode()).hexdigest()
        event(item, 'published')
        return item


@router.delete('/surveys/templates/{key}')
def borrar_formulario(key: str):
    with transaction() as state:
        item = find(state, 'templates', key)
        if item['status'] != 'draft':
            raise HTTPException(409, 'Un formulario finalizado no se puede borrar.')
        del state['templates'][key]
    return dict(ok=True)


# ---------------------------------------------------------------------------
# Entrevistas
# ---------------------------------------------------------------------------
class CreateInterview(BaseModel):
    template_id: str
    nombre: str = Field(default='', max_length=150)


class Answers(BaseModel):
    responses: dict
    revision: int = Field(ge=1)


def _resumen_entrevista(i: dict) -> dict:
    t = i.get('transcripcion')
    hallazgos = i.get('hallazgos', [])
    return dict(id=i['id'], codigo=i.get('codigo'), nombre=i.get('nombre'), status=i['status'],
                formulario=i['schema'].get('nombre') or i['schema']['template_code'], created_at=i['created_at'],
                transcripcion=bool(t), verificadas=len(hallazgos),
                discrepancias=sum(1 for h in hallazgos if h['estado'] == 'discrepancia'))


@router.get('/surveys/interviews')
def interviews():
    with transaction() as state:
        return sorted((_resumen_entrevista(i) for i in state.setdefault('interviews', {}).values() if i.get('codigo')),
                      key=lambda i: i['created_at'], reverse=True)


@router.post('/surveys/interviews')
def create_interview(body: CreateInterview):
    nombre = body.nombre.strip()
    if len(nombre) < 2:
        raise HTTPException(422, 'Escribe un nombre para identificar la entrevista (por ejemplo, el hogar o la boleta).')
    with transaction() as state:
        template = find(state, 'templates', body.template_id)
        if template['status'] != 'published':
            raise HTTPException(409, 'Finaliza el formulario antes de usarlo en una entrevista.')
        numero = state['encuestas_contador'] = state.get('encuestas_contador', 0) + 1
        item = dict(id=identifier(), codigo=f'ENT-{numero:04d}', nombre=nombre, template_id=template['id'],
                    status='draft', responses={}, revision=1, created_at=now(), hallazgos=[], transcripcion=None,
                    encuestador=None, schema=template['schema'])
        event(item, 'Entrevista creada')
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
        if item['status'] != 'draft':
            raise HTTPException(409, 'Esta entrevista ya está finalizada; sus respuestas no se pueden cambiar.')
        if body.revision != item['revision']:
            raise HTTPException(409, 'La entrevista se modificó en otra ventana. Recarga la página para ver la versión más reciente.')
        item['responses'] = body.responses
        item['revision'] += 1
        event(item, 'Respuestas guardadas')
        return item


@router.post('/surveys/interviews/{key}/submit')
def submit_interview(key: str):
    with transaction() as state:
        item = find(state, 'interviews', key)
        if item['status'] == 'submitted':
            return item
        result = validate(item['schema'], item['responses'])
        if not result['valid']:
            return JSONResponse(status_code=422, content={
                'detail': f'Hay {len(result["findings"])} respuestas por corregir antes de finalizar.',
                'errores': [dict(clave=f['question_id'], pregunta=f.get('pregunta'), mensaje=f['message'])
                            for f in result['findings']][:200]})
        item['status'] = 'submitted'
        item['validation'] = result
        event(item, 'Entrevista finalizada')
        return item


# ---------------------------------------------------------------------------
# Transcripción de Audio Audit
# ---------------------------------------------------------------------------
class Vinculo(BaseModel):
    consent: bool
    entrevista_codigo: str
    datos: dict
    archivo: str | None = Field(default=None, max_length=300)


def _turnos(datos: dict) -> list[dict]:
    resultado = datos.get('result') if isinstance(datos.get('result'), dict) else datos
    turnos = resultado.get('turns') if isinstance(resultado, dict) else None
    if not isinstance(turnos, list) or not turnos:
        raise HTTPException(422, 'El archivo no contiene una transcripción de Audio Audit. Usa el botón «Descargar JSON» de Audio Audit.')
    if len(turnos) > 20000:
        raise HTTPException(422, 'La transcripción es demasiado larga.')
    limpios = []
    for i, t in enumerate(turnos):
        try:
            inicio, fin = float(t['start']), float(t['end'])
            if not 0 <= inicio <= fin < 1e7:
                raise ValueError()
            limpios.append(dict(id=i, speaker=str(t['speaker'])[:100], text=str(t['text'])[:5000], start=inicio, end=fin))
        except (TypeError, ValueError, KeyError):
            raise HTTPException(422, f'La intervención número {i + 1} de la transcripción está incompleta. Vuelve a descargar el JSON desde Audio Audit.') from None
    return limpios


@router.post('/surveys/interviews/{key}/transcripts')
def transcript(key: str, body: Vinculo):
    if body.consent is not True:
        raise HTTPException(422, 'Confirma que cuentas con autorización para usar la grabación.')
    turnos = _turnos(body.datos)
    job = str(body.datos.get('job_id') or '').strip()[:100]
    huella = hashlib.sha256(json.dumps(turnos, sort_keys=True).encode()).hexdigest()
    with transaction() as state:
        item = find(state, 'interviews', key)
        if not item.get('codigo') or body.entrevista_codigo.strip().upper() != item['codigo']:
            raise HTTPException(409, 'El código de la entrevista no coincide. Abre la entrevista correcta antes de vincular la transcripción.')
        for otra in state['interviews'].values():
            t = otra.get('transcripcion')
            if otra['id'] != key and t and ((job and t.get('job_id') == job) or t.get('hash') == huella):
                raise HTTPException(409, f'Esta transcripción ya está vinculada a la entrevista {otra["codigo"]} «{otra["nombre"]}». Cada grabación se vincula a una sola entrevista.')
        item['transcripcion'] = dict(id=identifier(), job_id=job, archivo=body.archivo, hash=huella, turns=turnos,
                                     hablantes=sorted({t['speaker'] for t in turnos}), vinculada_en=now(),
                                     por=usuario_autenticado() or 'usuario local')
        item['encuestador'] = None
        item['hallazgos'] = []
        item.pop('verificacion', None)
        event(item, f'Transcripción vinculada ({len(turnos)} intervenciones)')
        return item


class Encuestador(BaseModel):
    hablante: str = Field(min_length=1, max_length=100)


@router.patch('/surveys/interviews/{key}/encuestador')
def elegir_encuestador(key: str, body: Encuestador):
    with transaction() as state:
        item = find(state, 'interviews', key)
        t = item.get('transcripcion')
        if not t:
            raise HTTPException(409, 'Primero vincula la transcripción de la entrevista.')
        if body.hablante not in t['hablantes']:
            raise HTTPException(422, 'Elige uno de los hablantes de la transcripción.')
        if item.get('encuestador') != body.hablante:
            item['encuestador'] = body.hablante
            item['hallazgos'] = [h for h in item['hallazgos'] if h['revision']['estado'] != 'pendiente']
            item.pop('verificacion', None)
            event(item, f'Encuestador: {body.hablante}')
        return item


# ---------------------------------------------------------------------------
# Validación cruzada con la transcripción
# ---------------------------------------------------------------------------
ESTADOS = {'coincidencia', 'discrepancia', 'no_verificable'}
ESQUEMA_VERIF = {
    "type": "object", "additionalProperties": False, "required": ["resultados"],
    "properties": {"resultados": {"type": "array", "items": {
        "type": "object", "additionalProperties": False,
        "required": ["clave", "turnos", "respuesta_escuchada", "estado", "explicacion"],
        "properties": {"clave": {"type": "string"}, "turnos": {"type": "array", "items": {"type": "integer"}},
                       "respuesta_escuchada": {"type": "string"},
                       "estado": {"type": "string", "enum": sorted(ESTADOS)}, "explicacion": {"type": "string"}}}}}}
SISTEMA_VERIF = """Auditas la calidad de entrevistas de encuestas del Instituto Nacional de Estadística de Guatemala.
Recibes la transcripción de la grabación (cada intervención con id, tiempo y rol) y una lista de preguntas
con la respuesta que el encuestador REGISTRÓ en el formulario digital. Las respuestas oficiales son las
registradas; la grabación solo sirve como evidencia para verificarlas.

Para cada pregunta de la lista:
1. Busca las intervenciones donde el encuestador hace esa pregunta (o una equivalente) y donde la persona
   entrevistada responde. Devuelve sus ids en "turnos", en orden. Usa solo ids que existan.
2. Resume en "respuesta_escuchada" lo que respondió la persona entrevistada, en pocas palabras.
3. "estado":
   - coincidencia: lo escuchado corresponde a la respuesta registrada (aunque se diga con otras palabras,
     o la opción registrada sea la que corresponde a lo dicho).
   - discrepancia: lo escuchado indica claramente una respuesta distinta a la registrada.
   - no_verificable: la pregunta no aparece en la grabación, la respuesta es inaudible, ambigua, o no
     hay forma de compararla. En ese caso "turnos" puede ir vacío.
4. "explicacion": una frase clara para un revisor sin conocimientos técnicos (qué se escuchó y por qué
   coincide o no). Menciona el minuto aproximado cuando ayude.
No inventes contenido que no esté en la transcripción. Devuelve un resultado por cada "clave" recibida."""
POR_LOTE = 25


def _etiqueta(q: dict, valor: Any) -> str:
    ops = {o['code']: o['label'] for o in q.get('options', [])}
    if isinstance(valor, list):
        return '; '.join(f'{v} - {ops.get(v, v)}' for v in valor)
    if ops:
        return f'{valor} - {ops.get(valor, valor)}'
    return str(valor)


def _preguntas_verificables(item: dict) -> list[dict]:
    resultado = item.get('validation') or validate(item['schema'], item['responses'])
    por_id = {q['id']: q for q in item['schema']['questions']}
    lista = []
    for clave, valor in resultado['active_responses'].items():
        qid, _, persona = clave.partition('#')
        q = por_id.get(qid)
        if not q:
            continue
        lista.append(dict(clave=clave, codigo=q.get('codigo') or '', persona=int(persona) if persona else None,
                          pregunta=q['label'], registrada=_etiqueta(q, valor)))
    return lista


@router.post('/surveys/interviews/{key}/verificacion')
def preparar_verificacion(key: str):
    with transaction() as state:
        item = find(state, 'interviews', key)
        if item['status'] != 'submitted':
            raise HTTPException(409, 'Finaliza la entrevista antes de validarla contra la grabación: así se verifican las respuestas definitivas.')
        if not item.get('transcripcion'):
            raise HTTPException(409, 'Primero vincula la transcripción de la entrevista.')
        if not item.get('encuestador'):
            raise HTTPException(409, 'Indica cuál de los hablantes es el encuestador.')
        if not ia.disponible() and ia.responder is ia._llamar:
            raise HTTPException(503, 'La validación contra la grabación necesita la llave de Claude (ANTHROPIC_API_KEY) configurada en el servidor.')
        preguntas = _preguntas_verificables(item)
        if not preguntas:
            raise HTTPException(409, 'La entrevista no tiene respuestas para verificar.')
        revisadas = {h['clave'] for h in item['hallazgos'] if h['revision']['estado'] != 'pendiente'}
        pendientes = [p['clave'] for p in preguntas if p['clave'] not in revisadas]
        lotes = [pendientes[i:i + POR_LOTE] for i in range(0, len(pendientes), POR_LOTE)]
        item['verificacion'] = dict(lotes=lotes, creada=now(), listos=[])
        return dict(lotes=len(lotes), preguntas=len(pendientes), ya_revisadas=len(revisadas))


@router.post('/surveys/interviews/{key}/verificacion/{n}')
def verificar_lote(key: str, n: int):
    with transaction() as state:
        item = json.loads(json.dumps(find(state, 'interviews', key)))
    v = item.get('verificacion')
    if not v or not 0 <= n < len(v['lotes']):
        raise HTTPException(409, 'Vuelve a iniciar la validación contra la grabación.')
    claves = set(v['lotes'][n])
    preguntas = [p for p in _preguntas_verificables(item) if p['clave'] in claves]
    t = item['transcripcion']
    encuestador = item['encuestador']
    turnos = [dict(id=x['id'], inicio=round(x['start'], 1), fin=round(x['end'], 1),
                   rol='Encuestador' if x['speaker'] == encuestador else f'Entrevistado ({x["speaker"]})', texto=x['text'])
              for x in t['turns']]
    mensaje = ('TRANSCRIPCIÓN (JSON):\n' + json.dumps(turnos, ensure_ascii=False) +
               '\n\nPREGUNTAS A VERIFICAR (JSON):\n' + json.dumps(preguntas, ensure_ascii=False))
    try:
        r = ia.generar('SURVEY_IA_MODELO', SISTEMA_VERIF, mensaje, ESQUEMA_VERIF, max_tokens=16000)
    except ia.IANoDisponible as exc:
        return _ocupada(exc)
    por_clave = {p['clave']: p for p in preguntas}
    por_id = {x['id']: x for x in t['turns']}
    nuevos = []
    for res in r.get('resultados', []):
        p = por_clave.get(res.get('clave'))
        if not p or res.get('estado') not in ESTADOS:
            continue
        evidencia = [dict(id=i, hablante=por_id[i]['speaker'],
                          rol='Encuestador' if por_id[i]['speaker'] == encuestador else 'Entrevistado',
                          inicio=por_id[i]['start'], fin=por_id[i]['end'], texto=por_id[i]['text'])
                     for i in res.get('turnos', []) if isinstance(i, int) and i in por_id][:12]
        estado = res['estado'] if evidencia or res['estado'] == 'no_verificable' else 'no_verificable'
        nuevos.append(dict(id=identifier(), clave=p['clave'], codigo=p['codigo'], persona=p['persona'],
                           pregunta=p['pregunta'], registrada=p['registrada'],
                           escuchada=str(res.get('respuesta_escuchada') or '')[:500], estado=estado,
                           explicacion=str(res.get('explicacion') or '')[:1000], evidencia=evidencia,
                           revision=dict(estado='pendiente', justificacion=None, por=None, en=None), creado_en=now()))
    faltantes = claves - {h['clave'] for h in nuevos}
    for clave in faltantes:
        p = por_clave[clave]
        nuevos.append(dict(id=identifier(), clave=clave, codigo=p['codigo'], persona=p['persona'], pregunta=p['pregunta'],
                           registrada=p['registrada'], escuchada='', estado='no_verificable',
                           explicacion='No se encontró esta pregunta en la grabación.', evidencia=[],
                           revision=dict(estado='pendiente', justificacion=None, por=None, en=None), creado_en=now()))
    with transaction() as state:
        actual = find(state, 'interviews', key)
        if (actual.get('transcripcion') or {}).get('id') != t['id'] or actual.get('encuestador') != encuestador:
            raise HTTPException(409, 'La transcripción o el encuestador cambiaron. Vuelve a iniciar la validación.')
        reemplazar = {h['clave'] for h in nuevos}
        actual['hallazgos'] = [h for h in actual['hallazgos'] if h['clave'] not in reemplazar or h['revision']['estado'] != 'pendiente'] + \
            [h for h in nuevos if h['clave'] not in {x['clave'] for x in actual['hallazgos'] if x['revision']['estado'] != 'pendiente'}]
        if 'verificacion' in actual:
            actual['verificacion']['listos'] = sorted(set(actual['verificacion'].get('listos', [])) | {n})
        event(actual, f'Validación contra la grabación: grupo {n + 1}')
        return dict(lote=n, resultados=len(nuevos))


class Review(BaseModel):
    estado: str
    justificacion: str = Field(min_length=3, max_length=1000)


@router.patch('/surveys/interviews/{key}/findings/{finding_id}')
def review(key: str, finding_id: str, body: Review):
    if body.estado not in {'confirmado', 'descartado'}:
        raise HTTPException(422, 'Elige si confirmas o descartas el resultado.')
    with transaction() as state:
        item = find(state, 'interviews', key)
        h = next((f for f in item.get('hallazgos', []) if f['id'] == finding_id), None)
        if not h:
            raise HTTPException(404, 'No se encontró el resultado. Actualiza la página.')
        h['revision'] = dict(estado=body.estado, justificacion=body.justificacion.strip(),
                             por=usuario_autenticado() or 'usuario local', en=now())
        event(item, f'Resultado revisado: {h["clave"]} {body.estado}')
        return h
