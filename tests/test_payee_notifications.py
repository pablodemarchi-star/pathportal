import json
import unittest
from unittest.mock import patch
from flask import Response
from app import db
from app.google_mail import MailNotSent, MailDeliveryUnknown
from app.models import PaymentRequest, FinanceContact, PayeePaymentNotification, FinanceCompletionNotification, GoogleDriveUpload
from app.payee_notifications import deliver_payee_notification
from app.finance_completion import deliver_completion
from app.routes import add_payment_event
from tests import test_finance_requests as fixtures


class PayeeNotificationTest(unittest.TestCase):
    setUp = fixtures.FinanceRequestsTest.setUp
    tearDown = fixtures.FinanceRequestsTest.tearDown
    create_user = fixtures.FinanceRequestsTest.create_user
    client_for = fixtures.FinanceRequestsTest.client_for
    payment = fixtures.FinanceRequestsTest.payment

    def enabled_payment(self):
        requester = self.create_user('requester@example.com')
        payment = self.payment(requester, status='Management approved')
        payment.automatic_payment_notification = True
        payment.payment_notification_email = 'payee@example.com'
        payment.payee_name_snapshot = 'External Payee'
        db.session.commit()
        return payment

    def complete(self, payment, proof='https://example.com/receipt.pdf', payee_error=None):
        finance = self.create_user('finance@example.com', department='Finance')
        client = self.client_for(finance)
        with patch('app.payee_notifications.send_notification_email', side_effect=payee_error, return_value='payee-gmail') as external, patch('app.finance_completion.send_notification_email', return_value='internal-gmail') as internal:
            result = client.post(f'/finance-requests/payment-requests/{payment.id}/finance', data={
                'status':'Payment completed', 'payment_proof_url':proof, 'finance_comments':'INTERNAL PRIVATE NOTE'})
        self.assertEqual(result.status_code, 302)
        return external, internal

    def test_creation_preferences_and_existing_request_snapshot(self):
        user = self.create_user('creator@example.com', department='Finance')
        client = self.client_for(user)
        data = {'payee_name':'Saved Payee', 'concept_id':str(self.concept.id), 'description':'Payment service',
                'amount':'100', 'currency':'ARS', 'payment_method':'Cash', 'payment_date_mode':'asap',
                'automatic_payment_notification':'yes', 'payment_notification_email':'payee@example.com'}
        for tab in ('payment_requests', 'finance_payments'):
            response = client.post('/finance-requests/payment-requests', data={**data, 'source_tab':tab})
            self.assertEqual(response.status_code, 302)
            item = PaymentRequest.query.order_by(PaymentRequest.id.desc()).first()
            self.assertTrue(item.automatic_payment_notification)
            self.assertEqual(item.payment_notification_email, 'payee@example.com')
        contact = FinanceContact.query.filter_by(display_name='Saved Payee').one()
        self.assertTrue(contact.automatic_payment_notification)
        original = PaymentRequest.query.first()
        client.post('/finance-requests/payment-requests', data={**data, 'automatic_payment_notification':'no'})
        db.session.refresh(contact); db.session.refresh(original)
        self.assertFalse(contact.automatic_payment_notification)
        self.assertIsNone(contact.payment_notification_email)
        self.assertTrue(original.automatic_payment_notification)
        viewer = self.create_user('manager@example.com', is_superadmin=True)
        html = self.client_for(viewer).get('/finance-requests?tab=management_review').get_data(as_text=True)
        self.assertIn('Automatic notification activated', html)
        self.assertIn('Automatic payment notification', html)
        self.assertNotIn('Contact / Payee', html)
        self.assertIn('data-payment-notification="no"', html)

    def test_invalid_email_does_not_save_payment_or_preference(self):
        user = self.create_user('creator@example.com')
        for email in ('', 'invalid', 'payee@example.com,', 'name@example.com\nBcc: other@example.com'):
            response = self.client_for(user).post('/finance-requests/payment-requests', data={
                'payee_name':'Payee', 'concept_id':str(self.concept.id), 'description':'Service',
                'amount':'100', 'currency':'ARS', 'payment_method':'Cash',
                'automatic_payment_notification':'yes', 'payment_notification_email':email})
            self.assertEqual(response.status_code, 302)
        self.assertEqual(PaymentRequest.query.count(), 0)
        self.assertEqual(FinanceContact.query.count(), 0)

    def test_completed_sends_external_and_internal_emails_and_private_receipt(self):
        payment = self.enabled_payment()
        external, internal = self.complete(payment)
        self.assertEqual(external.call_count, 1)
        self.assertEqual(internal.call_count, 1)
        recipient, _, text, html, _ = external.call_args.args
        self.assertEqual(recipient, 'payee@example.com')
        self.assertIn('External Payee', text)
        self.assertIn('ARS 100.00', text)
        self.assertIn('View payment receipt', html)
        self.assertNotIn('INTERNAL PRIVATE NOTE', text + html)
        self.assertIn('The Payee has been notified at payee@example.com.', internal.call_args.args[2])
        self.assertIn('The Payee has been notified', internal.call_args.args[3])
        notice = PayeePaymentNotification.query.one()
        public = self.app.test_client()
        response = public.get(f'/payment-receipts/{notice.receipt_token}/0')
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.location, 'https://example.com/receipt.pdf')
        self.assertEqual(public.get(f'/payment-receipts/{notice.receipt_token}/1').status_code, 404)
        self.assertEqual(public.get('/payment-receipts/invalid-token/0').status_code, 404)
        payment.status = 'Payment cancelled'; db.session.commit()
        self.assertEqual(public.get(f'/payment-receipts/{notice.receipt_token}/0').status_code, 404)

    def test_failed_payee_retry_does_not_repeat_internal_notification(self):
        payment = self.enabled_payment()
        external, internal = self.complete(payment, payee_error=MailNotSent('Unavailable'))
        self.assertEqual(external.call_count, 1)
        self.assertEqual(internal.call_count, 1)
        self.assertIn('not confirmed', internal.call_args.args[2])
        notice = PayeePaymentNotification.query.one()
        self.assertEqual(notice.status, 'failed')
        with self.app.test_request_context(), patch('app.payee_notifications.send_notification_email', return_value='retry-success') as retry, patch('app.finance_completion.send_notification_email') as requester_send:
            self.assertTrue(deliver_payee_notification(notice.id))
            self.assertFalse(deliver_completion(FinanceCompletionNotification.query.one().id))
            self.assertTrue(deliver_payee_notification(notice.id))
        self.assertEqual(retry.call_count, 1)
        requester_send.assert_not_called()

    def test_unknown_delivery_is_never_retried(self):
        self.complete(self.enabled_payment(), payee_error=MailDeliveryUnknown('Timeout'))
        notice = PayeePaymentNotification.query.one()
        self.assertEqual(notice.status, 'unknown')
        with patch('app.payee_notifications.send_notification_email') as send:
            self.assertFalse(deliver_payee_notification(notice.id))
        send.assert_not_called()

    def test_no_and_legacy_requests_do_not_send_payee_notices(self):
        requester = self.create_user('requester@example.com')
        payment = self.payment(requester, status='Management approved')
        self.assertFalse(payment.automatic_payment_notification)
        external, internal = self.complete(payment)
        external.assert_not_called()
        self.assertEqual(internal.call_count, 1)
        self.assertEqual(PayeePaymentNotification.query.count(), 0)

    def test_drive_receipt_is_scoped_to_the_payment_without_portal_signin(self):
        payment = self.enabled_payment()
        db.session.add(GoogleDriveUpload(file_id='private-drive-receipt', payment_request_id=payment.id,
            destination_key='finance_payment_receipts', filename='receipt.pdf', mime_type='application/pdf'))
        db.session.commit()
        self.complete(payment, proof='https://portal.pathinternalportal.com/finance-requests/drive-documents/private-drive-receipt')
        notice = PayeePaymentNotification.query.one()
        with patch('app.google_drive.stream_document', return_value=Response(b'receipt', mimetype='application/pdf')) as stream:
            response = self.app.test_client().get(f'/payment-receipts/{notice.receipt_token}/0')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data, b'receipt')
        self.assertEqual(stream.call_args.args[0].payment_request_id, payment.id)
        self.assertIn('no-store', response.headers['Cache-Control'])

    def test_existing_rows_migrate_to_no_without_notifications(self):
        from sqlalchemy import text
        from app.schema_migrations import migrate_payee_notification_preferences
        user = self.create_user('legacy@example.com')
        self.payment(user)
        db.session.add(FinanceContact(display_name='Legacy Payee'))
        db.session.commit()
        for table in ('payment_request', 'finance_contact'):
            db.session.execute(text(f'ALTER TABLE {table} DROP COLUMN automatic_payment_notification'))
            db.session.execute(text(f'ALTER TABLE {table} DROP COLUMN payment_notification_email'))
        db.session.commit()
        migrate_payee_notification_preferences()
        migrate_payee_notification_preferences()
        db.session.expire_all()
        self.assertFalse(PaymentRequest.query.one().automatic_payment_notification)
        self.assertFalse(FinanceContact.query.one().automatic_payment_notification)
        self.assertIsNone(PaymentRequest.query.one().payment_notification_email)
        self.assertEqual(PayeePaymentNotification.query.count(), 0)

    def test_receipt_cannot_expose_other_payment_files_or_supporting_documents(self):
        payment = self.enabled_payment()
        db.session.add(GoogleDriveUpload(file_id='supporting-file', payment_request_id=payment.id,
            destination_key='finance_supporting_documents', filename='private.pdf', mime_type='application/pdf'))
        db.session.commit()
        external, internal = self.complete(payment, proof='https://portal.pathinternalportal.com/finance-requests/drive-documents/supporting-file')
        external.assert_not_called()
        self.assertIn('not confirmed', internal.call_args.args[2])
        self.assertEqual(PayeePaymentNotification.query.one().status, 'failed')

    def test_multiple_receipts_are_individual_private_links(self):
        payment = self.enabled_payment()
        external, _ = self.complete(payment, proof='https://example.com/one.pdf\nhttps://example.com/two.pdf')
        self.assertEqual(external.call_count, 1)
        notice = PayeePaymentNotification.query.one()
        public = self.app.test_client()
        for index, name in enumerate(('one', 'two')):
            response = public.get(f'/payment-receipts/{notice.receipt_token}/{index}')
            self.assertEqual(response.location, f'https://example.com/{name}.pdf')

    def test_local_receipt_download_is_limited_to_this_payment_folder(self):
        from pathlib import Path
        import tempfile
        payment = self.enabled_payment()
        with tempfile.TemporaryDirectory() as folder, patch('app.routes.finance_upload_root', return_value=folder):
            relative = f'payment_proofs/{payment.request_number}/receipt.pdf'
            file = Path(folder) / relative
            file.parent.mkdir(parents=True)
            file.write_bytes(b'private local receipt')
            external, _ = self.complete(payment, proof='https://portal.pathinternalportal.com/finance-requests/uploads/' + relative)
            self.assertEqual(external.call_count, 1)
            notice = PayeePaymentNotification.query.one()
            response = self.app.test_client().get(f'/payment-receipts/{notice.receipt_token}/0')
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.data, b'private local receipt')
            self.assertTrue(response.headers['Content-Disposition'].startswith('attachment'))
            response.close()

    def test_rejected_or_discrepancy_does_not_notify_payee(self):
        payment = self.enabled_payment()
        with self.app.test_request_context():
            for status in ('Rejected', 'Needs correction'):
                payment.status = status
                add_payment_event(payment, status, previous_status='Submitted', new_status=status)
            db.session.commit()
        self.assertEqual(PayeePaymentNotification.query.count(), 0)

    def test_duplicate_transition_cannot_queue_another_payee_notice(self):
        from app.payee_notifications import queue_payee_notification
        payment = self.enabled_payment()
        self.complete(payment)
        notice = PayeePaymentNotification.query.one()
        with self.app.test_request_context(), patch('app.payee_notifications.send_notification_email') as send:
            from types import SimpleNamespace
            result = queue_payee_notification(payment, 'Management approved', 'Payment completed', SimpleNamespace(id=notice.event_id))
            self.assertEqual(result, notice.id)
            self.assertTrue(deliver_payee_notification(notice.id))
        self.assertEqual(PayeePaymentNotification.query.count(), 1)
        send.assert_not_called()

    def test_rollback_does_not_send_or_persist_external_notifications(self):
        payment = self.enabled_payment()
        with self.app.test_request_context(), patch('app.payee_notifications.send_notification_email') as send:
            payment.status = 'Payment completed'
            add_payment_event(payment, 'Payment completed', previous_status='Management approved', new_status='Payment completed')
            db.session.rollback()
        self.assertEqual(PayeePaymentNotification.query.count(), 0)
        send.assert_not_called()
