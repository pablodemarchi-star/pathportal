import io
import unittest
from unittest.mock import patch
from flask import Response
from app import db
from app.models import AcademicStaff, StaffIdDocument
from app.google_drive import DriveStorageError
from app.staff_id_documents import FOLDER_ID
from tests.test_google_drive import GoogleDriveTest


class StaffIdDocumentsTest(unittest.TestCase):
    setUpBase = GoogleDriveTest.setUpBase
    tearDownBase = GoogleDriveTest.tearDownBase
    api = GoogleDriveTest.api
    http = GoogleDriveTest.http

    def setUp(self):
        GoogleDriveTest.setUp(self)
        self.member = AcademicStaff(full_name='Staff document test', status='Active', roles='Examiner', id_issued=False)
        db.session.add(self.member); db.session.commit()
        self.url = f'/staff-members/{self.member.id}/id-document'
        self.trash_patch = patch('app.staff_id_documents.trash_document')
        self.trash = self.trash_patch.start()

    def tearDown(self):
        self.trash_patch.stop()
        GoogleDriveTest.tearDown(self)

    def upload(self, filename='identity.pdf', previous='', expiry='20/12/2099'):
        return self.client.post(self.url, data={'csrf_token':'test', 'previous_file_id':previous, 'expiry_date':expiry,
            'document':(io.BytesIO(b'%PDF-1.4 test'), filename, 'application/pdf')})

    def test_upload_replace_delete_keep_id_issued_independent(self):
        self.assertIsNone(self.client.get(self.url).json['document'])
        response = self.upload()
        self.assertEqual(response.status_code, 200, response.json)
        self.assertEqual(self.metadata[0]['parents'], [FOLDER_ID])
        original = response.json['document']['file_id']
        self.assertEqual(StaffIdDocument.query.count(), 1)
        self.assertFalse(self.member.id_issued)
        response = self.upload('replacement.pdf', original)
        self.assertEqual(response.status_code, 200, response.json)
        self.assertEqual(self.trash.call_args.args[0].file_id, original)
        replacement = response.json['document']['file_id']
        self.assertNotEqual(original, replacement)
        self.assertEqual(StaffIdDocument.query.count(), 1)
        self.assertEqual(self.client.delete(self.url, data={'csrf_token':'test', 'previous_file_id':replacement}).status_code, 200)
        self.assertEqual(StaffIdDocument.query.count(), 0)
        self.assertFalse(self.member.id_issued)

    def test_multiple_files_csrf_and_stale_dialog_are_rejected(self):
        response = self.client.post(self.url, data={'csrf_token':'test', 'document':[
            (io.BytesIO(b'one'), 'one.pdf'), (io.BytesIO(b'two'), 'two.pdf')]})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(self.generated, 0)
        self.assertEqual(self.client.post(self.url, data={}).status_code, 400)
        uploaded = self.upload().json['document']['file_id']
        self.assertEqual(self.upload().status_code, 409)
        self.assertEqual(self.client.delete(self.url, data={'csrf_token':'test', 'previous_file_id':'stale'}).status_code, 409)
        self.assertEqual(StaffIdDocument.query.one().file_id, uploaded)
        self.trash.assert_not_called()

    def test_drive_trash_failure_keeps_old_document_and_cleans_new_upload(self):
        original = self.upload().json['document']['file_id']
        self.trash.side_effect = DriveStorageError('Drive trash failed')
        response = self.upload('replacement.pdf', original)
        self.assertEqual(response.status_code, 503, response.json)
        self.assertEqual(StaffIdDocument.query.one().file_id, original)
        self.assertEqual(len(self.trashed), 1)
        self.assertNotEqual(self.trashed[0], original)
        response = self.client.delete(self.url, data={'csrf_token':'test', 'previous_file_id':original})
        self.assertEqual(response.status_code, 503)
        self.assertEqual(StaffIdDocument.query.one().file_id, original)

    def test_staff_menu_renders_single_file_popup_without_changing_issued_flag(self):
        page = self.client.get('/staff-members').get_data(as_text=True)
        self.assertIn('data-staff-id-open', page)
        self.assertIn('data-staff-id-dropzone', page)
        self.assertIn('data-staff-id-replace', page)
        self.assertIn('data-staff-id-delete', page)
        self.assertIn('name="document" data-staff-id-file', page)
        self.member.id_issued = True
        db.session.commit()
        self.assertEqual(self.upload().status_code, 403)
        self.assertTrue(self.member.id_issued)

    def test_issued_card_is_read_only_and_linked_from_staff_menu(self):
        uploaded = self.upload().json['document']['file_id']
        self.member.id_issued = True
        db.session.commit()
        response = self.client.get(self.url)
        self.assertTrue(response.json['read_only'])
        self.assertEqual(response.json['document']['file_id'], uploaded)
        page = self.client.get('/staff-members').get_data(as_text=True)
        self.assertIn('>ID issued ✓</button>', page)
        self.assertEqual(self.upload('replacement.pdf', uploaded).status_code, 403)
        self.assertEqual(self.client.delete(self.url, data={'csrf_token':'test', 'previous_file_id':uploaded}).status_code, 403)
        self.trash.assert_not_called()

    def test_individual_unissue_retires_card_and_failure_preserves_member(self):
        uploaded = self.upload().json['document']['file_id']
        self.member.id_issued = True
        db.session.commit()
        data = {'csrf_token':'test', 'status':'Active', 'full_name':self.member.full_name, 'roles':'Examiner'}
        self.trash.side_effect = DriveStorageError('Drive trash failed')
        response = self.client.post(f'/members/{self.member.id}', data=data)
        self.assertEqual(response.status_code, 302)
        db.session.refresh(self.member)
        self.assertTrue(self.member.id_issued)
        self.assertEqual(StaffIdDocument.query.one().file_id, uploaded)
        self.trash.side_effect = None
        self.client.post(f'/members/{self.member.id}', data=data)
        db.session.refresh(self.member)
        self.assertFalse(self.member.id_issued)
        self.assertEqual(StaffIdDocument.query.count(), 0)

    def test_bulk_unissue_preserves_failed_member_and_reports_name(self):
        uploaded = self.upload().json['document']['file_id']
        self.member.id_issued = True
        other = AcademicStaff(full_name='Other issued staff', status='Active', roles='Examiner', id_issued=True)
        db.session.add(other); db.session.commit()
        data = {'csrf_token':'test', 'bulk_action':'id_issued', 'id_issued':'0',
                'member_ids':[str(self.member.id), str(other.id)]}
        self.trash.side_effect = DriveStorageError('Drive trash failed')
        self.client.post('/members/bulk-update', data=data)
        db.session.refresh(self.member); db.session.refresh(other)
        self.assertTrue(self.member.id_issued)
        self.assertFalse(other.id_issued)
        self.assertEqual(StaffIdDocument.query.one().file_id, uploaded)
        with self.client.session_transaction() as state:
            self.assertTrue(any(self.member.full_name in text for _, text in state['_flashes']))
        self.trash.side_effect = None
        self.client.post('/members/bulk-update', data=data)
        db.session.refresh(self.member)
        self.assertFalse(self.member.id_issued)
        self.assertEqual(StaffIdDocument.query.count(), 0)

    def test_expiry_date_is_required_validated_and_updated_on_replacement(self):
        for expiry in ('', '2026-12-20', '31/02/2027', '1/1/2027'):
            response = self.upload(expiry=expiry)
            self.assertEqual(response.status_code, 400, response.json)
        self.assertEqual(self.generated, 0)
        response = self.upload(expiry='20/12/2099')
        self.assertEqual(response.json['document']['expiry_date'], '20/12/2099')
        self.assertEqual(response.json['document']['expires_at'], '2099-12-20T00:00:00-03:00')
        file_id = response.json['document']['file_id']
        response = self.upload('new.pdf', file_id, expiry='21/12/2099')
        self.assertEqual(response.status_code, 200, response.json)
        self.assertEqual(response.json['document']['expiry_date'], '21/12/2099')

    def test_expiry_starts_at_midnight_gmt_minus_three_and_legacy_cards_stay_valid(self):
        from datetime import date, datetime, timezone
        from app.staff_id_documents import card_expired
        self.upload()
        document = StaffIdDocument.query.one()
        document.expiry_date = date(2026, 12, 20)
        self.assertFalse(card_expired(document, datetime(2026, 12, 20, 2, 59, 59, tzinfo=timezone.utc)))
        self.assertTrue(card_expired(document, datetime(2026, 12, 20, 3, 0, 0, tzinfo=timezone.utc)))
        document.expiry_date = None
        db.session.commit()
        self.assertFalse(card_expired(document, datetime(2100, 1, 1, tzinfo=timezone.utc)))
        self.assertFalse(self.client.get(self.url).json['document']['expired'])

    def test_expired_cards_are_red_for_both_statuses_and_modal_can_unissue(self):
        response = self.upload(expiry='01/01/2000')
        file_id = response.json['document']['file_id']
        self.assertTrue(response.json['document']['expired'])
        for issued in (False, True):
            self.member.id_issued = issued
            db.session.commit()
            page = self.client.get('/staff-members').get_data(as_text=True)
            self.assertIn('has-document is-expired', page)
            self.assertIn('data-staff-id-unissue', page)
        data = {'csrf_token':'test', 'action':'unissue', 'previous_file_id':file_id}
        self.trash.side_effect = DriveStorageError('Drive trash failed')
        self.assertEqual(self.client.post(self.url, data=data).status_code, 503)
        db.session.refresh(self.member)
        self.assertTrue(self.member.id_issued)
        self.assertEqual(StaffIdDocument.query.one().file_id, file_id)
        self.trash.side_effect = None
        result = self.client.post(self.url, data=data)
        self.assertEqual(result.status_code, 200, result.json)
        self.assertFalse(result.json['read_only'])
        self.assertFalse(self.member.id_issued)
        self.assertIsNone(result.json['document'])
        self.assertEqual(StaffIdDocument.query.count(), 0)

    def test_unissue_expiry_action_cannot_bypass_csrf_or_target_current_card(self):
        file_id = self.upload().json['document']['file_id']
        self.member.id_issued = True
        db.session.commit()
        data = {'csrf_token':'test', 'action':'unissue', 'previous_file_id':file_id}
        self.assertEqual(self.client.post(self.url, data=data).status_code, 400)
        from datetime import date
        StaffIdDocument.query.one().expiry_date = date(2000, 1, 1)
        db.session.commit()
        self.assertEqual(self.client.post(self.url, data={**data, 'csrf_token':'wrong'}).status_code, 400)
        self.assertEqual(self.client.post(self.url, data={**data, 'previous_file_id':'stale'}).status_code, 409)
        self.assertTrue(self.member.id_issued)
        self.trash.assert_not_called()

    def test_migration_preserves_existing_card_without_expiry(self):
        from sqlalchemy import text
        from app.schema_migrations import migrate_staff_id_expiry
        db.session.execute(text('DROP TABLE staff_id_document'))
        db.session.execute(text('CREATE TABLE staff_id_document (member_id INTEGER PRIMARY KEY, file_id VARCHAR(160), destination_key VARCHAR(100), filename VARCHAR(500), mime_type VARCHAR(160), version INTEGER)'))
        db.session.execute(text("INSERT INTO staff_id_document VALUES (:member_id, 'legacy-file-id', 'staff_id_documents', 'old.pdf', 'application/pdf', 1)"), {'member_id': self.member.id})
        db.session.commit()
        migrate_staff_id_expiry()
        migrate_staff_id_expiry()
        document = db.session.get(StaffIdDocument, self.member.id)
        self.assertEqual(document.file_id, 'legacy-file-id')
        self.assertIsNone(document.expiry_date)
        self.assertFalse(self.client.get(self.url).json['document']['expired'])

    def test_download_is_attachment_and_preview_remains_inline(self):
        self.upload()
        preview = self.client.get(self.url + '/preview')
        download = self.client.get(self.url + '/preview?download=1')
        self.assertTrue(preview.headers['Content-Disposition'].startswith('inline;'))
        self.assertTrue(download.headers['Content-Disposition'].startswith('attachment;'))
        self.assertIn('identity.pdf', download.headers['Content-Disposition'])
        self.assertEqual(download.data, b'private document')
        page = self.client.get('/staff-members').get_data(as_text=True)
        self.assertIn('data-staff-id-filename download>Download</a>', page)

    def package_session(self):
        from datetime import date
        from app.models import ExamSession, ExamSessionScheduleWorkflow, ExamSessionExaminerAssignment
        record = ExamSession(exam_session_name='Staff ID package test', category='Path School',
            status='Pending', session_date=date(2026, 12, 20), shifts='Morning', modules='Speaking', format='Onsite',
            staff_member_ids_status='in_progress')
        db.session.add(record); db.session.flush()
        db.session.add(ExamSessionScheduleWorkflow(exam_session_id=record.id, status='Approved'))
        assignment = ExamSessionExaminerAssignment(exam_session_id=record.id, team_member_id=self.member.id,
            participation_status='Confirmed')
        db.session.add(assignment); db.session.commit()
        return record, assignment

    def test_package_links_require_confirmation_and_live_file(self):
        record, assignment = self.package_session()
        from app.routes import staff_member_id_requirements_for_session
        with self.app.test_request_context():
            item = staff_member_id_requirements_for_session(record, [assignment])[0]
            self.assertFalse(item['has_file'])
            self.assertIsNone(item['download_url'])
        self.upload()
        with self.app.test_request_context():
            item = staff_member_id_requirements_for_session(record, [assignment])[0]
            download_url = item['download_url']
            self.assertTrue(item['has_file'])
        response = self.client.get(download_url)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.headers['Content-Disposition'].startswith('attachment;'))
        self.assertEqual(response.data, b'private document')
        assignment.participation_status = 'Pending'
        db.session.commit()
        with self.app.test_request_context():
            self.assertIsNone(staff_member_id_requirements_for_session(record, [assignment])[0]['download_url'])
        self.assertEqual(self.client.get(download_url).status_code, 403)

    def test_package_completion_keeps_expiry_and_only_issues_with_files(self):
        from datetime import date
        from app.models import ExamSessionExaminerAssignment
        from app.routes import staff_member_id_requirements_for_session
        self.upload(expiry='01/01/2000')
        self.member.id_issued = True
        record, assignment = self.package_session()
        missing = AcademicStaff(full_name='Missing card staff', status='Active', roles='Examiner', id_issued=False)
        valid = AcademicStaff(full_name='Ready card staff', status='Active', roles='Examiner', id_issued=False)
        db.session.add_all([missing, valid]); db.session.flush()
        for member in (missing, valid):
            db.session.add(ExamSessionExaminerAssignment(exam_session_id=record.id, team_member_id=member.id,
                participation_status='Confirmed'))
        db.session.add(StaffIdDocument(member_id=valid.id, file_id='valid-card-for-package', filename='card.pdf',
            mime_type='application/pdf', destination_key='staff_id_documents', expiry_date=date(2099, 12, 20)))
        db.session.commit()
        with self.app.test_request_context():
            items = staff_member_id_requirements_for_session(record, list(record.examiner_assignments))
            expired = next(item for item in items if item['id'] == self.member.id)
        self.assertTrue(expired['expired'])
        blocked = self.client.get(expired['download_url'])
        self.assertEqual(blocked.status_code, 409)
        self.assertIn('ID card file update required before issuance.', blocked.get_data(as_text=True))
        result = self.client.post(f'/pre-session-control-tower/sessions/{record.id}/packages/staff-member-ids',
            data={'csrf_token':'test', 'action':'mark_complete'})
        self.assertEqual(result.status_code, 302)
        self.assertEqual(record.staff_member_ids_status, 'completed')
        self.assertTrue(valid.id_issued)
        self.assertFalse(missing.id_issued)
        self.assertTrue(self.member.id_issued)
        self.assertEqual(db.session.get(StaffIdDocument, self.member.id).expiry_date, date(2000, 1, 1))
        with self.client.session_transaction() as state:
            warnings = ' '.join(text for kind, text in state['_flashes'] if kind == 'warning')
        self.assertIn(missing.full_name, warnings)
        self.assertIn(self.member.full_name, warnings)
        with self.app.test_request_context():
            self.assertTrue(any(item['id'] == self.member.id and item['expired'] for item in
                staff_member_id_requirements_for_session(record, list(record.examiner_assignments))))

    def test_package_modal_links_and_expired_warning_follow_current_state(self):
        from datetime import date
        import re
        self.upload()
        record, assignment = self.package_session()
        url = f'/pre-session-control-tower?session_year=2026&view=sessions&session_modal={record.id}&open_schedule_modal={record.id}&packages_only=1'
        def staff_row():
            response = self.client.get(url)
            self.assertEqual(response.status_code, 200)
            html = response.get_data(as_text=True)
            self.assertIn('Staff ID cards', html)
            return re.search(r'<span class="package-staff-id-name">(.*?)</li>', html, re.S).group(1)
        row = staff_row()
        self.assertIn('class="package-staff-id-download"', row)
        assignment.participation_status = 'Pending'
        db.session.commit()
        row = staff_row()
        self.assertNotIn('class="package-staff-id-download"', row)
        self.assertIn('class="package-staff-id-download-disabled"', row)
        self.assertIn('aria-disabled="true"', row)
        self.assertNotIn('href=', row)
        self.assertIn('Do not proceed with printing this ID.', row)
        assignment.participation_status = 'Confirmed'
        self.member.id_issued = True
        db.session.get(StaffIdDocument, self.member.id).expiry_date = date(2000, 1, 1)
        db.session.commit()
        row = staff_row()
        self.assertIn('data-staff-id-expired-download', row)
        self.assertIn(self.member.full_name, row)

    def test_preview_is_private_and_downloaded_through_the_portal(self):
        self.upload()
        response = self.client.get(self.url + '/preview')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data, b'private document')
        self.assertEqual(response.headers['X-Frame-Options'], 'SAMEORIGIN')
        self.assertIn("frame-ancestors 'self'", response.headers['Content-Security-Policy'])
        self.assertIn('no-store', response.headers['Cache-Control'])
        with patch('app.routes.require_menu_view', side_effect=lambda _: __import__('flask').abort(403)):
            self.assertEqual(self.client.get(self.url).status_code, 403)
            self.assertEqual(self.client.get(self.url + '/preview').status_code, 403)
        with patch('app.routes.require_menu_edit', side_effect=lambda _: __import__('flask').abort(403)):
            self.assertEqual(self.client.delete(self.url, data={'csrf_token':'test'}).status_code, 403)
