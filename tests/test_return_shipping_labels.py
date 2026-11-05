import unittest
import re
from datetime import date
from io import BytesIO
from unittest.mock import patch

from tests import test_google_drive as fixtures
from app import db
from app.models import (AcademicStaff, ExamSession, ExamSessionSupervisorAssignment,
                        ExamSessionExaminerAssignment, ExamSessionSinapsisControl, ReturnShippingLabel)
from app.final_checks import final_checks_state
from app.google_drive import DriveStorageError
from app.return_labels import FOLDER_ID


class ReturnShippingLabelsTest(unittest.TestCase):
    setUpBase = fixtures.GoogleDriveTest.setUpBase
    tearDownBase = fixtures.GoogleDriveTest.tearDownBase
    api = fixtures.GoogleDriveTest.api
    http = fixtures.GoogleDriveTest.http
    tearDown = fixtures.GoogleDriveTest.tearDown

    def setUp(self):
        fixtures.GoogleDriveTest.setUp(self)
        self.person = AcademicStaff(full_name='Label Recipient', status='Active', roles='Supervisor, Examiner')
        self.record = ExamSession(exam_session_name='Label exam session', category='Path School', status='Pending',
            session_date=date(2026,11,20), shifts='Morning', modules='Speaking', format='Onsite')
        db.session.add_all([self.person, self.record]); db.session.flush()
        self.assignment = ExamSessionSupervisorAssignment(exam_session_id=self.record.id,
            team_member_id=self.person.id, participation_status='Confirmed', is_shipment_recipient=True)
        db.session.add(self.assignment); db.session.commit()
        self.select('immediate_dispatch')

    def select(self, method, **fields):
        return self.client.post(f'/pre-session-control-tower/sessions/{self.record.id}/return-materials',
            data={'csrf_token':'test', 'return_materials_method':method, **fields})

    def endpoint(self, method='immediate_dispatch', record=None):
        return f'/pre-session-control-tower/sessions/{(record or self.record).id}/return-label/{method}'

    def upload(self, method='immediate_dispatch', **fields):
        return self.client.post(self.endpoint(method), data={'csrf_token':'test', 'previous_file_id':'',
            'document':(BytesIO(b'%PDF-1.7 shipping label'), 'shipping-label.pdf'), **fields})

    def control(self, record=None):
        return ExamSessionSinapsisControl.query.filter_by(exam_session_id=(record or self.record).id).one()

    def test_single_file_uses_designated_drive_folder_and_private_view(self):
        response = self.upload()
        self.assertEqual(response.status_code, 200, response.json)
        doc = ReturnShippingLabel.query.one()
        self.assertEqual(self.metadata[0]['parents'], [FOLDER_ID])
        self.assertEqual(self.parts, [b'%PDF-1.7 shipping label'])
        self.assertEqual(doc.filename, 'shipping-label.pdf')
        self.assertEqual(self.control().return_shipping_label_id, doc.file_id)
        self.assertTrue(final_checks_state(self.record)['return_complete'])
        self.assertEqual(self.client.get(response.json['document']['url']).data, b'private document')
        self.assertEqual(self.app.test_client().get(response.json['document']['url']).status_code, 302)
        self.assertEqual(self.upload(previous_file_id=doc.file_id).status_code, 409)
        self.assertEqual(ReturnShippingLabel.query.count(), 1)

    def test_delete_trashes_file_and_returns_to_pending_label_action(self):
        self.upload(); document = ReturnShippingLabel.query.one(); file_id = document.file_id
        with patch('app.return_labels.trash_document') as trash:
            response = self.client.post(self.endpoint(), data={'csrf_token':'test', 'action':'delete', 'previous_file_id':file_id})
        self.assertEqual(response.status_code, 200, response.json)
        self.assertEqual(trash.call_args.args[0].file_id, file_id)
        self.assertIsNone(self.control().return_shipping_label_id)
        self.assertEqual(ReturnShippingLabel.query.count(), 0)
        state = final_checks_state(self.record)
        self.assertFalse(state['return_complete'])
        self.assertIn(('ADMIN','Issue return shipping label'), [(a['department'],a['description']) for a in state['actions']])

    def test_failed_drive_trash_keeps_file_and_all_portal_references(self):
        self.upload(); file_id = self.control().return_shipping_label_id
        with patch('app.return_labels.trash_document', side_effect=DriveStorageError('Drive trash failed')):
            response = self.client.post(self.endpoint(), data={'csrf_token':'test', 'action':'delete', 'previous_file_id':file_id})
        self.assertEqual(response.status_code, 503)
        self.assertEqual(self.control().return_shipping_label_id, file_id)
        self.assertIsNotNone(db.session.get(ReturnShippingLabel, file_id))
        self.assertTrue(final_checks_state(self.record)['return_complete'])

    def peer(self):
        peer = ExamSession(exam_session_name='Combined label peer', category='Path School', status='Pending',
            session_date=self.record.session_date, shifts='Morning', modules='Speaking', format='Onsite')
        db.session.add(peer); db.session.flush()
        db.session.add_all([
            ExamSessionSupervisorAssignment(exam_session_id=peer.id, team_member_id=self.person.id,
                participation_status='Confirmed', is_shipment_recipient=True),
            ExamSessionExaminerAssignment(exam_session_id=peer.id, team_member_id=self.person.id, participation_status='Confirmed')])
        db.session.commit()
        self.assertEqual(self.select('combined_dispatch', save_combined_return_sessions='1',
            combined_return_session_ids=[str(peer.id)]).status_code, 200)
        return peer

    def test_combined_upload_is_shared_and_delete_from_peer_removes_every_reference(self):
        peer = self.peer()
        response = self.upload('combined_dispatch')
        self.assertEqual(response.status_code, 200, response.json)
        file_id = self.control().combined_return_shipping_label_id
        self.assertEqual(self.control(peer).combined_return_shipping_label_id, file_id)
        self.assertEqual(set(response.json['session_ids']), {self.record.id, peer.id})
        self.assertTrue(final_checks_state(self.record)['return_complete'])
        with patch('app.return_labels.trash_document') as trash:
            response = self.client.post(self.endpoint('combined_dispatch', peer), data={
                'csrf_token':'test', 'action':'delete', 'previous_file_id':file_id})
        self.assertEqual(response.status_code, 200, response.json)
        trash.assert_called_once()
        self.assertIsNone(self.control().combined_return_shipping_label_id)
        self.assertIsNone(self.control(peer).combined_return_shipping_label_id)
        self.assertEqual(ReturnShippingLabel.query.count(), 0)
        self.assertFalse(final_checks_state(self.record)['return_complete'])
        self.assertFalse(final_checks_state(peer)['return_complete'])

    def test_validation_permissions_and_stale_document_cannot_mutate_drive(self):
        before = len(self.metadata)
        self.assertEqual(self.client.post(self.endpoint(), data={'csrf_token':'test'}).status_code, 400)
        response = self.client.post(self.endpoint(), data={'csrf_token':'test', 'document':[
            (BytesIO(b'one'), 'one.pdf'), (BytesIO(b'two'), 'two.pdf')]})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(self.upload(csrf_token='bad').status_code, 403)
        self.assertEqual(self.upload(previous_file_id='stale-file').status_code, 409)
        self.assertEqual(len(self.metadata), before)
        self.assignment.participation_status = 'Pending'; db.session.commit()
        self.assertEqual(self.upload().status_code, 403)
        self.assertEqual(len(self.metadata), before)

    def test_links_are_rejected_and_widget_has_no_url_field(self):
        self.assertEqual(self.select('immediate_dispatch', return_materials_label_url='https://example.com/old').status_code, 400)
        html = self.client.get(f'/pre-session-control-tower?session_year=2026&view=sessions&session_modal={self.record.id}&open_schedule_modal={self.record.id}&sinapsis_only=1').get_data(as_text=True)
        self.assertIn('Upload shipping label for sealed return exam packages', html)
        self.assertNotIn('name="return_materials_label_url"', html)
        self.assertNotIn('name="combined_return_materials_label_url"', html)
        self.assertNotIn('Insert label link for sealed return exam packages:', html)
        self.assertEqual(html.count('data-return-label-file aria-label='), 2)

    def test_shipping_information_includes_current_session_and_two_column_lists(self):
        self.peer()
        html = self.client.get(f'/pre-session-control-tower?session_year=2026&view=sessions&session_modal={self.record.id}&open_schedule_modal={self.record.id}&sinapsis_only=1').get_data(as_text=True)
        boxes = re.findall(r'<div class="return-shipping-info".*?</div>', html, re.S)
        self.assertEqual(len(boxes), 2)
        self.assertIn('data-return-shipping-height>7 cm', boxes[0])
        self.assertIn('data-return-shipping-height>14 cm', boxes[1])
        for box in boxes:
            self.assertIn('SHIPPING INFORMATION', box)
            self.assertIn('class="return-shipping-dimensions"', box)
            self.assertIn('Length:</span> 26 cm', box)
            self.assertIn('Width:</span> 30 cm', box)
            self.assertIn('data-return-shipping-weight>1 kg', box)
            self.assertEqual(box.count('<li>'), 4)

    def test_database_failure_after_trash_restores_drive_file(self):
        self.upload(); file_id = self.control().return_shipping_label_id
        with patch('app.return_labels.trash_document'), patch('app.return_labels.restore_document') as restore, \
             patch.object(db.session(), 'commit', side_effect=RuntimeError('Database unavailable')):
            response = self.client.post(self.endpoint(), data={'csrf_token':'test', 'action':'delete', 'previous_file_id':file_id})
        self.assertEqual(response.status_code, 500)
        restore.assert_called_once_with(file_id)
        self.assertEqual(self.control().return_shipping_label_id, file_id)
