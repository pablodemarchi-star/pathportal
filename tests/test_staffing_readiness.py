import unittest
from types import SimpleNamespace

from app.routes import (
    exam_session_pending_status_tooltip,
    final_email_ready,
    logistics_readiness_contract,
    staffing_readiness_contract,
)


def assignment(member_id=None, status="Pending", assignment_id=1):
    return SimpleNamespace(
        id=assignment_id,
        team_member_id=member_id,
        participation_status=status,
        logistics_enabled=False,
    )


def logistics_config(url="https://example.com/files"):
    return SimpleNamespace(logistics_files_url=url)


def logistics_concept(status="Pending", concept_id=1, provider="Provider"):
    return SimpleNamespace(
        id=concept_id,
        status=status,
        provider=provider,
    )


class StaffingReadinessContractTest(unittest.TestCase):
    def test_empty_pending_row_counts_as_open_position(self):
        result = staffing_readiness_contract([assignment()], [], [])

        self.assertEqual(result["totals"]["required"], 1)
        self.assertEqual(result["totals"]["assigned"], 0)
        self.assertEqual(result["totals"]["open_positions"], 1)
        self.assertEqual(result["totals"]["confirmed"], 0)
        self.assertFalse(result["ready"])
        self.assertEqual(result["status"], "open_positions")

    def test_empty_in_progress_row_is_invalid(self):
        result = staffing_readiness_contract([assignment(status="Pre-confirmation sent")], [], [])

        self.assertEqual(result["status"], "invalid")
        self.assertFalse(result["ready"])
        self.assertEqual(result["blockers"][0]["code"], "INVALID_EMPTY_STAFF_POSITION_STATUS")

    def test_empty_confirmed_row_is_invalid(self):
        result = staffing_readiness_contract([assignment(status="Confirmed")], [], [])

        self.assertEqual(result["status"], "invalid")
        self.assertFalse(result["ready"])

    def test_assigned_pending_counts_pending_assigned(self):
        result = staffing_readiness_contract([assignment(member_id=10, status="Pending")], [], [])

        self.assertEqual(result["totals"]["required"], 1)
        self.assertEqual(result["totals"]["assigned"], 1)
        self.assertEqual(result["totals"]["pending_assigned"], 1)
        self.assertFalse(result["ready"])
        self.assertEqual(result["status"], "awaiting_confirmations")

    def test_assigned_in_progress_statuses_are_not_ready(self):
        for status in ["Pre-confirmation sent", "Pre-confirmed", "Official confirmation sent", "Sent"]:
            with self.subTest(status=status):
                result = staffing_readiness_contract([assignment(member_id=10, status=status)], [], [])

                self.assertEqual(result["totals"]["sent"], 1)
                self.assertFalse(result["ready"])

    def test_single_assigned_confirmed_is_ready(self):
        result = staffing_readiness_contract([assignment(member_id=10, status="Confirmed")], [], [])

        self.assertEqual(result["totals"]["required"], 1)
        self.assertEqual(result["totals"]["assigned"], 1)
        self.assertEqual(result["totals"]["confirmed"], 1)
        self.assertTrue(result["ready"])
        self.assertEqual(result["status"], "confirmed")

    def test_confirmed_members_with_one_empty_row_are_not_ready(self):
        result = staffing_readiness_contract(
            [assignment(member_id=1, status="Confirmed", assignment_id=1)],
            [
                assignment(member_id=2, status="Confirmed", assignment_id=2),
                assignment(assignment_id=3),
            ],
            [],
        )

        self.assertEqual(result["totals"]["required"], 3)
        self.assertEqual(result["totals"]["assigned"], 2)
        self.assertEqual(result["totals"]["confirmed"], 2)
        self.assertEqual(result["totals"]["open_positions"], 1)
        self.assertFalse(result["ready"])

    def test_supervisor_examiner_and_intern_confirmed_are_counted_by_role(self):
        result = staffing_readiness_contract(
            [assignment(member_id=1, status="Confirmed")],
            [assignment(member_id=2, status="Confirmed")],
            [assignment(member_id=3, status="Confirmed")],
        )

        self.assertEqual(result["by_role"]["Supervisor"]["required"], 1)
        self.assertEqual(result["by_role"]["Examiner"]["required"], 1)
        self.assertEqual(result["by_role"]["Intern"]["required"], 1)
        self.assertEqual(result["totals"]["confirmed"], 3)
        self.assertTrue(result["ready"])

    def test_no_rows_is_not_configured_and_not_ready(self):
        result = staffing_readiness_contract([], [], [])

        self.assertEqual(result["status"], "not_configured")
        self.assertFalse(result["ready"])
        self.assertEqual(result["totals"]["required"], 0)

    def test_role_without_rows_does_not_block(self):
        result = staffing_readiness_contract(
            [assignment(member_id=1, status="Confirmed")],
            [
                assignment(member_id=2, status="Confirmed", assignment_id=2),
                assignment(member_id=3, status="Confirmed", assignment_id=3),
            ],
            [],
        )

        self.assertEqual(result["by_role"]["Intern"]["required"], 0)
        self.assertTrue(result["by_role"]["Intern"]["ready"])
        self.assertTrue(result["ready"])

    def test_deleted_row_does_not_count_when_omitted_from_active_assignments(self):
        result = staffing_readiness_contract(
            [assignment(member_id=1, status="Confirmed")],
            [],
            [],
        )

        self.assertEqual(result["totals"]["required"], 1)
        self.assertEqual(result["totals"]["open_positions"], 0)
        self.assertTrue(result["ready"])

    def test_member_removed_returns_row_to_open_position(self):
        result = staffing_readiness_contract([assignment(member_id=None, status="Pending")], [], [])

        self.assertEqual(result["totals"]["open_positions"], 1)
        self.assertFalse(result["ready"])

    def test_final_email_requires_staffing_and_logistics_ready(self):
        staffing_ready = staffing_readiness_contract([assignment(member_id=1, status="Confirmed")], [], [])
        staffing_blocked = staffing_readiness_contract([assignment()], [], [])
        logistics_ready = logistics_readiness_contract([], [], None)
        logistics_blocked = logistics_readiness_contract(
            [SimpleNamespace(team_member_id=1, logistics_enabled=True)],
            [],
            logistics_config(),
        )

        self.assertTrue(final_email_ready(staffing_ready, logistics_ready))
        self.assertFalse(final_email_ready(staffing_blocked, logistics_ready))
        self.assertFalse(final_email_ready(staffing_ready, logistics_blocked))

    def test_pending_status_tooltip_lists_staffing_and_logistics_blockers(self):
        staffing = staffing_readiness_contract(
            [assignment(member_id=1, status="Pending")],
            [assignment()],
            [],
        )
        logistics = logistics_readiness_contract(
            [SimpleNamespace(team_member_id=1, logistics_enabled=True)],
            [logistics_concept()],
            logistics_config(),
        )

        tooltip = exam_session_pending_status_tooltip(staffing, logistics)

        self.assertIn("Missing for Confirmed:", tooltip)
        self.assertIn("Assign staff members to 1 open staff position.", tooltip)
        self.assertIn("Confirm 1 logistics concept.", tooltip)

    def test_pending_status_tooltip_lists_awaiting_staff_confirmations(self):
        staffing = staffing_readiness_contract(
            [
                assignment(member_id=1, status="Pending", assignment_id=1),
                assignment(member_id=2, status="Pre-confirmed", assignment_id=2),
            ],
            [],
            [],
        )
        logistics = logistics_readiness_contract([], [], None)

        tooltip = exam_session_pending_status_tooltip(staffing, logistics)

        self.assertIn("Confirm all assigned staff", tooltip)
        self.assertIn("1 Pending staff member", tooltip)
        self.assertIn("1 confirmation in progress", tooltip)


if __name__ == "__main__":
    unittest.main()
