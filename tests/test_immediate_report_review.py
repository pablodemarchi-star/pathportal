import unittest
from datetime import timedelta
from unittest.mock import patch

from app import db, models as m
from app.staff_report_components import merge
from tests import test_staff_report_components as fixtures


class ImmediateReportReviewTest(unittest.TestCase):
    setUp = fixtures.StaffReportComponentsTest.setUp
    tearDown = fixtures.StaffReportComponentsTest.tearDown
    attendance_state = fixtures.StaffReportComponentsTest.attendance_state

    def create_case(self, kind='component', number='000012'):
        self.record.format = 'Online'
        self.record.modules = 'Listening and speaking,Reading and writing'
        db.session.commit()
        row = dict(number=number, name='Reported candidate', exam='B2 Competency', reason='Supervisor evidence')
        if kind == 'component':
            row['component'] = 'Listening'
        else:
            row['modules'] = ['Reading and writing']
        merge(self.record, [row], reason_field='component_reason' if kind == 'component' else 'it_reason')
        db.session.commit()
        self.attendance_state()
        return m.AbsenceCandidate.query.filter_by(number_key=number).one()

    def edit(self, candidate, field, value='', **extra):
        return self.client.post(f'/pre-session-control-tower/post/sessions/{self.record.id}/attendance',
            data=dict(csrf_token='test', action='candidate', candidate_id=candidate.id, field=field, value=value, **extra))

    def test_both_report_sources_can_be_completed_and_reviewed_on_exam_day(self):
        for kind, number in [('component', '000012'), ('it', '000013')]:
            with self.subTest(kind=kind), patch('app.post_attendance.local_today', return_value=self.record.session_date):
                candidate = self.create_case(kind, number)
                state = self.attendance_state().json['state']
                row = next(item for item in state['candidates'] if item['id'] == candidate.id)
                self.assertFalse(state['enabled'])
                self.assertFalse(state['documentation_enabled'])
                self.assertTrue(state['documentation_accessible'])
                self.assertTrue(row['edit_allowed'])
                self.assertTrue(row['review_allowed'])
                self.assertEqual(row['institution_name'], '')
                self.assertFalse(row['can_confirm'])
                self.assertFalse(row['can_decline'])
                for choice in ['Confirmed', 'Declined']:
                    self.assertEqual(self.edit(candidate, 'review', choice, reason='Reason').status_code, 400)
                result = self.edit(candidate, 'institution_name', 'Assigned school')
                self.assertEqual(result.status_code, 200, result.json)
                row = next(item for item in result.json['state']['candidates'] if item['id'] == candidate.id)
                self.assertTrue(row['can_decline'])
                self.assertFalse(row['can_confirm'], 'Credit is still required for confirmation')
                self.assertEqual(self.edit(candidate, 'name', 'Corrected candidate').status_code, 200)
                self.assertEqual(self.edit(candidate, 'number', number + '0').status_code, 200)
                self.assertEqual(self.edit(candidate, 'notes', 'Internal note').status_code, 200)
                self.assertEqual(self.edit(candidate, 'rescheduled_for', 'next_july_online').status_code, 200)
                self.assertEqual(self.edit(candidate, 'currency', 'ARS').status_code, 200)
                result = self.edit(candidate, 'credit_balance', '250')
                self.assertEqual(result.status_code, 200, result.json)
                row = next(item for item in result.json['state']['candidates'] if item['id'] == candidate.id)
                self.assertTrue(row['can_confirm'])
                result = self.edit(candidate, 'review', 'Confirmed', previous_file_id='')
                self.assertEqual(result.status_code, 200, result.json)
                self.assertFalse(result.json['state']['review_allowed'], 'The institutional review gate remains locked')
                self.assertFalse(result.json['state']['results_notification_enabled'])
                self.assertEqual(self.edit(candidate, 'name', 'Locked review').status_code, 400)
                result = self.edit(candidate, 'reopen', confirmed='1', previous_file_id='', previous_status='Confirmed')
                self.assertEqual(result.status_code, 200, result.json)
                self.assertEqual(self.edit(candidate, 'review', 'Declined', reason='').status_code, 400)
                result = self.edit(candidate, 'review', 'Declined', reason='Not accepted', previous_file_id='')
                self.assertEqual(result.status_code, 200, result.json)
                self.assertEqual(candidate.review_status, 'Declined')

    def test_report_exception_does_not_unlock_institutional_candidates_or_other_steps(self):
        with patch('app.post_attendance.local_today', return_value=self.record.session_date):
            reported = self.create_case()
            document = m.AttendanceDocument(file_id='institutional-proof', folder_id='folder', filename='proof.pdf', mime_type='application/pdf')
            db.session.add(document)
            institutional = m.AbsenceCandidate(exam_session_id=self.record.id, institution_id=reported.institution_id,
                number='0022', number_key='0022', name='Institutional candidate', institution_name='School', document=document)
            db.session.add(institutional); db.session.commit()
            state = self.attendance_state().json['state']
            row = next(item for item in state['candidates'] if item['id'] == institutional.id)
            self.assertFalse(row['edit_allowed']); self.assertFalse(row['review_allowed'])
            self.assertEqual(self.edit(institutional, 'name', 'Forbidden').status_code, 403)
            self.assertEqual(self.client.post(f'/pre-session-control-tower/post/sessions/{self.record.id}/attendance',
                data=dict(csrf_token='test', action='verified', value='1')).status_code, 403)
        with patch('app.post_attendance.local_today', return_value=self.record.session_date + timedelta(days=1)):
            self.assertEqual(self.edit(institutional, 'name', 'Still blocked').status_code, 400)
            self.assertEqual(self.edit(reported, 'institution_name', 'School').status_code, 200)

    def test_every_required_identity_and_evidence_field_is_required_for_both_decisions(self):
        candidate = self.create_case('it')
        self.assertEqual(self.edit(candidate, 'institution_name', 'School').status_code, 200)
        for field, empty in [('number', ''), ('name', ''), ('institution_name', ''), ('exam', ''), ('absent_modules', '[]')]:
            original = getattr(candidate, field)
            setattr(candidate, field, empty); db.session.commit()
            for choice in ['Confirmed', 'Declined']:
                result = self.edit(candidate, 'review', choice, reason='Not accepted', previous_file_id='')
                self.assertEqual(result.status_code, 400, (field, choice, result.json))
            setattr(candidate, field, original); db.session.commit()
        self.assertEqual(self.edit(candidate, 'review', 'Declined', reason='Not accepted', previous_file_id='').status_code, 200)

    def test_new_report_has_no_institution_field_and_existing_assignment_is_preserved(self):
        candidate = self.create_case()
        self.assertEqual(self.edit(candidate, 'institution_name', 'Keep this school').status_code, 200)
        institution_id = candidate.institution_id
        merge(self.record, [dict(number=candidate.number, name=candidate.name, exam=candidate.exam,
            component='Listening', reason='Updated explanation', institution='Ignored report institution')])
        db.session.commit()
        self.assertEqual(candidate.institution_name, 'Keep this school')
        self.assertEqual(candidate.institution_id, institution_id)
        page = self.client.get(f'/my-exam-sessions/{self.share.token}').get_data(as_text=True)
        self.assertNotIn('data-component-field="institution"', page)
        self.assertEqual(m.AbsenceCandidate.query.count(), 1)

    def test_pending_incidents_block_absence_notifications_until_all_are_reviewed(self):
        component = self.create_case('component', '000012')
        it_case = self.create_case('it', '000013')
        initial = self.attendance_state().json['state']
        self.assertEqual(initial['pending_supervisor_reviews'], 2)
        self.assertEqual(initial['steps']['notifications']['detail'], 'Verify the absence records first.')
        for candidate in [component, it_case]:
            self.assertEqual(self.edit(candidate, 'institution_name', 'Assigned school').status_code, 200)
        school = db.session.get(m.AttendanceInstitution, component.institution_id)
        absence_list = m.AttendanceDocument(file_id='incident-list', folder_id='folder', filename='list.pdf', mime_type='application/pdf')
        certificate = m.AttendanceDocument(file_id='institution-proof', folder_id='folder', filename='proof.pdf', mime_type='application/pdf')
        db.session.add_all([absence_list, certificate])
        db.session.flush()
        db.session.add(m.AttendanceModule(institution_id=school.id, module='Reading and writing', document_id=absence_list.file_id))
        institutional = m.AbsenceCandidate(exam_session_id=self.record.id, institution_id=school.id, institution_name=school.name,
            number='000014', number_key='000014', name='Institutional candidate', document_id=certificate.file_id)
        db.session.add_all([institutional, m.ExamSessionJourneyShare(exam_session_id=self.record.id,
            audience='external', token='incident-notification-share', is_enabled=True)])
        control = db.session.get(m.PostAttendance, self.record.id)
        control.submission_status = 'completed'
        control.verified = True
        it_case.rescheduled_for = str(self.record.id)
        db.session.commit()
        endpoint = f'/pre-session-control-tower/post/sessions/{self.record.id}/attendance'
        def sent(value='1'):
            return self.client.post(endpoint, data=dict(csrf_token='test', action='sent', institution_id=school.id, key='external', value=value))
        state = self.attendance_state().json['state']
        self.assertFalse(state['notifications_enabled'])
        self.assertTrue(state['documentation_accessible'])
        self.assertIn('Review all online examination incidents', state['steps']['notifications']['detail'])
        actions = next(card for card in state['institutions'] if card['id'] == str(school.id))['notification_actions']
        self.assertTrue(all(action['disabled_reason'] and not action['message'] and not action['url'] for action in actions))
        self.assertEqual(sent().status_code, 400, 'Direct POSTs cannot bypass the disabled controls')
        self.assertEqual(self.edit(component, 'review', 'Declined', reason='Not accepted', previous_file_id='').status_code, 200)
        self.assertEqual(self.attendance_state().json['state']['pending_supervisor_reviews'], 1)
        self.assertEqual(sent().status_code, 400)
        result = self.edit(it_case, 'review', 'Confirmed', previous_file_id='')
        self.assertEqual(result.status_code, 200, result.json)
        state = result.json['state']
        self.assertEqual(state['pending_supervisor_reviews'], 0)
        self.assertTrue(state['notifications_enabled'])
        self.assertEqual(institutional.review_status, 'Pending', 'Institution-only cases do not keep the incident warning active')
        actions = next(card for card in state['institutions'] if card['id'] == str(school.id))['notification_actions']
        self.assertTrue(all(not action['disabled_reason'] and action['message'] for action in actions))
        self.assertEqual(sent().status_code, 200)
        result = self.edit(component, 'reopen', confirmed='1', previous_file_id='', previous_status='Declined')
        self.assertEqual(result.status_code, 200, result.json)
        state = result.json['state']
        self.assertEqual(state['pending_supervisor_reviews'], 1)
        self.assertFalse(state['notifications_enabled'])
        self.assertTrue(state['documentation_accessible'])
        self.assertTrue(next(row for row in state['candidates'] if row['id'] == component.id)['edit_allowed'])
        self.assertEqual(sent().status_code, 400)
        self.assertEqual(sent('0').status_code, 400)

    def test_incident_notification_block_only_applies_to_online(self):
        self.create_case()
        for format_name, pending in [('Online', 1), ('Online at exam centre', 0), ('Onsite', 0)]:
            self.record.format = format_name
            db.session.commit()
            self.assertEqual(self.attendance_state().json['state']['pending_supervisor_reviews'], pending, format_name)
