import json
import unittest
from unittest.mock import patch
from app import db, models as m
from app.session_report_edit import report_values
from tests import test_staff_session_report as fixtures
from tests import test_session_reports as reports


class SessionReportEditTest(unittest.TestCase):
    setUp = fixtures.StaffSessionReportTest.setUp
    tearDown = fixtures.StaffSessionReportTest.tearDown
    post = fixtures.StaffSessionReportTest.post
    admin_client = reports.SessionReportsTest.admin_client
    review_people = fixtures.StaffSessionReportTest.review_people
    review_answers = fixtures.StaffSessionReportTest.review_answers

    def saved(self, online=False, **values):
        if online:
            self.record.format = 'Online'
            self.record.modules = 'Listening and speaking'
            db.session.commit()
        response = self.post(**values)
        self.assertEqual(response.status_code, 200, response.json)
        self.report = m.StaffExamSessionReport.query.one()
        self.edit_url = f'/quality-control/session-reports/{self.record.id}/edit'
        self.admin, self.user = self.admin_client()

    def payload(self):
        values = report_values(self.report)
        for key, value in list(values.items()):
            if isinstance(value, bool):
                values[key] = '1' if value else '0'
            elif isinstance(value, list) and key != 'return_verification':
                values[key] = json.dumps(value)
        if self.record.format == 'Onsite':
            from app.staff_return_materials import report_return_view
            with self.app.test_request_context():
                values['return_instructions_version'] = report_return_view(self.record, self.assignment, self.share)['version']
        values.update(csrf_token='test', _report_revision=str(len(json.loads(self.report.edit_history))))
        return values

    def test_editor_all_formats_and_audited_correction_without_date_gate(self):
        self.saved()
        submitted = self.report.submitted_at
        for index, format_name in enumerate(('Onsite', 'Online at exam centre', 'Online')):
            self.record.format = format_name
            db.session.commit()
            page = self.admin.get(self.edit_url)
            self.assertEqual(page.status_code, 200)
            self.assertEqual(page.headers['X-Frame-Options'], 'SAMEORIGIN')
            self.assertIn(b'data-admin-report-edit', page.data)
            self.assertIn(b'Save changes', page.data)
            values = self.payload()
            values.update(optional_comments='Correction ' + format_name, it_issues='0')
            if format_name == 'Online':
                values.update(examiner_marks_checked='1', recordings_reminder_confirmed='1')
            with patch('app.routes.staff_report_available', return_value=False), patch('app.routes.staff_report_feedback_submitted', return_value=True):
                result = self.admin.post(self.edit_url, data=values)
            self.assertEqual(result.status_code, 200, result.json)
            db.session.refresh(self.report)
            self.assertEqual(self.report.optional_comments, 'Correction ' + format_name)
            self.assertEqual(self.report.submitted_at, submitted)
            history = json.loads(self.report.edit_history)
            self.assertEqual(len(history), index + 1)
            self.assertEqual(history[-1]['user_id'], self.user.id)
            self.assertEqual(history[-1]['editor'], 'Review Admin')
            self.assertEqual(history[-1]['after']['optional_comments'], 'Correction ' + format_name)
        self.assertEqual(self.post().status_code, 409)

    def test_return_instruction_changes_require_a_new_acknowledgement_in_editor(self):
        import re
        self.saved()
        def initial_values():
            html = self.admin.get(self.edit_url).get_data(as_text=True)
            return json.loads(re.search(r'<script type="application/json" id="report-edit-values">(.*?)</script>', html, re.S).group(1))
        self.assertTrue(initial_values()['return_instructions_confirmed'])
        control = m.ExamSessionSinapsisControl.query.filter_by(exam_session_id=self.record.id).one()
        control.return_instructions_html = '<p>Updated return deadline.</p>'
        db.session.commit()
        self.assertFalse(initial_values()['return_instructions_confirmed'])
        values = self.payload(); values['return_instructions_confirmed'] = '0'
        with patch('app.routes.staff_report_feedback_submitted', return_value=True):
            self.assertEqual(self.admin.post(self.edit_url, data=values).status_code, 400)
            values['return_instructions_confirmed'] = '1'
            response = self.admin.post(self.edit_url, data=values)
        self.assertEqual(response.status_code, 200, response.json)
        db.session.refresh(self.report)
        self.assertEqual(json.loads(self.report.return_instructions_context)['instructions_html'], '<p>Updated return deadline.</p>')
        self.assertEqual(len(json.loads(self.report.edit_history)), 1)

    def test_permissions_csrf_and_concurrent_edit(self):
        self.saved(online=True)
        self.user.is_superadmin = False; db.session.commit()
        denied = self.admin
        self.assertEqual(denied.get(self.edit_url).status_code, 403)
        self.assertEqual(denied.post(self.edit_url, data=self.payload()).status_code, 403)
        self.user.is_superadmin = True; db.session.commit()
        self.assertEqual(self.admin.post(self.edit_url, data={**self.payload(), 'csrf_token': 'wrong'}).status_code, 400)
        self.assertEqual(self.admin.post(self.edit_url, data={**self.payload(), '_report_revision':'-1'}).status_code, 409)
        self.assertEqual(json.loads(self.report.edit_history), [])
        page = self.admin.get(f'/quality-control/session-reports/{self.record.id}')
        self.assertIn(b'>Edit</button>', page.data)

    def test_correct_and_remove_linked_absence(self):
        row = dict(number='00120', name='Candidate', institution='School', exam='B2 Competency', component='Listening', reason='Original reason')
        self.saved(online=True, component_completion='component_absences', component_absences=json.dumps([row]))
        candidate = m.AbsenceCandidate.query.one()
        candidate.review_status = 'Confirmed'; candidate.approved = True; db.session.commit()
        updated = {**row, 'component':'Speaking', 'reason':'Corrected explanation', 'name':'Corrected name'}
        values = self.payload(); values['component_absences'] = json.dumps([updated])
        self.assertEqual(self.admin.post(self.edit_url, data=values).status_code, 200)
        db.session.refresh(candidate)
        self.assertEqual(candidate.number, '00120')
        self.assertEqual(json.loads(candidate.absent_modules), ['Speaking'])
        self.assertEqual(candidate.component_reason, 'Corrected explanation')
        self.assertEqual(candidate.review_status, 'Pending')
        self.assertFalse(candidate.approved)
        values = self.payload(); values.update(component_completion='complete', component_absences='[]')
        response = self.admin.post(self.edit_url, data=values)
        self.assertEqual(response.status_code, 200, response.json)
        self.assertEqual(m.AbsenceCandidate.query.count(), 0)
        self.assertEqual(len(json.loads(self.report.edit_history)), 2)

    def test_invalid_edit_is_atomic(self):
        self.saved(online=True)
        values = self.payload(); values.update(optional_comments='Should not save', it_issues='')
        self.assertEqual(self.admin.post(self.edit_url, data=values).status_code, 400)
        db.session.refresh(self.report)
        self.assertEqual(self.report.optional_comments, '')
        self.assertEqual(self.report.edit_history, '[]')

    def test_edit_keeps_submitted_staff_roster_and_updates_assessments(self):
        examiner, _ = self.review_people()
        self.saved(**self.review_answers())
        m.ExamSessionExaminerAssignment.query.filter_by(exam_session_id=self.record.id).delete()
        db.session.commit()
        values = self.payload()
        values[f'review.examiner:{examiner.id}.notes'] = 'Corrected assessment notes'
        with patch('app.routes.staff_report_feedback_submitted', return_value=True):
            result = self.admin.post(self.edit_url, data=values)
        self.assertEqual(result.status_code, 200, result.json)
        saved = json.loads(self.report.staff_assessments)
        self.assertEqual(len(saved), 3)
        self.assertEqual(next(row for row in saved if row['key'] == f'examiner:{examiner.id}')['notes'], 'Corrected assessment notes')

    def test_editor_media_upload_is_authenticated_and_not_date_restricted(self):
        from io import BytesIO
        self.saved()
        with patch('app.staff_report_media.folder_metadata'), patch('app.staff_report_media.upload_document') as upload:
            result = self.admin.post(self.edit_url + '/media', data={'csrf_token':'test', 'file':(BytesIO(b'image'), 'photo.jpg')})
        self.assertEqual(result.status_code, 200, result.json)
        upload.assert_called_once()

    def test_shared_candidate_keeps_document_and_remaining_source(self):
        row = dict(number='00120', name='Candidate', institution='School', exam='B2 Competency', component='Listening', reason='Component explanation')
        it_row = {key: value for key, value in row.items() if key != 'component'}
        it_row.update(modules=['Listening and speaking'], reason='IT explanation')
        self.saved(online=True, component_completion='component_absences', component_absences=json.dumps([row]), it_issues='1', it_absences=json.dumps([it_row]))
        candidate = m.AbsenceCandidate.query.one()
        db.session.add(m.AttendanceDocument(file_id='evidence', folder_id='folder', filename='evidence.pdf', mime_type='application/pdf'))
        candidate.document_id = 'evidence'
        candidate.review_status = 'Confirmed'; candidate.approved = True; db.session.commit()
        values = self.payload(); values.update(component_completion='complete', component_absences='[]')
        result = self.admin.post(self.edit_url, data=values)
        self.assertEqual(result.status_code, 200, result.json)
        db.session.refresh(candidate)
        self.assertEqual(candidate.document_id, 'evidence')
        self.assertEqual(candidate.component_reason, '')
        self.assertEqual(candidate.it_reason, 'IT explanation')
        self.assertEqual(json.loads(candidate.absent_modules), ['Listening and speaking'])
        self.assertEqual(candidate.review_status, 'Pending')
        values = self.payload(); values.update(it_issues='0', it_absences='[]')
        self.assertEqual(self.admin.post(self.edit_url, data=values).status_code, 200)
        db.session.refresh(candidate)
        self.assertEqual(candidate.document_id, 'evidence')
        self.assertEqual(candidate.it_reason, '')
        self.assertEqual(json.loads(candidate.absent_modules), [])
