import json
import re
import unittest
from html import unescape

from tests import test_staff_portal_logistics as fixtures
from app import db
from app.models import (ExamSessionInternAssignment, ExamSessionExaminerAssignment,
                        ExamSessionLogisticsConcept, StaffExamSessionsShare)
from app.routes import assignment_currency_totals, build_staff_payment_rows, logistics_enabled_for_session
from app.staffing_rules import normalize_existing_interns, normalize_existing_online_travel_fees


class InternPortalTest(unittest.TestCase):
    setUp = fixtures.StaffPortalLogisticsTest.setUp
    tearDown = fixtures.StaffPortalLogisticsTest.tearDown
    add = fixtures.StaffPortalLogisticsTest.add

    def intern(self):
        assignment = ExamSessionInternAssignment(exam_session_id=self.record.id, team_member_id=self.person.id,
            participation_status='Pre-confirmed', staffing_role_check_verified=True,
            role_fee='ARS 25000', commuting='ARS 500', device_dep='ARS 100', km=50)
        db.session.add(assignment)
        db.session.commit()
        return assignment

    def details(self, client, url):
        html = client.get(url).get_data(as_text=True)
        article = re.search(r'<article class="staff-detail-assignment".*?</article>', html, re.S).group(0)
        payload = json.loads(unescape(re.search(r"data-staff-session-payload='([^']*)'", article).group(1)))
        return html, article, payload

    def test_intern_can_accept_in_all_formats_without_fees_or_logistics_folder(self):
        assignment = self.intern()
        for session_format in ('Onsite', 'Online', 'Online at exam centre'):
            with self.subTest(format=session_format):
                self.record.format = session_format
                assignment.participation_status = 'Pre-confirmed'
                db.session.commit()
                self.assertTrue(assignment.logistics_enabled)
                self.assertTrue(logistics_enabled_for_session(self.record.id))
                response = self.add('intern', assignment.id)
                self.assertEqual(response.status_code, 200, response.json)
                public = self.app.test_client()
                html, article, payload = self.details(public, response.json['url'])
                self.assertIn('Instructions will be available soon', article)
                self.assertIn('In progress', article)
                self.assertIn('Your session team', article)
                self.assertNotIn('Travel and logistics', article)
                self.assertNotIn('Open logistics folder', article)
                self.assertNotIn('Your fees', article)
                self.assertNotIn('Your exam session fees', html)
                self.assertEqual(payload['fee_lines'], [])
                self.assertEqual(payload['total_fee'], '')
                self.assertIn('15 minutes before' if session_format == 'Online' else '50 minutes before', article)
                result = public.post(payload['confirmation_url'], data={'csrf_token': payload['confirmation_csrf']})
                self.assertEqual(result.status_code, 303)
                db.session.refresh(assignment)
                self.assertEqual(assignment.participation_status, 'Confirmed')
                confirmed_html = public.get(response.json['url']).get_data(as_text=True)
                self.assertNotIn('Your exam session fees', confirmed_html)

    def test_intern_can_decline(self):
        assignment = self.intern()
        response = self.add('intern', assignment.id)
        public = self.app.test_client()
        _, _, payload = self.details(public, response.json['url'])
        result = public.post(payload['decline_url'], data={'csrf_token': payload['confirmation_csrf'], 'reconfirmed': '1'})
        self.assertEqual(result.status_code, 303)
        db.session.refresh(assignment)
        self.assertIsNone(assignment.team_member_id)
        self.assertFalse(assignment.logistics_enabled)

    def test_only_assigned_instructions_are_shown_and_progress_updates_live(self):
        assignment = self.intern()
        first = ExamSessionLogisticsConcept(exam_session_id=self.record.id, status='Confirmed',
            instructions_title='Arrival', instructions_html='<p><strong>Meet the supervisor</strong></p>', staff_members=[self.person])
        second = ExamSessionLogisticsConcept(exam_session_id=self.record.id, status='Pending',
            instructions_title='Afterwards', instructions_html='<p>Help with packing</p>', staff_members=[self.person])
        unrelated = ExamSessionLogisticsConcept(exam_session_id=self.record.id, status='Pending',
            instructions_title='Private instructions', instructions_html='<p>Other staff only</p>')
        db.session.add_all([first, second, unrelated]); db.session.commit()
        response = self.add('intern', assignment.id)
        public = self.app.test_client()
        _, article, payload = self.details(public, response.json['url'])
        self.assertIn('<h4>Arrival</h4>', article)
        self.assertIn('<strong>Meet the supervisor</strong>', article)
        self.assertIn('<h4>Afterwards</h4>', article)
        self.assertNotIn('Other staff only', article)
        self.assertEqual(payload['logistics_progress'], 'In progress')
        second.status = 'Confirmed'; first.instructions_html = '<p>Updated meeting point</p>'
        db.session.commit()
        _, article, payload = self.details(public, response.json['url'])
        self.assertEqual(payload['logistics_progress'], 'Confirmed')
        self.assertIn('Updated meeting point', article)
        self.assertIn('staff-detail-logistics-progress is-confirmed', article)

    def test_legacy_and_future_intern_fees_are_removed_without_affecting_paid_roles(self):
        assignment = self.intern()
        examiner = ExamSessionExaminerAssignment(exam_session_id=self.record.id, team_member_id=self.person.id,
            participation_status='Confirmed', role_fee='ARS 10000', role_fee_currency='ARS')
        db.session.add(examiner); db.session.commit()
        ExamSessionInternAssignment.query.filter_by(id=assignment.id).update({'role_fee': 'ARS 90000', 'km': 80}, synchronize_session=False)
        db.session.commit(); db.session.expire_all()
        self.assertFalse(any(assignment_currency_totals(assignment).values()))
        normalize_existing_interns()
        db.session.refresh(assignment)
        self.assertIsNone(assignment.role_fee)
        self.assertIsNone(assignment.km)
        rows = build_staff_payment_rows(2026)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['total_label'], '10000')
        assignment.role_fee = 'ARS 20000'; db.session.commit()
        self.assertIsNone(assignment.role_fee)
        self.assertEqual(examiner.role_fee, 'ARS 10000')

    def test_intern_card_has_time_without_fees_or_kilometres(self):
        assignment = self.intern()
        html = self.client.get('/exam-session-planner?session_year=2026').get_data(as_text=True)
        cards = re.findall(r'<article class="staff-assignment-card".*?</article>', html, re.S)
        card = next(card for card in cards if 'data-section-key="intern"' in card and f'data-assignment-id="{assignment.id}"' in card)
        self.assertIn('<h4>Time</h4>', card)
        self.assertNotIn('data-km-field', card)
        self.assertNotIn('staff-card-fees-block', card)
        self.assertIn('data-logistics-control', card)

    def test_planner_can_add_intern_before_instructions_exist(self):
        response = self.client.post(f'/exam-session-planner/sessions/{self.record.id}/members', data={
            'csrf_token': 'test', 'session_year': '2026', 'modal_action': 'save',
            'intern_row_keys': 'new-1', 'intern_team_member_id_new-1': str(self.person.id),
            'intern_participation_status_new-1': 'Pending',
            'intern_start_time_new-1': '09:00', 'intern_end_time_new-1': '12:00',
            'intern_role_fee_new-1': 'ARS 5000', 'intern_km_new-1': '90',
        }, headers={'Accept': 'application/json'})
        self.assertEqual(response.status_code, 200, response.json)
        assignment = ExamSessionInternAssignment.query.one()
        self.assertTrue(assignment.logistics_enabled)
        self.assertEqual(assignment.logistics_type, '')
        self.assertIsNone(assignment.role_fee)
        self.assertIsNone(assignment.km)
        self.assertEqual(assignment.start_time, '09:00')

    def test_intern_logistics_choice_is_preserved_in_all_formats(self):
        assignment = self.intern()
        key = f'existing-{assignment.id}'
        for session_format in ('Onsite', 'Online', 'Online at exam centre'):
            self.record.format = session_format
            db.session.commit()
            for value in ('', 'Does not apply', 'Uber ride', 'Carpooling', 'Complex logistics'):
                with self.subTest(format=session_format, choice=value):
                    response = self.client.post(f'/exam-session-planner/sessions/{self.record.id}/members', data={
                        'csrf_token': 'test', 'session_year': '2026', 'modal_action': 'save',
                        'intern_row_keys': key, f'intern_assignment_id_{key}': str(assignment.id),
                        f'intern_team_member_id_{key}': str(self.person.id),
                        f'intern_logistics_type_{key}': value,
                        f'intern_logistics_enabled_{key}': '1',
                        f'intern_start_time_{key}': '09:00', f'intern_end_time_{key}': '12:00',
                    }, headers={'Accept': 'application/json'})
                    self.assertEqual(response.status_code, 200, response.json)
                    db.session.refresh(assignment)
                    self.assertEqual(assignment.logistics_type, value)
                    self.assertTrue(assignment.logistics_enabled)
                    normalize_existing_interns()
                    normalize_existing_online_travel_fees()
                    db.session.refresh(assignment)
                    self.assertEqual(assignment.logistics_type, value)
