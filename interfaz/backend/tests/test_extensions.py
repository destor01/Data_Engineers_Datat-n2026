import json
import os
from pathlib import Path
import tempfile
import unittest
from fastapi.testclient import TestClient
from extensions.app import app


class FlowTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.previous = {key: os.environ.get(key) for key in ('QA_STORAGE', 'QA_DEMO_STORE')}
        os.environ['QA_STORAGE'] = 'demo'
        os.environ['QA_DEMO_STORE'] = str(Path(self.folder.name) / 'state.json')
        self.client = TestClient(app)

    def tearDown(self):
        for key, value in self.previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        self.folder.cleanup()

    def test_interview_and_reconciliation(self):
        schema = json.loads((Path(__file__).parents[3] / 'survey-audit/templates/pilot.synthetic.json').read_text())
        template = self.client.post('/api/surveys/templates', json={'schema_data': schema}).json()
        path = '/api/surveys/templates/' + template['id']
        self.assertEqual(self.client.post(path + '/publish').status_code, 200)
        self.assertEqual(self.client.patch(path, json={'schema_data': schema}).status_code, 409)
        interview = self.client.post('/api/surveys/interviews', json={'template_id': template['id']}).json()
        path = '/api/surveys/interviews/' + interview['id']
        self.assertEqual(self.client.post(path + '/submit').status_code, 422)
        body = {'responses': {'members': 4, 'improvements': '02', 'description': 'Histórico'}, 'revision': 1}
        self.assertEqual(self.client.patch(path, json=body).status_code, 200)
        self.assertEqual(self.client.patch(path, json=body).status_code, 409)
        self.assertEqual(self.client.post(path + '/submit').status_code, 200)
        self.assertNotIn('description', self.client.get(path).json()['validation']['active_responses'])
        transcript = {'consent': True, 'synthetic': True, 'result': {'turns': [
            {'speaker': 'A', 'start': 0, 'end': 1, 'text': '¿Cuántos viven?'},
            {'speaker': 'B', 'start': 1, 'end': 2, 'text': 'Cinco'}]}}
        self.assertEqual(self.client.post(path + '/transcripts', json=transcript).status_code, 200)
        self.client.post(path + '/transcripts', json=transcript)
        self.assertEqual(len(self.client.get(path).json()['transcripts']), 1)
        result = self.client.post(path + '/reconcile', json={'question_id': 'members', 'turn_ids': [0, 1], 'observed_value': 5, 'interviewer': 'A'})
        self.assertEqual(result.json()['status'], 'mismatch')
        self.assertEqual(self.client.get(path).json()['responses']['members'], 4)
        self.assertEqual(TestClient(app).get(path).status_code, 200)

    def test_recommendations_and_manual(self):
        report = {'institution': 'RENAP', 'source_run_ref': 'synthetic-test', 'source_run_at': '2026-11-25',
                  'synthetic': True, 'report': {'total_registros': 10, 'hallazgos': [
                      {'regla': 'geo_required', 'n': 2, 'severidad': 'error', 'ejemplos': ['SENSITIVE_SENTINEL']}]}}
        first = self.client.post('/api/improvement/reports', json=report)
        self.assertEqual(first.status_code, 200)
        self.client.post('/api/improvement/reports', json=report)
        recs = self.client.get('/api/improvement/recommendations').json()
        self.assertEqual(len(recs), 1)
        self.assertNotIn('SENSITIVE_SENTINEL', json.dumps(recs))
        manual = self.client.post('/api/improvement/manuals', json={'institution': 'RENAP', 'title': 'Manual piloto',
            'content': 'Ejemplos sintéticos y controles antes del envío', 'source_ids': [recs[0]['id']]}).json()
        path = '/api/improvement/manuals/' + manual['id']
        self.assertEqual(self.client.post(path + '/approve').status_code, 200)
        self.assertIn('validación institucional', self.client.get(path + '/download').text)
        self.assertEqual(self.client.patch(path, json={'title': 'Manual cambiado', 'content': 'Contenido cambiado'}).status_code, 409)


if __name__ == '__main__':
    unittest.main()
