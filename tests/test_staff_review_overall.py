import unittest
from types import SimpleNamespace
from unittest.mock import patch

from app.staff_report_review import assessment_criteria, validate_assessments


class OverallRatingTest(unittest.TestCase):
    def test_overall_matches_other_ratings_for_both_formats(self):
        row = dict(key='examiner:1', name='Examiner', role='Examiner', person_ref='1')
        for format_name in ('Online', 'Onsite'):
            with self.subTest(format=format_name), patch('app.staff_report_review.assessment_roster', return_value=[row]):
                record = SimpleNamespace(id=1, format=format_name)
                prefix = 'review.examiner:1.'
                answers = {prefix + c['key']: c['best'] for c in assessment_criteria(record)}
                self.assertEqual(validate_assessments(record, answers)[0]['criteria']['overall'], 'Remarkable')
                answers[prefix + 'overall'] = 'Unsatisfactory'
                answers[prefix + 'comments.overall'] = 'Explanation'
                with self.assertRaisesRegex(ValueError, 'Overall rating'):
                    validate_assessments(record, answers)
                answers[prefix + 'attitude'] = 'Satisfactory'
                self.assertEqual(validate_assessments(record, answers)[0]['criteria']['overall'], 'Unsatisfactory')
                answers[prefix + 'overall'] = 'Remarkable'
                with self.assertRaisesRegex(ValueError, 'Overall rating'):
                    validate_assessments(record, answers)
                answers[prefix + 'overall'] = 'Satisfactory'
                validate_assessments(record, answers)
