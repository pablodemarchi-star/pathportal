import json
import unittest
from unittest.mock import patch
from flask import Response
from app import db
from app.models import (BillingRequest, FinanceClientContact, ClientInvoiceNotification,
    FinanceCompletionNotification, GoogleDriveInvoiceUpload, GoogleDriveUpload, User)
from app.google_mail import MailNotSent, MailDeliveryUnknown
from app.payee_notifications import deliver_client_notification
from app.finance_completion import deliver_completion
from app.routes import add_billing_event
from tests import test_finance_requests as fixtures


class ClientInvoiceNotificationTest(unittest.TestCase):
    setUp = fixtures.FinanceRequestsTest.setUp
    tearDown = fixtures.FinanceRequestsTest.tearDown
    create_user = fixtures.FinanceRequestsTest.create_user
    client_for = fixtures.FinanceRequestsTest.client_for
    billing = fixtures.FinanceRequestsTest.billing
    payment = fixtures.FinanceRequestsTest.payment

    def enabled_invoice(self, language='en'):
        requester = User.query.filter_by(email='requester@example.com').first() or self.create_user('requester@example.com')
        billing = self.billing(requester)
        billing.automatic_payment_notification = True
        billing.payment_notification_email = 'client@example.com'
        billing.payment_notification_language = language
        billing.client_name_snapshot = 'External Client'
        db.session.commit()
        return billing

    def issue(self, billing, proof='https://example.com/invoice.pdf', error=None):
        finance = User.query.filter_by(email='finance@example.com').first() or self.create_user('finance@example.com', department='Finance')
        with patch('app.payee_notifications.send_notification_email', return_value='client-gmail', side_effect=error) as external, patch('app.finance_completion.send_notification_email', return_value='internal-gmail') as internal:
            response = self.client_for(finance).post(f'/finance-requests/billing-requests/{billing.id}/finance', data={
                'status':'Invoice issued', 'finance_filter':'today', 'invoice_link':proof, 'finance_comments':'PRIVATE INTERNAL COMMENT'})
        self.assertEqual(response.status_code, 302)
        return external, internal

    def form_data(self):
        return {'client_name':'Saved client', 'concept_id':str(self.concept.id), 'description':'Service invoice',
                'amount':'1200.50', 'currency':'ARS', 'client_tax_id':'30-12345678-9',
                'vat_status_invoice_type':'Consumidor Final (factura B)', 'automatic_payment_notification':'yes',
                'payment_notification_email':'client@example.com', 'payment_notification_language':'sp'}

    def test_create_remembers_client_preference_without_changing_previous_invoices(self):
        user = self.create_user('creator@example.com')
        client = self.client_for(user)
        data = self.form_data()
        self.assertEqual(client.post('/finance-requests/billing-requests', data=data).status_code, 302)
        first = BillingRequest.query.one()
        self.assertTrue(first.automatic_payment_notification)
        self.assertEqual(first.payment_notification_language, 'sp')
        contact = FinanceClientContact.query.one()
        self.assertTrue(contact.automatic_payment_notification)
        self.assertEqual(contact.payment_notification_email, 'client@example.com')
        self.assertEqual(contact.payment_notification_language, 'sp')
        page = client.get('/finance-requests?tab=billing_requests').get_data(as_text=True)
        self.assertIn('Automatic notification activated', page)
        self.assertIn('Automatic payment notification', page)
        self.assertNotIn('Contact / Client', page)
        self.assertIn('data-contact-id-field="client_contact_id"', page)
        self.assertIn('data-payment-notification-language="sp"', page)
        client.post('/finance-requests/billing-requests', data={**data, 'automatic_payment_notification':'no'})
        db.session.refresh(contact); db.session.refresh(first)
        self.assertFalse(contact.automatic_payment_notification)
        self.assertTrue(first.automatic_payment_notification)
        self.assertEqual(first.payment_notification_language, 'sp')

    def test_yes_requires_email_and_exactly_one_language(self):
        user = self.create_user('creator@example.com')
        client = self.client_for(user)
        data = self.form_data()
        for changes in ({'payment_notification_email':''}, {'payment_notification_email':'not-an-email'},
                        {'payment_notification_language':[]}, {'payment_notification_language':['en','sp']},
                        {'payment_notification_language':'fr'}):
            client.post('/finance-requests/billing-requests', data={**data, **changes})
            self.assertEqual(BillingRequest.query.count(), 0)
            self.assertEqual(FinanceClientContact.query.count(), 0)

    def test_issue_sends_localized_invoice_and_reports_client_result_internally(self):
        for language in ('en', 'sp'):
            billing = self.enabled_invoice(language)
            external, internal = self.issue(billing)
            self.assertEqual(billing.status, 'Invoice issued')
            self.assertEqual(external.call_count, 1)
            self.assertEqual(internal.call_count, 1)
            recipient, subject, text, html, _ = external.call_args.args
            self.assertEqual(recipient, 'client@example.com')
            self.assertIn('Invoice issued' if language == 'en' else 'Factura emitida', subject)
            self.assertIn('Your invoice has been issued.' if language == 'en' else 'Tu factura ha sido emitida.', text)
            self.assertIn('View invoice' if language == 'en' else 'Ver factura', html)
            self.assertNotIn('Your payment has been completed', text + html)
            self.assertNotIn('PRIVATE INTERNAL COMMENT', text + html)
            self.assertIn('The Client has been notified at client@example.com.', internal.call_args.args[2])
            notice = ClientInvoiceNotification.query.filter_by(billing_request_id=billing.id).one()
            public_url = f'/invoice-documents/{notice.receipt_token}/0'
            result = self.app.test_client().get(public_url)
            self.assertEqual(result.location, 'https://example.com/invoice.pdf')
            self.assertEqual(self.app.test_client().get(f'/payment-receipts/{notice.receipt_token}/0').status_code, 404)
            self.assertEqual(self.app.test_client().get(f'/invoice-documents/{notice.receipt_token}/9').status_code, 404)
            self.assertIn('no-store', result.headers['Cache-Control'])

    def test_failed_client_notification_retries_without_resending_requester_notice(self):
        billing = self.enabled_invoice()
        external, internal = self.issue(billing, error=MailNotSent('Unavailable'))
        self.assertEqual(external.call_count, 1)
        self.assertIn('The Client notification was not confirmed', internal.call_args.args[2])
        notice = ClientInvoiceNotification.query.one()
        self.assertEqual(notice.status, 'failed')
        with self.app.test_request_context(), patch('app.payee_notifications.send_notification_email', return_value='retry') as send, patch('app.finance_completion.send_notification_email') as requester_send:
            self.assertTrue(deliver_client_notification(notice.id))
            self.assertFalse(deliver_completion(FinanceCompletionNotification.query.one().id))
            self.assertTrue(deliver_client_notification(notice.id))
        self.assertEqual(send.call_count, 1)
        requester_send.assert_not_called()

    def test_unknown_delivery_is_not_retried(self):
        self.issue(self.enabled_invoice(), error=MailDeliveryUnknown('Timeout'))
        notice = ClientInvoiceNotification.query.one()
        self.assertEqual(notice.status, 'unknown')
        with patch('app.payee_notifications.send_notification_email') as send:
            self.assertFalse(deliver_client_notification(notice.id))
        send.assert_not_called()

    def test_no_preexisting_invoices_are_automatically_enabled(self):
        user = self.create_user('requester@example.com')
        billing = self.billing(user)
        self.assertFalse(billing.automatic_payment_notification)
        external, internal = self.issue(billing)
        external.assert_not_called()
        self.assertEqual(internal.call_count, 1)
        self.assertEqual(ClientInvoiceNotification.query.count(), 0)

    def test_drive_invoice_access_is_scoped_and_works_without_portal_login(self):
        billing = self.enabled_invoice()
        db.session.add(GoogleDriveInvoiceUpload(file_id='private-invoice', billing_request_id=billing.id,
            destination_key='finance_invoice_proofs', filename='invoice.pdf', mime_type='application/pdf'))
        db.session.commit()
        self.issue(billing, proof='https://portal.pathinternalportal.com/finance-requests/drive-documents/private-invoice')
        notice = ClientInvoiceNotification.query.one()
        with patch('app.google_drive.stream_document', return_value=Response(b'invoice', mimetype='application/pdf')) as stream:
            response = self.app.test_client().get(f'/invoice-documents/{notice.receipt_token}/0')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data, b'invoice')
        self.assertEqual(stream.call_args.args[0].billing_request_id, billing.id)
        billing.status = 'Invoice cancelled'; db.session.commit()
        self.assertEqual(self.app.test_client().get(f'/invoice-documents/{notice.receipt_token}/0').status_code, 404)

    def test_payment_files_cannot_be_shared_as_invoice_documents(self):
        billing = self.enabled_invoice()
        payment = self.payment(billing.requester)
        db.session.add(GoogleDriveUpload(file_id='another-payments-proof', payment_request_id=payment.id,
            destination_key='finance_payment_receipts', filename='payment.pdf', mime_type='application/pdf'))
        db.session.commit()
        external, internal = self.issue(billing, proof='https://portal.pathinternalportal.com/finance-requests/drive-documents/another-payments-proof')
        external.assert_not_called()
        self.assertIn('The Client notification was not confirmed', internal.call_args.args[2])
        self.assertEqual(ClientInvoiceNotification.query.one().status, 'failed')

    def test_migration_keeps_existing_invoice_and_contact_disabled(self):
        from sqlalchemy import text
        from app.schema_migrations import migrate_payee_notification_preferences
        user = self.create_user('requester@example.com')
        self.billing(user)
        db.session.add(FinanceClientContact(display_name='Legacy client'))
        db.session.commit()
        for table in ('billing_request', 'finance_client_contact'):
            for field in ('automatic_payment_notification', 'payment_notification_email', 'payment_notification_language'):
                db.session.execute(text(f'ALTER TABLE {table} DROP COLUMN {field}'))
        db.session.commit()
        migrate_payee_notification_preferences(); migrate_payee_notification_preferences()
        db.session.expire_all()
        self.assertFalse(BillingRequest.query.one().automatic_payment_notification)
        self.assertFalse(FinanceClientContact.query.one().automatic_payment_notification)
        self.assertEqual(BillingRequest.query.one().payment_notification_language, 'en')
        self.assertEqual(ClientInvoiceNotification.query.count(), 0)

    def test_rollback_never_sends_client_notification(self):
        billing = self.enabled_invoice()
        with self.app.test_request_context(), patch('app.payee_notifications.send_notification_email') as send:
            billing.status = 'Invoice issued'
            add_billing_event(billing, 'Invoice issued', previous_status='Requested', new_status='Invoice issued')
            db.session.rollback()
        self.assertEqual(ClientInvoiceNotification.query.count(), 0)
        send.assert_not_called()
