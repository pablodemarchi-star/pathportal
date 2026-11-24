import json
import re
import unittest
from unittest.mock import patch
from flask import Response
from app import db, models as m
from app.staff_return_materials import return_view
from tests import test_staff_portal_logistics as fixtures


class StaffReturnMaterialsTest(unittest.TestCase):
    setUp = fixtures.StaffPortalLogisticsTest.setUp
    tearDown = fixtures.StaffPortalLogisticsTest.tearDown

    def assign(self, role='examiner', status='Confirmed', person=None, token='return-portal'):
        person = person or self.person
        model = {'supervisor': m.ExamSessionSupervisorAssignment, 'examiner': m.ExamSessionExaminerAssignment, 'intern': m.ExamSessionInternAssignment}[role]
        assignment = model(exam_session_id=self.record.id, team_member_id=person.id,
            participation_status=status, is_shipment_recipient=True, logistics_type='Does not apply')
        share = m.StaffExamSessionsShare.query.filter_by(person_ref=str(person.id)).first()
        if share is None:
            share = m.StaffExamSessionsShare(person_ref=str(person.id), token=token)
            db.session.add(share)
        db.session.add(assignment); db.session.flush()
        db.session.add(m.StaffExamSessionSubmission(share_id=share.id, exam_session_id=self.record.id,
            assignment_type=role, assignment_id=assignment.id))
        db.session.commit()
        return assignment, share

    def control(self, method=None):
        control = m.ExamSessionSinapsisControl.query.filter_by(exam_session_id=self.record.id).first()
        if control is None:
            control = m.ExamSessionSinapsisControl(exam_session_id=self.record.id)
            db.session.add(control)
        control.return_materials_method = method
        db.session.commit()
        return control

    def page(self, token='return-portal'):
        response = self.app.test_client().get('/my-exam-sessions/' + token)
        self.assertEqual(response.status_code, 200)
        return response.get_data(as_text=True)

    def section(self, page):
        return re.search(r'<section class="staff-detail-material staff-return-materials".*?</section>', page, re.S).group(0)

    def test_return_only_for_confirmed_marked_assignment_of_any_role(self):
        previous = None
        for role in ['examiner', 'supervisor', 'intern']:
            if previous:
                previous.is_shipment_recipient = False
            assignment, share = self.assign(role, status='Pre-confirmed')
            for status in ['Pre-confirmed', 'Confirmed']:
                assignment.participation_status = status; db.session.commit()
                page = self.page()
                self.assertEqual(page.count('data-staff-return-materials>'), 1 if status == 'Confirmed' else 0)
                self.assertEqual(page.count('data-staff-return-open '), 1 if status == 'Confirmed' else 0)
                if status == 'Confirmed':
                    self.assertIn('title="Return of exam materials · Pending"', page)
                    self.assertIn(f'data-staff-return-role="{role}"', page)
                    self.assertIn('>📦 Return of exam materials</a>', page)
                    name_cell = re.search(r'<td data-label="Exam session">(.*?)</td>', page, re.S).group(1)
                    self.assertNotIn('data-staff-return-open', name_cell)
                    self.assertIn('>Actions</th>', page)
                else:
                    self.assertNotIn('Read important instructions', page)
                    continue
                section = self.section(page)
                self.assertIn('📦 Return of exam materials', section)
                self.assertIn('>Pending</span>', section)
                self.assertIn('Return instructions are being prepared', section)
                self.assertIn('<strong>ensure that all examination materials are securely returned to Path Examinations</strong>', section)
                self.assertNotIn('Read important instructions', section)
            previous = assignment

    def test_drop_off_handover_instructions_and_pending_recipient_review(self):
        assignment, share = self.assign()
        control = self.control('location_drop_off')
        control.return_drop_off_address_url = 'https://maps.example.com/return'
        control.return_instructions_title = 'Packing requirements'
        control.return_instructions_html = '<p><strong>Seal all packages.</strong></p><script>bad()</script>'
        db.session.commit()
        section = self.section(self.page())
        self.assertIn('>Completed</span>', section)
        self.assertIn('title="Return of exam materials · Completed"', self.page())
        self.assertIn('Immediate location drop-off', section)
        self.assertIn('href="https://maps.example.com/return" target="_blank"', section)
        self.assertIn('Read important instructions', section)
        self.assertIn('<strong>Seal all packages.</strong>', section)
        self.assertNotIn('<script>', section)
        control.return_review_required = True; db.session.commit()
        section = self.section(self.page())
        self.assertIn('>Pending</span>', section)
        self.assertNotIn('href="https://maps.example.com/return"', section)
        self.assertIn('Read important instructions', section)
        recipient = m.AcademicStaff(full_name='Handover colleague', status='Active', phone='+54 11 1234 5678')
        db.session.add(recipient); db.session.flush()
        control.return_review_required = False
        control.return_materials_method = 'staff_handover'; control.return_handover_staff_id = recipient.id
        db.session.commit()
        section = self.section(self.page())
        self.assertIn('>Completed</span>', section)
        self.assertIn('Handover colleague', section)
        self.assertIn('+54 11 1234 5678', section)
        self.assertNotIn('View drop-off address', section)

    def test_shipping_label_uses_token_scoped_access_and_revokes_old_recipient(self):
        assignment, share = self.assign(status='Pre-confirmed')
        control = self.control('immediate_dispatch')
        label = m.ReturnShippingLabel(file_id='return-private-file', destination_key='return_shipping_labels', filename='label.pdf', mime_type='application/pdf')
        db.session.add(label); control.return_shipping_label = label
        db.session.commit()
        url = f'/my-exam-sessions/{share.token}/sessions/{self.record.id}/return-label'
        self.assertEqual(self.app.test_client().get(url).status_code, 404)
        self.assertNotIn('data-staff-return-materials>', self.page())
        assignment.participation_status = 'Confirmed'
        db.session.commit()
        section = self.section(self.page())
        url = f'/my-exam-sessions/{share.token}/sessions/{self.record.id}/return-label'
        self.assertIn('>Completed</span>', section)
        self.assertIn(url, section)
        self.assertNotIn('/return-labels/', section)
        self.assertIn('Height: 7 cm', section)
        anonymous = self.app.test_client()
        with patch('app.google_drive.stream_document', return_value=Response(b'label', mimetype='application/pdf')) as stream:
            self.assertEqual(anonymous.get(url).status_code, 200)
            self.assertEqual(stream.call_args.args[0].file_id, label.file_id)
            self.assertEqual(anonymous.get(url.replace(share.token, 'wrong-token')).status_code, 404)
            other = m.AcademicStaff(full_name='Other member', status='Active')
            db.session.add(other); db.session.flush()
            other_assignment, other_share = self.assign(person=other, token='other-return')
            other_assignment.is_shipment_recipient = False; db.session.commit()
            self.assertEqual(anonymous.get(url.replace(share.token, other_share.token)).status_code, 404)
            self.assertNotIn('data-staff-return-materials>', self.page(other_share.token))
            self.assertNotIn('data-staff-return-open ', self.page(other_share.token))
            assignment.is_shipment_recipient = False
            other_assignment.is_shipment_recipient = True
            db.session.commit()
            self.assertEqual(anonymous.get(url).status_code, 404)
            self.assertNotIn('data-staff-return-materials>', self.page())

    def test_combined_configuration_uses_management_selection_and_label(self):
        assignment, share = self.assign('supervisor')
        control = self.control('combined_dispatch')
        peer = m.ExamSession(exam_session_name='Combined peer', category='Path School', status='Pending',
            session_date=self.record.session_date, shifts='Morning', modules='Speaking', format='Onsite')
        db.session.add(peer); db.session.flush()
        label = m.ReturnShippingLabel(file_id='combined-label', destination_key='return_shipping_labels', filename='combined.pdf', mime_type='application/pdf')
        db.session.add(label); control.combined_return_shipping_label = label
        control.combined_return_session_ids_json = json.dumps([peer.id])
        db.session.commit()
        with self.app.test_request_context(), patch('app.routes.combined_return_session_options', return_value=[peer]), patch('app.routes.combined_return_examiner_confirmed', return_value=True):
            info = return_view(self.record, assignment, share)
            self.assertEqual(info['status'], 'Completed')
            self.assertEqual(info['sessions'][0]['name'], 'Combined peer')
            self.assertEqual(info['shipping']['height'], 14)
            control.return_materials_method = 'combined_location_drop_off'
            control.combined_return_drop_off_address_url = 'https://maps.example.com/shared'
            info = return_view(self.record, assignment, share)
            self.assertEqual(info['status'], 'Completed')
            self.assertEqual(info['address_url'], 'https://maps.example.com/shared')
            self.assertEqual(info['label_url'], '')
        db.session.rollback()
