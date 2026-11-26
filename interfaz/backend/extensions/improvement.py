"""Quality Improvement: recomendaciones a partir del reporte de Data Audit y manual institucional en PDF.

Flujo:
  1. POST /reports           se sube el reporte.json de Data Audit. Los hallazgos se agrupan por
                             institución + base + período + regla, y cada grupo genera una recomendación
                             específica (explicación de la regla + cifras y columnas reales; con IA si
                             hay ANTHROPIC_API_KEY).
  2. PATCH /recommendations/{id}           editar textos y acciones de mejora (queda historial).
     POST  /recommendations/{id}/approve   aprobar con el cargo de quien aprueba.
  3. POST /manuals           manual con las recomendaciones aprobadas de una institución.
     PATCH /manuals/{id}     editar nombre de la institución y contenido.
     POST  /manuals/{id}/finalize, GET /manuals/{id}/pdf   finalizar, ver y descargar en PDF.

No hay asignación de responsables ni seguimiento entre períodos.
"""
from __future__ import annotations

import hashlib
import json
import logging
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Callable

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel, Field

from . import ia
from .api import identifier, now
from .repository import transaction

logger = logging.getLogger("quality_audit.mejora")
router = APIRouter(prefix='/api/improvement', tags=['Quality Improvement'])

PLANTILLAS = Path(__file__).resolve().parents[3] / 'quality-improvement/templates'
INSTITUCIONES: dict[str, dict] = json.loads((PLANTILLAS / 'institutions.json').read_text(encoding='utf-8'))
REGLAS: dict[str, dict] = json.loads((PLANTILLAS / 'reglas.json').read_text(encoding='utf-8'))
BASE_INSTITUCION = {base: clave for clave, d in INSTITUCIONES.items() for base in d['bases']}
BASE_NOMBRE = {'DEFUNCIONES': 'Defunciones', 'NACIMIENTOS': 'Nacimientos', 'DETENIDOS': 'Detenidos',
               'CALIDAD_AIRE': 'Calidad del aire', 'EMERGENCIAS': 'Emergencias y desastres'}
MESES = ['enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio', 'julio', 'agosto', 'septiembre', 'octubre',
         'noviembre', 'diciembre']
PRIORIDAD = {'error': 'alta', 'advertencia': 'media', 'info': 'baja'}
ORDEN = {'alta': 0, 'media': 1, 'baja': 2}
TEXTOS = ('titulo', 'que_ocurrio', 'por_que', 'como_corregir', 'como_prevenir')

# La plataforma unificada lo reemplaza por el correo de la sesión.
usuario_autenticado: Callable[[], str | None] = lambda: None  # noqa: E731


def _usuario() -> str:
    return usuario_autenticado() or 'usuario local'


def _recs(state) -> dict:
    return state.setdefault('mejora_recomendaciones', {})


def _manuales(state) -> dict:
    return state.setdefault('mejora_manuales', {})


def periodo_texto(anio: int | None, mes: int | None) -> str:
    if not anio:
        return 'Período no indicado'
    return f'{MESES[mes - 1].capitalize()} {anio}' if mes and 1 <= mes <= 12 else f'Año {anio}'


def _explicacion_regla(regla: str) -> dict:
    if regla in REGLAS:
        return REGLAS[regla]
    if regla.endswith('_LLAVE_UNICA'):
        return REGLAS['LLAVE_UNICA']
    return REGLAS['_GENERICA']


def _numero(n: int) -> str:
    return f'{n:,}'.replace(',', ' ')


