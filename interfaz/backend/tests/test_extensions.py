"""Flujos completos de Survey Audit y Quality Improvement con la IA simulada."""
import json
import os
import re
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient
from fpdf import FPDF

from extensions import api as sapi, cuestionario, ia
from extensions.app import app

from tests.encuesta_prueba import PAGINAS

FUENTE = Path(__file__).parents[1] / 'extensions/fuentes/DejaVuSans.ttf'


def pdf_prueba(paginas: int = 5) -> bytes:
    doc = FPDF(); doc.add_font('D', '', str(FUENTE))
    for i in range(1, paginas + 1):
        doc.add_page(); doc.set_font('D', size=12); doc.multi_cell(0, 8, f'Página {i} del cuestionario de prueba')
    return bytes(doc.output())


def ia_simulada(model, sistema, contenido, esquema, max_tokens):
    if sistema == cuestionario.SISTEMA:
        d, h = map(int, re.search(r'páginas (\d+) a (\d+)', contenido[1]['text']).groups())
        out = dict(secciones=[], preguntas=[], catalogos=[])
        for p in range(d, h + 1):
            for k in out:
                out[k] += PAGINAS[p][k]
        return out
    if sistema == sapi.SISTEMA_VERIF:
        preguntas = json.loads(contenido[0]['text'].split('PREGUNTAS A VERIFICAR (JSON):\n')[1])
        res = []
        for p in preguntas:
            if 'agua entubada' in p['pregunta']:
                res.append(dict(clave=p['clave'], turnos=[0, 1], respuesta_escuchada='Sí', estado='coincidencia', explicacion='Dijo que sí.'))
            elif 'horas' in p['pregunta']:
                res.append(dict(clave=p['clave'], turnos=[2, 3], respuesta_escuchada='8 horas', estado='discrepancia', explicacion='Se registró 12 y dijo 8.'))
            else:
                res.append(dict(clave=p['clave'], turnos=[], respuesta_escuchada='', estado='no_verificable', explicacion='No se escucha.'))
        return dict(resultados=res)
    raise AssertionError('llamada inesperada a la IA')


