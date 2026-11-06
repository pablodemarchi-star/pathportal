import json
import re
import unittest
from datetime import date, datetime, timedelta, timezone
from unittest.mock import patch
from io import BytesIO

from tests import test_schedule_workflow as fixtures
from app import db
from app.models import (AcademicStaff, ExamSession, ExamSessionSupervisorAssignment, ExamSessionExaminerAssignment,
                        ExamSessionSinapsisControl, ExamSessionSinapsisChecklistItem, ReturnShippingLabel)
from app.routes import (LOCAL_TZ, argentina_add_business_days, argentina_subtract_business_days,
                        ensure_sinapsis_checklist_items, final_checks_gate_contract, schedule_workflow_view)
from app.final_checks import final_checks_state, initialize_existing_final_checks
from app.final_checks import sync_lifecycle


class FinalChecksWorkflowTest(unittest.TestCase):
    setUp = fixtures.ScheduleWorkflowTest.setUp
    tearDown = fixtures.ScheduleWorkflowTest.tearDown
    login_client = fixtures.ScheduleWorkflowTest.login_client

    def assign(self, status='Confirmed'):
        person = AcademicStaff(full_name='Shipment Recipient', status='Active', roles='Supervisor')
        db.session.add(person); db.session.flush()
        assignment = ExamSessionSupervisorAssignment(exam_session_id=self.session_record.id,
            team_member_id=person.id, participation_status=status, is_shipment_recipient=True)
        db.session.add(assignment); db.session.commit()
        return assignment

    def control(self):
        control = ExamSessionSinapsisControl.query.filter_by(exam_session_id=self.session_record.id).first()
        if not control:
            control = ExamSessionSinapsisControl(exam_session_id=self.session_record.id, status='Not reviewed')
            db.session.add(control)
        ensure_sinapsis_checklist_items(control)
        db.session.commit()
        return control

    def state(self, today=None):
        return final_checks_state(self.session_record, today=today)

    def modal(self):
        return self.login_client().get(f'/pre-session-control-tower?session_year={self.session_record.session_date.year}&view=sessions&session_modal={self.session_record.id}&open_schedule_modal={self.session_record.id}&sinapsis_only=1').get_data(as_text=True)

    def return_post(self, **fields):
        return self.login_client().post(f'/pre-session-control-tower/sessions/{self.session_record.id}/return-materials',
            data={'csrf_token': 'token', 'return_materials_method': 'immediate_dispatch', **fields})

    def check_post(self, item, checked=True):
        return self.login_client().post(f'/pre-session-control-tower/sessions/{self.session_record.id}/sinapsis-checklist/{item.id}',
            data={'csrf_token': 'token', 'is_checked': '1' if checked else '0'}, headers={'X-Requested-With': 'XMLHttpRequest'})

    def label(self, method='immediate_dispatch', delete=False):
        control = self.control()
        if control.return_materials_method != method:
            self.return_post(return_materials_method=method)
        field = 'return_shipping_label' if method == 'immediate_dispatch' else 'combined_return_shipping_label'
        document = getattr(control, field)
        data = {'csrf_token': 'token', 'previous_file_id': document.file_id if document else ''}
        if delete:
            data['action'] = 'delete'
        else:
            data['document'] = (BytesIO(b'%PDF-1.7 test'), 'shipping-label.pdf')
        def upload(file, target, destination):
            target.document = ReturnShippingLabel(file_id='test-label-' + str(ReturnShippingLabel.query.count() + 1),
                destination_key=destination.key, filename=file.filename, mime_type=file.mimetype)
            db.session.add(target.document)
        with patch('app.return_labels.upload_document', side_effect=upload), patch('app.return_labels.trash_document'):
            return self.login_client().post(f'/pre-session-control-tower/sessions/{self.session_record.id}/return-label/{method}', data=data)

    def test_gates_require_confirmed_recipient_and_eight_business_day_window_only(self):
        today = date(2026, 11, 5)
        self.session_record.session_date = argentina_add_business_days(today, 9)
        assignment = self.assign('Pending')
        self.assertEqual(self.state(today)['status'], 'blocked')
        assignment.participation_status = 'Confirmed'; db.session.commit()
        self.assertEqual(self.state(today)['status'], 'semi_unblocked')
        self.session_record.session_date = argentina_add_business_days(today, 8); db.session.commit()
        gate = final_checks_gate_contract(self.session_record, 'Not started', {}, {}, {}, {}, {}, {}, today=today)
        self.assertEqual(gate['status'], 'unblocked')
        assignment.participation_status = 'Pending'; db.session.commit()
        self.assertEqual(self.state(today)['status'], 'blocked')
        assignment.participation_status = 'Confirmed'; db.session.commit()
        self.assertEqual(self.state(today)['status'], 'unblocked')

    def test_29_calendar_day_window_and_clock_begin_when_both_conditions_are_met(self):
        today = date(2026,11,5)
        self.session_record.session_date = date(2026,12,20)
        assigned = self.assign()
        control = self.control()
        self.assertIsNone(control.return_started_on)
        self.assertEqual(control.return_recipient_confirmed_on, datetime.now(LOCAL_TZ).date())
        self.assertEqual(self.state(date(2026,11,20))['status'], 'blocked')
        opened = self.state(date(2026,11,21))
        self.assertEqual(opened['status'], 'semi_unblocked')
        self.assertEqual(opened['return_deadline_badge']['date'], date(2026,12,1))
        self.assertEqual(self.state(date(2026,11,25))['return_deadline_badge']['date'], date(2026,12,1))
        assigned.participation_status = 'Pending'
        with db.session.no_autoflush:
            sync_lifecycle(self.session_record, db.session(), today=date(2026,11,25))
        db.session.commit()
        self.assertEqual(control.return_started_on, date(2026,11,21))
        assigned.participation_status = 'Confirmed'
        with db.session.no_autoflush:
            sync_lifecycle(self.session_record, db.session(), today=date(2026,12,1))
        db.session.commit()
        self.assertEqual(control.return_started_on, date(2026,11,21))

    def test_confirmation_after_window_opens_starts_the_clock_on_confirmation_day(self):
        self.session_record.session_date = date(2026,12,20)
        assigned = self.assign('Pending'); control = self.control()
        assigned.participation_status = 'Confirmed'
        with db.session.no_autoflush:
            sync_lifecycle(self.session_record, db.session(), today=date(2026,11,25))
        db.session.commit()
        self.assertEqual(control.return_started_on, date(2026,11,25))
        self.assertEqual(self.state(date(2026,11,25))['return_deadline_badge']['date'], date(2026,12,5))

    def test_final_checks_tooltips_list_every_pending_condition_and_opening_dates(self):
        self.session_record.session_date = date(2026,12,20); db.session.commit()
        blocked = self.state(date(2026,11,5))
        self.assertIn('Assign a staff member with Receives shipment.', blocked['message'])
        self.assertIn('29 calendar days', blocked['message'])
        self.assertIn('21/11/2026', blocked['message'])
        assigned = self.assign('Pending')
        self.assertIn('must confirm participation', self.state(date(2026,11,5))['message'])
        assigned.participation_status = 'Confirmed'; db.session.commit()
        self.assertNotIn('must confirm participation', self.state(date(2026,11,5))['message'])
        semi = self.state(date(2026,11,21))
        self.assertIn('8 Argentine business days', semi['message'])
        self.assertIn(argentina_subtract_business_days(self.session_record.session_date, 8).strftime('%d/%m/%Y'), semi['message'])

    def test_finance_tooltips_follow_actual_unlock_conditions_in_table_and_modal(self):
        client = self.login_client()
        base = '/pre-session-control-tower?session_year=2026&view=sessions'
        modal = base + f'&session_modal={self.session_record.id}&open_schedule_modal={self.session_record.id}&finance_only=1'
        reason = 'Close exam registrations and confirm exam session date'
        self.assertIn(f'title="{reason}"', client.get(base).get_data(as_text=True))
        self.assertIn(f'title="{reason}"', client.get(modal).get_data(as_text=True))
        self.session_record.monthly_registrations_closed = True; db.session.commit()
        self.assertIn('title="Confirm exam session date to begin pre-session preparation"', client.get(modal).get_data(as_text=True))
        self.session_record.date_confirmation_status = 'Confirmed'; db.session.commit()
        html = client.get(modal).get_data(as_text=True)
        self.assertNotIn('aria-label="Finance gate blocked', html)

    def test_return_deadline_uses_earlier_limit_and_next_day_overdue(self):
        self.assign()
        control = self.control()
        control.return_started_on = date(2026, 11, 5)
        for session_date, expected in ((date(2026,11,20), date(2026,11,13)),
                                       (date(2026,11,10), date(2026,11,3)),
                                       (date(2026,12,20), date(2026,11,15))):
            self.session_record.session_date = session_date; db.session.commit()
            self.assertEqual(self.state(date(2026,11,5))['return_deadline_badge']['date'], expected)
        self.assertEqual(self.state(date(2026,11,15))['return_deadline_badge']['status'], 'on-track')
        self.assertEqual(self.state(date(2026,11,16))['return_deadline_badge']['status'], 'overdue')

    def test_deadline_does_not_restart_on_confirmation_toggles_or_staff_replacement(self):
        assignment = self.assign()
        control = self.control()
        control.return_started_on = date(2026,11,5); db.session.commit()
        original = self.state()['return_deadline_badge']['date']
        assignment.participation_status = 'Pending'; db.session.commit()
        assignment.participation_status = 'Confirmed'; db.session.commit()
        person = AcademicStaff(full_name='New Recipient', roles='Supervisor', status='Active')
        db.session.add(person); db.session.flush()
        assignment.team_member_id = person.id; db.session.commit()
        self.assertTrue(control.return_review_required)
        self.assertEqual(control.return_started_on, date(2026,11,5))
        self.assertEqual(self.state()['return_deadline_badge']['date'], original)

    def test_existing_confirmations_start_today_and_initialization_is_idempotent(self):
        assignment = self.assign('Pending')
        # Simulate an old confirmation from before this feature's event hook existed.
        ExamSessionSupervisorAssignment.query.filter_by(id=assignment.id).update({'participation_status':'Confirmed'}, synchronize_session=False)
        db.session.commit(); db.session.expire_all()
        initialize_existing_final_checks()
        control = self.control()
        self.assertEqual(control.return_started_on, datetime.now(LOCAL_TZ).date())
        old = date(2026,11,1); control.return_started_on = old; db.session.commit()
        initialize_existing_final_checks()
        self.assertEqual(control.return_started_on, old)

    def test_http_blocking_is_enforced_and_final_communications_is_removed(self):
        self.session_record.session_date = datetime.now(LOCAL_TZ).date() + timedelta(days=20)
        assignment = self.assign('Pending'); control = self.control()
        item = control.checklist_items[0]
        self.assertEqual(self.return_post().status_code, 403)
        self.assertEqual(self.check_post(item).status_code, 403)
        html = self.modal()
        self.assertIn('final-checks-disabled', html)
        self.assertNotIn('Final communications', html)
        self.assertIn('class="final-checks-fields" disabled', html)
        assignment.participation_status = 'Confirmed'; db.session.commit()
        self.assertEqual(self.return_post().status_code, 200)
        self.assertEqual(self.check_post(item).status_code, 403)
        self.session_record.session_date = datetime.now(LOCAL_TZ).date() + timedelta(days=2); db.session.commit()
        self.assertEqual(self.check_post(item).status_code, 200)
        self.assertTrue(item.is_checked)
        assignment.participation_status = 'Pending'; db.session.commit()
        self.assertEqual(self.check_post(item, False).status_code, 403)
        self.assertTrue(item.is_checked)

    def test_management_and_admin_actions_progress_independently(self):
        self.assign(); control = self.control()
        self.assertEqual([(a['department'],a['description']) for a in self.state()['actions']], [
            ('MANAGEMENT','Configure exam material return'), ('ADMIN','Start pre-session Sinapsis checks')])
        self.assertEqual(self.return_post().status_code, 200)
        self.assertEqual(self.state()['actions'][0]['description'], 'Issue return shipping label')
        self.assertEqual(self.state()['actions'][0]['department'], 'ADMIN')
        self.assertEqual(self.label().status_code, 200)
        self.assertEqual([a['department'] for a in self.state()['actions']], ['ADMIN'])
        self.assertEqual(self.check_post(control.checklist_items[0]).status_code, 200)
        self.assertEqual(self.state()['actions'][0]['description'], 'Continue with pre-session Sinapsis checks')
        for item in control.checklist_items[1:]:
            self.assertEqual(self.check_post(item).status_code, 200)
        self.assertEqual(self.state()['actions'], [])
        self.assertTrue(self.state()['checks_complete'])

        self.assertIn('Completed', self.modal())
        self.label(delete=True)
        self.assertEqual([row['department'] for row in self.state()['actions']], ['ADMIN'])
        self.assertTrue(self.state()['checks_complete'])

    def test_overall_progress_counts_return_and_checks_and_retains_history(self):
        self.assign(); control = self.control()
        self.assertEqual(self.state()['progress'], 'not_started')
        self.assertEqual(self.return_post().status_code, 200)
        self.assertEqual(self.state()['progress'], 'in_progress')
        self.label()
        self.assertEqual(self.state()['progress'], 'in_progress')
        for item in control.checklist_items:
            self.assertEqual(self.check_post(item).status_code, 200)
        self.assertEqual(self.state()['progress'], 'completed')
        self.label(delete=True)
        self.assertEqual(self.state()['progress'], 'in_progress')
        self.assertIn('final-checks-progress-in-progress', self.modal())
        for item in control.checklist_items:
            self.assertEqual(self.check_post(item, False).status_code, 200)
        control.return_materials_method = None
        db.session.commit()
        self.assertEqual(self.state()['progress'], 'in_progress')

    def test_receiver_change_requires_explicit_review_but_other_staff_change_does_not(self):
        assignment = self.assign(); control = self.control()
        self.label()
        self.assertTrue(self.state()['return_complete'])
        other = AcademicStaff(full_name='Other Examiner', roles='Examiner', status='Active')
        db.session.add(other); db.session.flush()
        examiner = ExamSessionExaminerAssignment(exam_session_id=self.session_record.id, team_member_id=other.id)
        db.session.add(examiner); db.session.commit()
        examiner.participation_status = 'Pre-confirmed'; db.session.commit()
        self.assertFalse(control.return_review_required)
        assignment.team_member_id = other.id
        assignment.participation_status = 'Pending'; db.session.commit()
        self.assertTrue(control.return_review_required)
        self.assertIsNotNone(control.return_shipping_label)
        review_url = f'/pre-session-control-tower/sessions/{self.session_record.id}/return-review'
        self.assertEqual(self.login_client().post(review_url, data={'csrf_token':'token'}).status_code, 403)
        assignment.participation_status = 'Confirmed'; db.session.commit()
        self.assertEqual(self.state()['actions'][0]['description'], 'Review package return due to staff change')
        html = self.modal()
        self.assertIn('Confirm return review', html)
        self.assertIn('data-return-review-required="true"', html)
        self.assertFalse(self.state()['return_complete'])
        self.assertEqual(self.login_client().post(review_url, data={'csrf_token':'token'}).status_code, 302)
        self.assertFalse(control.return_review_required)
        self.assertTrue(self.state()['return_complete'])

    def test_review_cannot_complete_with_missing_return_details(self):
        assignment = self.assign(); control = self.control()
        self.return_post()
        other = AcademicStaff(full_name='Replacement', roles='Supervisor', status='Active')
        db.session.add(other); db.session.flush(); assignment.team_member_id = other.id; db.session.commit()
        response = self.login_client().post(f'/pre-session-control-tower/sessions/{self.session_record.id}/return-review', data={'csrf_token':'token'})
        self.assertEqual(response.status_code, 302)
        db.session.refresh(control)
        self.assertTrue(control.return_review_required)

    def test_incomplete_dispatch_options_assign_label_issuance_to_admin_only(self):
        self.assign(); self.control()
        for method in ('immediate_dispatch', 'location_drop_off', 'combined_location_drop_off', 'staff_handover'):
            with self.subTest(method=method):
                self.assertEqual(self.return_post(return_materials_method=method).status_code, 200)
                action = self.state()['actions'][0]
                dispatch = method in ('immediate_dispatch', 'combined_dispatch')
                self.assertEqual(action['department'], 'ADMIN' if dispatch else 'MANAGEMENT')
                self.assertEqual(action['description'], 'Issue return shipping label' if dispatch else 'Finalise return of exam material configuration')

    def test_combined_dispatch_assigns_sessions_and_label_independently(self):
        self.session_record.session_date = datetime.now(LOCAL_TZ).date() + timedelta(days=20)
        assigned = self.assign(); self.control()
        peer = ExamSession(exam_session_name='Combined return peer', category='Path School', status='Pending',
            session_date=self.session_record.session_date, shifts='Morning', modules='Speaking', format='Onsite')
        db.session.add(peer); db.session.flush()
        db.session.add_all([
            ExamSessionSupervisorAssignment(exam_session_id=peer.id, team_member_id=assigned.team_member_id,
                participation_status='Confirmed', is_shipment_recipient=True),
            ExamSessionExaminerAssignment(exam_session_id=peer.id, team_member_id=assigned.team_member_id,
                participation_status='Confirmed')])
        db.session.commit()
        def actions():
            return {(row['department'], row['description']) for row in self.state()['actions']}
        management = ('MANAGEMENT', 'Select sessions for combined return')
        admin = ('ADMIN', 'Issue return shipping label')
        self.assertEqual(self.return_post(return_materials_method='combined_dispatch').status_code, 200)
        self.assertEqual(actions(), {management, admin})
        self.assertEqual(self.label('combined_dispatch').status_code, 200)
        self.assertEqual(actions(), {management})
        self.assertEqual(self.label('combined_dispatch', delete=True).status_code, 200)
        self.assertEqual(self.return_post(return_materials_method='combined_dispatch',
            save_combined_return_sessions='1',
            combined_return_session_ids=[str(peer.id)]).status_code, 200)
        self.assertEqual(actions(), {admin})
        self.assertEqual(self.label('combined_dispatch').status_code, 200)
        self.assertEqual(actions(), set())

    def test_checks_deadline_is_four_business_days_and_only_all_checked_meets_it(self):
        self.assign(); control = self.control()
        self.session_record.session_date = date(2026,11,20); db.session.commit()
        expected = argentina_subtract_business_days(self.session_record.session_date, 4)
        state = self.state(expected)
        self.assertEqual(state['checks_deadline_badge']['date'], expected)
        self.assertEqual(state['checks_deadline_badge']['status'], 'on-track')
        self.assertEqual(self.state(expected + timedelta(days=1))['checks_deadline_badge']['status'], 'overdue')
        for item in control.checklist_items:
            item.is_checked = True
            item.checked_at = datetime.combine(expected, datetime.min.time()).replace(hour=12, tzinfo=timezone.utc)
        db.session.commit()
        self.assertEqual(self.state()['checks_deadline_badge']['status'], 'met')
        control.checklist_items[-1].checked_at += timedelta(days=1); db.session.commit()
        self.assertEqual(self.state()['checks_deadline_badge']['status'], 'missed')

    def test_department_table_includes_both_independent_actions(self):
        self.assign(); self.control()
        html = self.login_client().get('/pre-session-control-tower?session_year=2026&view=sessions').get_data(as_text=True)
        self.assertIn('Configure exam material return', html)
        self.assertIn('Start pre-session Sinapsis checks', html)
        self.assertIn('MANAGEMENT', html)
        self.assertIn('ADMIN', html)

    def test_legacy_schema_upgrade_removes_label_links_and_keeps_drop_off_and_clock(self):
        from sqlalchemy import text
        from app.schema_migrations import migrate_final_checks_workflow
        self.assign()
        control = self.control()
        control.return_materials_method = 'combined_dispatch'
        control.return_materials_label_url = 'https://example.com/old-immediate'
        control.combined_return_materials_label_url = 'https://example.com/old-combined'
        control.return_drop_off_address_url = 'https://example.com/drop-off'
        db.session.commit()
        data = dict(db.session.execute(text('SELECT * FROM exam_session_sinapsis_control')).mappings().one())
        removed = {'return_started_on', 'return_recipient_ref', 'return_review_required', 'return_reviewed_at',
                   'return_completed_at', 'return_shipping_label_id', 'combined_return_shipping_label_id'}
        schema = db.session.execute(text("SELECT sql FROM sqlite_master WHERE name='exam_session_sinapsis_control'")).scalar()
        schema = '\n'.join(line for line in schema.splitlines() if not any(field in line for field in removed))
        schema = re.sub(r',\s*\)$', '\n)', schema)
        db.session.expunge_all()
        db.session.execute(text('DROP TABLE exam_session_sinapsis_control'))
        db.session.execute(text(schema))
        kept = {key: value for key, value in data.items() if key not in removed}
        db.session.execute(text('INSERT INTO exam_session_sinapsis_control (' + ','.join(kept) + ') VALUES (' + ','.join(':' + key for key in kept) + ')'), kept)
        db.session.commit()
        migrate_final_checks_workflow()
        initialize_existing_final_checks()
        migrate_final_checks_workflow()
        restored = db.session.get(ExamSessionSinapsisControl, data['id'])
        self.assertEqual(restored.return_materials_method, 'combined_dispatch')
        self.assertIsNone(restored.return_materials_label_url)
        self.assertIsNone(restored.combined_return_materials_label_url)
        self.assertEqual(restored.return_drop_off_address_url, 'https://example.com/drop-off')
        self.assertEqual(restored.return_started_on, datetime.now(LOCAL_TZ).date())
        self.assertFalse(restored.return_review_required)
