import json
import unittest
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import patch
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import Session
from app import db
from app import models as m
from app import post_attendance as attendance
from tests import test_staff_session_report as fixtures


class StaffReportComponentsTest(unittest.TestCase):
    setUp = fixtures.StaffSessionReportTest.setUp
    tearDown = fixtures.StaffSessionReportTest.tearDown
    post = fixtures.StaffSessionReportTest.post

    def online(self):
        self.record.format = 'Online'
        self.record.modules = 'Listening and speaking'
        db.session.commit()

    def entry(self, **values):
        return dict(number='001230', name='Candidate Example', exam='B2 Competency',
                    component='Listening', reason='Connection lost during the Listening component.', **values)

    def submit_entries(self, rows):
        return self.post(component_completion='component_absences', component_absences=json.dumps(rows))

    def attendance_state(self):
        with self.client.session_transaction() as state:
            state.update(user='admin', user_department='Admin')
        return self.client.get(f'/pre-session-control-tower/post/sessions/{self.record.id}/attendance')

    def test_required_choice_and_all_candidate_fields(self):
        self.online()
        self.assertEqual(self.post(component_completion='').status_code, 400)
        self.assertEqual(self.submit_entries([]).status_code, 400)
        for key in self.entry():
            invalid = self.entry(); invalid[key] = ''
            self.assertEqual(self.submit_entries([invalid]).status_code, 400, key)
        for key, value in [('number', '123x'), ('component', 'Both'), ('exam', 'Unknown'), ('reason', 'x' * 10001)]:
            invalid = self.entry(); invalid[key] = value
            self.assertEqual(self.submit_entries([invalid]).status_code, 400)
        self.assertEqual(self.submit_entries([self.entry(), self.entry()]).status_code, 400)
        self.assertEqual(m.AbsenceCandidate.query.count(), 0)
        self.assertEqual(m.StaffExamSessionReport.query.count(), 0)

    def test_report_creates_attendance_candidate_and_reason_without_a_file(self):
        self.online()
        response = self.submit_entries([self.entry()])
        self.assertEqual(response.status_code, 200, response.json)
        candidate = m.AbsenceCandidate.query.one()
        self.assertEqual(candidate.institution_name, '')
        self.assertEqual(candidate.number, '001230')
        self.assertEqual(candidate.number_key, '001230')
        self.assertIsNone(candidate.document_id)
        self.assertEqual(candidate.component_reason, self.entry()['reason'])
        self.assertEqual(json.loads(candidate.absent_modules), ['Listening'])
        self.assertEqual(candidate.review_status, 'Pending')
        self.assertFalse(candidate.approved)
        self.assertEqual(m.StaffExamSessionReport.query.one().component_completion, 'component_absences')
        state = self.attendance_state()
        self.assertEqual(state.status_code, 200, state.get_data(as_text=True)[:200])
        row = state.json['state']['candidates'][0]
        self.assertIsNone(row['document'])
        self.assertEqual(row['component_reason'], self.entry()['reason'])
        self.assertIn('Listening', row['allowed_modules'])
        self.assertTrue(state.json['state']['has_absences'])
        self.assertEqual(self.submit_entries([self.entry()]).status_code, 409)
        self.assertEqual(m.AbsenceCandidate.query.count(), 1)

    def test_existing_candidate_preserves_document_modules_and_reopens_review(self):
        self.online()
        institution = m.AttendanceInstitution(exam_session_id=self.record.id, name='Example School', is_main=False)
        document = m.AttendanceDocument(file_id='existingProof', folder_id='folder', filename='medical.pdf', mime_type='application/pdf')
        db.session.add_all([institution, document]); db.session.flush()
        candidate = m.AbsenceCandidate(exam_session_id=self.record.id, institution_id=institution.id,
            number='001230', number_key='001230', name='Candidate Example', institution_name='Example School',
            exam='B2 Competency', document_id=document.file_id, absent_modules='["Reading and writing"]', approved=True,
            review_status='Confirmed', currency='ARS', credit_balance=500, notes='Preserve notes')
        db.session.add(candidate)
        db.session.add(m.PostAttendance(exam_session_id=self.record.id, verified=True, review_results_notified=True,
                                       review_completed_at=datetime.now(timezone.utc), no_documentation_received=True))
        db.session.commit()
        response = self.submit_entries([self.entry()])
        self.assertEqual(response.status_code, 200, response.json)
        self.assertEqual(m.AbsenceCandidate.query.count(), 1)
        self.assertEqual(candidate.document_id, 'existingProof')
        self.assertEqual(set(json.loads(candidate.absent_modules)), {'Reading and writing', 'Listening'})
        self.assertEqual(candidate.review_status, 'Pending')
        self.assertFalse(candidate.approved)
        self.assertEqual(candidate.notes, 'Preserve notes')
        self.assertEqual(candidate.credit_balance, 500)
        self.assertFalse(db.session.get(m.PostAttendance, self.record.id).review_results_notified)
        self.assertIsNone(db.session.get(m.PostAttendance, self.record.id).review_completed_at)
        state = self.attendance_state().json['state']['candidates'][0]
        self.assertEqual(state['document']['id'], 'existingProof')
        self.assertEqual(state['component_reason'], self.entry()['reason'])

    def test_unchanged_information_does_not_reopen_but_reason_change_does(self):
        from app.staff_report_components import merge
        self.online()
        merge(self.record, [self.entry()]); db.session.commit()
        candidate = m.AbsenceCandidate.query.one()
        candidate.review_status = 'Confirmed'; candidate.approved = True; db.session.commit()
        merge(self.record, [self.entry()]); db.session.commit()
        self.assertEqual(candidate.review_status, 'Confirmed')
        changed = self.entry(); changed['reason'] = 'Updated explanation'
        merge(self.record, [changed]); db.session.commit()
        self.assertEqual(candidate.review_status, 'Pending')

    def test_only_applicable_online_modules_show_and_accept_component_absences(self):
        for format_name, modules, visible in [('Online', 'Listening and speaking', True), ('Online', 'Speaking', False),
                                               ('Onsite', 'Listening and speaking', False), ('Online at exam centre', 'Listening and speaking', False)]:
            self.record.format, self.record.modules = format_name, modules; db.session.commit()
            html = self.client.get(f'/my-exam-sessions/{self.share.token}?session_year=2026').get_data(as_text=True)
            self.assertEqual('data-report-components>' in html, visible)
            self.assertNotIn('name="listening_speaking_components_checked"', html)
        self.record.format = 'Online'; self.record.modules = 'Speaking'; db.session.commit()
        self.assertEqual(self.submit_entries([self.entry()]).status_code, 200)
        self.assertEqual(m.AbsenceCandidate.query.count(), 0)
        self.assertEqual(m.StaffExamSessionReport.query.one().component_completion, '')

    def test_report_and_attendance_rollback_together(self):
        from app.staff_report_components import merge
        from sqlalchemy.exc import IntegrityError
        self.online()
        def fail_after_merge(record, rows):
            merge(record, rows)
            db.session.flush()
            raise IntegrityError('simulated conflict', {}, None)
        with patch('app.staff_report_components.merge', side_effect=fail_after_merge):
            self.assertEqual(self.submit_entries([self.entry()]).status_code, 409)
        self.assertEqual(m.StaffExamSessionReport.query.count(), 0)
        self.assertEqual(m.AbsenceCandidate.query.count(), 0)
        self.assertEqual(m.AttendanceInstitution.query.count(), 0)

    def test_choice_complete_does_not_import_hidden_candidates(self):
        self.online()
        self.assertEqual(self.post(component_completion='complete', component_absences=json.dumps([self.entry()])).status_code, 200)
        self.assertEqual(m.AbsenceCandidate.query.count(), 0)

    def test_reason_only_candidate_follows_normal_confirmation_and_notification_flow(self):
        self.online()
        self.assertEqual(self.submit_entries([self.entry()]).status_code, 200)
        candidate = m.AbsenceCandidate.query.one()
        self.attendance_state()
        self.client.post(f'/pre-session-control-tower/post/sessions/{self.record.id}/attendance', data=dict(csrf_token='test',action='candidate',candidate_id=candidate.id,field='institution_name',value='Example School'))
        institution = db.session.get(m.AttendanceInstitution, candidate.institution_id)
        institution.notifications = '{"external":true}'
        value = attendance.control(self.record, True); value.submission_status = 'completed'; value.verified = True
        candidate.rescheduled_for = str(self.record.id)
        db.session.commit()
        self.attendance_state()
        url = f'/pre-session-control-tower/post/sessions/{self.record.id}/attendance'
        with patch('app.post_attendance.local_today', return_value=self.record.session_date + timedelta(days=20)):
            response = self.client.post(url, data=dict(csrf_token='test', action='candidate', candidate_id=candidate.id,
                                                     field='review', value='Confirmed', previous_file_id=''))
        self.assertEqual(response.status_code, 200, response.json)
        self.assertEqual(candidate.review_status, 'Confirmed')
        self.assertTrue(response.json['state']['results_notification_enabled'])
        self.assertIn('001230', response.json['state']['candidates'][0]['whatsapp_message'])


