import unittest
import uuid
from datetime import date
from io import BytesIO
from unittest.mock import patch
from flask import Response
from app import db, models as m
from app.announcements import FOLDER_ID, pending_action
from tests import test_google_drive as drive_fixtures
from tests import test_staff_return_materials as portal_fixtures

MP3 = b'ID3\x04\x00\x00\x00\x00\x00\x00audio frames'
WAV = b'RIFF\x20\x00\x00\x00WAVEfmt audio'


class AnnouncementsTest(unittest.TestCase):
    setUpBase = drive_fixtures.GoogleDriveTest.setUpBase
    tearDownBase = drive_fixtures.GoogleDriveTest.tearDownBase
    api = drive_fixtures.GoogleDriveTest.api
    http = drive_fixtures.GoogleDriveTest.http
    tearDown = drive_fixtures.GoogleDriveTest.tearDown
    assign = portal_fixtures.StaffReturnMaterialsTest.assign

    def setUp(self):
        drive_fixtures.GoogleDriveTest.setUp(self)
        self.record = m.ExamSession(exam_session_name='Onsite announcements', category='Path School', status='Pending',
            session_date=date(2026, 12, 15), shifts='Morning', modules='Speaking', format='Onsite')
        self.person = m.AcademicStaff(full_name='Session Supervisor', status='Active', roles='Supervisor')
        db.session.add_all([self.record, self.person]); db.session.commit()
        self.assignment, self.share = self.assign('supervisor', token='announcements-supervisor')
        self.gate = patch('app.routes.logistics_actions_are_blocked', return_value=False); self.gate.start(); self.addCleanup(self.gate.stop)
        self.trash = patch('app.announcements.trash_document'); self.trasher = self.trash.start(); self.addCleanup(self.trash.stop)
        self.url = f'/pre-session-control-tower/sessions/{self.record.id}/announcements'
        self.revision = 0

    def post(self, action, **fields):
        result = self.client.post(self.url, data=dict(csrf_token='test', revision=str(self.revision), action=action, **fields))
        if result.status_code == 200:
            self.revision = result.json['revision']
        return result

    def enable(self):
        self.assertEqual(self.post('toggle', enabled='1').status_code, 200)

    def save(self, key=None, title='Opening announcement', audio=True, **fields):
        key = key or str(uuid.uuid4())
        if audio:
            fields['audio'] = (BytesIO(MP3), 'opening.mp3')
        return self.post('save', id=key, title=title, **fields)

    def portal(self, share=None):
        response = self.app.test_client().get('/my-exam-sessions/' + (share or self.share).token)
        self.assertEqual(response.status_code, 200)
        return response.get_data(as_text=True)

    def test_required_fields_audio_validation_and_multiple_independent_cards(self):
        self.enable()
        self.assertEqual(self.post('ready').status_code, 400)
        for title, contents, name in [('', MP3, 'audio.mp3'), ('Title', b'bad', 'fake.mp3'), ('Title', MP3, 'audio.pdf'), ('Title', b'', 'empty.wav')]:
            result = self.post('save', id=str(uuid.uuid4()), title=title, audio=(BytesIO(contents), name))
            self.assertEqual(result.status_code, 400, result.json)
        self.assertEqual(self.save(audio=False).status_code, 400)
        self.assertEqual(m.ExamSessionAnnouncement.query.count(), 0)
        self.assertEqual(self.metadata, [])
        first = self.save(); self.assertEqual(first.status_code, 200, first.json)
        key = first.json['announcements'][0]['id']
        second = self.save(title='Closing announcement'); self.assertEqual(second.status_code, 200, second.json)
        self.assertEqual(len(second.json['announcements']), 2)
        self.assertEqual(self.metadata[0]['parents'], [FOLDER_ID])
        self.assertEqual(m.GoogleDriveUpload.query.count(), 0)
        edit = self.save(key, title='New title', audio=False)
        self.assertEqual(edit.status_code, 200, edit.json)
        self.assertEqual(m.ExamSessionAnnouncement.query.count(), 2)
        self.assertEqual(db.session.get(m.ExamSessionAnnouncement, key).title, 'New title')
        self.assertEqual(len(self.metadata), 2)

    def test_ready_action_deadline_and_edit_add_delete_reset(self):
        self.enable()
        self.assertEqual(pending_action(self.record, today=date(2026, 12, 15))[0], dict(department='LOGISTICS', description='Upload session announcements', section='logistics', overdue=True))
        result = self.save(); key = result.json['announcements'][0]['id']
        self.assertTrue(self.post('ready').json['ready'])
        self.assertEqual(pending_action(self.record), [])
        self.assertFalse(self.save(key, title='Edited', audio=False).json['ready'])
        self.assertTrue(pending_action(self.record))
        self.post('ready'); self.assertFalse(self.save(title='Another').json['ready'])
        self.post('ready'); self.assertFalse(self.post('delete', id=key).json['ready'])
        self.assertEqual(self.trasher.call_count, 1)
        self.post('ready'); self.assertFalse(self.post('pending').json['ready'])

    def test_replacement_and_deletion_trash_old_audio_and_failures_preserve_saved_data(self):
        self.enable(); result = self.save(); key = result.json['announcements'][0]['id']
        old = db.session.get(m.ExamSessionAnnouncement, key).file_id
        result = self.post('save', id=key, title='Updated', audio=(BytesIO(WAV), 'updated.WAV'))
        self.assertEqual(result.status_code, 200, result.json)
        self.assertEqual(self.trasher.call_args.args[0].file_id, old)
        self.assertEqual(db.session.get(m.ExamSessionAnnouncement, key).mime_type, 'audio/wav')
        self.trasher.side_effect = OSError('unavailable')
        self.assertEqual(self.post('delete', id=key).status_code, 503)
        self.assertIsNotNone(db.session.get(m.ExamSessionAnnouncement, key))
        self.trasher.side_effect = None
        self.assertEqual(self.post('delete', id=key).status_code, 200)
        self.assertEqual(m.ExamSessionAnnouncement.query.count(), 0)
        self.assertEqual(self.post('ready').status_code, 400)

    def test_toggle_retains_files_and_reopens_confirmation(self):
        self.enable(); self.save(); self.post('ready')
        self.assertTrue(self.client.get(self.url).json['ready'])
        result = self.post('toggle', enabled='0')
        self.assertFalse(result.json['enabled']); self.assertFalse(result.json['ready'])
        self.assertEqual(len(result.json['announcements']), 1)
        self.assertEqual(pending_action(self.record), [])
        self.assertEqual(self.post('ready').status_code, 409)
        self.assertEqual(self.save().status_code, 409)
        self.enable()
        self.assertFalse(self.client.get(self.url).json['ready']); self.assertTrue(pending_action(self.record))
        self.trasher.assert_not_called()

    def test_stale_revision_csrf_permissions_format_and_gate(self):
        self.enable()
        self.assertEqual(self.client.post(self.url, data=dict(csrf_token='test', revision=0, action='toggle', enabled='0')).status_code, 409)
        self.assertEqual(self.client.post(self.url, data=dict(csrf_token='wrong', revision=self.revision, action='ready')).status_code, 403)
        with patch('app.routes.user_can_edit', return_value=False), patch('app.routes.user_can_view', return_value=True):
            self.assertFalse(self.client.get(self.url).json['can_edit'])
            self.assertEqual(self.save().status_code, 403)
        with patch('app.routes.user_can_view', return_value=False):
            self.assertEqual(self.client.get(self.url).status_code, 403)
        with patch('app.routes.logistics_actions_are_blocked', return_value=True):
            self.assertFalse(self.client.get(self.url).json['can_edit'])
            self.assertEqual(self.save().status_code, 403)
        for format in ['Online', 'Online at exam centre']:
            self.record.format = format; db.session.commit()
            self.assertEqual(self.client.get(self.url).status_code, 404)
            self.assertEqual(self.save().status_code, 404)
        self.record.format = 'Onsite'; db.session.commit()
        self.assertIn(self.app.test_client().get(self.url).status_code, [302, 401])

    def test_staff_portal_only_ready_confirmed_supervisors_and_live_audio_authorization(self):
        self.enable(); result = self.save(title='Listen carefully'); key = result.json['announcements'][0]['id']
        audio = f'/my-exam-sessions/{self.share.token}/sessions/{self.record.id}/announcements/{key}/audio'
        self.assertNotIn('data-announcements-open=', self.portal())
        self.assertEqual(self.app.test_client().get(audio).status_code, 404)
        self.post('ready')
        page = self.portal(); self.assertIn('data-announcements-open=', page); self.assertIn('Listen carefully</h3>', page)
        self.assertIn(audio, page); self.assertNotIn('uploaded-file-', page)
        with patch('app.announcements.stream_document', return_value=Response(b'audio', mimetype='audio/mpeg')):
            response = self.app.test_client().get(audio)
        self.assertEqual(response.status_code, 200); self.assertEqual(response.headers['Cache-Control'], 'private, no-store')
        for status in ['Pending', 'Pre-confirmed', 'Official confirmation sent', 'Declined', 'Cancelled']:
            self.assignment.participation_status = status; db.session.commit()
            self.assertNotIn('data-announcements-open=', self.portal())
            self.assertEqual(self.app.test_client().get(audio).status_code, 404)
        self.assignment.participation_status = 'Confirmed'; db.session.commit()
        self.post('pending')
        self.assertNotIn('data-announcements-open=', self.portal())
        self.assertEqual(self.app.test_client().get(audio).status_code, 404)

    def test_multiple_supervisors_can_access_but_examiners_and_unsubmitted_cannot(self):
        self.enable(); self.save(); self.post('ready')
        other = m.AcademicStaff(full_name='Second supervisor', status='Active', roles='Supervisor'); db.session.add(other); db.session.commit()
        _, other_share = self.assign('supervisor', person=other, token='second-supervisor')
        self.assertIn('data-announcements-open=', self.portal(other_share))
        examiner = m.AcademicStaff(full_name='Examiner', status='Active', roles='Examiner'); db.session.add(examiner); db.session.commit()
        _, examiner_share = self.assign('examiner', person=examiner, token='only-examiner')
        self.assertNotIn('data-announcements-open=', self.portal(examiner_share))
        key = m.ExamSessionAnnouncement.query.first().id
        self.assertEqual(self.app.test_client().get(f'/my-exam-sessions/{examiner_share.token}/sessions/{self.record.id}/announcements/{key}/audio').status_code, 404)

    def test_audio_range_mime_and_private_streaming(self):
        self.enable(); result = self.save(); url = result.json['announcements'][0]['audio_url']
        response = self.client.get(url, headers={'Range':'bytes=0-'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.mimetype, 'audio/mpeg')
        self.assertTrue(response.headers['Content-Disposition'].startswith('inline'))
        self.assertEqual(response.data, b'private document')
        self.assertEqual(self.http.call_args.args[0].get_header('Range'), 'bytes=0-')

    def test_internal_tower_action_my_actions_and_deadline(self):
        from app.routes import schedule_workflow_view, department_my_actions, logistics_session_deadline
        from flask import session
        self.enable()
        view = schedule_workflow_view(self.record, today=date(2026, 12, 15))
        actions = [a for a in view['bundle_detail_actions'] if a['description'] == 'Upload session announcements']
        self.assertEqual(len(actions), 1)
        self.assertTrue(actions[0]['overdue'])
        with self.app.test_request_context():
            session['user_department'] = 'Logistics'
            rows = department_my_actions([view], [], None, {}, today=date(2026, 12, 15))
            self.assertTrue(any(a['description'] == 'Upload session announcements' for row in rows for a in row['actions']))
        self.assertIsNotNone(logistics_session_deadline(self.record))
        self.save(); self.post('ready')
        view = schedule_workflow_view(self.record)
        self.assertFalse(any(a['description'] == 'Upload session announcements' for a in view['bundle_detail_actions']))

    def test_internal_section_speaker_and_assets_render_onsite_only(self):
        url = f'/pre-session-control-tower?session_year=2026&session_modal={self.record.id}&open_schedule_modal={self.record.id}&logistics_only=1'
        response = self.client.get(url); self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        for fragment in ['data-announcement-toggle=', 'data-announcements-section=', 'data-announcement-template=', 'Announcements are ready', 'js/announcements.js', 'css/announcements.css']:
            self.assertIn(fragment, html)
        self.assertLess(html.index('>View in Sinapsis</a>'), html.index('data-announcement-toggle='))
        self.assertLess(html.index('class="staff-logistics-cards"'), html.index('data-announcements-section='))
        self.record.format = 'Online at exam centre'; db.session.commit()
        html = self.client.get(url.replace('/pre-session-control-tower?', '/pre-online-session-control-tower?')).get_data(as_text=True)
        self.assertNotIn('data-announcement-toggle=', html)
        self.assertNotIn('data-announcements-section=', html)

    def test_session_deletion_trashes_audio_and_removes_controls(self):
        self.enable(); self.save()
        from app.routes import delete_exam_session_dependencies
        with patch('app.staff_invoices.trash_document') as trash:
            delete_exam_session_dependencies(self.record.id); db.session.commit()
            trash.assert_called_once()
        self.assertEqual(m.ExamSessionAnnouncement.query.count(), 0)
        self.assertEqual(m.ExamSessionAnnouncementControl.query.count(), 0)

    def test_fixed_drive_destination(self):
        url = '/integrations/google/drive/folders/session_announcements'
        self.assertEqual(self.client.post(url, data=dict(csrf_token='test', folder_id='wrong-folder')).status_code, 400)
        self.assertEqual(self.client.post(url, data=dict(csrf_token='test', folder_id=FOLDER_ID)).status_code, 200)
        self.assertEqual(db.session.get(m.GoogleDriveDestination, 'session_announcements').folder_id, FOLDER_ID)

    def test_supervisor_action_follows_pen_and_audio_changes_hide_both_link_and_modal(self):
        self.record.pen_enabled = True
        db.session.add(m.ExamSessionPenCandidate(id=str(uuid.uuid4()), exam_session_id=self.record.id, candidate_no='0001', candidate_name='PEN Candidate', examiner_refs='[]', recommendations_html=''))
        db.session.commit()
        self.enable(); self.save(); self.post('ready')
        html = self.portal()
        self.assertLess(html.index('>⚠️ Personal Educational Needs</a>'), html.index('>🔊 Announcements</a>'))
        self.post('pending')
        html = self.portal()
        self.assertNotIn('data-announcements-open=', html)
        self.assertNotIn('class="announcements-dialog"', html)

    def test_audio_partial_response_preserves_range_headers(self):
        from tests.test_google_drive import FakeResponse
        self.enable(); result = self.save(); url = result.json['announcements'][0]['audio_url']
        upstream = FakeResponse(b'ID3', headers={'Content-Length':'3', 'Content-Range':'bytes 0-2/20', 'Accept-Ranges':'bytes'})
        upstream.status = 206
        with patch('app.google_drive.urlopen', return_value=upstream):
            result = self.client.get(url, headers={'Range':'bytes=0-2'})
            self.assertEqual(result.status_code, 206)
            self.assertEqual(result.headers['Content-Range'], 'bytes 0-2/20')
            self.assertEqual(result.headers['Content-Length'], '3')
            self.assertEqual(result.data, b'ID3')
