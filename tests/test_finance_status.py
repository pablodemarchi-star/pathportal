import unittest
import json
from datetime import date

from app.models import ExamSessionFinanceControl
from app.routes import (
    FINANCE_STATUS_OPTIONS, FINANCE_LEGACY_STATUSES,
    finance_readiness_contract, finance_action_contract, validate_finance_transition,
)


class FinanceStatusTest(unittest.TestCase):
    def test_unselected_standing_is_not_reviewed_with_fixed_deadline(self):
        result = finance_readiness_contract(session_date=date(2026, 11, 1))
        self.assertEqual(result['label'], 'Not applicable')
        self.assertEqual(result['current_deadline'], date(2026, 10, 30))
        self.assertEqual(result['block_label'], 'Not reviewed')
        self.assertFalse(result['standing_selected'])
        self.assertFalse(result['can_proceed'])
        self.assertTrue(result['requires_action'])

    def test_statuses_can_be_selected_without_note(self):
        for previous in FINANCE_STATUS_OPTIONS + list(FINANCE_LEGACY_STATUSES):
            for selected in FINANCE_STATUS_OPTIONS:
                with self.subTest(previous=previous, selected=selected):
                    self.assertIsNone(validate_finance_transition(previous, selected, ''))
        self.assertIsNotNone(validate_finance_transition('Not applicable', 'Unknown', ''))

    def test_debt_states_require_follow_up_and_block_clearance(self):
        for status in ['Mid-risk debt', 'High-risk debt']:
            result = finance_readiness_contract(ExamSessionFinanceControl(status=status))
            self.assertFalse(result['can_proceed'])
            self.assertTrue(result['blockers'])
            self.assertIsNotNone(finance_action_contract(result))

    def test_existing_statuses_remain_meaningful(self):
        for old, new in FINANCE_LEGACY_STATUSES.items():
            result = finance_readiness_contract(ExamSessionFinanceControl(status=old))
            self.assertEqual(result['label'], new)
            self.assertTrue(result['message'])

    def test_selected_status_and_description_are_returned(self):
        for status in FINANCE_STATUS_OPTIONS:
            result = finance_readiness_contract(ExamSessionFinanceControl(status=status))
            self.assertEqual(result['label'], status)
            self.assertTrue(result['message'])

    def test_block_status_is_separate_from_account_standing(self):
        expected = {
            'Effective clearance': 'Cleared',
            'Not applicable': 'Cleared',
            'Conditional clearance': 'Monitoring required',
            'Mid-risk debt': 'Monitoring required',
            'High-risk debt': 'Close monitoring required',
        }
        for standing, label in expected.items():
            result = finance_readiness_contract(ExamSessionFinanceControl(status=standing, institutions_confirmed_with_admin=True))
            self.assertEqual(result['label'], standing)
            self.assertEqual(result['block_label'], label)
            self.assertTrue(result['standing_selected'])

    def test_legacy_unreviewed_is_not_a_saved_not_applicable_selection(self):
        result = finance_readiness_contract(ExamSessionFinanceControl(status='Not reviewed'))
        self.assertEqual(result['block_label'], 'Not reviewed')
        self.assertFalse(result['standing_selected'])

    def test_only_cleared_standings_meet_exam_deadline(self):
        for standing in [None] + FINANCE_STATUS_OPTIONS:
            control = ExamSessionFinanceControl(status=standing, institutions_confirmed_with_admin=True, finance_due_at=date(2030, 1, 1)) if standing else None
            for today in [date(2026, 10, 29), date(2026, 10, 30), date(2026, 10, 31)]:
                with self.subTest(standing=standing, today=today):
                    result = finance_readiness_contract(control, today=today, session_date=date(2026, 11, 1))
                    expected_overdue = today >= date(2026, 10, 30) and standing not in ['Effective clearance', 'Not applicable']
                    self.assertEqual(result['deadline'], date(2026, 10, 30))
                    self.assertEqual(result['is_overdue'], expected_overdue)
                    if expected_overdue:
                        self.assertEqual(result['block_label'], 'Overdue')
                    elif standing in ['Effective clearance', 'Not applicable']:
                        self.assertEqual(result['block_label'], 'Cleared')

    def test_all_institutions_and_admin_confirmation_determine_readiness(self):
        cases = [
            ('Effective clearance', ['Not applicable'], True, 'Cleared'),
            ('Not applicable', ['Effective clearance'], False, 'Verification missing'),
            ('Effective clearance', ['Conditional clearance'], True, 'Monitoring required'),
            ('Effective clearance', ['Mid-risk debt'], False, 'Monitoring required'),
            ('Conditional clearance', ['High-risk debt'], True, 'Close monitoring required'),
            ('Not reviewed', ['High-risk debt'], False, 'Close monitoring required'),
            ('Not reviewed', [], True, 'Not reviewed'),
            ('Not reviewed', ['Effective clearance'], True, 'Not reviewed'),
        ]
        for primary, extra, confirmed, expected in cases:
            with self.subTest(primary=primary, extra=extra, confirmed=confirmed):
                control = ExamSessionFinanceControl(status=primary, additional_institutions=json.dumps([{'name': 'School', 'standing': value} for value in extra]), institutions_confirmed_with_admin=confirmed)
                result = finance_readiness_contract(control)
                self.assertEqual(result['block_label'], expected)
                self.assertEqual(result['can_proceed'], expected == 'Cleared')

    def test_sessions_actions_add_finance_to_existing_logistics_actions(self):
        from app.routes import bundle_detail_action_items
        descriptions = {
            'Not reviewed': 'Review account standing of the institutions listed in this session.',
            'Monitoring required': 'Follow up on the account standing of the institutions listed in this session.',
            'Close monitoring required': 'Closely monitor financial standing and notify Management.',
            'Verification missing': 'Verify with Admin whether any other institutions are included in this session.',
            'Cleared': None,
        }
        for logistics_state in ['not_applicable', 'not_started', 'in_progress', 'completed']:
            for finance_state, description in descriptions.items():
                with self.subTest(logistics=logistics_state, finance=finance_state):
                    args = dict(schedule_status='Approved', schedule_gate={'is_ready': True}, schedule_next_action='', schedule_responsible='ADMIN', logistics={'status': logistics_state}, logistics_gate={'is_unblocked': True}, sessions_logistics_action_mode=True)
                    original = bundle_detail_action_items(**args)
                    result = bundle_detail_action_items(**args, finance={'readiness_label': finance_state, 'block_label': 'Overdue', 'is_overdue': True})
                    self.assertEqual(result[:len(original)], original)
                    finance_rows = [row for row in result if row.get('department') == 'FINANCE']
                    self.assertEqual(len(finance_rows), 1 if description else 0)
                    if description:
                        self.assertEqual(finance_rows[0]['description'], description)
                        self.assertTrue(finance_rows[0]['preserve_period'])

    def test_blocked_finance_has_no_department_or_action(self):
        from app.routes import bundle_detail_action_items
        for state in ['Not reviewed', 'Monitoring required', 'Close monitoring required', 'Verification missing']:
            with self.subTest(state=state):
                args = dict(schedule_status='Approved', schedule_gate={'is_ready': True}, schedule_next_action='', schedule_responsible='ADMIN', monthly_registrations_closed=False, logistics={'status': 'in_progress'}, logistics_gate={'is_unblocked': True}, sessions_logistics_action_mode=True)
                logistics_actions = bundle_detail_action_items(**args)
                actions = bundle_detail_action_items(**args, finance={'readiness_label': state})
                self.assertEqual(actions, logistics_actions)
                self.assertFalse(any(action.get('department') == 'FINANCE' for action in actions))
