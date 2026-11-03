import io
import unittest
from datetime import date
from unittest.mock import patch
from app import db
from app.models import (AcademicStaff, ExamSession, ExamSessionSupervisorAssignment, StaffExamSessionsShare,
    StaffExamSessionSubmission, GoogleDriveStaffInvoiceUpload, GoogleDriveDestination, StaffPaymentSettings)
from tests import test_google_drive as drive


class StaffInvoiceUploadTest(unittest.TestCase):
    setUpBase = drive.GoogleDriveTest.setUpBase
    tearDownBase = drive.GoogleDriveTest.tearDownBase
    setUpDrive = drive.GoogleDriveTest.setUp
    tearDown = drive.GoogleDriveTest.tearDown
    api = drive.GoogleDriveTest.api
    http = drive.GoogleDriveTest.http
    folder = drive.GoogleDriveTest.folder

    def setUp(self):
        self.setUpDrive()
        self.person=AcademicStaff(full_name='Staff Invoice',status='Active',roles='Supervisor')
        self.record=ExamSession(exam_session_name='Invoice session',category='Path School',status='Pending',
            session_date=date(2026,11,3),shifts='Morning',modules='Speaking',format='Online')
        db.session.add_all([self.person,self.record]);db.session.flush()
        self.assignment=ExamSessionSupervisorAssignment(exam_session_id=self.record.id,team_member_id=self.person.id,
            participation_status='Confirmed',logistics_type='Does not apply',start_time='09:00',end_time='10:00')
        self.share=StaffExamSessionsShare(person_ref=str(self.person.id),token='private-staff-invoice-token')
        db.session.add_all([self.assignment,self.share]);db.session.flush()
        db.session.add(StaffExamSessionSubmission(share_id=self.share.id,exam_session_id=self.record.id,
            assignment_type='supervisor',assignment_id=self.assignment.id))
        settings=StaffPaymentSettings.query.first()
        if settings is None:
            settings=StaffPaymentSettings();db.session.add(settings)
        settings.next_payment_date=date(2026,12,29)
        db.session.commit()
        self.folder('staff_portal_invoices','1_VrUoXNBbVT_hSo_vAbL7prSj8hBAUNV')
        self.portal=self.app.test_client()
        self.page=f'/my-exam-sessions/{self.share.token}?session_year=2026'
        self.endpoint=f'/my-exam-sessions/{self.share.token}/invoices'
        self.portal.get(self.page)
        with self.portal.session_transaction() as state:
            self.csrf=state['csrf_token']

    def upload(self,files=None,csrf=None,year='2026'):
        return self.portal.post(self.endpoint,data={'csrf_token':csrf if csrf is not None else self.csrf,
            'session_year':year,'invoice_file':files if files is not None else (io.BytesIO(b'%PDF-invoice'),'invoice.pdf')},
            content_type='multipart/form-data',follow_redirects=True)

    def test_one_file_reaches_authorized_drive_folder_and_is_private(self):
        response=self.upload()
        self.assertEqual(response.status_code,200)
        document=GoogleDriveStaffInvoiceUpload.query.one()
        self.assertEqual(document.share_id,self.share.id)
        self.assertEqual(document.year,2026)
        self.assertEqual(self.metadata[-1]['parents'],['1_VrUoXNBbVT_hSo_vAbL7prSj8hBAUNV'])
        html=response.get_data(as_text=True)
        self.assertIn('Your invoice was uploaded successfully.',html)
        self.assertIn('29/12/2026 at 5:00 pm (GMT-3)',html)
        self.assertIn('at least two business days before',html)
        self.assertNotIn('View sample invoice',html)
        self.assertNotIn('name="invoice_file" multiple',html)
        url=f'/my-exam-sessions/{self.share.token}/invoices/{document.file_id}'
        with self.portal.get(url) as opened:
            self.assertEqual(opened.data,b'private document')
            self.assertEqual(opened.headers['Cache-Control'],'private, no-store')
            self.assertEqual(opened.headers['Referrer-Policy'],'no-referrer')
        other=StaffExamSessionsShare(person_ref='different',token='different-token')
        db.session.add(other);db.session.commit()
        self.assertEqual(self.portal.get(f'/my-exam-sessions/{other.token}/invoices/{document.file_id}').status_code,404)
        self.assertEqual(self.app.test_client().get('/finance-requests/drive-documents/'+document.file_id).status_code,302)

    def test_multiple_files_missing_csrf_wrong_year_or_unconfirmed_staff_never_upload(self):
        response=self.upload([(io.BytesIO(b'one'),'one.pdf'),(io.BytesIO(b'two'),'two.pdf')])
        self.assertIn('exactly one invoice file',response.get_data(as_text=True))
        self.assertIn('Security token expired',self.upload(csrf='bad').get_data(as_text=True))
        self.assertEqual(self.upload(year='2027').status_code,403)
        self.assignment.participation_status='Pending';db.session.commit()
        self.assertEqual(self.upload().status_code,403)
        self.assertEqual(GoogleDriveStaffInvoiceUpload.query.count(),0)
        self.assertEqual(self.metadata,[])

    def test_missing_folder_and_drive_failure_do_not_claim_success(self):
        GoogleDriveDestination.query.filter_by(key='staff_portal_invoices').delete();db.session.commit()
        self.assertIn('Invoice uploads are not available yet',self.upload().get_data(as_text=True))
        self.assertEqual(GoogleDriveStaffInvoiceUpload.query.count(),0)
        self.folder('staff_portal_invoices','1_VrUoXNBbVT_hSo_vAbL7prSj8hBAUNV')
        from app.google_drive import DriveStorageError
        with patch('app.staff_invoices.upload_document',side_effect=DriveStorageError('Drive is unavailable.')):
            self.assertIn('Drive is unavailable.',self.upload().get_data(as_text=True))
        self.assertEqual(GoogleDriveStaffInvoiceUpload.query.count(),0)

    def test_existing_invoice_blocks_another_upload_until_admin_trashes_it(self):
        from app.google_drive import DriveStorageError
        self.assignment.role_fee='ARS 100'
        self.assignment.manual_fee_override=True
        db.session.commit()
        self.upload()
        first=GoogleDriveStaffInvoiceUpload.query.one().file_id
        self.assertNotIn('data-staff-invoice-form',self.portal.get(self.page).get_data(as_text=True))
        response=self.upload((io.BytesIO(b'%PDF-replacement'),'replacement.pdf'))
        self.assertEqual(GoogleDriveStaffInvoiceUpload.query.count(),1)
        self.assertIn('already been uploaded',response.get_data(as_text=True))
        self.assertEqual(len(self.metadata),1)
        list_page=self.client.get('/staff-payments?session_year=2026')
        self.assertEqual(list_page.status_code,200)
        html=list_page.get_data(as_text=True)
        self.assertIn('<th>Invoice</th>',html)
        self.assertIn('<th>Verification</th>',html)
        self.assertIn('data-staff-invoice-view',html)
        preview=f'/staff-payments/{self.person.id}/2026/invoice'
        with self.client.get(preview) as opened:
            self.assertEqual(opened.data,b'private document')
            self.assertEqual(opened.headers['X-Frame-Options'],'SAMEORIGIN')
        remove=preview+'/remove'
        self.assertEqual(self.client.post(remove,data={'csrf_token':'wrong'}).status_code,400)
        self.assertEqual(GoogleDriveStaffInvoiceUpload.query.count(),1)
        with patch('app.staff_invoices.trash_document',side_effect=DriveStorageError('Drive unavailable')):
            self.assertEqual(self.client.post(remove,data={'csrf_token':'test'}).status_code,302)
        self.assertEqual(GoogleDriveStaffInvoiceUpload.query.count(),1)
        with patch('app.staff_invoices.trash_document') as trash:
            self.assertEqual(self.client.post(remove,data={'csrf_token':'test'}).status_code,302)
            self.assertEqual(trash.call_args.args[0].file_id,first)
        self.assertEqual(GoogleDriveStaffInvoiceUpload.query.count(),0)
        self.assertIn('Not yet',self.client.get('/staff-payments?session_year=2026').get_data(as_text=True))
        self.assertIn('data-staff-invoice-form',self.portal.get(self.page).get_data(as_text=True))
        self.upload((io.BytesIO(b'%PDF-new'),'new.pdf'))
        self.assertEqual(GoogleDriveStaffInvoiceUpload.query.count(),1)
        self.assertNotEqual(GoogleDriveStaffInvoiceUpload.query.one().file_id,first)
        self.assertEqual(self.portal.get(f'/my-exam-sessions/{self.share.token}/invoices/{first}').status_code,404)

    def test_verification_completed_requires_an_uploaded_invoice(self):
        from app.models import StaffPayment
        self.assignment.role_fee='ARS 100'
        self.assignment.manual_fee_override=True
        db.session.commit()
        endpoint=f'/staff-payments/{self.person.id}/2026'
        data={'csrf_token':'test','invoice_verified':'1','payment_completed':'0'}
        response=self.client.post(endpoint,data=data)
        self.assertEqual(response.status_code,400)
        self.assertIn('Upload an invoice',response.json['message'])
        self.assertEqual(StaffPayment.query.filter_by(member_id=self.person.id,year=2026).count(),0)
        html=self.client.get('/staff-payments?session_year=2026').get_data(as_text=True)
        import re
        field=re.search(r'<input[^>]*data-staff-payment-invoice[^>]*>',html).group(0)
        self.assertIn('disabled',field)
        self.upload()
        html=self.client.get('/staff-payments?session_year=2026').get_data(as_text=True)
        field=re.search(r'<input[^>]*data-staff-payment-invoice[^>]*>',html).group(0)
        self.assertNotIn('disabled',field)
        self.assertNotIn('<span>Verified</span>',html)
        self.assertEqual(self.client.post(endpoint,data=data).status_code,200)
        self.assertTrue(StaffPayment.query.filter_by(member_id=self.person.id,year=2026).one().invoice_verified)

    def test_annulment_email_is_sent_once_after_successful_removal(self):
        from app.models import StaffInvoiceCancellationNotification
        from app.staff_invoice_notifications import deliver_invoice_cancellation
        from app.google_drive import DriveStorageError
        self.person.email='staff-invoice@example.com';db.session.commit()
        self.upload()
        original=GoogleDriveStaffInvoiceUpload.query.one().file_id
        endpoint=f'/staff-payments/{self.person.id}/2026/invoice/remove'
        with patch('app.staff_invoices.trash_document',side_effect=DriveStorageError('Drive unavailable')),patch('app.staff_invoice_notifications.send_notification_email') as send:
            self.client.post(endpoint,data={'csrf_token':'test'})
        send.assert_not_called()
        self.assertEqual(StaffInvoiceCancellationNotification.query.count(),0)
        self.assertEqual(GoogleDriveStaffInvoiceUpload.query.count(),1)
        def accepted(recipient,subject,text,html,message_id):
            self.assertEqual(GoogleDriveStaffInvoiceUpload.query.count(),0)
            self.assertEqual(StaffInvoiceCancellationNotification.query.one().status,'sending')
            return 'cancellation-gmail-id'
        with patch('app.staff_invoices.trash_document'),patch('app.staff_invoice_notifications.send_notification_email',side_effect=accepted) as send:
            response=self.client.post(endpoint,data={'csrf_token':'test'})
        self.assertEqual(response.status_code,302)
        self.assertEqual(send.call_count,1)
        recipient,subject,text,html,_=send.call_args.args
        self.assertEqual(recipient,'staff-invoice@example.com')
        self.assertIn('your invoice has been cancelled',subject)
        self.assertIn('errors were identified',text)
        self.assertIn('contact Administration',text)
        self.assertIn('within the established deadlines',text)
        self.assertIn('at least 2 business days',html)
        self.assertIn('Open your staff portal',html)
        notice=StaffInvoiceCancellationNotification.query.one()
        self.assertEqual(notice.file_id,original)
        self.assertEqual(notice.status,'sent')
        with self.app.test_request_context('/'),patch('app.staff_invoice_notifications.send_notification_email') as send:
            self.assertTrue(deliver_invoice_cancellation(notice.id))
            self.assertEqual(self.client.post(endpoint,data={'csrf_token':'test'}).status_code,404)
        send.assert_not_called()

    def test_email_failure_keeps_annulment_and_safe_retries_work(self):
        from app.models import StaffInvoiceCancellationNotification
        from app.google_mail import MailNotSent,MailDeliveryUnknown
        from app.staff_invoice_notifications import deliver_invoice_cancellation
        self.person.email='staff-invoice@example.com';db.session.commit()
        self.upload()
        endpoint=f'/staff-payments/{self.person.id}/2026/invoice/remove'
        with patch('app.staff_invoices.trash_document'),patch('app.staff_invoice_notifications.send_notification_email',side_effect=MailNotSent('Not sent')):
            self.client.post(endpoint,data={'csrf_token':'test'})
        self.assertEqual(GoogleDriveStaffInvoiceUpload.query.count(),0)
        notice=StaffInvoiceCancellationNotification.query.one()
        self.assertEqual(notice.status,'failed')
        self.assertIn('data-staff-invoice-form',self.portal.get(self.page).get_data(as_text=True))
        with patch('app.staff_invoice_notifications.send_notification_email',return_value='retry-gmail') as send:
            response=self.client.post('/integrations/google/retry-payment-notifications',data={'csrf_token':'test'})
        self.assertEqual(response.status_code,302)
        self.assertEqual(send.call_count,1)
        db.session.refresh(notice)
        self.assertEqual(notice.status,'sent')
        self.upload((io.BytesIO(b'%PDF-new'),'new.pdf'))
        with patch('app.staff_invoices.trash_document'),patch('app.staff_invoice_notifications.send_notification_email',side_effect=MailDeliveryUnknown('Unknown')):
            self.client.post(endpoint,data={'csrf_token':'test'})
        unknown=StaffInvoiceCancellationNotification.query.filter_by(status='unknown').one()
        with self.app.test_request_context('/'),patch('app.staff_invoice_notifications.send_notification_email') as send:
            self.assertFalse(deliver_invoice_cancellation(unknown.id))
        send.assert_not_called()

    def test_trash_request_updates_drive_file_and_requires_google_confirmation(self):
        from app.staff_invoices import trash_document
        from app.google_drive import DriveStorageError
        import json
        self.upload()
        document=GoogleDriveStaffInvoiceUpload.query.one()
        with patch('urllib.request.urlopen',return_value=drive.FakeResponse(json.dumps({'id':document.file_id,'trashed':True}).encode())) as call:
            with self.app.test_request_context('/'):
                trash_document(document)
        sent=call.call_args.args[0]
        self.assertEqual(sent.get_method(),'PATCH')
        self.assertTrue(json.loads(sent.data)['trashed'])
        self.assertIn(document.file_id,sent.full_url)
        self.assertIn('fields=id%2Ctrashed',sent.full_url)
        with patch('urllib.request.urlopen',return_value=drive.FakeResponse(b'{}')):
            with self.app.test_request_context('/'),self.assertRaises(DriveStorageError):
                trash_document(document)

    def test_staff_payment_invoice_endpoints_require_their_own_menu_permission(self):
        from app.models import User, UserMenuPermission
        self.upload()
        outsider=User(full_name='No access',email='no-access@example.com',department='Admissions',is_active=True,password_hash='test')
        db.session.add(outsider);db.session.flush()
        db.session.add(UserMenuPermission(user_id=outsider.id,menu_key='staff_payments',can_view=False,can_edit=False))
        db.session.commit()
        client=self.app.test_client()
        with client.session_transaction() as state:
            state.update(user=outsider.full_name,user_id=outsider.id,user_email=outsider.email,user_department=outsider.department,csrf_token='test')
        endpoint=f'/staff-payments/{self.person.id}/2026/invoice'
        self.assertEqual(client.get(endpoint).status_code,403)
        self.assertEqual(client.post(endpoint+'/remove',data={'csrf_token':'test'}).status_code,403)
        self.assertEqual(GoogleDriveStaffInvoiceUpload.query.count(),1)
        permission=UserMenuPermission.query.filter_by(user_id=outsider.id,menu_key='staff_payments').one()
        permission.can_view=True
        db.session.commit()
        with client.get(endpoint) as opened:
            self.assertEqual(opened.status_code,200)
            self.assertEqual(opened.data,b'private document')
        self.assertEqual(client.post(endpoint+'/remove',data={'csrf_token':'test'}).status_code,403)
