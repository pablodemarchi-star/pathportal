import json
import unittest
import uuid
from datetime import date
from io import BytesIO
from unittest.mock import patch
from app import db, models as m
from app.google_drive import DriveStorageError
from app.pen_arrangements import FOLDER_ID
from tests import test_google_drive as fixtures


class PenArrangementsTest(unittest.TestCase):
    setUpBase = fixtures.GoogleDriveTest.setUpBase
    tearDownBase = fixtures.GoogleDriveTest.tearDownBase
    api = fixtures.GoogleDriveTest.api
    http = fixtures.GoogleDriveTest.http
    tearDown = fixtures.GoogleDriveTest.tearDown

    def setUp(self):
        fixtures.GoogleDriveTest.setUp(self)
        self.record = m.ExamSession(exam_session_name='PEN session', category='Path School', status='Pending',
            session_date=date(2026, 11, 26), shifts='Morning', modules='Speaking', format='Onsite', pen_enabled=True)
        self.examiner = m.AcademicStaff(full_name='Assigned Examiner', status='Active', roles='Examiner')
        self.supervisor = m.AcademicStaff(full_name='Assigned Supervisor', status='Active', roles='Supervisor')
        db.session.add_all([self.record, self.examiner, self.supervisor]); db.session.flush()
        db.session.add(m.ExamSessionExaminerAssignment(exam_session_id=self.record.id, team_member_id=self.examiner.id, participation_status='Confirmed'))
        db.session.add(m.ExamSessionSupervisorAssignment(exam_session_id=self.record.id, team_member_id=self.supervisor.id, participation_status='Confirmed'))
        db.session.commit()
        self.url = f'/pre-session-control-tower/sessions/{self.record.id}/pen-candidates'
        self.key = str(uuid.uuid4())

    def values(self, **fields):
        return dict(csrf_token='test', revision='0', candidate_no='00018', candidate_name='Test Candidate',
                    examiner_refs=[str(self.examiner.id)], recommendations_html='') | fields

    def save(self, key=None, **fields):
        return self.client.post(self.url + '/' + (key or self.key), data=self.values(**fields))

    def test_independent_cards_required_fields_and_sanitized_recommendations(self):
        for fields in [dict(candidate_no=''), dict(candidate_name=' '), dict(examiner_refs=[])]:
            response = self.save(document=(BytesIO(b'not uploaded'), 'assessment.pdf'), **fields)
            self.assertEqual(response.status_code, 400, response.json)
        self.assertEqual(m.ExamSessionPenCandidate.query.count(), 0)
        self.assertEqual(self.metadata, [])
        response = self.save(recommendations_html='<p><strong>Extra time</strong></p><ul><li>Quiet room</li></ul><script>bad()</script>')
        self.assertEqual(response.status_code, 200, response.json)
        first = response.json['candidate']
        self.assertEqual(first['candidate_no'], '00018')
        self.assertIn('<strong>Extra time</strong>', first['recommendations_html'])
        self.assertNotIn('<script>', first['recommendations_html'])
        second_key = str(uuid.uuid4())
        self.assertEqual(self.save(second_key, candidate_name='Second Candidate').status_code, 200)
        updated = self.save(revision=first['revision'], candidate_name='Updated first')
        self.assertEqual(updated.status_code, 200, updated.json)
        rows = self.client.get(self.url).json['candidates']
        self.assertEqual({row['candidate_name'] for row in rows}, {'Updated first', 'Second Candidate'})
        # Invalid edits retain the complete, previously saved card.
        self.assertEqual(self.save(revision=updated.json['candidate']['revision'], candidate_name='').status_code, 400)
        self.assertEqual(db.session.get(m.ExamSessionPenCandidate, self.key).candidate_name, 'Updated first')

    def test_examiners_are_only_assigned_examiners_and_multi_select_is_persisted(self):
        data = self.client.get(self.url).json
        self.assertEqual(data['examiners'], [dict(value=str(self.examiner.id), label=self.examiner.full_name)])
        self.assertEqual(self.save(examiner_refs=[str(self.supervisor.id)]).status_code, 400)
        other = m.AcademicStaff(full_name='Other Examiner', status='Active', roles='Examiner')
        db.session.add(other); db.session.commit()
        self.assertEqual(self.save(examiner_refs=[str(other.id)]).status_code, 400)
        assignment = m.ExamSessionExaminerAssignment(exam_session_id=self.record.id, team_member_id=other.id)
        db.session.add(assignment); db.session.commit()
        response = self.save(examiner_refs=[str(self.examiner.id), str(other.id)])
        self.assertEqual(response.status_code, 200)
        self.assertEqual(set(response.json['candidate']['examiner_refs']), {str(other.id), str(self.examiner.id)})
        db.session.delete(assignment); db.session.commit()
        self.assertEqual(self.save(revision=1, examiner_refs=[str(other.id)]).status_code, 400)

    def test_online_at_exam_centre_disables_and_does_not_require_examiners(self):
        self.record.format = 'Online at exam centre'; db.session.commit()
        listing = self.client.get(self.url).json
        self.assertTrue(listing['examiners_disabled']); self.assertEqual(listing['examiners'], [])
        response = self.save(examiner_refs=[])
        self.assertEqual(response.status_code, 200, response.json)
        self.assertEqual(response.json['candidate']['examiner_refs'], [])
        self.assertEqual(self.save(revision=1, examiner_refs=['forged']).json['candidate']['examiner_refs'], [])

    def test_online_uses_assigned_examiners(self):
        self.record.format = 'Online'; db.session.commit()
        self.assertFalse(self.client.get(self.url).json['examiners_disabled'])
        self.assertEqual(self.save(examiner_refs=[]).status_code, 400)
        self.assertEqual(self.save().status_code, 200)

    def test_pen_toggle_hides_but_preserves_data_and_disallows_writes(self):
        self.assertEqual(self.save().status_code, 200)
        self.record.pen_enabled = False; db.session.commit()
        data = self.client.get(self.url).json
        self.assertFalse(data['enabled']); self.assertEqual(len(data['candidates']), 1)
        self.assertEqual(self.save(revision=1).status_code, 409)
        self.record.pen_enabled = True; db.session.commit()
        self.assertEqual(len(self.client.get(self.url).json['candidates']), 1)

    def test_stale_versions_and_deleted_cards_cannot_be_overwritten_or_recreated(self):
        self.assertEqual(self.save().status_code, 200)
        self.assertEqual(self.save(candidate_name='Duplicate create').status_code, 409)
        self.assertEqual(self.save(revision=1, candidate_name='Current').status_code, 200)
        self.assertEqual(self.save(revision=1, candidate_name='Stale').status_code, 409)
        response = self.client.post(self.url + '/' + self.key, data=dict(csrf_token='test', action='delete', revision=2))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.save(revision=2).status_code, 409)
        self.assertIsNone(db.session.get(m.ExamSessionPenCandidate, self.key))

    def test_file_is_optional_single_private_and_uploaded_to_requested_folder(self):
        response = self.save(document=(BytesIO(b'%PDF-1.7 assessment'), 'assessment.pdf'))
        self.assertEqual(response.status_code, 200, response.json)
        row = db.session.get(m.ExamSessionPenCandidate, self.key)
        self.assertEqual(self.metadata[0]['parents'], [FOLDER_ID])
        self.assertEqual(self.parts, [b'%PDF-1.7 assessment'])
        self.assertEqual(row.filename, 'assessment.pdf')
        url = response.json['candidate']['document']['url']
        self.assertEqual(self.client.get(url).data, b'private document')
        self.assertEqual(self.app.test_client().get(url).status_code, 302)
        self.assertEqual(self.client.get(url.replace(f'sessions/{self.record.id}', 'sessions/999999')).status_code, 404)
        self.assertEqual(self.client.get(url).headers['Cache-Control'], 'private, no-store')
        self.assertEqual(self.save(str(uuid.uuid4()), document=[(BytesIO(b'a'), 'a.pdf'), (BytesIO(b'b'), 'b.pdf')]).status_code, 400)
        self.assertEqual(len(self.metadata), 1)

    def test_replace_remove_document_and_delete_card_trash_previous_file(self):
        self.save(document=(BytesIO(b'original'), 'original.pdf'))
        row = db.session.get(m.ExamSessionPenCandidate, self.key); old = row.file_id
        with patch('app.pen_arrangements.trash_document') as trash:
            response = self.save(revision=1, document=(BytesIO(b'new'), 'new.pdf'))
            self.assertEqual(response.status_code, 200, response.json)
            self.assertEqual(trash.call_args.args[0].file_id, old)
        row = db.session.get(m.ExamSessionPenCandidate, self.key); new = row.file_id
        self.assertNotEqual(new, old)
        with patch('app.pen_arrangements.trash_document') as trash:
            response = self.save(revision=2, remove_document='1')
            self.assertEqual(response.status_code, 200, response.json)
            self.assertEqual(trash.call_args.args[0].file_id, new)
        self.assertIsNone(response.json['candidate']['document'])
        self.save(revision=3, document=(BytesIO(b'again'), 'again.pdf'))
        with patch('app.pen_arrangements.trash_document') as trash:
            response = self.client.post(self.url+'/'+self.key, data=dict(csrf_token='test', revision=4, action='delete'))
            self.assertEqual(response.status_code, 200, response.json); trash.assert_called_once()
        self.assertEqual(m.ExamSessionPenCandidate.query.count(), 0)

    def test_drive_failure_keeps_previous_card_and_document(self):
        self.save(document=(BytesIO(b'original'), 'original.pdf'))
        old = db.session.get(m.ExamSessionPenCandidate, self.key).file_id
        with patch('app.pen_arrangements.trash_document', side_effect=DriveStorageError('Could not trash report.')):
            response = self.save(revision=1, candidate_name='Do not commit', document=(BytesIO(b'new'), 'new.pdf'))
            self.assertEqual(response.status_code, 503, response.json)
            row = db.session.get(m.ExamSessionPenCandidate, self.key)
            self.assertEqual(row.file_id, old); self.assertEqual(row.candidate_name, 'Test Candidate'); self.assertEqual(row.revision, 1)
            self.assertEqual(self.client.post(self.url+'/'+self.key, data=dict(csrf_token='test', action='delete', revision=1)).status_code, 503)
            self.assertIsNotNone(db.session.get(m.ExamSessionPenCandidate, self.key))
        self.assertIn(self.metadata[-1]['id'], self.trashed)

    def test_permissions_csrf_and_session_scope(self):
        self.assertEqual(self.save(csrf_token='bad').status_code, 403)
        self.assertEqual(self.app.test_client().get(self.url).status_code, 302)
        with patch('app.routes.user_can_edit', return_value=False), patch('app.routes.user_can_view', return_value=True):
            self.assertFalse(self.client.get(self.url).json['can_edit'])
            self.assertEqual(self.save().status_code, 403)
        with patch('app.routes.user_can_view', return_value=False):
            self.assertEqual(self.client.get(self.url).status_code, 403)
        self.assertEqual(self.save().status_code, 200)
        second = m.ExamSession(exam_session_name='Other', category='Path School', status='Pending', session_date=date(2026,11,26), shifts='Morning', modules='Speaking', format='Onsite', pen_enabled=True)
        db.session.add(second); db.session.commit()
        url = self.url.replace(f'sessions/{self.record.id}', f'sessions/{second.id}') + '/' + self.key
        self.assertEqual(self.client.post(url, data=self.values(revision=1)).status_code, 409)
        self.assertEqual(db.session.get(m.ExamSessionPenCandidate,self.key).exam_session_id,self.record.id)

    def confirmation(self, checked=True, **fields):
        data = dict(csrf_token='test', confirmed='1' if checked else '0', snapshot=self.client.get(self.url).json['completion']['snapshot'])
        data.update(fields)
        return self.client.post(self.url+'/confirmation', data=data)

    def test_completion_requires_saved_candidate_and_honours_permissions_and_snapshot(self):
        self.assertFalse(self.client.get(self.url).json['completion']['complete'])
        self.assertEqual(self.confirmation().status_code, 400)
        self.assertEqual(self.save().status_code, 200)
        snapshot = self.client.get(self.url).json['completion']['snapshot']
        self.assertEqual(self.confirmation(csrf_token='bad').status_code, 403)
        with patch('app.routes.user_can_edit', return_value=False):
            self.assertEqual(self.confirmation().status_code, 403)
        self.assertEqual(self.confirmation(confirmed='invalid').status_code, 400)
        self.save(revision=1, candidate_name='Latest')
        self.assertEqual(self.confirmation(snapshot=snapshot).status_code, 409)
        response = self.confirmation()
        self.assertEqual(response.status_code, 200, response.json)
        self.assertTrue(response.json['completion']['complete'])
        self.assertIsNotNone(m.ExamSessionPenControl.query.one().confirmed_at)
        self.assertEqual(self.confirmation(False).status_code, 200)
        self.assertFalse(self.client.get(self.url).json['completion']['complete'])

    def test_every_saved_card_and_file_change_invalidates_confirmation(self):
        self.save()
        for fields in [dict(candidate_name='Changed'), dict(recommendations_html='<p>Extra time</p>'),
                       dict(document=(BytesIO(b'assessment'), 'assessment.pdf')), dict(remove_document='1')]:
            self.assertTrue(self.confirmation().json['completion']['complete'])
            revision = db.session.get(m.ExamSessionPenCandidate,self.key).revision
            with patch('app.pen_arrangements.trash_document'):
                response = self.save(revision=revision, **fields)
            self.assertEqual(response.status_code, 200, response.json)
            self.assertFalse(response.json['completion']['complete'])
            self.assertIsNone(m.ExamSessionPenControl.query.one().confirmed_at)
        self.confirmation()
        second_key = str(uuid.uuid4()); self.save(second_key)
        self.assertFalse(self.client.get(self.url).json['completion']['complete'])
        self.confirmation()
        revision = db.session.get(m.ExamSessionPenCandidate,self.key).revision
        self.client.post(self.url+'/'+self.key,data=dict(csrf_token='test',revision=revision,action='delete'))
        self.assertFalse(self.client.get(self.url).json['completion']['complete'])
        self.confirmation()
        result = self.client.post(self.url+'/'+second_key,data=dict(csrf_token='test',revision=1,action='delete'))
        self.assertEqual(result.json['completion']['count'], 0)
        self.assertFalse(result.json['completion']['complete'])
        self.assertEqual(self.confirmation().status_code, 400)

    def test_direct_model_edits_also_invalidate_the_verified_snapshot(self):
        self.save();self.confirmation()
        row=db.session.get(m.ExamSessionPenCandidate,self.key)
        row.recommendations_html='<p>Changed recommendations</p>';db.session.commit()
        self.assertFalse(self.client.get(self.url).json['completion']['complete'])

    def test_failed_edits_leave_completed_saved_arrangements_unchanged(self):
        self.save(document=(BytesIO(b'original'), 'report.pdf')); self.confirmation()
        self.assertEqual(self.save(revision=1,candidate_name='').status_code,400)
        self.assertTrue(self.client.get(self.url).json['completion']['complete'])
        with patch('app.pen_arrangements.trash_document', side_effect=DriveStorageError('Could not trash report.')):
            self.assertEqual(self.save(revision=1,document=(BytesIO(b'replace'), 'new.pdf')).status_code,503)
        self.assertTrue(self.client.get(self.url).json['completion']['complete'])

    def test_final_checks_and_pen_share_deadline_but_require_independent_confirmation(self):
        from app.routes import ensure_sinapsis_checklist_items
        from app.final_checks import final_checks_state
        from datetime import datetime, timezone
        self.save()
        control = m.ExamSessionSinapsisControl.query.filter_by(exam_session_id=self.record.id).first()
        if control is None:
            control = m.ExamSessionSinapsisControl(exam_session_id=self.record.id)
            db.session.add(control)
        control.return_materials_method='location_drop_off';control.return_drop_off_address_url='https://maps.example.com/return'
        ensure_sinapsis_checklist_items(control)
        for item in control.checklist_items:
            item.is_checked=True;item.checked_at=datetime.now(timezone.utc)
        db.session.commit()
        for format_name in ['Onsite','Online','Online at exam centre']:
            self.record.format=format_name;db.session.commit();self.confirmation(False)
            gate=final_checks_state(self.record)
            self.assertTrue(gate['checks_complete']);self.assertNotEqual(gate['progress'],'completed')
            action=next(action for action in gate['actions'] if 'candidates with PEN' in action['description'])
            self.assertEqual(action['department'],'MANAGEMENT')
            self.assertEqual(action['deadline'],gate['checks_deadline_badge']['date'])
            self.assertEqual(gate['pen_deadline_badge']['date'],gate['checks_deadline_badge']['date'])
            self.assertTrue(self.confirmation().json['completion']['complete'])
            gate=final_checks_state(self.record)
            self.assertEqual(gate['progress'],'completed')
            self.assertFalse(any('candidates with PEN' in action['description'] for action in gate['actions']))
        self.record.pen_enabled=False;db.session.commit()
        self.assertEqual(final_checks_state(self.record)['progress'],'completed')

    def test_management_my_actions_and_table_follow_candidate_and_completion_states(self):
        user=m.User(full_name='PEN Manager',email='penmanager@example.com',department='Management',is_active=True,is_superadmin=True,password_hash='test')
        db.session.add(user);db.session.commit()
        manager=self.app.test_client()
        with manager.session_transaction() as state:
            state.update(user=user.full_name,user_id=user.id,user_email=user.email,user_department='Management',csrf_token='test')
        def page():
            response=manager.get('/my-actions?session_year=2026&actions_section=sinapsis')
            self.assertEqual(response.status_code,200)
            return response.get_data(as_text=True)
        for format_name in ['Onsite','Online','Online at exam centre']:
            self.record.format=format_name;db.session.commit()
            self.assertIn('Complete exam arrangements for candidates with PEN',page())
        self.record.format='Onsite'
        if not m.ExamSessionExaminerAssignment.query.filter_by(exam_session_id=self.record.id,team_member_id=self.examiner.id).first():
            db.session.add(m.ExamSessionExaminerAssignment(exam_session_id=self.record.id,team_member_id=self.examiner.id,participation_status='Confirmed'))
        db.session.commit()
        response=self.save();self.assertEqual(response.status_code,200,response.json)
        self.assertIn('Finalise exam arrangements for candidates with PEN',page())
        self.assertNotIn('Complete exam arrangements for candidates with PEN',page())
        self.confirmation()
        self.assertNotIn('exam arrangements for candidates with PEN',page())
        self.save(revision=1,candidate_name='Review again')
        self.assertIn('Finalise exam arrangements for candidates with PEN',page())
        self.record.pen_enabled=False;db.session.commit()
        self.assertNotIn('exam arrangements for candidates with PEN',page())

    def test_designated_drive_folder_cannot_be_redirected(self):
        url = '/integrations/google/drive/folders/pen_assessment_reports'
        self.assertEqual(self.client.post(url, data=dict(csrf_token='test', folder_id='some-other-folder')).status_code, 400)
        self.assertEqual(self.client.post(url, data=dict(csrf_token='test', folder_id=FOLDER_ID)).status_code, 200)
        self.assertEqual(db.session.get(m.GoogleDriveDestination, 'pen_assessment_reports').folder_id, FOLDER_ID)

    def test_session_deletion_cleans_up_the_card_and_its_drive_report(self):
        self.save(document=(BytesIO(b'report'), 'report.pdf'))
        from app.routes import delete_exam_session_dependencies
        with patch('app.staff_invoices.trash_document') as trash:
            delete_exam_session_dependencies(self.record.id); db.session.commit()
            trash.assert_called_once()
        self.assertEqual(m.ExamSessionPenCandidate.query.count(), 0)

    def test_section_rendered_after_sinapsis_only_with_pen_for_all_formats(self):
        for format_name in ['Onsite', 'Online', 'Online at exam centre']:
            self.record.format = format_name; db.session.commit()
            base = '/pre-online-session-control-tower' if format_name != 'Onsite' else '/pre-session-control-tower'
            url = f'{base}?session_year=2026&session_modal={self.record.id}&open_schedule_modal={self.record.id}&sinapsis_only=1'
            response = self.client.get(url)
            self.assertEqual(response.status_code, 200)
            html = response.get_data(as_text=True)
            self.assertIn('Arrangements for candidates with PEN', html)
            self.assertLess(html.index('aria-label="Sinapsis checks"'), html.index('data-pen-section'))
            self.assertIn('data-pen-card-template', html)
            self.record.pen_enabled = False; db.session.commit()
            self.assertNotIn('data-pen-section', self.client.get(url).get_data(as_text=True))
            self.record.pen_enabled = True; db.session.commit()
