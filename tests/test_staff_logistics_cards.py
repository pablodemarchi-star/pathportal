import json
import unittest
from unittest.mock import patch
from app import db, models as m
from app.staff_logistics import state, migrate
from tests import test_staff_session_report as fixtures
from tests import test_session_reports as reports


class StaffLogisticsCardsTest(unittest.TestCase):
    setUp=fixtures.StaffSessionReportTest.setUp
    tearDown=fixtures.StaffSessionReportTest.tearDown
    admin_client=reports.SessionReportsTest.admin_client

    def enable(self, kind='Uber ride'):
        self.assignment=db.session.get(m.ExamSessionSupervisorAssignment,self.submission.assignment_id)
        self.assignment.logistics_type=kind;self.assignment.logistics_enabled=True
        db.session.commit()
        return m.StaffLogisticsCard.query.filter_by(active=True).one()

    def payment(self, card, paid=False):
        concept=m.FinanceConcept(name='Flights',is_active=True)
        db.session.add(concept);db.session.flush()
        item=m.PaymentRequest(request_number='PAY-100',description='Hotel',concept_id=concept.id,concept_name_snapshot='Flights',amount=100,currency='ARS',payment_method='Bank transfer',status='Payment completed' if paid else 'Submitted',logistics_card_id=card.id)
        db.session.add(item);db.session.commit();return item

    def test_cards_default_status_and_completion_ignores_payments(self):
        card=self.enable();self.assertEqual(card.status,'Pending')
        self.assertFalse(state(self.record)['ready'])
        self.payment(card)
        card.status='Completed';db.session.commit()
        self.assertTrue(state(self.record)['ready'])
        self.assignment.logistics_type='Complex Uber ride';db.session.commit()
        self.assertEqual(card.status,'Pending')
        self.assignment.team_member_id=None;db.session.commit()
        self.assertFalse(card.active)
        self.assertTrue(state(self.record)['open_roles'])
        self.assertFalse(state(self.record)['ready'])
        self.assertEqual(m.PaymentRequest.query.one().status,'Payment cancelled')

    def test_paid_payment_preserved_with_alert_and_rejected_staff_excluded(self):
        card=self.enable();payment=self.payment(card,paid=True)
        self.assignment.participation_status='Declined';db.session.commit()
        self.assertFalse(card.active)
        self.assertEqual(payment.status,'Payment completed')
        self.assertIn('already completed',payment.logistics_alert)
        self.assertTrue(state(self.record)['open_roles'])
        self.assertEqual(m.StaffLogisticsCard.query.filter_by(active=True).count(),0)

    def test_formats_and_does_not_apply(self):
        self.assertTrue(state(self.record)['pending_definition'])
        assignment=db.session.get(m.ExamSessionSupervisorAssignment,self.submission.assignment_id)
        assignment.logistics_type='Does not apply';db.session.commit()
        self.assertFalse(state(self.record)['applies'])
        self.enable();self.record.format='Online';db.session.commit()
        self.assertIsNone(state(self.record))
        self.assertEqual(m.StaffLogisticsCard.query.filter_by(active=True).count(),0)

    def test_shared_card_scope_links_and_permissions(self):
        card=self.enable()
        peer=m.ExamSession(exam_session_name='Peer',category='Path School',status='Pending',session_date=self.record.session_date,shifts='Morning',modules='Speaking',format='Online at exam centre',concat_session_ids=json.dumps([self.record.id]))
        db.session.add(peer);db.session.flush()
        other=m.ExamSessionSupervisorAssignment(exam_session_id=peer.id,team_member_id=self.person.id,logistics_enabled=True,logistics_type='Carpooling',participation_status='Confirmed')
        db.session.add(other);db.session.commit()
        self.assertEqual(m.StaffLogisticsCard.query.filter_by(active=True).count(),1)
        admin,user=self.admin_client()
        url=f'/pre-session-control-tower/logistics/cards/{card.id}'
        data=dict(csrf_token='test',session_ids=[str(self.record.id),str(peer.id)],status='Completed',description='Flight details',links=json.dumps([dict(name='Flight',url='https://example.com/flight')]))
        with patch('app.routes.logistics_actions_are_blocked',return_value=False):
            result=admin.post(url,data=data)
            self.assertEqual(result.status_code,200,result.data)
            self.assertEqual(card.status,'Pending')
            self.assertEqual(set(json.loads(card.session_ids)),{self.record.id,peer.id})
            result=admin.post(url,data=data);self.assertEqual(result.status_code,200)
            self.assertEqual(card.status,'Completed')
            result=admin.post(url,data={**data,'links':'[{"name":"Unsafe","url":"javascript:alert(1)"}]'})
            self.assertEqual(result.status_code,400)
            self.assertEqual(admin.post(url,data={**data,'csrf_token':'bad'}).status_code,400)
            data['session_ids']=[str(peer.id)]
            self.assertEqual(admin.post(url,data=data).status_code,200)
            self.assertEqual(card.status,'Pending')
            self.assertFalse(state(self.record)['applies'])
            self.assertTrue(state(peer)['applies'])
        other.participation_status='Declined';db.session.commit()
        self.assertFalse(card.active)
        self.assertEqual(json.loads(m.StaffLogisticsCard.query.filter_by(active=True).one().session_ids),[self.record.id])
        self.assertFalse(any(row.id == card.id for row in state(peer)['cards']))

    def test_one_time_reset_cancels_old_requests_and_keeps_online_data(self):
        card=self.enable()
        config=m.ExamSessionLogistics(exam_session_id=self.record.id,logistics_files_url='https://example.com/old',logistics_planned=True)
        old=m.ExamSessionLogisticsConcept(exam_session_id=self.record.id,provider='Old provider')
        db.session.add_all([config,old]);db.session.flush()
        payment=self.payment(card);payment.logistics_card_id=None;payment.logistics_concept_id=old.id;db.session.commit()
        migrate()
        self.assertEqual(payment.status,'Payment cancelled')
        self.assertIsNone(payment.logistics_concept_id)
        self.assertIsNone(config.logistics_files_url)
        self.assertEqual(m.ExamSessionLogisticsConcept.query.count(),0)
        self.assertEqual(m.StaffLogisticsCard.query.filter_by(active=True).count(),1)
        card.description='Keep after migration';db.session.commit();migrate()
        self.assertEqual(card.description,'Keep after migration')

    def test_planner_and_tower_render_cards_without_legacy_sections(self):
        self.enable()
        admin,user=self.admin_client()
        planner=admin.get('/exam-session-planner?session_year=2026')
        self.assertEqual(planner.status_code,200)
        self.assertNotIn(b'data-logistics-section',planner.data)
        response=admin.get(f'/pre-session-control-tower?session_year=2026&view=sessions&session_modal={self.record.id}')
        self.assertEqual(response.status_code,200)
        html=response.get_data(as_text=True)
        self.assertIn('data-logistics-card-form',html)
        self.assertIn('Schedule payment',html)
        self.assertIn('Not configured',html)
        self.assertNotIn('Open logistics files',html)
        self.assertNotIn('logistics-concepts-readonly-table',html)
        self.assertIn('packages-control-section',html)

    def test_payment_created_from_blank_form_links_to_card_and_opens_in_modal(self):
        card=self.enable()
        admin,user=self.admin_client()
        concept=m.FinanceConcept(name='Hotel',is_active=True)
        db.session.add(concept);db.session.commit()
        with patch('app.routes.logistics_actions_are_blocked',return_value=False), patch('app.payment_notifications.deliver_management_notification'):
            result=admin.post('/finance-requests/payment-requests',data=dict(csrf_token='test',logistics_card_id=card.id,description='Hotel reservation',concept_id=concept.id,amount='5000',currency='ARS',payment_method='Cash',payment_date_mode='asap',payee_name='Hotel Example'))
        self.assertEqual(result.status_code,302)
        payment=m.PaymentRequest.query.one()
        self.assertEqual(payment.logistics_card_id,card.id)
        self.assertEqual(payment.payee_name_snapshot,'Hotel Example')
        self.assertNotEqual(payment.payee_name_snapshot,self.person.full_name)
        page=admin.get(f'/pre-session-control-tower/logistics/payments/{payment.id}')
        self.assertEqual(page.status_code,200)
        self.assertIn(b'Hotel reservation',page.data)
        self.assertIn(payment.request_number.encode(),page.data)

    def test_card_edit_changes_modal_revision(self):
        from app.tower_live import session_revision
        card=self.enable()
        before=session_revision(self.record.id)
        card.description='New travel details';db.session.commit()
        self.assertNotEqual(session_revision(self.record.id),before)

    def test_intermediate_planner_flush_does_not_cancel_payments(self):
        card=self.enable();payment=self.payment(card)
        db.session.delete(self.assignment);db.session.flush()
        replacement=m.ExamSessionSupervisorAssignment(exam_session_id=self.record.id,team_member_id=self.person.id,logistics_enabled=True,logistics_type='Uber ride',participation_status='Pending')
        db.session.add(replacement);db.session.commit()
        self.assertTrue(card.active)
        self.assertEqual(payment.status,'Submitted')
        self.assertEqual(m.StaffLogisticsCard.query.filter_by(active=True).count(),1)

    def test_bulk_assignment_removal_also_cancels_pending_requests(self):
        card=self.enable();payment=self.payment(card)
        m.ExamSessionSupervisorAssignment.query.filter_by(id=self.assignment.id).delete(synchronize_session=False)
        db.session.commit()
        self.assertFalse(card.active)
        self.assertEqual(payment.status,'Payment cancelled')

    def test_rich_instructions_survive_save_and_reopen_safely(self):
        card=self.enable();admin,user=self.admin_client()
        url=f'/pre-session-control-tower/logistics/cards/{card.id}'
        html='<p><strong>Travel instructions</strong> <em>Arrive early</em></p><ul><li>Bring ID</li></ul><a href="https://example.com/booking" onclick="bad()">Booking</a><script>unsafe()</script>'
        data=dict(csrf_token='test',session_ids=str(self.record.id),status='Pending',links='[]',instructions_html=html)
        with patch('app.routes.logistics_actions_are_blocked',return_value=False):
            self.assertEqual(admin.post(url,data=data).status_code,200)
        self.assertIn('<strong>Travel instructions</strong>',card.instructions_html)
        self.assertIn('<em>Arrive early</em>',card.instructions_html)
        self.assertIn('<li>Bring ID</li>',card.instructions_html)
        self.assertNotIn('script',card.instructions_html)
        self.assertNotIn('onclick',card.instructions_html)
        page=admin.get(f'/pre-session-control-tower?session_year=2026&view=sessions&session_modal={self.record.id}')
        self.assertEqual(page.status_code,200)
        self.assertIn(b'<strong>Travel instructions</strong>',page.data)
        self.assertIn(b'name="instructions_html" value="&lt;p&gt;',page.data)
        with patch('app.routes.logistics_actions_are_blocked',return_value=False):
            self.assertEqual(admin.post(url,data={**data,'instructions_html':'x'*50001}).status_code,400)
        card.instructions_html='';card.description='Legacy <literal> text\nSecond line';db.session.commit()
        page=admin.get(f'/pre-session-control-tower?session_year=2026&view=sessions&session_modal={self.record.id}')
        self.assertIn(b'Legacy &lt;literal&gt; text<br>Second line',page.data)
