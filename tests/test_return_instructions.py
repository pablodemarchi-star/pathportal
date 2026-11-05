import unittest

from tests import test_final_checks_workflow as fixtures
from app import db
from app.models import ExamSession, ExamSessionSupervisorAssignment, ExamSessionExaminerAssignment, ExamSessionSinapsisControl


class ReturnInstructionsTest(unittest.TestCase):
    setUp = fixtures.FinalChecksWorkflowTest.setUp
    tearDown = fixtures.FinalChecksWorkflowTest.tearDown
    login_client = fixtures.FinalChecksWorkflowTest.login_client
    assign = fixtures.FinalChecksWorkflowTest.assign
    control = fixtures.FinalChecksWorkflowTest.control
    modal = fixtures.FinalChecksWorkflowTest.modal
    return_post = fixtures.FinalChecksWorkflowTest.return_post

    def save(self, text='', title='', record=None, **fields):
        return self.login_client().post(f'/pre-session-control-tower/sessions/{(record or self.session_record).id}/return-instructions',
            data={'csrf_token':'token', 'instructions':text, 'title':title, **fields})

    def peer(self, assignment):
        record = ExamSession(exam_session_name='Return instructions peer', category='Path School', status='Pending',
            session_date=self.session_record.session_date, shifts='Morning', modules='Speaking', format='Onsite')
        db.session.add(record); db.session.flush()
        db.session.add_all([
            ExamSessionSupervisorAssignment(exam_session_id=record.id, team_member_id=assignment.team_member_id,
                participation_status='Confirmed', is_shipment_recipient=True),
            ExamSessionExaminerAssignment(exam_session_id=record.id, team_member_id=assignment.team_member_id,
                participation_status='Confirmed')])
        db.session.commit()
        return record

    def peer_control(self, record):
        return ExamSessionSinapsisControl.query.filter_by(exam_session_id=record.id).one()

    def test_chip_uses_shared_editor_and_sanitised_optional_instructions(self):
        self.assign(); control = self.control()
        html = self.modal()
        self.assertIn('Instructions (<em>empty</em>)', html)
        self.assertEqual(html.count('id="logistics-instructions-dialog"'), 1)
        self.assertIn('Return instructions', html)
        response = self.save('<p><strong>Pack securely</strong><script>alert(1)</script></p>', 'Return packing')
        self.assertEqual(response.status_code, 200, response.json)
        self.assertIn('<strong>Pack securely</strong>', control.return_instructions_html)
        self.assertNotIn('<script>', control.return_instructions_html)
        self.assertEqual(control.return_instructions_title, 'Return packing')
        self.assertIn('Instructions (<em>added</em>)', self.modal())
        self.assertEqual(self.save().status_code, 200)
        self.assertEqual(control.return_instructions_html, '')
        self.assertIn('Instructions (<em>empty</em>)', self.modal())

    def shared_case(self, method):
        assigned = self.assign(); control = self.control(); peer = self.peer(assigned)
        self.save('<p>Original return instructions</p>', 'Original title')
        result = self.return_post(return_materials_method=method, save_combined_return_sessions='1', combined_return_session_ids=[str(peer.id)])
        self.assertEqual(result.status_code, 200, result.json)
        other = self.peer_control(peer)
        self.assertEqual(other.return_instructions_html, control.return_instructions_html)
        self.assertEqual(result.json['return_instructions']['html'], control.return_instructions_html)
        response = self.save('<p><em>Updated shared instructions</em></p>', 'Updated title', record=peer)
        self.assertEqual(response.status_code, 200, response.json)
        self.assertEqual(set(response.json['session_ids']), {peer.id, self.session_record.id})
        db.session.refresh(control)
        self.assertEqual(control.return_instructions_html, other.return_instructions_html)
        self.assertEqual(control.return_instructions_title, 'Updated title')
        self.assertEqual(self.save(record=peer).status_code, 200)
        db.session.refresh(control)
        self.assertEqual(control.return_instructions_html, '')
        self.assertEqual(other.return_instructions_html, '')

    def test_combined_dispatch_instructions_are_shared_and_deleted_from_every_session(self):
        self.shared_case('combined_dispatch')

    def test_combined_drop_off_instructions_are_shared_and_deleted_from_every_session(self):
        self.shared_case('combined_location_drop_off')

    def test_pending_recipient_csrf_and_length_validation_cannot_change_instructions(self):
        assigned = self.assign('Pending'); control = self.control()
        self.assertEqual(self.save('<p>Blocked</p>').status_code, 403)
        assigned.participation_status = 'Confirmed'; db.session.commit()
        self.assertEqual(self.save('<p>Bad CSRF</p>', csrf_token='wrong').status_code, 403)
        self.assertEqual(self.save('x' * 50001).status_code, 400)
        self.assertEqual(self.save('Valid text', title='x' * 201).status_code, 400)
        self.assertEqual(control.return_instructions_html, '')

    def test_detached_session_keeps_its_copy_and_stops_receiving_shared_edits(self):
        assigned = self.assign(); self.control(); peer = self.peer(assigned)
        self.return_post(return_materials_method='combined_dispatch', save_combined_return_sessions='1', combined_return_session_ids=[str(peer.id)])
        self.save('<p>Shared before detaching</p>')
        response = self.login_client().post(f'/pre-session-control-tower/sessions/{peer.id}/return-materials',
            data={'csrf_token':'token', 'return_materials_method':'immediate_dispatch', 'confirm_return_method_change':'1'})
        self.assertEqual(response.status_code, 200, response.json)
        previous = self.peer_control(peer).return_instructions_html
        self.save('<p>Only the original session</p>')
        self.assertEqual(self.peer_control(peer).return_instructions_html, previous)

    def test_conflicting_notes_are_not_silently_overwritten_when_combining(self):
        assigned = self.assign(); control = self.control(); peer = self.peer(assigned)
        self.save('<p>Session A instructions</p>')
        self.save('<p>Session B instructions</p>', record=peer)
        result = self.return_post(return_materials_method='combined_dispatch', save_combined_return_sessions='1', combined_return_session_ids=[str(peer.id)])
        self.assertEqual(result.status_code, 400)
        db.session.refresh(control)
        self.assertIn('Session A', control.return_instructions_html)
        self.assertIn('Session B', self.peer_control(peer).return_instructions_html)