def _resumen(hallazgos: list[dict], total: int | None) -> str:
    """Frase con las columnas y cifras reales del grupo, para insertar en la explicación."""
    partes = []
    for h in hallazgos[:6]:
        donde = f'la columna «{h["columna"]}»' if h.get('columna') else 'el archivo'
        if h['n'] and total and h['n'] >= total and h['regla'].startswith('GEN_COLUMNA'):
            partes.append(donde)
        elif h['n']:
            pct = f' ({h["porcentaje"]:.1f} %)' if isinstance(h.get('porcentaje'), (int, float)) else ''
            partes.append(f'{_numero(h["n"])} {"registro" if h["n"] == 1 else "registros"} en {donde}{pct}')
        else:
            partes.append(donde)
    if len(hallazgos) > 6:
        resto = len(hallazgos) - 6
        partes.append(f'{resto} {"caso más" if resto == 1 else "casos más"}')
    if not partes:
        return 'sin detalle'
    return partes[0] if len(partes) == 1 else ', '.join(partes[:-1]) + ' y ' + partes[-1]


def _evidencia(h: dict) -> dict:
    """Solo cifras, columnas, el mensaje del motor y números de fila: nunca valores de los registros."""
    filas = [e.get('fila') for e in (h.get('ejemplos') or []) if isinstance(e, dict) and isinstance(e.get('fila'), int)]
    return dict(columna=h.get('columna'), hoja=h.get('hoja'), n=int(h.get('n') or 0),
                porcentaje=h.get('porcentaje') if isinstance(h.get('porcentaje'), (int, float)) else None,
                mensaje=str(h.get('mensaje') or h.get('nombre') or '')[:400], filas=filas[:10], regla=h['regla'])


# ---------------------------------------------------------------------------
# Generación de recomendaciones
# ---------------------------------------------------------------------------
ESQUEMA_IA = {
    "type": "object", "additionalProperties": False, "required": ["recomendaciones"],
    "properties": {"recomendaciones": {"type": "array", "items": {
        "type": "object", "additionalProperties": False,
        "required": ["id", "titulo", "que_ocurrio", "por_que", "como_corregir", "como_prevenir", "acciones"],
        "properties": {"id": {"type": "string"}, "titulo": {"type": "string"}, "que_ocurrio": {"type": "string"},
                       "por_que": {"type": "string"}, "como_corregir": {"type": "string"},
                       "como_prevenir": {"type": "string"}, "acciones": {"type": "array", "items": {"type": "string"}}}}}}}

SISTEMA_IA = """Eres especialista en calidad de datos del Instituto Nacional de Estadística (INE) de Guatemala.
Redactas recomendaciones para la institución que envió una base de datos, a partir de los hallazgos de la
auditoría automática (Data Audit). Cada recomendación debe:
- explicar en lenguaje claro y profesional, sin jerga técnica, qué ocurrió, por qué es un problema y cómo
  corregirlo y prevenirlo;
- usar las cifras, columnas, filas de ejemplo y período reales que recibes, sin inventar datos;
- proponer de 2 a 5 acciones de mejora concretas y verificables para la institución;
- no asignar responsables, personas ni plazos, y no proponer seguimiento entre períodos;
- no incluir datos personales.
Escribe en español de Guatemala, en segunda o tercera persona formal. Mantén el mismo "id" de cada grupo."""


def _texto_base(grupo: dict) -> dict:
    base = _explicacion_regla(grupo['regla'])
    detalle = _resumen(grupo['evidencia']['hallazgos'], grupo['total_registros'])
    return dict(titulo=base['titulo'], que_ocurrio=base['que_ocurrio'].format(detalle_hallazgo=detalle),
                por_que=base['por_que'], como_corregir=base['como_corregir'], como_prevenir=base['como_prevenir'],
                acciones=list(base['acciones']))


