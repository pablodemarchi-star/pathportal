import json
import unittest
from datetime import date
from unittest.mock import patch

from app import db
from app.finance_numbering import next_number, next_identity
from app.models import PaymentRequest, BillingRequest, PaymentRequestEvent, FinanceAgendaNotification, FinanceAgendaCoverage
from tests import test_finance_requests as fixtures


class FinanceNumberingTest(unittest.TestCase):
    setUp = fixtures.FinanceRequestsTest.setUp
    tearDown = fixtures.FinanceRequestsTest.tearDown
    create_user = fixtures.FinanceRequestsTest.create_user
    client_for = fixtures.FinanceRequestsTest.client_for
    payment = fixtures.FinanceRequestsTest.payment

    def test_created_request_numbers_and_ids_survive_deleting_all_requests(self):
        user = self.create_user('numbering@example.com')
        client = self.client_for(user)
        for kind, model in [('payment', PaymentRequest), ('invoice', BillingRequest)]:
            with self.subTest(kind=kind), patch('app.routes.today_local', return_value=date(2026,11,3)):
                path = '/finance-requests/payment-requests' if kind == 'payment' else '/finance-requests/billing-requests'
                data = {'concept_id':str(self.concept.id), 'currency':'ARS', 'amount':'100',
                    'description':'Unique request', 'payment_method':'Cash', 'client_name':'Client',
                    'client_tax_id':'20-11111111-1', 'vat_status_invoice_type':'Consumidor Final (factura B)'}
                self.assertEqual(client.post(path,data=data).status_code,302)
                first = model.query.one()
                first_number, first_id = first.request_number, first.id
                event_id = first.events[0].id
                # A real deletion leaves counters intact, even if there are no requests left.
                db.session.delete(first);db.session.commit()
                self.assertEqual(client.post(path,data=data).status_code,302)
                second = model.query.one()
                self.assertNotEqual(second.request_number,first_number)
                self.assertGreater(second.id,first_id)
                self.assertGreater(second.events[0].id,event_id)
                self.assertTrue(second.request_number.endswith('0002'))

    def test_deleting_legacy_request_before_first_allocation_reserves_its_number(self):
        user=self.create_user('legacy-delete@example.com')
        payment=self.payment(user)
        payment.request_number='PAY-2026-0090'
        db.session.commit()
        self.assertEqual(self.client_for(user).post(f'/finance-requests/payment-requests/{payment.id}/delete').status_code,302)
        self.assertEqual(next_number(PaymentRequest,'PAY',2026),'PAY-2026-0091')
        self.assertGreater(next_identity(PaymentRequest),payment.id)

    def test_seed_recovers_deleted_number_from_email_and_keeps_legacy_invoice_sequence(self):
        notice=FinanceAgendaNotification(notice_key='historical',category='late',agenda_date=date(2026,11,3),
            payload=json.dumps([{'number':'PAY-2026-0090'},{'number':'INVOICE-2026-0040'}]),status='sent')
        db.session.add(notice);db.session.commit()
        self.assertEqual(next_number(PaymentRequest,'PAY',2026),'PAY-2026-0091')
        self.assertEqual(next_number(BillingRequest,'INVOICE',2026,('BILL',)),'INVOICE-2026-0041')
        db.session.commit()
        # Deleting history after initialization must not rewind the persistent sequence.
        db.session.delete(notice);db.session.commit()
        self.assertEqual(next_number(PaymentRequest,'PAY',2026),'PAY-2026-0092')
        self.assertEqual(next_number(PaymentRequest,'PAY',2027),'PAY-2027-0001')

    def test_numeric_maximum_is_used_beyond_four_digits(self):
        user=self.create_user('numeric@example.com')
        first=self.payment(user);first.request_number='PAY-2026-9999'
        second=self.payment(user);second.request_number='PAY-2026-10000'
        db.session.commit()
        self.assertEqual(next_number(PaymentRequest,'PAY',2026),'PAY-2026-10001')

    def test_deleted_identity_in_agenda_is_never_assigned_to_new_request(self):
        notice=FinanceAgendaNotification(notice_key='historical',category='late',agenda_date=date(2026,11,3),payload='[]',status='sent')
        db.session.add(notice);db.session.flush()
        db.session.add(FinanceAgendaCoverage(agenda_date=date(2026,11,3),request_kind='payment',request_id=90,notification_id=notice.id))
        db.session.commit()
        self.assertEqual(next_identity(PaymentRequest),91)
        db.session.commit()
        self.assertEqual(next_identity(PaymentRequest),92)
