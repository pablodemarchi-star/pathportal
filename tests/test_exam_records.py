import io
import json
from datetime import date
import unittest
from unittest.mock import patch
from app import db
from app.models import (AcademicStaff, ExamSession, ExamSessionExaminerAssignment, ExamSessionSupervisorAssignment,
    ExamSessionStaffingControl, ExamSessionScheduleWorkflow, ExamRecordsControl, ExaminerSpeakingRecord, BeyondSetupControl, SpeakingRecordsSetup)
from app.exam_records import state
from tests import test_google_drive as drive


class ExamRecordsTest(unittest.TestCase):
    setUpBase = drive.GoogleDriveTest.setUpBase
    tearDownBase = drive.GoogleDriveTest.tearDownBase
    tearDown = drive.GoogleDriveTest.tearDown
    api = drive.GoogleDriveTest.api
    http = drive.GoogleDriveTest.http

    def setUp(self):
        drive.GoogleDriveTest.setUp(self)
        self.person = AcademicStaff(full_name='María Examiner', status='Active', roles='Examiner')
        self.record = ExamSession(exam_session_name='B2 Online', category='Path School', status='Pending',
            session_date=date(2026, 12, 15), shifts='Morning', modules='Speaking,Reading and writing,Listening and speaking', format='Online',
            digitalised_exams_url='https://drive.google.com/drive/folders/folder123456789')
        db.session.add_all([self.person, self.record]); db.session.flush()
        self.assignment = ExamSessionExaminerAssignment(exam_session_id=self.record.id,
            team_member_id=self.person.id, participation_status='Confirmed')
        self.workflow = ExamSessionScheduleWorkflow(exam_session_id=self.record.id, status='Approved')
        db.session.add_all([self.assignment, self.workflow,
            ExamSessionStaffingControl(exam_session_id=self.record.id, schedule_notification_confirmed=True)])
        db.session.commit()
        self.url = f'/pre-online-session-control-tower/sessions/{self.record.id}/exam-records'

    def post(self, **values):
        return self.client.post(self.url, data=dict(csrf_token='test', **values))

    def upload(self, previous=''):
        current = state(self.record)
        if current['unlocked']:
            for step in range(current['speaking']['count'] + 1, 3):
                response = self.speaking(step)
                if response.status_code != 200:
                    return response
        return self.post(action='upload', person_ref=f'staff:{self.person.id}', previous_file_id=previous, revision=state(self.record)['speaking']['revision'],
                         record=(io.BytesIO(b'%PDF-record'), 'speaking.pdf'))

    def speaking(self, step, checked=True, previous=None, revision=None):
        current = state(self.record)['speaking']
        return self.post(action='speaking', step=str(step), checked='1' if checked else '0',
            previous_steps=str(current['count'] if previous is None else previous),
            revision=current['revision'] if revision is None else revision)

    def test_gate_and_deadline_and_online_table(self):
        current = state(self.record)
        self.assertTrue(current['unlocked'])
        self.assertEqual(current['deadline']['date'], date(2026, 12, 8))
        response = self.client.get('/pre-online-session-control-tower?session_year=2026')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'<th>Exam records</th>', response.data)
        self.assertIn(b'0/1 records for examiners', response.data)
        self.assertIn(b'Speaking records', response.data)
        self.assertNotIn(b'aria-label="Final check"', response.data)
        self.assignment.participation_status = 'Pending'; db.session.commit()
        self.assertFalse(state(self.record)['unlocked'])
        self.assertEqual(self.upload().status_code, 409)
        self.assertEqual(self.speaking(1).status_code, 409)

    def test_reading_writing_only_does_not_require_examiner_but_keeps_schedule_and_staffing_gates(self):
        db.session.delete(self.assignment)
        supervisor = ExamSessionSupervisorAssignment(exam_session_id=self.record.id,
            team_member_id=self.person.id, participation_status='Confirmed')
        db.session.add(supervisor)
        for format_name in ['Online', 'Online at exam centre']:
            self.record.format = format_name
            self.record.modules = 'Reading and writing'
            db.session.commit()
            current = state(self.record)
            self.assertTrue(current['unlocked'], format_name)
            self.assertFalse(current['requires_examiner'])
            self.assertEqual(current['total'], 0)
            self.assertNotIn('Examiner', current['blocking_message'])
            self.assertEqual(self.beyond(1).status_code, 200)
            self.assertEqual(self.beyond(1, checked=False).status_code, 200)
            self.workflow.status = 'Pending'
            db.session.commit()
            self.assertFalse(state(self.record)['unlocked'])
            self.assertEqual(self.beyond(1).status_code, 409)
            self.workflow.status = 'Approved'
            supervisor.participation_status = 'Pending'
            db.session.commit()
            self.assertFalse(state(self.record)['unlocked'])
            supervisor.participation_status = 'Confirmed'
            self.record.staffing_control.schedule_notification_confirmed = False
            db.session.commit()
            self.assertFalse(state(self.record)['unlocked'])
            self.record.staffing_control.schedule_notification_confirmed = True
            for modules in ['Reading and writing,Speaking', 'Reading and writing,Listening and speaking', 'Speaking', '']:
                self.record.modules = modules
                db.session.commit()
                self.assertTrue(state(self.record)['requires_examiner'])
                self.assertFalse(state(self.record)['unlocked'], modules)

    def test_optional_examiner_position_still_has_to_be_filled_and_confirmed(self):
        # Online at exam centre removes Examiner positions by its existing staffing rules.
        self.record.modules = 'Reading and writing'
        self.assignment.participation_status = 'Pending'
        db.session.commit()
        self.assertFalse(state(self.record)['unlocked'])
        self.assignment.participation_status = 'Confirmed'
        db.session.commit()
        self.assertTrue(state(self.record)['unlocked'])
        self.assignment.team_member_id = None
        db.session.commit()
        self.assertFalse(state(self.record)['unlocked'])

    def test_upload_name_folder_count_replacement_and_speaking_steps(self):
        self.assertEqual(self.upload().status_code, 200)
        document = ExaminerSpeakingRecord.query.one()
        self.assertEqual(document.filename, 'María Examiner - B2 Online - 15-12-2026.pdf')
        self.assertEqual(document.folder_id, 'folder123456789')
        self.assertEqual(state(self.record)['count'], 1)
        self.assertTrue(state(self.record)['started'])
        self.assertEqual(self.speaking(3).status_code, 200)
        self.assertEqual(self.upload(previous=document.file_id).status_code, 200)
        self.assertEqual(ExaminerSpeakingRecord.query.count(), 1)
        self.assertEqual(state(self.record)['speaking']['count'], 2)
        self.assertEqual(self.upload(previous='stale').status_code, 409)

    def test_speaking_steps_require_files_and_cascade(self):
        self.assertEqual(self.speaking(2).status_code, 409)
        self.assertEqual(self.speaking(1).status_code, 200)
        self.assertTrue(state(self.record)['started'])
        self.assertEqual(self.speaking(2).status_code, 200)
        self.assertEqual(self.speaking(3).status_code, 409)
        self.upload()
        self.assertEqual(self.speaking(3).status_code, 200)
        self.assertEqual(self.speaking(1, checked=False).status_code, 200)
        self.assertEqual(state(self.record)['speaking']['count'], 0)
        self.assertEqual(ExaminerSpeakingRecord.query.count(), 1)
        self.assertEqual(self.speaking(2).status_code, 409)
        self.assertEqual(self.post(action='final', status='In progress').status_code, 400)

    def test_missing_folder_failed_upload_and_schedule_block(self):
        self.record.digitalised_exams_url = None; db.session.commit()
        self.assertEqual(self.upload().status_code, 400)
        self.assertTrue(state(self.record)['started'])
        self.workflow.status = 'Not started'; db.session.commit()
        self.assertEqual(self.speaking(1).status_code, 409)

    def test_speaking_checks_reset_after_schedule_or_examiner_changes(self):
        self.upload(); self.speaking(3)
        self.assertEqual(state(self.record)['speaking']['count'], 3)
        self.workflow.review_round += 1; db.session.commit()
        self.assertEqual(state(self.record)['speaking']['count'], 0)
        self.upload(previous=ExaminerSpeakingRecord.query.one().file_id)
        self.speaking(3)
        db.session.delete(self.assignment); db.session.commit(); db.session.expire_all()
        self.assertEqual(state(self.record)['total'], 0)
        self.assertFalse(state(self.record)['unlocked'])
        self.assertEqual(ExaminerSpeakingRecord.query.count(), 1)
        self.assertEqual(state(self.record)['speaking']['count'], 0)

    def test_csrf_and_single_file_validation(self):
        response = self.client.post(self.url, data=dict(action='final', status='In progress'))
        self.assertEqual(response.status_code, 403)
        self.speaking(1); self.speaking(2)
        self.assertEqual(self.post(action='upload', revision=state(self.record)['speaking']['revision'], person_ref=f'staff:{self.person.id}',
            record=[(io.BytesIO(b'a'), 'a.pdf'), (io.BytesIO(b'b'), 'b.pdf')]).status_code, 400)

    def test_staffing_confirmation_and_permissions_are_enforced(self):
        self.record.staffing_control.schedule_notification_confirmed = False
        db.session.commit()
        self.assertFalse(state(self.record)['unlocked'])
        self.assertEqual(self.upload().status_code, 409)
        self.record.staffing_control.schedule_notification_confirmed = True
        db.session.commit()
        with patch('app.routes.user_can_edit', return_value=False):
            self.assertEqual(self.upload().status_code, 403)
        self.assertEqual(ExaminerSpeakingRecord.query.count(), 0)

    def test_drive_failure_does_not_start_block_or_count_file(self):
        from app.google_drive import DriveStorageError
        with patch('app.exam_records.upload_document', side_effect=DriveStorageError('Drive unavailable')):
            self.assertEqual(self.upload().status_code, 503)
        self.assertEqual(state(self.record)['count'], 0)
        self.assertTrue(state(self.record)['started'])

    def test_session_deletion_clears_records_metadata(self):
        from app.routes import delete_exam_session_dependencies
        self.assertEqual(self.upload().status_code, 200)
        self.assertEqual(self.beyond(1).status_code, 200)
        delete_exam_session_dependencies(self.record.id)
        db.session.delete(self.record)
        db.session.commit()
        self.assertEqual(ExaminerSpeakingRecord.query.count(), 0)
        self.assertEqual(ExamRecordsControl.query.count(), 0)
        self.assertEqual(BeyondSetupControl.query.count(), 0)

    def beyond(self, step, checked=True, previous=None, revision=None):
        current = state(self.record)['beyond']
        return self.post(action='beyond', step=str(step), checked='1' if checked else '0',
            previous_steps=str(current['count'] if previous is None else previous),
            revision=current['revision'] if revision is None else revision)

    def test_beyond_steps_are_sequential_persistent_and_cascade(self):
        self.assertEqual(self.beyond(2).status_code, 409)
        for step in range(1, 6):
            self.assertEqual(self.beyond(step).status_code, 200)
            db.session.expire_all()
            self.assertEqual(state(self.record)['beyond']['count'], step)
        self.assertTrue(state(self.record)['started'])
        self.assertEqual(self.beyond(2, checked=False).status_code, 200)
        self.assertEqual(state(self.record)['beyond']['count'], 1)
        self.assertEqual(self.beyond(4).status_code, 409)
        self.assertEqual(self.beyond(2, previous=5).status_code, 409)
        self.assertEqual(self.beyond(1, checked=False).status_code, 200)
        self.assertEqual(state(self.record)['beyond']['count'], 0)

    def test_beyond_resets_when_session_details_change_even_if_restored(self):
        for field, value in [('exam_session_name', 'Renamed session'), ('session_date', date(2027, 1, 10)),
                             ('schedule_folder_url', 'https://example.com/schedule'),
                             ('details_url', 'https://example.com/details')]:
            self.assertEqual(self.beyond(1).status_code, 200)
            original = getattr(self.record, field)
            old_revision = state(self.record)['beyond']['revision']
            setattr(self.record, field, value)
            db.session.commit()
            self.assertEqual(state(self.record)['beyond']['count'], 0)
            self.assertEqual(self.beyond(1, revision=old_revision).status_code, 409)
            setattr(self.record, field, original)
            db.session.commit()
            self.assertEqual(state(self.record)['beyond']['count'], 0)

    def test_beyond_blocking_permissions_and_original_template(self):
        from pathlib import Path
        template_url = self.url.replace('exam-records', 'beyond-template')
        response = self.client.get(template_url)
        self.assertEqual(response.status_code, 200)
        self.assertIn('attachment', response.headers['Content-Disposition'])
        self.assertEqual(response.data, (Path(self.app.root_path) / 'downloads' / 'Reading and Writing import Excel template.xlsx').read_bytes())
        response.close()
        with patch('app.routes.user_can_edit', return_value=False):
            self.assertEqual(self.beyond(1).status_code, 403)
        self.workflow.status = 'Not started'; db.session.commit()
        self.assertEqual(self.beyond(1).status_code, 409)
        self.assertEqual(self.client.get(template_url).status_code, 403)

    def test_beyond_renders_session_name_date_and_download(self):
        self.beyond(1); self.beyond(2)
        response = self.client.get('/pre-online-session-control-tower?session_year=2026')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Reading and Writing records', response.data)
        self.assertIn(b'RW - B2 Online', response.data)
        self.assertIn(b'15/12/2026', response.data)
        self.assertIn(b'Reading and Writing import Excel template', response.data)
        self.assertIn(b'2/6 steps', response.data)
        self.assertIn(b'data-beyond-step="3"', response.data)

    def rw_upload(self, previous='', filename='records.xlsx', extra=None):
        return self.post(action='rw_upload', previous_file_id=previous,
            revision=state(self.record)['beyond']['revision'],
            record=extra if extra is not None else (io.BytesIO(b'Excel data'), filename))

    def complete_beyond_five(self):
        for step in range(1, 6):
            self.assertEqual(self.beyond(step).status_code, 200)

    def test_rw_marking_upload_name_folder_single_file_and_replacement(self):
        from app.models import RWMarkingRecord
        self.assertEqual(self.rw_upload().status_code, 409)
        self.complete_beyond_five()
        self.assertEqual(self.beyond(6).status_code, 409)
        self.assertEqual(self.rw_upload().status_code, 200)
        document = RWMarkingRecord.query.one()
        self.assertEqual(document.filename, 'RW marking record - B2 Online - 15-12-2026.xlsx')
        self.assertEqual(document.folder_id, 'folder123456789')
        self.assertEqual(state(self.record)['count'], 0)
        self.assertEqual(state(self.record)['beyond']['count'], 5)
        self.assertEqual(self.beyond(6).status_code, 200)
        old_id = document.file_id
        self.assertEqual(self.rw_upload(previous=old_id, filename='replacement.xls').status_code, 200)
        self.assertEqual(RWMarkingRecord.query.count(), 1)
        self.assertNotEqual(document.file_id, old_id)
        self.assertEqual(document.filename, 'RW marking record - B2 Online - 15-12-2026.xls')
        self.assertEqual(state(self.record)['beyond']['count'], 5)
        self.assertEqual(self.rw_upload(previous=old_id).status_code, 409)
        self.assertEqual(self.beyond(6).status_code, 200)
        self.assertEqual(self.beyond(3, checked=False).status_code, 200)
        self.assertEqual(state(self.record)['beyond']['count'], 2)
        self.assertIsNotNone(state(self.record)['beyond']['document'])
        self.assertEqual(self.rw_upload(previous=document.file_id).status_code, 409)

    def test_rw_marking_validation_block_and_drive_failure(self):
        from app.models import RWMarkingRecord
        from app.google_drive import DriveStorageError
        self.complete_beyond_five()
        self.assertEqual(self.rw_upload(filename='record.pdf').status_code, 400)
        self.assertEqual(self.rw_upload(extra=[(io.BytesIO(b'a'), 'a.xlsx'), (io.BytesIO(b'b'), 'b.xlsx')]).status_code, 400)
        with patch('app.exam_records.upload_document', side_effect=DriveStorageError('Drive unavailable')):
            self.assertEqual(self.rw_upload().status_code, 503)
        self.assertEqual(RWMarkingRecord.query.count(), 0)
        self.assertEqual(state(self.record)['beyond']['count'], 5)
        self.workflow.status = 'Not started'; db.session.commit()
        self.assertEqual(self.rw_upload().status_code, 409)

    def test_rw_marking_retained_on_session_change_and_removed_with_session(self):
        from app.models import RWMarkingRecord
        from app.routes import delete_exam_session_dependencies
        self.complete_beyond_five(); self.rw_upload(); self.beyond(6)
        self.record.exam_session_name = 'Renamed session'; db.session.commit()
        self.assertEqual(state(self.record)['beyond']['count'], 0)
        self.assertEqual(RWMarkingRecord.query.count(), 1)
        response = self.client.get('/pre-online-session-control-tower?session_year=2026')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Reading and Writing records', response.data)
        self.assertIn(b'0/6 steps', response.data)
        self.assertIn(b'RW marking record - B2 Online - 15-12-2026.xlsx', response.data)
        delete_exam_session_dependencies(self.record.id)
        db.session.expire_all()
        db.session.delete(self.record); db.session.commit()
        self.assertEqual(RWMarkingRecord.query.count(), 0)

    def test_speaking_upload_gate_download_and_stale_changes(self):
        from pathlib import Path
        self.assertEqual(self.post(action='upload', revision=state(self.record)['speaking']['revision'],
            person_ref=f'staff:{self.person.id}', record=(io.BytesIO(b'file'), 'record.xlsx')).status_code, 409)
        self.speaking(1)
        url = self.url.replace('/exam-records', '/speaking-template')
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data, Path('app/downloads/Speaking import Excel template.xlsx').read_bytes())
        response.close()
        self.speaking(2)
        old_revision = state(self.record)['speaking']['revision']
        self.record.exam_session_name = 'New session name'; db.session.commit()
        self.assertEqual(state(self.record)['speaking']['count'], 0)
        self.assertEqual(self.speaking(1, revision=old_revision).status_code, 409)
        self.record.exam_session_name = 'B2 Online'; db.session.commit()
        self.assertEqual(state(self.record)['speaking']['count'], 0)
        self.speaking(1)
        self.assertEqual(self.speaking(2, previous=0).status_code, 409)
        self.assignment.participation_status = 'Pending'; db.session.commit()
        self.assertEqual(self.client.get(url).status_code, 403)

    def test_speaking_checks_reset_for_session_details_and_assignment_times(self):
        for field, value in [('session_date', date(2027, 2, 1)),
                             ('schedule_folder_url', 'https://example.com/new-schedule'),
                             ('details_url', 'https://example.com/details')]:
            self.speaking(1); self.speaking(2)
            setattr(self.record, field, value); db.session.commit()
            self.assertEqual(state(self.record)['speaking']['count'], 0)
        self.speaking(1); self.speaking(2)
        self.assignment.start_time = '10:00'; db.session.commit()
        self.assertEqual(state(self.record)['speaking']['count'], 0)

    def test_speaking_step_three_requires_every_confirmed_examiner(self):
        second = AcademicStaff(full_name='Second Examiner', status='Active', roles='Examiner')
        db.session.add(second); db.session.flush()
        db.session.add(ExamSessionExaminerAssignment(exam_session_id=self.record.id,
            team_member_id=second.id, participation_status='Confirmed'))
        db.session.commit(); db.session.expire_all()
        self.assertEqual(self.upload().status_code, 200)
        self.assertEqual(state(self.record)['count'], 1)
        self.assertEqual(state(self.record)['total'], 2)
        self.assertEqual(self.speaking(3).status_code, 409)
        self.assertEqual(self.post(action='upload', person_ref=f'staff:{second.id}', previous_file_id='',
            revision=state(self.record)['speaking']['revision'],
            record=(io.BytesIO(b'record'), 'second.xlsx')).status_code, 200)
        self.assertEqual(self.speaking(3).status_code, 200)
        db.session.expire_all()
        self.assertEqual(state(self.record)['speaking']['count'], 3)
        self.assertEqual(state(self.record)['beyond']['count'], 0)

    def listening(self, step, checked=True, revision=None, previous=None):
        current = state(self.record)['listening']
        return self.post(action='listening', step=str(step), checked='1' if checked else '0',
            revision=current['revision'] if revision is None else revision,
            previous_steps=str(current['count'] if previous is None else previous))

    def listening_upload(self, previous='', filename='listening.xlsx'):
        return self.post(action='listening_upload', previous_file_id=previous,
            revision=state(self.record)['listening']['revision'],
            record=(io.BytesIO(b'Listening Excel'), filename))

    def test_listening_is_independent_and_follows_the_same_sequence(self):
        self.assertEqual(self.listening(2).status_code, 409)
        self.assertEqual(self.listening_upload().status_code, 409)
        for step in range(1, 6):
            self.assertEqual(self.listening(step).status_code, 200)
        self.assertEqual(state(self.record)['listening']['count'], 5)
        self.assertEqual(state(self.record)['beyond']['count'], 0)
        self.assertEqual(state(self.record)['speaking']['count'], 0)
        self.assertTrue(state(self.record)['started'])
        self.assertEqual(self.listening(6).status_code, 409)
        self.assertEqual(self.listening_upload().status_code, 200)
        self.assertEqual(self.listening(6).status_code, 200)
        self.assertEqual(self.listening(2, checked=False).status_code, 200)
        self.assertEqual(state(self.record)['listening']['count'], 1)
        self.assertIsNotNone(state(self.record)['listening']['document'])
        self.assertEqual(self.listening(2, previous=6).status_code, 409)

    def test_listening_and_rw_files_are_independent_and_replaceable(self):
        from app.models import ListeningMarkingRecord, RWMarkingRecord
        self.complete_beyond_five()
        self.rw_upload(); self.beyond(6)
        rw_file = RWMarkingRecord.query.one().file_id
        for step in range(1, 6):
            self.listening(step)
        self.assertEqual(self.listening_upload(filename='invalid.pdf').status_code, 400)
        self.assertEqual(self.listening_upload().status_code, 200)
        document = ListeningMarkingRecord.query.one()
        self.assertEqual(document.filename, 'L marking record - B2 Online - 15-12-2026.xlsx')
        self.assertEqual(document.folder_id, 'folder123456789')
        self.assertEqual(self.listening(6).status_code, 200)
        old_file = document.file_id
        self.assertEqual(self.listening_upload(previous=old_file).status_code, 200)
        self.assertEqual(ListeningMarkingRecord.query.count(), 1)
        self.assertEqual(state(self.record)['listening']['count'], 5)
        self.assertEqual(state(self.record)['beyond']['count'], 6)
        self.assertEqual(RWMarkingRecord.query.one().file_id, rw_file)
        self.assertEqual(self.listening_upload(previous=old_file).status_code, 409)
        self.assertEqual(state(self.record)['count'], 0)

    def test_listening_rendering_reset_and_blocking(self):
        for step in range(1, 6):
            self.listening(step)
        self.listening_upload(); self.listening(6)
        response = self.client.get('/pre-online-session-control-tower?session_year=2026')
        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertLess(html.index('<h3>Reading and Writing records</h3>'), html.index('<h3>Listening records</h3>'))
        self.assertIn('L - B2 Online', html)
        self.assertIn('<strong>Module:</strong> Listening and Speaking.', html)
        self.assertIn('data-upload-action="listening_upload"', html)
        self.assertIn('data-setup-action="listening"', html)
        revision = state(self.record)['listening']['revision']
        self.record.exam_session_name = 'Changed'; db.session.commit()
        self.assertEqual(state(self.record)['listening']['count'], 0)
        self.assertIsNotNone(state(self.record)['listening']['document'])
        self.assertEqual(self.listening(1, revision=revision).status_code, 409)
        self.record.exam_session_name = 'B2 Online'; db.session.commit()
        self.assertEqual(state(self.record)['listening']['count'], 0)
        self.workflow.status = 'Not started'; db.session.commit()
        self.assertEqual(self.listening(1).status_code, 409)
        self.assertEqual(self.listening_upload().status_code, 409)

    def test_online_finance_column_opens_existing_modal_and_saves(self):
        import re
        from app.models import ExamSessionFinanceControl
        self.record.monthly_registrations_closed = True
        self.record.date_confirmation_status = 'Confirmed'
        db.session.commit()
        page = self.client.get('/pre-online-session-control-tower?session_year=2026').get_data(as_text=True)
        table = re.search(r'<table class="control-tower-table online-control-tower-table">.*?</table>', page, re.S).group(0)
        self.assertIn('aria-label="Online session control tower views"', page)
        self.assertIn('aria-current="page"', page)
        self.assertIn('>Pre checks</a>', page)
        self.assertIn('<th>Staffing</th><th>Finance</th><th>Exam records</th>', table)
        self.assertIn('data-modal-finance-only="true"', table)
        self.assertIn('aria-label="Finance gate unblocked', table)
        modal_url = f'/pre-online-session-control-tower?session_year=2026&session_modal={self.record.id}&open_schedule_modal={self.record.id}&finance_only=1'
        html = self.client.get(modal_url).get_data(as_text=True)
        self.assertIn('Current account standing', html)
        self.assertIn('data-finance-auto-save-status', html)
        self.assertIn('name="view" value="online"', html)
        response = self.client.post(f'/pre-session-control-tower/sessions/{self.record.id}/finance-control',
            data=dict(csrf_token='test', view='online', finance_status='Effective clearance', finance_comments='Reviewed online'),
            headers={'X-Finance-Autosave':'1','Accept':'application/json'})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json['ok'])
        control = ExamSessionFinanceControl.query.one()
        self.assertEqual(control.status, 'Effective clearance')
        self.assertIn('Reviewed online', self.client.get(modal_url).get_data(as_text=True))

    def test_online_finance_keeps_existing_block_and_permissions(self):
        from app.models import ExamSessionFinanceControl
        page = self.client.get('/pre-online-session-control-tower?session_year=2026').get_data(as_text=True)
        self.assertIn('aria-label="Finance gate blocked', page)
        response = self.client.post(f'/pre-session-control-tower/sessions/{self.record.id}/finance-control',
            data=dict(csrf_token='test', view='online', finance_status='Effective clearance'),
            headers={'X-Finance-Autosave':'1'})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(ExamSessionFinanceControl.query.count(), 0)
        self.record.monthly_registrations_closed = True
        db.session.commit()
        with patch('app.routes.user_can_edit', return_value=False):
            response = self.client.post(f'/pre-session-control-tower/sessions/{self.record.id}/finance-control',
                data=dict(csrf_token='test', finance_status='Effective clearance'))
        self.assertEqual(response.status_code, 403)

    def test_online_final_checks_column_uses_existing_modal(self):
        import re
        for format_name in ('Online', 'Online at exam centre'):
            self.record.format = format_name
            db.session.commit()
            page = self.client.get('/pre-online-session-control-tower?session_year=2026').get_data(as_text=True)
            table = re.search(r'<table class="control-tower-table online-control-tower-table">.*?</table>', page, re.S).group(0)
            self.assertIn('<th>Exam records</th><th>Final checks</th><th>Session readiness</th></tr>', table)
            self.assertIn('data-modal-sinapsis-only="true"', table)
            self.assertIn('session-readiness-final-cell', table)
            self.assertNotIn('Register incidents', table)
            self.assertIn(f'data-modal-scroll-target="sinapsis-{self.record.id}"', table)
            response = self.client.get(f'/pre-online-session-control-tower?session_year=2026&session_modal={self.record.id}&open_schedule_modal={self.record.id}&sinapsis_only=1')
            self.assertEqual(response.status_code, 200)
            modal = response.get_data(as_text=True)
            self.assertIn(f'id="sinapsis-{self.record.id}"', modal)
            self.assertIn('aria-label="Final checks details"', modal)
            self.assertIn('name="view" value="online"', modal)
            self.assertNotIn(f'id="return-materials-title-{self.record.id}"', modal)

    def test_exam_record_sections_follow_selected_modules(self):
        cases = [
            ('Speaking', {'Speaking records'}),
            ('Reading and writing', {'Reading and Writing records'}),
            ('Listening and speaking', {'Speaking records', 'Listening records'}),
            ('Speaking,Reading and writing', {'Speaking records', 'Reading and Writing records'}),
            ('Reading and writing,Listening and speaking', {'Speaking records', 'Reading and Writing records', 'Listening records'}),
            ('Listening and Speaking', {'Speaking records', 'Listening records'}),
            ('', set()),
        ]
        for modules, expected in cases:
            with self.subTest(modules=modules):
                self.record.modules = modules
                db.session.commit()
                response = self.client.get('/pre-online-session-control-tower?session_year=2026')
                self.assertEqual(response.status_code, 200)
                html = response.get_data(as_text=True)
                for title in ('Speaking records', 'Reading and Writing records', 'Listening records'):
                    self.assertEqual(f'<h3>{title}</h3>' in html, title in expected)

    def test_exam_records_department_actions_follow_gate_and_progress(self):
        description_start = 'Configure exam records for the session'
        description_finish = 'Finalise the exam record configuration for the session'
        self.assertEqual(state(self.record)['status'], 'not_started')
        self.assertEqual(state(self.record)['action']['department'], 'LOGISTICS')
        html = self.client.get('/pre-online-session-control-tower?session_year=2026').get_data(as_text=True)
        self.assertIn(description_start, html)
        self.assertNotIn(description_finish, html)
        self.assertEqual(self.speaking(1).status_code, 200)
        self.assertEqual(state(self.record)['status'], 'in_progress')
        html = self.client.get('/pre-online-session-control-tower?session_year=2026').get_data(as_text=True)
        self.assertIn(description_finish, html)
        self.assertNotIn(description_start, html)
        self.record.staffing_control.schedule_notification_confirmed = False
        db.session.commit()
        self.assertIsNone(state(self.record)['action'])
        html = self.client.get('/pre-online-session-control-tower?session_year=2026').get_data(as_text=True)
        self.assertNotIn(description_start, html)
        self.assertNotIn(description_finish, html)

    def test_exam_records_complete_only_when_all_active_checks_are_complete(self):
        self.upload(); self.speaking(3)
        self.assertEqual(state(self.record)['status'], 'in_progress')
        self.complete_beyond_five(); self.rw_upload(); self.beyond(6)
        self.assertEqual(state(self.record)['status'], 'in_progress')
        for step in range(1, 6):
            self.listening(step)
        self.listening_upload(); self.listening(6)
        self.assertEqual(state(self.record)['status'], 'completed')
        self.assertEqual(state(self.record)['label'], 'Completed')
        self.assertIsNone(state(self.record)['action'])
        html = self.client.get('/pre-online-session-control-tower?session_year=2026').get_data(as_text=True)
        self.assertIn('staffing-status-confirmed">Completed</span>', html)
        self.assertNotIn('Finalise the exam record configuration for the session', html)
        self.assertNotIn('Configure exam records for the session', html)
        self.beyond(6, checked=False)
        self.assertEqual(state(self.record)['status'], 'in_progress')
        self.beyond(6)
        self.assertEqual(state(self.record)['status'], 'completed')
        previous = state(self.record)['listening']['document'].file_id
        self.listening_upload(previous=previous)
        self.assertEqual(state(self.record)['status'], 'in_progress')

    def test_exam_records_recalculate_for_modules_and_keep_inactive_data(self):
        self.record.modules = 'Speaking'; db.session.commit()
        self.upload(); self.speaking(3)
        self.assertEqual(state(self.record)['status'], 'completed')
        self.record.modules = 'Listening and speaking'; db.session.commit()
        self.assertEqual(state(self.record)['status'], 'in_progress')
        self.assertEqual(state(self.record)['speaking']['count'], 3)
        self.record.modules = 'Speaking'; db.session.commit()
        self.assertEqual(state(self.record)['status'], 'completed')
        self.record.modules = ''; db.session.commit()
        self.assertEqual(state(self.record)['status'], 'not_started')
        self.assertIsNone(state(self.record)['action'])
        self.assertEqual(ExaminerSpeakingRecord.query.count(), 1)
        self.record.modules = 'Speaking'; db.session.commit()
        self.assertEqual(state(self.record)['status'], 'completed')
        self.record.exam_session_name = 'Changed name'; db.session.commit()
        self.assertEqual(state(self.record)['status'], 'in_progress')

    def test_online_session_ready_requires_exactly_the_five_online_blocks(self):
        import re
        from app.models import ExamSessionFinanceControl, ExamSessionSinapsisControl
        from app.routes import ensure_sinapsis_checklist_items
        self.record.modules = 'Speaking'
        self.record.monthly_registrations_closed = True
        self.record.date_confirmation_status = 'Confirmed'
        db.session.commit()
        self.upload(); self.speaking(3)
        finance = ExamSessionFinanceControl(exam_session_id=self.record.id, status='Effective clearance',
            institutions_confirmed_with_admin=True)
        checks = ExamSessionSinapsisControl(exam_session_id=self.record.id, status='Not reviewed')
        db.session.add_all([finance, checks]); db.session.flush()
        ensure_sinapsis_checklist_items(checks); db.session.flush()
        for item in checks.checklist_items:
            item.is_checked = True
        db.session.commit()
        def readiness_cell():
            response = self.client.get('/pre-online-session-control-tower?session_year=2026')
            self.assertEqual(response.status_code, 200)
            table = re.search(r'<table class="control-tower-table online-control-tower-table">.*?</table>', response.get_data(as_text=True), re.S).group(0)
            return re.search(r'<span class="session-readiness-final-cell">.*?</td>', table, re.S).group(0)
        self.assertIn('>Ready</span>', readiness_cell())
        self.assertNotIn('Operational readiness', readiness_cell())
        for model, field, temporary in [(self.workflow, 'status', 'Ready'),
                                         (self.record.staffing_control, 'schedule_notification_confirmed', False),
                                         (finance, 'institutions_confirmed_with_admin', False),
                                         (checks.checklist_items[0], 'is_checked', False)]:
            original = getattr(model, field)
            setattr(model, field, temporary); db.session.commit()
            self.assertIn('>Not ready</span>', readiness_cell())
            setattr(model, field, original); db.session.commit()
            # Schedule and Staffing edits reset the Speaking checklist.
            if state(self.record)['speaking']['count'] < 3:
                self.upload(previous=ExaminerSpeakingRecord.query.one().file_id); self.speaking(3)
            self.assertIn('>Ready</span>', readiness_cell())
        self.speaking(3, checked=False)
        self.assertIn('>Not ready</span>', readiness_cell())
