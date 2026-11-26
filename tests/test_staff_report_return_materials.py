"""Onsite report return instructions, required acknowledgements and live server gates."""
import json
import re
import unittest
from types import SimpleNamespace
from unittest.mock import patch
from flask import Response
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import Session
from app import db, models as m
from app.staff_return_materials import report_return_view, RECIPIENT_CONFIRMATION, SUPERVISOR_CONFIRMATION
from tests import test_staff_session_report as fixtures


class StaffReportReturnMaterialsTest(unittest.TestCase):
    setUp = fixtures.StaffSessionReportTest.setUp
    tearDown = fixtures.StaffSessionReportTest.tearDown
    post = fixtures.StaffSessionReportTest.post
    review_answers = fixtures.StaffSessionReportTest.review_answers

    def control(self):
        return m.ExamSessionSinapsisControl.query.filter_by(exam_session_id=self.record.id).one()

    def page(self):
        html = self.client.get(f'/my-exam-sessions/{self.share.token}?session_year=2026').get_data(as_text=True)
        start = html.index('<li data-report-stage="checks" data-report-return-materials>')
        return html, html[start:html.index('<li data-report-stage="finish">', start)]

    def test_own_instructions_follow_feedback_and_confirmation_is_saved(self):
        html, section = self.page()
        self.assertLess(html.index('<b class="staff-report-check-title">Exam centre feedback</b>'), html.index('data-report-return-materials>'))
        self.assertIn('Return of exam session materials', section)
        self.assertIn('Immediate location drop-off', section)
        self.assertIn('href="https://maps.example.com/materials-return"', section)
        self.assertIn(RECIPIENT_CONFIRMATION, section)
        self.assertNotIn('the following instructions apply', section)
        self.assertNotIn('Read important instructions', section)
        self.assertRegex(section, r'name="return_instructions_confirmed"[^>]*required[^>]*data-report-return-confirmed>')
        self.assertEqual(self.post().status_code, 200)
        saved = m.StaffExamSessionReport.query.one()
        self.assertTrue(saved.return_instructions_confirmed)
        context = json.loads(saved.return_instructions_context)
        self.assertEqual(context['recipient_name'], self.person.full_name)
        self.assertTrue(context['acknowledged_by_recipient'])
        self.assertEqual(context['method'], 'location_drop_off')

    def test_other_role_recipient_has_named_warning_and_alternative_confirmation(self):
        self.assignment.is_shipment_recipient = False
        person = m.AcademicStaff(full_name='Responsible <Colleague>', status='Active', roles='Examiner')
        db.session.add(person); db.session.flush()
        assigned = m.ExamSessionExaminerAssignment(exam_session_id=self.record.id, team_member_id=person.id,
            participation_status='Confirmed', is_shipment_recipient=True)
        db.session.add(assigned); db.session.commit()
        control = self.control(); control.return_review_required = False; db.session.commit()
        _, section = self.page()
        self.assertIn('<strong>Important:</strong> the following instructions apply to <strong>Responsible &lt;Colleague&gt;</strong>.', section)
        self.assertIn(SUPERVISOR_CONFIRMATION, section)
        self.assertNotIn(RECIPIENT_CONFIRMATION, section)
        response = self.post(**self.review_answers())
        self.assertEqual(response.status_code, 200, response.json)
        context = json.loads(m.StaffExamSessionReport.query.one().return_instructions_context)
        self.assertEqual(context['recipient_name'], person.full_name)
        self.assertFalse(context['acknowledged_by_recipient'])

    def test_missing_recipient_blocks_ui_and_cannot_be_bypassed(self):
        self.assignment.is_shipment_recipient = False; db.session.commit()
        _, section = self.page()
        self.assertIn('No staff member is marked Receives shipment', section)
        self.assertIn('required data-report-return-confirmed disabled', section)
        response = self.post(return_instructions_confirmed='1')
        self.assertEqual(response.status_code, 400)
        self.assertIn('No staff member is marked', response.json['error'])
        self.assertEqual(m.StaffExamSessionReport.query.count(), 0)

    def test_pending_review_or_configuration_blocks_even_a_forged_confirmation(self):
        control = self.control()
        for review, url in [(True, 'https://maps.example.com/return'), (False, '')]:
            control.return_review_required = review; control.return_drop_off_address_url = url; db.session.commit()
            _, section = self.page()
            self.assertIn('Return instructions are pending', section)
            self.assertIn('required data-report-return-confirmed disabled', section)
            response = self.post(return_instructions_confirmed='1')
            self.assertEqual(response.status_code, 400)
            self.assertIn('pending', response.json['error'])
        self.assertEqual(m.StaffExamSessionReport.query.count(), 0)

    def test_confirmation_and_current_instructions_version_are_required(self):
        for value in ['', '0']:
            response = self.post(return_instructions_confirmed=value)
            self.assertEqual(response.status_code, 400)
            self.assertIn('Please confirm', response.json['error'])
        old = report_return_view(self.record, self.assignment, self.share)['version']
        control = self.control(); control.return_instructions_html = '<p>New deadline.</p>'; db.session.commit()
        for version in ['', old]:
            response = self.post(return_instructions_version=version)
            self.assertEqual(response.status_code, 400)
            self.assertIn('changed', response.json['error'])
        self.assertEqual(m.StaffExamSessionReport.query.count(), 0)
        self.assertEqual(self.post().status_code, 200)

    def test_specific_instructions_are_sanitized_and_have_a_unique_dialog(self):
        control = self.control(); control.return_instructions_title = 'Return deadlines'
        control.return_instructions_html = '<p><strong>Return tomorrow.</strong></p><script>bad()</script>'; db.session.commit()
        html, section = self.page()
        self.assertIn('Read important instructions', section)
        self.assertIn('<strong>Return tomorrow.</strong>', section)
        self.assertNotIn('<script>', section)
        dialog_id = re.search(r'aria-controls="([^"]+)"', section).group(1)
        self.assertTrue(dialog_id.startswith('report-return-instructions-'))
        self.assertEqual(html.count(f'id="{dialog_id}"'), 1)
        self.assertIn('Return deadlines', section)

    def test_supervisor_can_access_label_from_report_without_being_the_recipient(self):
        self.assignment.is_shipment_recipient = False
        other = m.AcademicStaff(full_name='Shipment intern', status='Active', roles='Intern')
        db.session.add(other); db.session.flush()
        db.session.add(m.ExamSessionInternAssignment(exam_session_id=self.record.id, team_member_id=other.id,
            participation_status='Confirmed', is_shipment_recipient=True))
        label = m.ReturnShippingLabel(file_id='reportLabel123', destination_key='report-return', filename='Return.pdf', mime_type='application/pdf')
        db.session.add(label); db.session.commit()
        control = self.control(); control.return_review_required = False
        control.return_materials_method = 'immediate_dispatch'; control.return_shipping_label_id = label.file_id
        db.session.commit()
        with self.app.test_request_context():
            url = report_return_view(self.record, self.assignment, self.share)['info']['label_url']
        with patch('app.google_drive.stream_document', return_value=Response(b'label')) as stream:
            self.assertEqual(self.client.get(url).status_code, 200)
            stream.assert_called_once()
            self.assignment.participation_status = 'Declined'; db.session.commit()
            self.assertEqual(self.client.get(url).status_code, 404)


class ReturnAcknowledgementMigrationTest(unittest.TestCase):
    def test_existing_reports_default_to_unconfirmed_and_migration_is_idempotent(self):
        from app.schema_migrations import migrate_staff_session_report_attendance
        engine = create_engine('sqlite:///:memory:')
        with Session(engine) as unit:
            unit.execute(text('CREATE TABLE staff_exam_session_report (id INTEGER PRIMARY KEY)'))
            unit.execute(text('INSERT INTO staff_exam_session_report (id) VALUES (1)')); unit.commit()
            with patch('app.schema_migrations.db', SimpleNamespace(engine=engine, session=unit)):
                migrate_staff_session_report_attendance()
                migrate_staff_session_report_attendance()
            row = unit.execute(text('SELECT return_instructions_confirmed, return_instructions_context FROM staff_exam_session_report')).one()
            self.assertEqual(row[0], 0); self.assertEqual(row[1], '{}')
            self.assertIn('return_instructions_confirmed', {c['name'] for c in inspect(engine).get_columns('staff_exam_session_report')})
        engine.dispose()