def _con_ia(grupos: list[dict], contexto: dict) -> dict[str, dict]:
    """Ajusta los textos de cada grupo con Claude. Devuelve {id: textos}; los que fallen quedan fuera."""
    import os
    if not ia.disponible() and ia.responder is ia._llamar or (os.environ.get('MEJORA_IA') or '1') == '0':
        return {}
    lotes = [grupos[i:i + 6] for i in range(0, len(grupos), 6)]

    def pedir(lote: list[dict]) -> dict[str, dict]:
        datos = [dict(id=g['id'], regla=g['regla'], nombre_regla=g['regla_nombre'], dimension=g['dimension'],
                      severidad=g['severidad'], accion_del_motor=g['accion_regla'],
                      registros_afectados=g['afectados'], hallazgos=g['evidencia']['hallazgos'],
                      propuesta_base=_texto_base(g)) for g in lote]
        mensaje = (f"Institución: {contexto['institucion_nombre']}\nBase: {contexto['base_nombre']}\n"
                   f"Período: {contexto['periodo']}\nTotal de registros recibidos: {contexto['total']}\n\n"
                   "Grupos de hallazgos (JSON). Mejora y especifica la propuesta base de cada uno:\n"
                   + json.dumps(datos, ensure_ascii=False))
        r = ia.generar('MEJORA_IA_MODELO', SISTEMA_IA, mensaje, ESQUEMA_IA, max_tokens=12000)
        ids = {g['id'] for g in lote}
        return {x['id']: x for x in r.get('recomendaciones', []) if x.get('id') in ids
                and all(isinstance(x.get(k), str) and x[k].strip() for k in TEXTOS)
                and isinstance(x.get('acciones'), list) and x['acciones']}

    salida: dict[str, dict] = {}
    with ThreadPoolExecutor(max_workers=4) as ex:
        for futuro in [ex.submit(pedir, lote) for lote in lotes]:
            try:
                salida.update(futuro.result())
            except ia.IANoDisponible as exc:
                logger.warning("Recomendaciones sin IA para un lote: %s", exc)
    return salida


class ReporteEntrada(BaseModel):
    report: dict
    institucion: str | None = None
    archivo: str | None = Field(default=None, max_length=300)


@router.get('/institutions')
def instituciones():
    return [dict(clave=k, nombre=v['nombre'], bases=[dict(codigo=b, nombre=BASE_NOMBRE.get(b, b)) for b in v['bases']])
            for k, v in INSTITUCIONES.items()]


@router.post('/reports')
def recibir_reporte(body: ReporteEntrada):
    r = body.report
    hallazgos = r.get('hallazgos')
    if not isinstance(hallazgos, list) or len(hallazgos) > 20000:
        raise HTTPException(422, 'El archivo no parece un reporte de Data Audit. Usa el «reporte JSON» que descargas al terminar una auditoría.')
    base = str(r.get('base') or '').upper()
    institucion = (body.institucion or BASE_INSTITUCION.get(base) or '').upper()
    if institucion not in INSTITUCIONES:
        raise HTTPException(422, 'No se reconoce la institución de este reporte. Elige la institución y vuelve a subirlo.')
    anio = r.get('anio') if isinstance(r.get('anio'), int) else None
    mes = r.get('mes') if isinstance(r.get('mes'), int) and 1 <= r['mes'] <= 12 else None
    total = r.get('total_registros') if isinstance(r.get('total_registros'), int) else None
    huella = hashlib.sha256(json.dumps(r, sort_keys=True, default=str).encode()).hexdigest()

    # Agrupación efectiva: institución + base + período + regla
    grupos: dict[str, dict] = {}
    for h in hallazgos:
        if not isinstance(h, dict) or not isinstance(h.get('regla'), str) or h.get('severidad') not in PRIORIDAD:
            raise HTTPException(422, 'El reporte tiene hallazgos con un formato desconocido. Vuelve a descargarlo desde Data Audit.')
        clave = '|'.join([institucion, base, str(anio or ''), str(mes or ''), h['regla']])
        gid = hashlib.sha256(clave.encode()).hexdigest()[:24]
        g = grupos.setdefault(gid, dict(
            id=gid, institucion=institucion, institucion_nombre=INSTITUCIONES[institucion]['nombre'], base=base,
            base_nombre=BASE_NOMBRE.get(base, base.title() or 'Base sin nombre'), anio=anio, mes=mes,
            periodo=periodo_texto(anio, mes), regla=h['regla'], regla_nombre=str(h.get('nombre') or h['regla'])[:200],
            dimension=str(h.get('dimension') or ''), severidad=h['severidad'], accion_regla=str(h.get('accion') or ''),
            prioridad=PRIORIDAD[h['severidad']], total_registros=total, afectados=0,
            evidencia=dict(hallazgos=[], archivo=body.archivo, reporte=huella[:16], recibido=now())))
        g['evidencia']['hallazgos'].append(_evidencia(h))
        g['afectados'] += int(h.get('n') or 0)

    lista = sorted(grupos.values(), key=lambda g: (ORDEN[g['prioridad']], -g['afectados']))
    contexto = dict(institucion_nombre=INSTITUCIONES[institucion]['nombre'], base_nombre=BASE_NOMBRE.get(base, base),
                    periodo=periodo_texto(anio, mes), total=total)
    ajustes = _con_ia(lista, contexto) if lista else {}
    actor = _usuario()
    nuevas = actualizadas = 0
    with transaction() as state:
        recs = _recs(state)
        for g in lista:
            existente = recs.get(g['id'])
            if existente:
                existente['evidencia'] = g['evidencia']
                existente['afectados'] = g['afectados']
                existente['total_registros'] = g['total_registros']
                existente['historial'].append(dict(en=now(), por=actor, accion='Se actualizó la evidencia con un nuevo reporte del mismo período.'))
                actualizadas += 1
                continue
            textos = ajustes.get(g['id']) or _texto_base(g)
            g.update({k: textos[k].strip() for k in TEXTOS})
            g['acciones'] = [a.strip() for a in textos['acciones'] if isinstance(a, str) and a.strip()][:8]
            g.update(generado_por='ia' if g['id'] in ajustes else 'reglas', estado='borrador', aprobacion=None,
                     creado_en=now(), historial=[dict(en=now(), por=actor, accion='Recomendación generada a partir del reporte de Data Audit.')])
            recs[g['id']] = g
            nuevas += 1
        resultado = [recs[g['id']] for g in lista]
    return dict(institucion=institucion, base=base, periodo=periodo_texto(anio, mes), nuevas=nuevas,
                actualizadas=actualizadas, con_ia=bool(ajustes), recomendaciones=resultado)


