import copy
import json
from pathlib import Path
import unittest
from survey_audit.validation import check_template, validate

TEMPLATE = json.loads((Path(__file__).parents[1] / 'templates/pilot.synthetic.json').read_text(encoding='utf-8'))


class ValidationTests(unittest.TestCase):
    def test_leading_zero_codes(self):
        self.assertTrue(validate(TEMPLATE, {'members': 4, 'improvements': '02'})['valid'])
        self.assertFalse(validate(TEMPLATE, {'members': 4, 'improvements': 2})['valid'])

    def test_server_types(self):
        for value in [True, '4', 4.5, 0]:
            self.assertFalse(validate(TEMPLATE, {'members': value, 'improvements': '02'})['valid'])

    def test_skip_preserves_history_excludes_active(self):
        responses = {'members': 4, 'improvements': '02', 'description': 'Techo'}
        result = validate(TEMPLATE, responses)
        self.assertEqual(result['applicability']['description'], 'not_applicable')
        self.assertNotIn('description', result['active_responses'])
        self.assertEqual(responses['description'], 'Techo')

    def test_conditional_required(self):
        result = validate(TEMPLATE, {'members': 4, 'improvements': '01'})
        self.assertEqual(result['findings'][0]['question_id'], 'description')

    def test_unsupported_and_cyclic_conditions(self):
        template = copy.deepcopy(TEMPLATE)
        template['questions'][0]['visible_when'] = {'question_id': 'description', 'operator': 'eval'}
        self.assertTrue(check_template(template))

    def test_unknown_question(self):
        self.assertFalse(validate(TEMPLATE, {'injected': 2})['valid'])


if __name__ == '__main__':
    unittest.main()
