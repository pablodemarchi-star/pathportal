import json
import unittest
from datetime import date
from unittest.mock import patch
from app import db, models as m
from tests import test_staff_logistics_cards as fixtures


class StaffLogisticsSharingTest(unittest.TestCase):
    setUp=fixtures.StaffLogisticsCardsTest.setUp
    tearDown=fixtures.StaffLogisticsCardsTest.tearDown
    enable=fixtures.StaffLogisticsCardsTest.enable
    admin_client=fixtures.StaffLogisticsCardsTest.admin_client

    def other(self, name='Other session', year=2026, format_name='Onsite', kind='Carpooling', status='Pending', unavailable=False):
        record=m.ExamSession(exam_session_name=name,category='Path School',status='Pending',session_date=date(year,2,1),shifts='Morning',modules='Speaking',format=format_name)
        db.session.add(record);db.session.flush()
        assignment=m.ExamSessionSupervisorAssignment(exam_session_id=record.id,team_member_id=self.person.id,participation_status=status,logistics_enabled=kind!='Does not apply',logistics_type=kind)
        if unavailable: record.non_available_member_ids=json.dumps([str(self.person.id)])
        db.session.add(assignment);db.session.commit()
        return record

    def card_for(self, record):
        return next(card for card in m.StaffLogisticsCard.query.filter_by(active=True) if record.id in json.loads(card.session_ids))

    def payload(self, sessions, **values):
        return dict(csrf_token='test', session_year='2026',session_ids=[str(row.id) for row in sessions],status='Completed',description='Current instructions',links='[]',**values)

    def save(self, admin, card, data):
        with patch('app.routes.logistics_actions_are_blocked',return_value=False):
            return admin.post(f'/pre-session-control-tower/logistics/cards/{card.id}',data=data)

    def payment(self, card, number, paid=False):
        concept=m.FinanceConcept.query.first()
        if concept is None:
            concept=m.FinanceConcept(name='Travel',is_active=True);db.session.add(concept);db.session.flush()
        payment=m.PaymentRequest(request_number=number,description='Travel',concept_id=concept.id,concept_name_snapshot='Travel',amount=100,currency='ARS',payment_method='Cash',status='Payment completed' if paid else 'Submitted',logistics_card_id=card.id)
        db.session.add(payment);db.session.commit();return payment

    def test_dropdown_uses_filtered_year_and_all_eligible_formats(self):
        self.enable();peer=self.other('Past non-concatenated centre session',format_name='Online at exam centre')
        self.other('Future-year hidden',year=2027)
        self.other('Online hidden',format_name='Online')
        self.other('Does not apply hidden',kind='Does not apply')
        self.other('Declined hidden',status='Declined')
        self.other('Unavailable hidden',unavailable=True)
        admin,_=self.admin_client()
        html=admin.get(f'/pre-session-control-tower?session_year=2026&view=sessions&session_modal={self.record.id}').get_data(as_text=True)
        picker=html.split('data-logistics-session-picker',1)[1].split('</details>',1)[0]
        self.assertIn(peer.exam_session_name,picker)
        for excluded in ('Future-year hidden','Online hidden','Does not apply hidden','Declined hidden','Unavailable hidden'):
            self.assertNotIn(excluded,picker)
        self.assertIn('Choose one or more sessions from 2026',html)

    def test_single_eligible_session_has_no_dropdown(self):
        self.enable();admin,_=self.admin_client()
        html=admin.get(f'/pre-session-control-tower?session_year=2026&view=sessions&session_modal={self.record.id}').get_data(as_text=True)
        self.assertNotIn('data-logistics-session-picker',html)

    def test_conflict_does_not_change_data_and_keeps_source_when_confirmed(self):
        source=self.enable();peer=self.other();other=self.card_for(peer)
        source.description='Source';other.description='Other';db.session.commit()
        pending=self.payment(other,'PAY-101');paid=self.payment(other,'PAY-102',True)
        admin,_=self.admin_client();data=self.payload([self.record,peer])
        response=self.save(admin,source,data)
        self.assertEqual(response.status_code,409,response.data)
        self.assertEqual(response.json['code'],'logistics_card_conflict')
        self.assertEqual({row['id'] for row in response.json['cards']},{source.id,other.id})
        self.assertTrue(other.active);self.assertEqual(pending.status,'Submitted');self.assertEqual(source.description,'Source')
        data.update(conflict_token=response.json['conflict_token'],keep_card_id=str(source.id))
        self.assertEqual(self.save(admin,source,data).status_code,200)
        self.assertFalse(other.active);self.assertEqual(source.description,'Current instructions')
        self.assertEqual(source.status,'Pending')
        self.assertEqual(pending.status,'Payment cancelled');self.assertEqual(paid.status,'Payment completed');self.assertIn('already completed',paid.logistics_alert)
        self.assertEqual(set(json.loads(source.session_ids)),{self.record.id,peer.id})
        # A later staffing save must keep a non-concatenated shared card intact.
        self.assignment.logistics_type='Complex Uber ride';db.session.commit()
        self.assertEqual(m.StaffLogisticsCard.query.filter_by(active=True).count(),1)
        self.assertEqual(set(json.loads(source.session_ids)),{self.record.id,peer.id})

    def test_keep_other_card_preserves_its_content_and_payments(self):
        source=self.enable();peer=self.other();other=self.card_for(peer)
        other.description='Retain these instructions';other.instructions_html='<b>Retain</b>';other.links='[{"name":"Hotel","url":"https://example.com"}]';db.session.commit()
        discarded=self.payment(source,'PAY-201');retained=self.payment(other,'PAY-202')
        admin,_=self.admin_client();data=self.payload([self.record,peer])
        response=self.save(admin,source,data)
        data.update(conflict_token=response.json['conflict_token'],keep_card_id=str(other.id))
        result=self.save(admin,source,data)
        self.assertEqual(result.status_code,200,result.data)
        self.assertFalse(source.active);self.assertTrue(other.active)
        self.assertEqual(other.description,'Retain these instructions');self.assertEqual(other.instructions_html,'<b>Retain</b>')
        self.assertEqual(len(json.loads(other.links)),1)
        self.assertEqual(discarded.status,'Payment cancelled');self.assertEqual(retained.status,'Submitted')

    def test_stale_confirmation_cannot_discard_changed_card(self):
        source=self.enable();peer=self.other();other=self.card_for(peer)
        admin,_=self.admin_client();data=self.payload([self.record,peer])
        response=self.save(admin,source,data)
        other.description='Changed by another user';db.session.commit()
        data.update(conflict_token=response.json['conflict_token'],keep_card_id=str(source.id))
        result=self.save(admin,source,data)
        self.assertEqual(result.status_code,409)
        self.assertNotEqual(result.json['conflict_token'],data['conflict_token'])
        self.assertTrue(other.active)

    def test_cross_year_and_ineligible_selections_are_rejected(self):
        source=self.enable();other=self.other(year=2027);excluded=self.other(kind='Does not apply')
        admin,_=self.admin_client()
        for row in (other,excluded):
            self.assertEqual(self.save(admin,source,self.payload([self.record,row])).status_code,400)

    def test_payment_completed_during_confirmation_requires_another_review(self):
        source=self.enable();peer=self.other();other=self.card_for(peer)
        payment=self.payment(other,'PAY-301')
        admin,_=self.admin_client();data=self.payload([self.record,peer])
        preview=self.save(admin,source,data).json
        payment.status='Payment completed';db.session.commit()
        data.update(conflict_token=preview['conflict_token'],keep_card_id=str(source.id))
        response=self.save(admin,source,data)
        self.assertEqual(response.status_code,409)
        self.assertTrue(other.active);self.assertEqual(payment.status,'Payment completed')
        data['conflict_token']=response.json['conflict_token']
        self.assertEqual(self.save(admin,source,data).status_code,200)
        self.assertEqual(payment.status,'Payment completed')
        self.assertIn('already completed',payment.logistics_alert)

    def test_excluded_sessions_stay_excluded_after_merge_and_assignment_save(self):
        source=self.enable();peer=self.other();admin,_=self.admin_client()
        data=self.payload([self.record,peer]);response=self.save(admin,source,data)
        data.update(conflict_token=response.json['conflict_token'],keep_card_id=str(source.id))
        self.assertEqual(self.save(admin,source,data).status_code,200)
        data=self.payload([peer]);self.assertEqual(self.save(admin,source,data).status_code,200)
        self.assignment.logistics_type='Complex Uber ride';db.session.commit()
        self.assertEqual(m.StaffLogisticsCard.query.filter_by(active=True).count(),1)
        self.assertEqual(json.loads(source.session_ids),[peer.id])