@router.get('/recommendations')
def recomendaciones(institucion: str | None = Query(None)):
    with transaction() as state:
        lista = [r for r in _recs(state).values() if r.get('estado') != 'descartada'
                 and (not institucion or r['institucion'] == institucion.upper())]
    return sorted(lista, key=lambda r: (-(r['anio'] or 0), -(r['mes'] or 0), r['base'], ORDEN[r['prioridad']], -r['afectados']))


class EdicionRecomendacion(BaseModel):
    titulo: str = Field(min_length=3, max_length=200)
    que_ocurrio: str = Field(min_length=3, max_length=4000)
    por_que: str = Field(min_length=3, max_length=4000)
    como_corregir: str = Field(min_length=3, max_length=4000)
    como_prevenir: str = Field(min_length=3, max_length=4000)
    acciones: list[str] = Field(min_length=1, max_length=12)


def _buscar(coleccion: dict, clave: str, que: str) -> dict:
    item = coleccion.get(clave)
    if not item:
        raise HTTPException(404, f'No se encontró {que}. Actualiza la página e inténtalo de nuevo.')
    return item


@router.patch('/recommendations/{key}')
def editar_recomendacion(key: str, body: EdicionRecomendacion):
    acciones = [a.strip() for a in body.acciones if a.strip()]
    if not acciones:
        raise HTTPException(422, 'Escribe al menos una acción de mejora.')
    with transaction() as state:
        r = _buscar(_recs(state), key, 'la recomendación')
        cambios = {k: [r[k], getattr(body, k).strip()] for k in TEXTOS if r[k] != getattr(body, k).strip()}
        if r['acciones'] != acciones:
            cambios['acciones'] = [r['acciones'], acciones]
        if not cambios:
            return r
        for k, (_, nuevo) in cambios.items():
            r[k] = nuevo
        nota = 'Se editó la recomendación.'
        if r['estado'] == 'aprobada':
            r['estado'], r['aprobacion'] = 'borrador', None
            nota = 'Se editó una recomendación aprobada; necesita aprobarse de nuevo.'
        r['historial'].append(dict(en=now(), por=_usuario(), accion=nota, campos=sorted(cambios)))
        return r


