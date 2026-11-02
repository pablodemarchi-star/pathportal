import os
import re
import unittest
from datetime import date
from unittest.mock import patch

os.environ['DATABASE_URL'] = 'sqlite:///:memory:'
from flask import jsonify, request
from app import create_app, db
from app.models import ExamSession, ExamSessionYear, ExamSessionScheduleWorkflow, ExamSessionScheduleNote
from app.tower_live import session_revision


class TowerLiveTest(unittest.TestCase):
    def setUp(self):
        self.app = create_app()
        self.app.config['TESTING'] = True
        self.context = self.app.app_context()
        self.context.push()
        db.drop_all(); db.create_all()
        db.session.add(ExamSessionYear(year=2026))
        self.first = self.record('First session')
        self.second = self.record('Other session')
        db.session.commit()
        self.client = self.app.test_client()
        with self.client.session_transaction() as state:
            state.update(user='admin', csrf_token='test')

        @self.app.post('/pre-session-control-tower/test-write/<int:session_id>')
        def test_write(session_id):
            record = db.session.get(ExamSession, session_id)
            record.exam_session_name = request.form['name']
            db.session.commit()
            if request.form.get('simulate_external_after_commit'):
                with db.engine.begin() as connection:
                    connection.execute(ExamSession.__table__.update().where(ExamSession.id == session_id).values(exam_session_name='Another writer'))
            return jsonify(ok=True)

    def record(self, name):
        record = ExamSession(exam_session_name=name, category='Path School', status='Pending',
            session_date=date(2026, 11, 20), shifts='Morning', modules='Speaking', format='Onsite')
        db.session.add(record); db.session.flush()
        return record

    def tearDown(self):
        db.session.remove(); db.drop_all(); self.context.pop()

    def revision_url(self):
        return f'/pre-session-control-tower/sessions/{self.first.id}/revision'

    def test_page_defers_modals_and_modal_document_only_renders_requested_session(self):
        response = self.client.get('/pre-session-control-tower?session_year=2026&view=sessions')
        self.assertEqual(response.status_code, 200)
        page = response.get_data(as_text=True)
        self.assertIn('data-tower-session=', page)
        self.assertNotIn('data-revision-url=', page)
        self.assertNotIn('id="staffing-control-form-', page)
        modal = self.client.get(f'/pre-session-control-tower?session_year=2026&view=sessions&session_modal={self.first.id}&open_schedule_modal={self.first.id}&schedule_only=1')
        self.assertEqual(modal.status_code, 200)
        content = modal.get_data(as_text=True)
        self.assertIn('data-tower-modal-document', content)
        self.assertIn(f'id="staffing-control-form-{self.first.id}"', content)
        self.assertNotIn(f'id="staffing-control-form-{self.second.id}"', content)
        self.assertNotIn('class="sidebar"', content)
        self.assertEqual(modal.headers['X-Frame-Options'], 'SAMEORIGIN')
        self.assertEqual(modal.headers['Cache-Control'], 'no-store')
        token = re.search(r'data-revision="([a-f0-9]+)"', content).group(1)
        self.assertEqual(token, self.client.get(self.revision_url()).json['revision'])

    def test_revision_is_private_no_store_stable_and_responds_to_real_edits(self):
        self.assertEqual(self.app.test_client().get(self.revision_url()).status_code, 302)
        with patch('app.routes.user_can_view', return_value=False):
            self.assertEqual(self.client.get(self.revision_url()).status_code, 403)
        first = self.client.get(self.revision_url())
        self.assertEqual(first.headers['Cache-Control'], 'no-store')
        self.assertEqual(set(first.json), {'revision'})
        self.assertEqual(first.json, self.client.get(self.revision_url()).json)
        self.second.exam_session_name = 'Unrelated edit'; db.session.commit()
        self.assertEqual(first.json, self.client.get(self.revision_url()).json)
        self.first.exam_session_name = 'Changed by another user'; db.session.commit()
        self.assertNotEqual(first.json, self.client.get(self.revision_url()).json)

    def test_revision_detects_child_note_creation_edit_and_deletion(self):
        workflow = ExamSessionScheduleWorkflow(exam_session_id=self.first.id, status='In progress')
        db.session.add(workflow); db.session.commit()
        initial = session_revision(self.first.id)
        note = ExamSessionScheduleNote(workflow_id=workflow.id, note_text='Original note', note_id='live-test-note', from_full_name='admin')
        db.session.add(note); db.session.commit()
        added = session_revision(self.first.id)
        self.assertNotEqual(initial, added)
        note.note_text = 'Edited'; db.session.commit()
        self.assertNotEqual(added, session_revision(self.first.id))
        db.session.delete(note); db.session.commit()
        self.assertEqual(initial, session_revision(self.first.id))

    def test_stale_ajax_and_regular_forms_cannot_overwrite_and_fresh_saves_get_new_revision(self):
        token = session_revision(self.first.id)
        url = f'/pre-session-control-tower/test-write/{self.first.id}'
        response = self.client.post(url, data={'name':'First writer'}, headers={
            'X-Tower-Session':str(self.first.id), 'X-Tower-Revision':token})
        self.assertEqual(response.status_code, 200)
        next_token = response.headers['X-Tower-Revision']
        self.assertNotEqual(token, next_token)
        stale = self.client.post(url, data={'name':'Overwrite', 'tower_revision_session_id':self.first.id, 'tower_revision':token})
        self.assertEqual(stale.status_code, 409)
        self.assertEqual(stale.json['error'], 'This session was updated by another user.')
        self.assertEqual(db.session.get(ExamSession, self.first.id).exam_session_name, 'First writer')
        self.assertEqual(self.client.post(url, data={'name':'Fresh save'}, headers={
            'X-Tower-Session':str(self.first.id), 'X-Tower-Revision':next_token}).status_code, 200)

    def test_invalid_and_missing_modal_ids(self):
        self.assertEqual(self.client.get('/pre-session-control-tower?session_modal=bad').status_code, 400)
        self.assertEqual(self.client.get('/pre-session-control-tower?session_modal=999999').status_code, 404)

    def test_revision_tracks_bundle_members_and_recipient_contact_updates(self):
        from app.models import AcademicStaff, ExamSessionShipmentBundle, ExamSessionShipmentBundleSession
        member = AcademicStaff(status='Active', full_name='Shipment recipient')
        db.session.add(member); db.session.flush()
        bundle = ExamSessionShipmentBundle(supervisor_staff_id=member.id, delivery_address='Test address',
            status='Preparing bundle', bundle_year=2026)
        db.session.add(bundle); db.session.flush()
        for record in (self.first, self.second):
            db.session.add(ExamSessionShipmentBundleSession(bundle=bundle, exam_session_id=record.id))
        db.session.commit()
        initial = session_revision(self.first.id)
        self.second.exam_session_name = 'Bundle member updated'; db.session.commit()
        updated = session_revision(self.first.id)
        self.assertNotEqual(initial, updated)
        member.full_name = 'Updated recipient contact'; db.session.commit()
        self.assertNotEqual(updated, session_revision(self.first.id))

    def test_save_header_does_not_acknowledge_another_writers_later_change(self):
        token = session_revision(self.first.id)
        url = f'/pre-session-control-tower/test-write/{self.first.id}'
        response = self.client.post(url, data={'name':'My save','simulate_external_after_commit':'1'}, headers={
            'X-Tower-Session':str(self.first.id),'X-Tower-Revision':token})
        self.assertEqual(response.status_code, 200)
        acknowledged = response.headers['X-Tower-Revision']
        self.assertNotEqual(acknowledged, session_revision(self.first.id))
        blocked = self.client.post(url, data={'name':'Must not overwrite'}, headers={
            'X-Tower-Session':str(self.first.id),'X-Tower-Revision':acknowledged})
        self.assertEqual(blocked.status_code, 409)
