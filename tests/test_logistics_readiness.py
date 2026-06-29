import unittest
from types import SimpleNamespace

from app.routes import logistics_readiness_contract, persisted_staff_confirmed


def assignment(member_id=1, logistics_enabled=False, participation_status="Confirmed"):
    return SimpleNamespace(
        team_member_id=member_id,
        logistics_enabled=logistics_enabled,
        participation_status=participation_status,
    )


def concept(status="Confirmed", concept_id=1):
    return SimpleNamespace(id=concept_id, status=status, provider=f"Provider {concept_id}")


def logistics_config(url="https://example.com/files"):
    return SimpleNamespace(logistics_files_url=url)


class LogisticsReadinessContractTest(unittest.TestCase):
    def test_without_logistics_is_ready_for_final_email(self):
        result = logistics_readiness_contract([], [], None)

        self.assertEqual(result["status"], "not_applicable")
        self.assertTrue(result["ready"])
        self.assertTrue(result["final_email_ready"])

    def test_enabled_logistics_without_concepts_is_blocked(self):
        result = logistics_readiness_contract([assignment(logistics_enabled=True)], [], None)

        self.assertEqual(result["status"], "configuration_required")
        self.assertFalse(result["ready"])
        self.assertFalse(result["final_email_ready"])
        self.assertEqual(result["blockers"][0]["code"], "LOGISTICS_CONCEPTS_MISSING")

    def test_pending_concept_is_blocked(self):
        result = logistics_readiness_contract(
            [assignment(logistics_enabled=True)],
            [concept("Pending")],
            logistics_config(),
        )

        self.assertEqual(result["status"], "in_progress")
        self.assertFalse(result["final_email_ready"])
        self.assertEqual(result["blocking_concepts"][0]["status"], "Pending")

    def test_in_progress_concept_is_blocked(self):
        result = logistics_readiness_contract(
            [assignment(logistics_enabled=True)],
            [concept("In progress")],
            logistics_config(),
        )

        self.assertEqual(result["status"], "in_progress")
        self.assertFalse(result["final_email_ready"])

    def test_pre_confirmed_concept_is_blocked(self):
        result = logistics_readiness_contract(
            [assignment(logistics_enabled=True)],
            [concept("Pre-confirmed")],
            logistics_config(),
        )

        self.assertEqual(result["status"], "in_progress")
        self.assertFalse(result["final_email_ready"])

    def test_confirmed_concepts_with_valid_link_are_ready_for_final_email(self):
        result = logistics_readiness_contract(
            [assignment(logistics_enabled=True)],
            [concept("Confirmed")],
            logistics_config(),
        )

        self.assertEqual(result["status"], "confirmed")
        self.assertTrue(result["ready"])
        self.assertTrue(result["final_email_ready"])

    def test_confirmed_concepts_without_link_block_final_email_only(self):
        result = logistics_readiness_contract(
            [assignment(logistics_enabled=True)],
            [concept("Confirmed")],
            logistics_config(""),
        )

        self.assertEqual(result["status"], "confirmed")
        self.assertTrue(result["ready"])
        self.assertFalse(result["final_email_ready"])
        self.assertEqual(result["blockers"][0]["code"], "LOGISTICS_FILES_URL_MISSING")

    def test_pending_member_prevents_final_email_stage(self):
        self.assertFalse(persisted_staff_confirmed([
            assignment(participation_status="Pending"),
            assignment(member_id=2, participation_status="Confirmed"),
        ]))

    def test_sent_member_prevents_final_email_stage(self):
        self.assertFalse(persisted_staff_confirmed([
            assignment(participation_status="Pre-confirmation sent"),
            assignment(member_id=2, participation_status="Confirmed"),
        ]))

    def test_all_members_confirmed_allows_final_email_stage(self):
        self.assertTrue(persisted_staff_confirmed([
            assignment(participation_status="Confirmed"),
            assignment(member_id=2, participation_status="Confirmed"),
        ]))


if __name__ == "__main__":
    unittest.main()