class Base(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.previous = {k: os.environ.get(k) for k in ('QA_STORAGE', 'QA_DEMO_STORE', 'MEJORA_IA', 'SURVEY_PAGINAS_BLOQUE')}
        os.environ.update(QA_STORAGE='demo', QA_DEMO_STORE=str(Path(self.folder.name) / 'state.json'), MEJORA_IA='0', SURVEY_PAGINAS_BLOQUE='2')
        self.responder = ia.responder
        ia.responder = ia_simulada
        self.client = TestClient(app)

    def tearDown(self):
        ia.responder = self.responder
        for k, v in self.previous.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        self.folder.cleanup()


class SurveyTests(Base):
    def formulario(self):
        c = self.client
        self.assertEqual(c.post('/api/surveys/documents', json={'nombre': 'X', 'archivo': 'x.docx', 'tamano': 10}).status_code, 422)
        d = c.post('/api/surveys/documents', json={'nombre': 'Encuesta de prueba', 'archivo': 'c.pdf', 'tamano': 900}).json()
        did = d['documento']['id']
        self.assertEqual(c.put(d['subida']['url'], content=pdf_prueba()).status_code, 200)
        prep = c.post(f'/api/surveys/documents/{did}/preparar').json()
        self.assertEqual(prep['paginas'], 5)
        self.assertNotEqual(c.post(f'/api/surveys/documents/{did}/formulario').status_code, 200)  # faltan páginas
        for b in prep['bloques']:
            self.assertEqual(c.post(f'/api/surveys/documents/{did}/leer', json=b).status_code, 200)
        t = c.post(f'/api/surveys/documents/{did}/formulario').json()
        return t

    def test_formulario_desde_pdf(self):
        t = self.formulario()
        s = t['schema']
        self.assertEqual(len(s['sections']), 2)  # la «continuación» se une a su sección
        self.assertEqual([x['scope'] for x in s['sections']], ['household', 'person'])
        org = next(q for q in s['questions'] if 'organización' in q['label'])
        self.assertEqual([o['code'] for o in org['options']], ['1', '10'])  # catálogo resuelto
        alertas = [q for q in s['questions'] if q.get('alertas')]
        self.assertEqual(len(alertas), 1)  # «Pase a 99» no existe
        self.assertEqual(self.client.post(f"/api/surveys/templates/{t['id']}/publish").status_code, 409)

    def test_entrevista_completa(self):
        c = self.client
        t = self.formulario()
        s = t['schema']
        for q in s['questions']:
            q.pop('alertas', None)
        self.assertEqual(c.patch(f"/api/surveys/templates/{t['id']}", json={'schema_data': s, 'revision': t['revision']}).status_code, 200)
        self.assertEqual(c.post(f"/api/surveys/templates/{t['id']}/publish").status_code, 200)
        self.assertEqual(c.post('/api/surveys/interviews', json={'template_id': t['id']}).status_code, 422)
        e = c.post('/api/surveys/interviews', json={'template_id': t['id'], 'nombre': 'Hogar 15'}).json()
        otra = c.post('/api/surveys/interviews', json={'template_id': t['id'], 'nombre': 'Hogar 16'}).json()
        self.assertEqual((e['codigo'], otra['codigo']), ('ENT-0001', 'ENT-0002'))
        path = f"/api/surveys/interviews/{e['id']}"
        c.patch(path, json={'responses': {'q0001': '1', 'q0002': 30, '_personas': 1}, 'revision': 1})
        fin = c.post(path + '/submit')
        self.assertEqual(fin.status_code, 422)
        mensajes = [x['mensaje'] for x in fin.json()['errores']]
        self.assertIn('El valor debe ser mayor o igual a 0 y menor o igual a 24.', mensajes)
        self.assertNotRegex(json.dumps(fin.json(), ensure_ascii=False), r'HTTP|\b4\d\d\b|Traceback')
        c.patch(path, json={'responses': {'q0001': '1', 'q0002': 12, '_personas': 1, 'q0004#1': 35, 'q0005#1': '2', 'q0007#1': '1'}, 'revision': 2})
        self.assertEqual(c.post(path + '/submit').status_code, 200)
        audio = {'fuente': 'Audio Audit', 'job_id': 'abc123', 'result': {'speakers': ['A', 'B'], 'turns': [
            {'speaker': 'A', 'start': 1, 'end': 4, 'text': '¿Tienen agua entubada?'}, {'speaker': 'B', 'start': 4, 'end': 6, 'text': 'Sí'},
            {'speaker': 'A', 'start': 7, 'end': 9, 'text': '¿Cuántas horas?'}, {'speaker': 'B', 'start': 9, 'end': 11, 'text': 'Como 8 horas'}]}}
        vin = lambda ruta, **kw: c.post(ruta + '/transcripts', json={'consent': True, 'entrevista_codigo': 'ENT-0001', 'datos': audio, **kw})
        self.assertEqual(vin(path, consent=False).status_code, 422)
        self.assertEqual(vin(path, entrevista_codigo='ENT-0002').status_code, 409)
        self.assertEqual(vin(path).status_code, 200)
        self.assertEqual(vin(f"/api/surveys/interviews/{otra['id']}", entrevista_codigo='ENT-0002').status_code, 409)
        self.assertNotEqual(c.post(path + '/verificacion').status_code, 200)  # falta elegir encuestador
        c.patch(path + '/encuestador', json={'hablante': 'A'})
        v = c.post(path + '/verificacion').json()
        for n in range(v['lotes']):
            self.assertEqual(c.post(f'{path}/verificacion/{n}').status_code, 200)
        h = c.get(path).json()['hallazgos']
        estados = {x['estado'] for x in h}
        self.assertTrue({'coincidencia', 'discrepancia', 'no_verificable'} <= estados)
        d = next(x for x in h if x['estado'] == 'discrepancia')
        self.assertEqual(d['registrada'], '12')
        self.assertEqual([y['inicio'] for y in d['evidencia']], [7, 9])
        self.assertEqual(c.get(path).json()['responses']['q0002'], 12)  # la respuesta oficial no cambia
        r = c.patch(f"{path}/findings/{d['id']}", json={'estado': 'confirmado', 'justificacion': 'Se escucha 8 horas.'})
        self.assertEqual(r.json()['revision']['estado'], 'confirmado')


REPORTE = {'base': 'DETENIDOS', 'anio': 2025, 'mes': 3, 'total_registros': 100, 'hallazgos': [
    {'regla': 'GEN_FECHA_INVALIDA', 'columna': 'fecha', 'n': 4, 'severidad': 'error', 'nombre': 'Fecha no válida', 'porcentaje': 4.0,
     'mensaje': 'Fecha no válida.', 'ejemplos': [{'fila': 8, 'valor': 'SENSITIVE_SENTINEL'}]},
    {'regla': 'GEN_FECHA_INVALIDA', 'columna': 'fecha_hecho', 'n': 2, 'severidad': 'error', 'nombre': 'Fecha no válida', 'mensaje': 'Fecha no válida.'},
    {'regla': 'GEN_VACIO', 'columna': 'edad', 'n': 10, 'severidad': 'advertencia', 'nombre': 'Valor vacío', 'mensaje': 'Vacío.'}]}


class ImprovementTests(Base):
    def test_recomendaciones_y_manual(self):
        c = self.client
        r = c.post('/api/improvement/reports', json={'report': REPORTE, 'archivo': 'reporte.json'}).json()
        self.assertEqual((r['institucion'], r['nuevas']), ('PNC', 2))  # agrupa por institución + período + regla
        self.assertEqual(c.post('/api/improvement/reports', json={'report': REPORTE}).json()['nuevas'], 0)
        self.assertEqual(c.post('/api/improvement/reports', json={'report': {**REPORTE, 'mes': 4}}).json()['nuevas'], 2)
        recs = c.get('/api/improvement/recommendations').json()
        self.assertNotIn('SENSITIVE_SENTINEL', json.dumps(recs))
        fecha = next(x for x in recs if x['regla'] == 'GEN_FECHA_INVALIDA' and 'marzo' in x['periodo'].lower())
        self.assertEqual(len(fecha['evidencia']['hallazgos']), 2)
        for k in ('que_ocurrio', 'por_que', 'como_corregir', 'como_prevenir'):
            self.assertTrue(fecha[k])
        path = f"/api/improvement/recommendations/{fecha['id']}"
        self.assertEqual(c.post('/api/improvement/manuals', json={'institucion': 'PNC'}).status_code, 409)
        edicion = {k: fecha[k] for k in ('que_ocurrio', 'por_que', 'como_corregir', 'como_prevenir', 'acciones')}
        self.assertEqual(c.patch(path, json={**edicion, 'titulo': 'Fechas inválidas en detenidos'}).status_code, 200)
        self.assertEqual(c.post(path + '/approve', json={}).status_code, 422)
        self.assertEqual(c.post(path + '/approve', json={'cargo': 'Jefa de Calidad'}).json()['aprobacion']['cargo'], 'Jefa de Calidad')
        m = c.post('/api/improvement/manuals', json={'institucion': 'PNC'}).json()
        self.assertEqual([s['titulo'] for s in m['secciones']], ['Fechas inválidas en detenidos'])
        mp = f"/api/improvement/manuals/{m['id']}"
        cuerpo = {k: m[k] for k in ('titulo', 'introduccion', 'cierre')}
        cuerpo['secciones'] = [{k: s[k] for k in ('id', 'titulo', 'que_ocurrio', 'por_que', 'como_corregir', 'como_prevenir', 'acciones')} for s in m['secciones']]
        editado = c.patch(mp, json={**cuerpo, 'institucion_nombre': 'PNC — Estadística'})
        self.assertEqual(editado.json()['institucion_nombre'], 'PNC — Estadística')
        pdf = c.get(mp + '/pdf')
        self.assertEqual(pdf.headers['content-type'], 'application/pdf')
        self.assertTrue(pdf.content.startswith(b'%PDF'))
        self.assertEqual(c.get(mp + '/download').status_code, 404)  # ya no hay descarga .md
        self.assertEqual(c.post(mp + '/finalize', json={'cargo': 'Director'}).status_code, 200)
        self.assertEqual(c.patch(mp, json={**cuerpo, 'institucion_nombre': 'Otra'}).status_code, 409)


if __name__ == '__main__':
    unittest.main()
