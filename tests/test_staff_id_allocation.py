import json
import os
import unittest
from datetime import date, timedelta
from unittest.mock import patch

os.environ['DATABASE_URL'] = 'sqlite:///:memory:'
from app import create_app, db
from app.models import (AcademicStaff, ExamSession, ExamSessionScheduleWorkflow, StaffIdDocument,
    ExamSessionSupervisorAssignment, ExamSessionExaminerAssignment, ExamSessionInternAssignment)
from app.routes import staff_members_pending_id_for_session, staff_member_id_requirements_for_session
from app.staff_id_allocation import staff_id_session_owners


class StaffIdAllocationTest(unittest.TestCase):
    def setUp(self):
        self.app = create_app()
        self.app.config['TESTING'] = True
        self.context = self.app.app_context(); self.context.push()
        db.drop_all(); db.create_all()
        self.today = date(2026, 11, 4)
        self.clock = patch('app.routes.pre_session_control_tower_today', return_value=self.today)
        self.clock.start()
        self.member = AcademicStaff(full_name='Shared staff', status='Active', roles='Supervisor,Examiner,Intern')
        db.session.add(self.member); db.session.commit()
        self.client = self.app.test_client()
        with self.client.session_transaction() as state:
            state.update(user='admin', csrf_token='test')

    def tearDown(self):
        self.clock.stop()
        db.session.remove(); db.drop_all(); self.context.pop()

    def record(self, name, days=0, shift='Morning', format_name='Onsite', completed=False,
               model=ExamSessionSupervisorAssignment, status='Confirmed'):
        record = ExamSession(exam_session_name=name, category='Path School', status='Pending',
            session_date=self.today + timedelta(days=days), shifts=shift, modules='Speaking', format=format_name,
            staff_member_ids_status='completed' if completed else 'in_progress')
        db.session.add(record); db.session.flush()
        assignment = model(exam_session_id=record.id, team_member_id=self.member.id, participation_status=status)
        db.session.add(assignment); db.session.commit()
        return record, assignment

    def listed(self, record):
        return [member.id for member in staff_members_pending_id_for_session(record)]

    def requirements(self, record):
        with self.app.test_request_context(method='POST'):
            return staff_member_id_requirements_for_session(record)

    def card(self, expired=False):
        db.session.add(StaffIdDocument(member_id=self.member.id, file_id='staff-id-file',
            destination_key='staff_id_documents', filename='card.pdf', mime_type='application/pdf',
            expiry_date=date(2000, 1, 1) if expired else date(2099, 1, 1)))
        db.session.commit()

    def complete(self, record):
        db.session.add(ExamSessionScheduleWorkflow(exam_session_id=record.id, status='Approved'))
        db.session.commit()
        return self.client.post(f'/pre-session-control-tower/sessions/{record.id}/packages/staff-member-ids',
            data={'csrf_token':'test', 'action':'mark_complete'})

    def test_same_date_prioritizes_morning_all_day_afternoon_evening(self):
        choices = [self.record(shift, shift=shift) for shift in ('Evening', 'Afternoon', 'All day', 'Morning')]
        for expected in ('Morning', 'All day', 'Afternoon', 'Evening'):
            owner = staff_id_session_owners()[self.member.id]
            record, assignment = next(item for item in choices if item[0].exam_session_name == expected)
            self.assertEqual(owner, record.id)
            db.session.delete(assignment); db.session.commit()
        self.assertNotIn(self.member.id, staff_id_session_owners())

    def test_same_shift_breaks_ties_by_name_then_id(self):
        last, _ = self.record('Zulu', shift='All day')
        first, assignment = self.record('Alpha', shift='All day')
        second, _ = self.record('Alpha', shift='All day')
        self.assertEqual(staff_id_session_owners()[self.member.id], first.id)
        db.session.delete(assignment); db.session.commit()
        self.assertEqual(staff_id_session_owners()[self.member.id], second.id)
        self.assertEqual(self.listed(last), [])

    def test_earliest_date_wins_before_shift_and_confirmation_does_not_change_owner(self):
        first, _ = self.record('First evening', shift='Evening', status='Pending')
        next_day, _ = self.record('Tomorrow morning', days=1)
        self.assertEqual(self.listed(first), [self.member.id])
        self.assertEqual(self.listed(next_day), [])
        self.assertFalse(self.requirements(first)[0]['is_confirmed'])

    def test_reassignment_skips_completed_online_and_past_sessions(self):
        past, _ = self.record('Past', days=-1)
        online, _ = self.record('Online', format_name='Online')
        centre, _ = self.record('Online centre', format_name='Online at exam centre')
        first, assignment = self.record('First onsite')
        completed, _ = self.record('Already done', days=1, completed=True)
        next_onsite, _ = self.record('Next onsite', days=2, model=ExamSessionInternAssignment)
        self.assertEqual(self.listed(first), [self.member.id])
        for record in (past, online, centre, completed, next_onsite):
            self.assertEqual(self.listed(record), [])
        first.staff_member_ids_snapshot = json.dumps([{'id':self.member.id, 'name':self.member.full_name}])
        db.session.delete(assignment); db.session.commit()
        self.assertEqual(self.requirements(first), [])
        self.assertEqual(self.listed(next_onsite), [self.member.id])

    def test_date_edit_and_cross_role_assignments_recompute_the_single_owner(self):
        first, _ = self.record('Examiner session', model=ExamSessionExaminerAssignment)
        second, _ = self.record('Intern session', days=1, model=ExamSessionInternAssignment)
        self.assertEqual(self.listed(first), [self.member.id])
        first.session_date = self.today + timedelta(days=2)
        db.session.commit()
        self.assertEqual(self.listed(first), [])
        self.assertEqual(self.listed(second), [self.member.id])

    def test_role_to_cover_and_replacement_release_the_previous_member(self):
        first, assignment = self.record('First')
        second, _ = self.record('Second', days=1)
        assignment.team_member_id = None
        db.session.commit()
        self.assertEqual(self.listed(first), [])
        self.assertEqual(self.listed(second), [self.member.id])
        replacement = AcademicStaff(full_name='Replacement', status='Active', roles='Supervisor')
        db.session.add(replacement); db.session.flush()
        assignment.team_member_id = replacement.id
        db.session.commit()
        self.assertEqual(self.listed(first), [replacement.id])
        self.assertEqual(self.listed(second), [self.member.id])

    def test_no_eligible_session_has_no_pending_listing(self):
        completed, _ = self.record('Done', completed=True)
        online, _ = self.record('Online only', format_name='Online')
        self.assertEqual(self.listed(completed), [])
        self.assertEqual(self.listed(online), [])
        self.assertEqual(staff_id_session_owners(), {})

    def test_completion_issues_only_current_owner_and_preserves_history(self):
        first, _ = self.record('First')
        second, _ = self.record('Second', days=1)
        self.card()
        self.assertEqual(self.complete(second).status_code, 302)
        self.assertFalse(self.member.id_issued)
        self.assertEqual(self.complete(first).status_code, 302)
        self.assertTrue(self.member.id_issued)
        self.assertEqual(self.listed(first), [])
        self.assertEqual(self.listed(second), [])
        self.assertEqual(self.requirements(first)[0]['id'], self.member.id)

    def test_missing_file_passes_to_next_session_after_completion(self):
        first, _ = self.record('First')
        second, _ = self.record('Second', days=1)
        self.assertEqual(self.complete(first).status_code, 302)
        self.assertFalse(self.member.id_issued)
        self.assertEqual(self.listed(second), [self.member.id])
        self.assertEqual(self.requirements(first)[0]['id'], self.member.id)

    def test_expired_issued_card_moves_forward_without_losing_expiry(self):
        first, _ = self.record('First')
        second, _ = self.record('Second', days=1)
        self.card(expired=True)
        self.member.id_issued = True; db.session.commit()
        self.assertEqual(self.listed(first), [self.member.id])
        self.assertEqual(self.listed(second), [])
        self.assertEqual(self.complete(first).status_code, 302)
        self.assertEqual(self.listed(second), [self.member.id])
        self.assertTrue(self.member.id_issued)
        self.assertEqual(db.session.get(StaffIdDocument, self.member.id).expiry_date, date(2000, 1, 1))
        self.assertTrue(self.requirements(first)[0]['expired'])

    def test_get_requests_reassign_after_assignment_removal(self):
        first, assignment = self.record('First')
        second, _ = self.record('Second', days=1)
        self.card()
        url = f'/pre-session-control-tower/sessions/{first.id}/staff-id-cards/{self.member.id}/download'
        # Ask only for allocation metadata, without reaching Drive downloads.
        with self.app.test_request_context():
            self.assertEqual(staff_id_session_owners()[self.member.id], first.id)
        db.session.delete(assignment); db.session.commit()
        with self.app.test_request_context():
            self.assertEqual(staff_id_session_owners()[self.member.id], second.id)
        self.assertEqual(self.client.get(url).status_code, 409)