class ComponentSchemaMigrationTest(unittest.TestCase):
    def test_legacy_documents_and_candidate_links_are_preserved(self):
        from app.schema_migrations import migrate_staff_report_components
        engine = create_engine('sqlite:///:memory:')
        unit = Session(engine)
        statements = [
            'CREATE TABLE staff_exam_session_report (id INTEGER PRIMARY KEY)',
            'CREATE TABLE absence_candidate (id INTEGER PRIMARY KEY, exam_session_id INTEGER, number_key VARCHAR(80), name VARCHAR(250), document_id VARCHAR(160) NOT NULL, UNIQUE(exam_session_id,number_key))',
            'CREATE INDEX ix_legacy_candidate_name ON absence_candidate(name)',
            'CREATE TABLE legacy_event (id INTEGER PRIMARY KEY, candidate_id INTEGER REFERENCES absence_candidate(id))',
            "INSERT INTO absence_candidate VALUES (4,10,'0012','Candidate','proof123')",
            'INSERT INTO legacy_event VALUES (1,4)',
        ]
        for statement in statements: unit.execute(text(statement))
        unit.commit()
        with patch('app.schema_migrations.db', SimpleNamespace(engine=engine, session=unit)):
            migrate_staff_report_components(); migrate_staff_report_components()
        self.assertIn('edit_history', {column['name'] for column in inspect(engine).get_columns('staff_exam_session_report')})
        self.assertTrue(next(column for column in inspect(engine).get_columns('absence_candidate') if column['name']=='document_id')['nullable'])
        self.assertEqual(unit.execute(text('SELECT document_id FROM absence_candidate WHERE id=4')).scalar_one(), 'proof123')
        self.assertEqual(unit.execute(text('SELECT candidate_id FROM legacy_event')).scalar_one(), 4)
        self.assertIn('ix_legacy_candidate_name', {item['name'] for item in inspect(engine).get_indexes('absence_candidate')})
        unit.execute(text("INSERT INTO absence_candidate(id,exam_session_id,number_key,name) VALUES (5,10,'0001','Text only')"));unit.commit()
        self.assertIsNone(unit.execute(text('SELECT document_id FROM absence_candidate WHERE id=5')).scalar_one())
        unit.close();engine.dispose()