class Aprobacion(BaseModel):
    cargo: str = Field(min_length=2, max_length=150)


@router.post('/recommendations/{key}/approve')
def aprobar_recomendacion(key: str, body: Aprobacion):
    with transaction() as state:
        r = _buscar(_recs(state), key, 'la recomendación')
        r['estado'] = 'aprobada'
        r['aprobacion'] = dict(cargo=body.cargo.strip(), por=_usuario(), en=now())
        r['historial'].append(dict(en=now(), por=_usuario(), accion=f'Aprobada por: {body.cargo.strip()}.'))
        return r


@router.post('/recommendations/{key}/discard')
def descartar_recomendacion(key: str):
    with transaction() as state:
        r = _buscar(_recs(state), key, 'la recomendación')
        r['estado'] = 'descartada'
        r['historial'].append(dict(en=now(), por=_usuario(), accion='Descartada; no se incluirá en el manual.'))
        return r


# ---------------------------------------------------------------------------
# Manual institucional
# ---------------------------------------------------------------------------
class NuevoManual(BaseModel):
    institucion: str
    recomendaciones: list[str] | None = None


def _introduccion(nombre: str, secciones: list[dict]) -> str:
    bases = sorted({f"{s['base_nombre']} ({s['periodo']})" for s in secciones})
    altas = sum(1 for s in secciones if s['prioridad'] == 'alta')
    return (f"Este manual reúne los principales problemas de calidad encontrados en la información que "
            f"{nombre} envía al Instituto Nacional de Estadística, a partir de la revisión automática de "
            f"{', '.join(bases)}. Para cada problema se explica qué ocurrió, por qué afecta las estadísticas "
            f"oficiales y qué puede hacerse para corregirlo y evitar que se repita. "
            f"{'De las ' + str(len(secciones)) + ' recomendaciones, ' + str(altas) + ' son de prioridad alta y conviene atenderlas primero.' if altas else ''}").strip()


def _seccion(r: dict) -> dict:
    return {k: r[k] for k in ('id', 'base_nombre', 'periodo', 'prioridad', 'severidad', 'regla_nombre', 'afectados',
                              'total_registros', 'acciones', *TEXTOS)} | dict(
        evidencia=r['evidencia']['hallazgos'], aprobacion=r.get('aprobacion'))


@router.post('/manuals')
def crear_manual(body: NuevoManual):
    clave = body.institucion.upper()
    if clave not in INSTITUCIONES:
        raise HTTPException(422, 'Elige una institución válida.')
    with transaction() as state:
        aprobadas = [r for r in _recs(state).values() if r['institucion'] == clave and r['estado'] == 'aprobada'
                     and (body.recomendaciones is None or r['id'] in body.recomendaciones)]
        if not aprobadas:
            raise HTTPException(409, 'Primero aprueba al menos una recomendación de esta institución; el manual solo incluye recomendaciones aprobadas.')
        aprobadas.sort(key=lambda r: (ORDEN[r['prioridad']], -r['afectados']))
        nombre = INSTITUCIONES[clave]['nombre']
        secciones = [_seccion(r) for r in aprobadas]
        manuales = _manuales(state)
        item = dict(id=identifier(), institucion=clave, institucion_nombre=nombre,
                    titulo='Manual de prevención de errores en el envío de datos al INE',
                    introduccion=_introduccion(nombre, secciones), secciones=secciones,
                    cierre=('Antes de cada envío, revise esta guía con el equipo que prepara los archivos y ejecute '
                            'la auditoría de Data Audit para confirmar que los problemas descritos no se repiten.'),
                    estado='borrador', version=1 + max((m['version'] for m in manuales.values() if m['institucion'] == clave), default=0),
                    creado_en=now(), finalizacion=None,
                    historial=[dict(en=now(), por=_usuario(), accion=f'Manual creado con {len(secciones)} recomendaciones aprobadas.')])
        manuales[item['id']] = item
        return item


