import unittest
from datetime import date, datetime, timezone
from unittest.mock import patch
from flask import template_rendered
from app import db, models as m
from tests import test_staff_portal_logistics as fixtures


class StaffSessionDatesTest(unittest.TestCase):
    setUp = fixtures.StaffPortalLogisticsTest.setUp
    tearDown = fixtures.StaffPortalLogisticsTest.tearDown

    def create_sessions(self, pending=False):
        share = m.StaffExamSessionsShare(person_ref=str(self.person.id), token='session-dates')
        db.session.add(share); db.session.flush()
        records = []
        for day in [20, 10, 15]:
            record = m.ExamSession(exam_session_name=f'Date {day}', category='Path School', status='Pending', session_date=date(2026, 11, day), shifts='Morning', modules='Speaking', format='Onsite',
                emergency_contact_member_id=self.person.id, emergency_contact_participation_status='Confirmed')
            db.session.add(record); db.session.flush()
            examiner = m.ExamSessionExaminerAssignment(exam_session_id=record.id, team_member_id=self.person.id, participation_status='Pending' if pending else 'Confirmed', logistics_type='Does not apply')
            remote = m.ExamSessionSupervisorAssignment(exam_session_id=record.id, team_member_id=self.person.id, participation_status='Confirmed', is_remote=True, logistics_type='Does not apply')
            db.session.add_all([examiner, remote]); db.session.flush()
            for role, key in [('examiner', examiner.id), ('supervisor', remote.id), ('emergency_contact', record.id)]:
                db.session.add(m.StaffExamSessionSubmission(share_id=share.id, exam_session_id=record.id, assignment_type=role, assignment_id=key))
            records.append(record)
        db.session.commit()
        return records

    def page(self, instant):
        contexts = []
        def capture(sender, template, context, **extra):
            contexts.append(context)
        with template_rendered.connected_to(capture, self.app), patch('app.routes.datetime', wraps=datetime) as clock:
            clock.now.side_effect = lambda tz=None: instant.astimezone(tz) if tz else instant.replace(tzinfo=None)
            response = self.client.get('/my-exam-sessions/session-dates')
        self.assertEqual(response.status_code, 200)
        return response.get_data(as_text=True), contexts[-1]

    def test_all_tables_keep_current_first_then_past_in_ascending_date_order(self):
        self.create_sessions()
        html, context = self.page(datetime(2026, 11, 16, 12, tzinfo=timezone.utc))
        for group in ['confirmed_regular_sessions', 'confirmed_remote_sessions', 'confirmed_emergency_sessions']:
            self.assertEqual([row.session_date.day for row in context[group]], [20, 10, 15], group)
        self.assertEqual([row['session'].session_date.day for row in context['fee_rows']], [20]*3 + [10]*3 + [15]*3)
        self.assertEqual(context['portal_today'], date(2026, 11, 16))
        self.assertIn('data-staff-session-date="2026-11-10" class="is-past-session"', html)
        self.assertNotIn('data-staff-session-date="2026-11-20" class="is-past-session"', html)
        self.assertIn('js/staff_session_dates.js', html)

    def test_switches_at_argentina_midnight_after_session_and_restores_original_order(self):
        self.create_sessions()
        for instant, days in [
            (datetime(2026, 11, 16, 2, 59, 59, tzinfo=timezone.utc), [15, 20, 10]),
            (datetime(2026, 11, 16, 3, 0, tzinfo=timezone.utc), [20, 10, 15]),
            (datetime(2026, 11, 21, 3, 0, tzinfo=timezone.utc), [10, 15, 20]),
            (datetime(2026, 11, 10, 3, 0, tzinfo=timezone.utc), [10, 15, 20]),
        ]:
            with self.subTest(instant=instant):
                _, context = self.page(instant)
                self.assertEqual([record.session_date.day for record in context['exam_sessions']], days)

    def test_awaiting_confirmation_chips_follow_same_rule(self):
        self.create_sessions(pending=True)
        html, context = self.page(datetime(2026, 11, 16, 12, tzinfo=timezone.utc))
        self.assertEqual([record.session_date.day for record in context['awaiting_sessions']], [20, 10, 15])
        self.assertEqual(html.count('class="staff-exam-session-chip is-awaiting is-past-session"'), 2)
