import json
import unittest

from tests import test_schedule_workflow as fixtures
from app import db
from app.models import ExamSessionFinanceControl


class FinanceCardCommentsTest(unittest.TestCase):
    setUp = fixtures.ScheduleWorkflowTest.setUp
    tearDown = fixtures.ScheduleWorkflowTest.tearDown
    login_client = fixtures.ScheduleWorkflowTest.login_client

    def save(self, **changes):
        self.session_record.monthly_registrations_closed = True
        self.session_record.date_confirmation_status = 'Confirmed'
        db.session.commit()
        data = {'csrf_token': 'token', 'finance_institutions_form': '1', 'finance_status': '',
                'finance_comments': 'Main comment', 'institution_name': ['School A', 'School B'],
                'institution_standing': ['', 'Effective clearance'],
                'institution_comments': ['Comment A', 'Comment B'], **changes}
        return self.login_client().post(
            f'/pre-session-control-tower/sessions/{self.session_record.id}/finance-control',
            data=data, headers={'X-Finance-Autosave': '1', 'Accept': 'application/json'})

    def test_comments_are_independent_optional_and_render_safely(self):
        self.assertEqual(self.save(finance_comments='<script>unsafe</script>').status_code, 200)
        control = ExamSessionFinanceControl.query.one()
        self.assertEqual(control.comments, '<script>unsafe</script>')
        self.assertEqual(control.status, 'Not reviewed')
        self.assertEqual([row['comments'] for row in json.loads(control.additional_institutions)], ['Comment A', 'Comment B'])
        html = self.login_client().get(f'/pre-session-control-tower?session_year=2026&view=sessions&session_modal={self.session_record.id}&open_schedule_modal={self.session_record.id}&finance_only=1').get_data(as_text=True)
        self.assertIn('&lt;script&gt;unsafe&lt;/script&gt;', html)
        self.assertIn('>Comment A</textarea>', html)
        self.assertIn('>Comment B</textarea>', html)
        self.assertNotRegex(html, r'<textarea[^>]*name="(?:finance_comments|institution_comments)"[^>]*required')
        self.assertEqual(self.save(finance_comments='', institution_name=['School B'],
            institution_standing=['Effective clearance'], institution_comments=['Updated B']).status_code, 200)
        db.session.refresh(control)
        self.assertEqual(control.comments, '')
        self.assertEqual(json.loads(control.additional_institutions), [
            {'name': 'School B', 'standing': 'Effective clearance', 'comments': 'Updated B'}])

    def test_invalid_comments_do_not_overwrite_saved_values(self):
        self.assertEqual(self.save().status_code, 200)
        for changes in ({'finance_comments': 'x' * 2001},
                        {'institution_comments': ['x' * 2001, 'B']},
                        {'institution_comments': ['A']}):
            with self.subTest(changes=next(iter(changes))):
                self.assertEqual(self.save(**changes).status_code, 400)
                db.session.expire_all()
                control = ExamSessionFinanceControl.query.one()
                self.assertEqual(control.comments, 'Main comment')
                self.assertEqual(json.loads(control.additional_institutions)[1]['comments'], 'Comment B')
