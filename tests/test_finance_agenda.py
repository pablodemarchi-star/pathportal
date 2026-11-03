import json
import os
import unittest
from datetime import date, datetime, timedelta
from unittest.mock import patch
from app import db
from app.finance_agenda import LOCAL_TZ, queue_daily, deliver_agenda
from app.google_mail import MailNotSent, MailDeliveryUnknown
from app.models import FinanceAgendaNotification, FinanceAgendaCoverage
from tests import test_finance_requests as fixtures


class FinanceAgendaTest(unittest.TestCase):
    setUp = fixtures.FinanceRequestsTest.setUp
    tearDown = fixtures.FinanceRequestsTest.tearDown
    create_user = fixtures.FinanceRequestsTest.create_user
    client_for = fixtures.FinanceRequestsTest.client_for
    payment = fixtures.FinanceRequestsTest.payment
    billing = fixtures.FinanceRequestsTest.billing
    today = date(2026, 11, 3)

    def deliver(self, notice_id):
        with self.app.test_request_context('/'):
            return deliver_agenda(notice_id)

    def now(self,hour=6,minute=30):
        return datetime(2026,11,3,hour,minute,tzinfo=LOCAL_TZ)

    def test_daily_combines_payments_and_invoices_once_and_excludes_nonactionable(self):
        user=self.create_user('requester@example.com')
        due=self.payment(user,status='Management approved',scheduled_payment_date=self.today)
        overdue=self.payment(user,status='Payment scheduled',scheduled_payment_date=self.today-timedelta(days=1))
        self.payment(user,status='Management approved',scheduled_payment_date=self.today+timedelta(days=1))
        self.payment(user,status='Payment completed',scheduled_payment_date=self.today)
        self.payment(user,status='Rejected',scheduled_payment_date=self.today)
        self.payment(user,status='Submitted',scheduled_payment_date=self.today)
        self.payment(user,status='Management approved',scheduled_payment_date=self.today,is_archived=True)
        invoice=self.billing(user)
        invoice.scheduled_invoice_issue_date=self.today
        future=self.billing(user)
        future.scheduled_invoice_issue_date=self.today+timedelta(days=1)
        rejected=self.billing(user,status='Rejected')
        no_date=self.billing(user)
        db.session.commit()
        with patch('app.finance_agenda.send_notification_email',return_value='gmail-id') as send:
            notice_id=queue_daily(self.now())
            self.assertTrue(self.deliver(notice_id))
            self.assertEqual(queue_daily(self.now(7)),notice_id)
            self.assertTrue(self.deliver(notice_id))
        self.assertEqual(send.call_count,1)
        self.assertEqual(send.call_args.args[0],'finance@pathexaminations.com')
        payload=json.loads(db.session.get(FinanceAgendaNotification,notice_id).payload)
        self.assertEqual({row['number'] for row in payload},{due.request_number,overdue.request_number,invoice.request_number,no_date.request_number})
        self.assertEqual(FinanceAgendaCoverage.query.count(),4)
        self.assertIn('Open Finance actions',send.call_args.args[3])

    def test_empty_days_and_before_cutoff_do_not_send(self):
        self.assertIsNone(queue_daily(self.now(6,29)))
        with patch('app.finance_agenda.send_notification_email') as send:
            notice_id=queue_daily(self.now())
            self.assertTrue(self.deliver(notice_id))
        send.assert_not_called()
        self.assertEqual(db.session.get(FinanceAgendaNotification,notice_id).status,'empty')

    def test_scheduled_today_after_cutoff_notifies_immediately_and_edits_do_not_duplicate(self):
        user=self.create_user('requester@example.com')
        admin=self.create_user('admin@example.com',is_superadmin=True)
        item=self.payment(user,status='Submitted')
        client=self.client_for(admin)
        with patch('app.finance_agenda.local_now',return_value=self.now(10)), patch('app.finance_agenda.send_notification_email',return_value='sent') as send, patch('app.routes.send_finance_scheduled_payment_email'):
            response=client.post(f'/finance-requests/payment-requests/{item.id}/management',data={
                'csrf_token':'token','action':'approve','scheduled_payment_date':self.today.strftime('%d/%m/%Y')})
            self.assertEqual(response.status_code,302)
            self.assertEqual(send.call_count,1)
            client.post(f'/finance-requests/payment-requests/{item.id}/finance',data={
                'status':'Payment scheduled','scheduled_payment_date':self.today.strftime('%d/%m/%Y')})
            self.assertEqual(send.call_count,1)
            self.assertTrue(self.deliver(queue_daily(self.now(10))))
            self.assertEqual(send.call_count,1)
        notice=FinanceAgendaNotification.query.filter_by(category='late').one()
        self.assertEqual(notice.status,'sent')

    def test_invoice_creation_after_cutoff_and_future_reschedule(self):
        user=self.create_user('requester@example.com')
        with patch('app.finance_agenda.local_now',return_value=self.now(8)),patch('app.finance_agenda.send_notification_email',return_value='sent') as send:
            self.client_for(user).post('/finance-requests/billing-requests',data={
                'concept_id':str(self.concept.id),'client_name':'Client','currency':'ARS','amount':'100',
                'client_tax_id':'20-11111111-1','vat_status_invoice_type':'Consumidor Final (factura B)',
                'scheduled_invoice_issue_date':(self.today+timedelta(days=1)).strftime('%d/%m/%Y')})
            send.assert_not_called()
            from app.models import BillingRequest
            item=BillingRequest.query.one()
            with self.app.test_request_context('/'):
                item.scheduled_invoice_issue_date=self.today
                db.session.commit()
                from app.finance_agenda import send_immediate_notices
                send_immediate_notices(self.app.response_class())
            self.assertEqual(send.call_count,1)
            self.assertIn(item.request_number,send.call_args.args[2])

    def test_before_cutoff_changes_wait_for_digest_and_late_items_are_separate(self):
        user=self.create_user('requester@example.com')
        with patch('app.finance_agenda.local_now',return_value=self.now(6,29)), self.app.test_request_context('/'):
            self.payment(user,status='Management approved',scheduled_payment_date=self.today)
        self.assertEqual(FinanceAgendaNotification.query.count(),0)
        with patch('app.finance_agenda.send_notification_email',return_value='sent') as send:
            self.deliver(queue_daily(self.now()))
            with patch('app.finance_agenda.local_now',return_value=self.now(6,31)),self.app.test_request_context('/'):
                late=self.payment(user,status='Management approved',scheduled_payment_date=self.today)
                from app.finance_agenda import send_immediate_notices
                send_immediate_notices(self.app.response_class())
            self.assertEqual(send.call_count,2)
            self.assertIn(late.request_number,send.call_args.args[2])
        self.assertEqual(FinanceAgendaCoverage.query.count(),2)

    def test_failed_delivery_can_retry_and_uncertain_delivery_is_not_repeated(self):
        user=self.create_user('requester@example.com')
        self.payment(user,status='Management approved',scheduled_payment_date=self.today)
        notice_id=queue_daily(self.now())
        with patch('app.finance_agenda.send_notification_email',side_effect=MailNotSent('not sent')):
            self.assertFalse(self.deliver(notice_id))
        self.assertEqual(db.session.get(FinanceAgendaNotification,notice_id).status,'failed')
        with patch('app.finance_agenda.send_notification_email',side_effect=MailDeliveryUnknown('unknown')):
            self.assertFalse(self.deliver(notice_id))
        with patch('app.finance_agenda.send_notification_email') as send:
            self.assertFalse(self.deliver(notice_id))
        send.assert_not_called()

    def test_rollback_does_not_queue_or_send_and_job_requires_shared_secret(self):
        user=self.create_user('requester@example.com')
        item=self.payment(user,status='Management approved',scheduled_payment_date=self.today+timedelta(days=1))
        with patch('app.finance_agenda.local_now',return_value=self.now(8)),self.app.test_request_context('/'):
            item.scheduled_payment_date=self.today
            db.session.flush()
            db.session.rollback()
            db.session.commit()
        self.assertEqual(FinanceAgendaNotification.query.count(),0)
        client=self.app.test_client()
        with patch.dict(os.environ,{'FINANCE_AGENDA_JOB_TOKEN':'s'*40}),patch('app.finance_agenda.local_now',return_value=self.now()):
            self.assertEqual(client.post('/internal/jobs/finance-agenda').status_code,403)
            self.assertEqual(client.post('/internal/jobs/finance-agenda',headers={'Authorization':'Bearer wrong'}).status_code,403)
            response=client.post('/internal/jobs/finance-agenda',headers={'Authorization':'Bearer '+'s'*40})
            self.assertEqual(response.status_code,200)
            self.assertEqual(response.json['status'],'ok')