@router.get('/manuals')
def manuales(institucion: str | None = Query(None)):
    with transaction() as state:
        lista = [m for m in _manuales(state).values() if not institucion or m['institucion'] == institucion.upper()]
    return sorted(lista, key=lambda m: m['creado_en'], reverse=True)


@router.get('/manuals/{key}')
def manual(key: str):
    with transaction() as state:
        return _buscar(_manuales(state), key, 'el manual')


class SeccionEditada(BaseModel):
    id: str
    titulo: str = Field(min_length=3, max_length=200)
    que_ocurrio: str = Field(min_length=3, max_length=4000)
    por_que: str = Field(min_length=3, max_length=4000)
    como_corregir: str = Field(min_length=3, max_length=4000)
    como_prevenir: str = Field(min_length=3, max_length=4000)
    acciones: list[str] = Field(min_length=1, max_length=12)


class EdicionManual(BaseModel):
    titulo: str = Field(min_length=3, max_length=200)
    institucion_nombre: str = Field(min_length=2, max_length=200)
    introduccion: str = Field(min_length=3, max_length=6000)
    cierre: str = Field(default='', max_length=4000)
    secciones: list[SeccionEditada]


@router.patch('/manuals/{key}')
def editar_manual(key: str, body: EdicionManual):
    with transaction() as state:
        m = _buscar(_manuales(state), key, 'el manual')
        if m['estado'] != 'borrador':
            raise HTTPException(409, 'Este manual ya está finalizado y no se puede modificar. Crea una versión nueva si necesitas cambiarlo.')
        actuales = {s['id']: s for s in m['secciones']}
        if {s.id for s in body.secciones} != set(actuales):
            raise HTTPException(409, 'El manual cambió en otra ventana. Actualiza la página antes de guardar.')
        for s in body.secciones:
            destino = actuales[s.id]
            destino.update({k: getattr(s, k).strip() for k in TEXTOS})
            destino['acciones'] = [a.strip() for a in s.acciones if a.strip()] or destino['acciones']
        m['secciones'] = [actuales[s.id] for s in body.secciones]
        m.update(titulo=body.titulo.strip(), institucion_nombre=body.institucion_nombre.strip(),
                 introduccion=body.introduccion.strip(), cierre=body.cierre.strip())
        m['historial'].append(dict(en=now(), por=_usuario(), accion='Se guardaron cambios en el contenido.'))
        return m


@router.post('/manuals/{key}/finalize')
def finalizar_manual(key: str, body: Aprobacion):
    with transaction() as state:
        m = _buscar(_manuales(state), key, 'el manual')
        if m['estado'] == 'final':
            return m
        m['estado'] = 'final'
        m['finalizacion'] = dict(cargo=body.cargo.strip(), por=_usuario(), en=now())
        m['historial'].append(dict(en=now(), por=_usuario(), accion=f'Manual finalizado por: {body.cargo.strip()}.'))
        return m


@router.delete('/manuals/{key}')
def borrar_manual(key: str):
    with transaction() as state:
        m = _buscar(_manuales(state), key, 'el manual')
        if m['estado'] != 'borrador':
            raise HTTPException(409, 'Un manual finalizado no se puede borrar.')
        del _manuales(state)[key]
    return dict(ok=True)


@router.get('/manuals/{key}/pdf')
def manual_pdf(key: str, descargar: bool = False):
    from .manual_pdf import generar_pdf
    with transaction() as state:
        m = json.loads(json.dumps(_buscar(_manuales(state), key, 'el manual')))
    contenido = generar_pdf(m)
    nombre = f"manual-{m['institucion'].lower()}-v{m['version']}{'-borrador' if m['estado'] != 'final' else ''}.pdf"
    disposicion = 'attachment' if descargar else 'inline'
    return Response(contenido, media_type='application/pdf',
                    headers={'Content-Disposition': f'{disposicion}; filename="{nombre}"', 'Cache-Control': 'no-store'})
