import json
import unittest
from unittest.mock import patch
from werkzeug.security import generate_password_hash
from app import db
from app.models import FinanceCompletionNotification
from app.finance_completion import deliver_completion
from app.google_mail import MailNotSent, MailDeliveryUnknown
from app.routes import payment_whatsapp_copy_contract, billing_whatsapp_copy_contract, add_payment_event
from tests import test_finance_requests as fixtures


class FinanceCompletionTest(unittest.TestCase):
    setUp = fixtures.FinanceRequestsTest.setUp
    tearDown = fixtures.FinanceRequestsTest.tearDown
    create_user = fixtures.FinanceRequestsTest.create_user
    client_for = fixtures.FinanceRequestsTest.client_for
    payment = fixtures.FinanceRequestsTest.payment
    billing = fixtures.FinanceRequestsTest.billing

    def test_payment_and_invoice_notify_requester_once_with_exact_copy_messages(self):
        requester = self.create_user('requester@example.com')
        finance = self.create_user('finance@example.com', department='Finance')
        client = self.client_for(finance)
        for kind in ('payment', 'invoice'):
            with self.subTest(kind=kind):
                item = self.payment(requester, status='Management approved') if kind == 'payment' else self.billing(requester)
                if kind == 'payment':
                    item.payee_name_snapshot = 'Payee'
                    db.session.commit()
                url = f"/finance-requests/{'payment' if kind == 'payment' else 'billing'}-requests/{item.id}/finance"
                data = {'status': 'Payment completed' if kind == 'payment' else 'Invoice issued', 'finance_filter': 'today',
                        'payment_proof_url' if kind == 'payment' else 'invoice_link': 'https://example.com/proof.pdf'}
                with patch('app.finance_completion.send_notification_email', return_value='gmail-id') as send:
                    self.assertEqual(client.post(url, data=data).status_code, 302)
                    self.assertEqual(client.post(url, data=data).status_code, 302)
                self.assertEqual(send.call_count, 1)
                recipient, subject, text, html, message_id = send.call_args.args
                self.assertEqual(recipient, requester.email)
                self.assertIn('completed', subject)
                self.assertIn('>EN</a>', html)
                self.assertIn('>SP</a>', html)
                notice = FinanceCompletionNotification.query.filter_by(request_kind=kind, request_id=item.id).one()
                self.assertEqual(notice.status, 'sent')
                contract = payment_whatsapp_copy_contract if kind == 'payment' else billing_whatsapp_copy_contract
                payload = json.loads(notice.payload)
                self.assertEqual(payload['en'], contract(item, 'en'))
                self.assertEqual(payload['sp'], contract(item, 'sp'))
                self.assertTrue(payload['en']['message'])
                for language in ('en', 'sp'):
                    page = self.client_for(requester).get(f'/finance-requests/completion/{notice.id}/{language}')
                    self.assertEqual(page.status_code, 200)
                    self.assertIn('data-copy-text=', page.get_data(as_text=True))
                    self.assertEqual(page.headers['Cache-Control'], 'private, no-store')
                stranger = self.create_user(f'{kind}-other@example.com')
                self.assertEqual(self.client_for(stranger).get(f'/finance-requests/completion/{notice.id}/en').status_code, 404)

    def test_rejections_and_discrepancies_notify_requester_in_both_kinds(self):
        requester = self.create_user('requester@example.com')
        reviewer = self.create_user('reviewer@example.com', is_superadmin=True)
        for kind in ('payment', 'invoice'):
            for status, label, action in (('Rejected', 'Rejected', 'reject'), ('Needs correction', 'With discrepancy', 'needs_correction')):
                with self.subTest(kind=kind, status=status):
                    item = self.payment(requester) if kind == 'payment' else self.billing(requester)
                    if kind == 'payment':
                        item.payee_name_snapshot = 'Payee'
                        item.amount = 0
                        db.session.commit()
                    url = f'/finance-requests/payment-requests/{item.id}/management' if kind == 'payment' else f'/finance-requests/billing-requests/{item.id}/finance'
                    data = {'csrf_token': 'token', 'action': action, 'management_comments': 'Please correct <bank details>.'} if kind == 'payment' else {
                        'finance_filter': 'today', 'status': status,
                    }
                    with patch('app.finance_completion.send_notification_email', return_value='sent') as send:
                        response = self.client_for(reviewer).post(url, data=data)
                    self.assertEqual(response.status_code,302)
                    self.assertEqual(send.call_count,1)
                    notice = FinanceCompletionNotification.query.filter_by(request_kind=kind,request_id=item.id).one()
                    payload = json.loads(notice.payload)
                    self.assertEqual(payload['status'],label)
                    self.assertEqual(send.call_args.args[0],requester.email)
                    self.assertIn(label.lower(),send.call_args.args[1])
                    self.assertIn('>EN</a>',send.call_args.args[3])
                    self.assertIn('>SP</a>',send.call_args.args[3])
                    self.assertNotIn('request is complete.',send.call_args.args[3])
                    if kind == 'payment':
                        self.assertEqual(payload['amount'],'Amount pending')
                        self.assertIn('Please correct &lt;bank details&gt;.',send.call_args.args[3])
                    contract = payment_whatsapp_copy_contract if kind == 'payment' else billing_whatsapp_copy_contract
                    self.assertEqual(payload['en'],contract(item,'en'))
                    self.assertEqual(payload['sp'],contract(item,'sp'))

    def test_discrepancy_then_resubmission_can_notify_again_and_complete(self):
        user = self.create_user('requester@example.com')
        item = self.payment(user)
        item.payee_name_snapshot = 'Payee'
        db.session.commit()
        with self.app.test_request_context('/'):
            for previous,status in [('Submitted','Needs correction'),('Resubmitted','Needs correction'),('Management approved','Payment completed')]:
                item.status = status
                if status == 'Payment completed':
                    item.payment_proof_url = 'https://example.com/proof.pdf'
                add_payment_event(item,status,previous_status=previous,new_status=status,comment='Details')
                db.session.commit()
            self.assertEqual(FinanceCompletionNotification.query.count(),3)
            add_payment_event(item,'Payment completed',previous_status='Payment completed',new_status='Payment completed')
            db.session.commit()
            self.assertEqual(FinanceCompletionNotification.query.count(),3)

    def test_failed_or_uncertain_email_does_not_revert_completion_and_retry_is_safe(self):
        requester = self.create_user('requester@example.com')
        finance = self.create_user('finance@example.com', department='Finance')
        for error, expected in ((MailNotSent('not sent'), 'failed'), (MailDeliveryUnknown('uncertain'), 'unknown')):
            item = self.payment(requester, status='Management approved')
            item.payee_name_snapshot = 'Payee'
            db.session.commit()
            with patch('app.finance_completion.send_notification_email', side_effect=error):
                self.client_for(finance).post(f'/finance-requests/payment-requests/{item.id}/finance', data={
                    'status': 'Payment completed', 'payment_proof_url': 'https://example.com/proof.pdf'})
            db.session.refresh(item)
            self.assertEqual(item.status, 'Payment completed')
            notice = FinanceCompletionNotification.query.filter_by(request_id=item.id).one()
            self.assertEqual(notice.status, expected)
            with self.app.test_request_context('/'), patch('app.finance_completion.send_notification_email', return_value='retry') as send:
                self.assertEqual(deliver_completion(notice.id), expected == 'failed')
            self.assertEqual(send.call_count, 1 if expected == 'failed' else 0)

    def test_rollback_and_non_completed_status_do_not_send(self):
        requester = self.create_user('requester@example.com')
        item = self.payment(requester)
        with self.app.test_request_context('/'):
            item.status = 'Payment completed'
            add_payment_event(item, 'Payment completed', previous_status='Submitted', new_status='Payment completed')
            self.assertEqual(FinanceCompletionNotification.query.count(), 1)
            db.session.rollback()
            self.assertEqual(FinanceCompletionNotification.query.count(), 0)
        finance = self.create_user('finance@example.com', department='Finance')
        with patch('app.finance_completion.send_notification_email') as send:
            self.client_for(finance).post(f'/finance-requests/payment-requests/{item.id}/finance', data={
                'status': 'Payment cancelled'})
        send.assert_not_called()

    def test_email_copy_link_survives_login(self):
        requester = self.create_user('requester@example.com')
        requester.password_hash = generate_password_hash('test-password', method='pbkdf2:sha256')
        finance = self.create_user('finance@example.com', department='Finance')
        item = self.payment(requester, status='Management approved')
        item.payee_name_snapshot = 'Payee'
        db.session.commit()
        with patch('app.finance_completion.send_notification_email', return_value='sent'):
            self.client_for(finance).post(f'/finance-requests/payment-requests/{item.id}/finance', data={
                'status': 'Payment completed', 'payment_proof_url': 'https://example.com/proof.pdf'})
        notice = FinanceCompletionNotification.query.one()
        client = self.app.test_client()
        path = f'/finance-requests/completion/{notice.id}/sp'
        self.assertEqual(client.get(path).status_code, 302)
        response = client.post('/login', data={'email': requester.email, 'password': 'test-password'})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers['Location'], path)
