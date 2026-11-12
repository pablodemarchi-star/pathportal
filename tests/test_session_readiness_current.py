import unittest
from app.routes import session_readiness_contract, operational_readiness_contract, finance_readiness_contract
from app.models import ExamSessionFinanceControl


class SessionReadinessCurrentTest(unittest.TestCase):
    def operational(self, completed=True, legacy_ready=False, shipment_status='Delivered successfully'):
        return operational_readiness_contract(
            {'status': 'ready', 'is_ready': True},
            {'status': 'confirmed', 'ready': True},
            {'status': 'not_applicable', 'final_email_ready': True},
            {'status': 'quality_checked' if legacy_ready else 'pre_packing_not_started', 'ready': legacy_ready},
            {'status': shipment_status},
            package_preparation={'status': 'completed' if completed else 'in_progress'})

    def readiness(self, progress='completed', communications=None, package_completed=True, incidents=None, flags=None, shipment_status='Delivered successfully'):
        finance = finance_readiness_contract(ExamSessionFinanceControl(
            status='Effective clearance', institutions_confirmed_with_admin=True))
        return session_readiness_contract(self.operational(package_completed, shipment_status=shipment_status), finance,
            {'label': 'Ready', 'ready': True, 'overall_progress': progress}, communications,
            incidents or {'status': 'none', 'active_count': 0},
            flags or {'status': 'ready', 'ready': True})

    def test_completed_package_ignores_legacy_quality_state(self):
        self.assertTrue(self.operational(completed=True)['is_ready'])
        self.assertFalse(self.operational(completed=False, legacy_ready=True)['is_ready'])

    def test_delivered_shipment_satisfies_readiness_without_recipient_review(self):
        self.assertTrue(self.readiness(shipment_status='Delivered successfully')['is_ready'])
        self.assertTrue(self.readiness(shipment_status='Recipient review successful')['is_ready'])
        for status in ['not_bundled', 'Preparing bundle', 'Ready to dispatch', 'In transit to post office',
                       'Dispatched', 'Recipient notified', 'In transit to recipient', 'Delayed',
                       'Recipient review with discrepancy']:
            with self.subTest(status=status):
                self.assertFalse(self.readiness(shipment_status=status)['is_ready'])

    def test_communications_never_blocks_or_appears(self):
        for communications in [None, {}, {'status': 'needs_review', 'label': 'Invalid', 'blockers': [{'message': 'Old communications blocker'}]}]:
            result = self.readiness(communications=communications)
            self.assertTrue(result['is_ready'])
            self.assertEqual(result['total_requirements'], 5)
            self.assertNotIn('communications', [item['key'] for item in result['requirements']])
            self.assertNotIn('Communications', result['tooltip'] + result['scope_note'])

    def test_all_other_requirements_ready_still_require_final_checks_completed(self):
        for progress in [None, 'not_started', 'in_progress']:
            result = self.readiness(progress=progress)
            self.assertFalse(result['is_ready'])
            self.assertIn('FINAL_CHECKS_INCOMPLETE', [item['code'] for item in result['blockers']])
        self.assertTrue(self.readiness()['is_ready'])

    def test_reopened_package_and_incidents_remove_readiness(self):
        self.assertFalse(self.readiness(package_completed=False)['is_ready'])
        self.assertFalse(self.readiness(incidents={'status': 'active', 'active_count': 1})['is_ready'])
        self.assertFalse(self.readiness(flags={'status': 'active', 'ready': False, 'active_flags_count': 1})['is_ready'])
