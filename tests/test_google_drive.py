import io
import json
import os
import unittest
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

os.environ['DATABASE_URL']='sqlite:///:memory:'
from flask import jsonify, request
from app import db
from app.google_drive import DRIVE_SCOPE, FOLDER_MIME, DriveStorageError, upload_document
from app.google_mail import SEND_SCOPE, save_connection, read_connection
from app.models import GoogleDriveDestination, GoogleDriveUpload, FinanceConcept, PaymentRequest, User, BillingRequest, GoogleDriveInvoiceUpload
from tests import test_google_mail as mail_tests


class FakeResponse(io.BytesIO):
    def __init__(self, data=b'{}', headers=None):
        super().__init__(data); self.headers=headers or {}


class GoogleDriveTest(unittest.TestCase):
    setUpBase=mail_tests.GoogleMailTest.setUp
    tearDownBase=mail_tests.GoogleMailTest.tearDown

    def setUp(self):
        self.setUpBase()
        self.config_patch=patch.dict(os.environ,{'GOOGLE_PICKER_API_KEY':'picker-test','GOOGLE_CLOUD_PROJECT_NUMBER':'197615227759'})
        self.config_patch.start()
        self.app.config['DRIVE_API_IN_TESTS']=True
        save_connection({'account':'pablo.demarchi@pathexaminations.com','client_id':'client-test',
                         'refresh_token':'refresh-test','scopes':[SEND_SCOPE,DRIVE_SCOPE]})
        user=User(full_name='Requester',email='requester@example.com',department='Admissions',is_active=True,password_hash='test')
        concept=FinanceConcept(name='Drive test',applies_to='Both',is_active=True)
        db.session.add_all([user,concept]);db.session.flush()
        self.payment=PaymentRequest(request_number='PAY-2026-0001',requester_user_id=user.id,
            requester_department='Admissions',description='Drive document',concept_id=concept.id,concept_name_snapshot=concept.name,
            amount=Decimal('100'),currency='ARS',payment_method='Cash',status='Submitted')
        db.session.add(self.payment);db.session.commit()
        self.metadata=[];self.parts=[];self.trashed=[];self.generated=0
        self.network_patch=patch('app.google_drive.google_json',side_effect=self.api)
        self.network=self.network_patch.start()
        self.http_patch=patch('app.google_drive.urlopen',side_effect=self.http)
        self.http=self.http_patch.start()

        @self.app.post('/test-drive-upload/<category>')
        def upload(category):
            from app.routes import save_finance_supporting_document
            try:
                urls=[save_finance_supporting_document(file,self.payment,category) for file in request.files.getlist('files')]
                db.session.commit()
                return jsonify(ok=True,urls=urls)
            except OSError as exc:
                db.session.rollback()
                return jsonify(ok=False,error=str(exc)),503

    def tearDown(self):
        self.http_patch.stop();self.network_patch.stop();self.config_patch.stop();self.tearDownBase()

    def api(self,url,**kwargs):
        if 'oauth2.googleapis.com/token' in url:return {'access_token':'access-test'}
        if '/generateIds' in url:
            self.generated+=1;return {'ids':[f'uploaded-file-{self.generated:010d}']}
        if '/files/' in url:
            folder_id=urlsplit(url).path.rsplit('/',1)[-1]
            return {'id':folder_id,'name':'Chosen folder','mimeType':FOLDER_MIME,'capabilities':{'canAddChildren':True}}
        raise AssertionError('Unexpected Google operation')

    def http(self,req,**kwargs):
        if req.get_method()=='POST':
            metadata=json.loads(req.data);self.metadata.append(metadata)
            return FakeResponse(headers={'Location':'https://www.googleapis.com/upload/drive/v3/files?uploadType=resumable&upload_id='+metadata['id']})
        if req.get_method()=='PUT':
            self.parts.append(req.data)
            ident=parse_qs(urlsplit(req.full_url).query)['upload_id'][0]
            return FakeResponse(json.dumps({'id':ident}).encode())
        if req.get_method()=='PATCH':
            self.trashed.append(urlsplit(req.full_url).path.rsplit('/',1)[-1]);return FakeResponse()
        if req.get_method()=='GET' and 'alt=media' in req.full_url:return FakeResponse(b'private document')
        raise AssertionError('Unexpected Drive HTTP operation')

    def folder(self,key='finance_supporting_documents',folder_id='chosen-folder-12345'):
        db.session.add(GoogleDriveDestination(key=key,folder_id=folder_id,folder_name='Configured folder'));db.session.commit()

    def test_attendance_upload_keeps_generated_name_and_uses_selected_folder(self):
        from werkzeug.datastructures import FileStorage
        from app.attendance_drive import upload
        from app.models import AttendanceDocument
        with self.app.test_request_context():
            document=upload(FileStorage(stream=io.BytesIO(b'absence record'),filename='original.pdf',content_type='application/pdf'),
                'absence-folder-12345','Session name - 17/11/2026 - Speaking')
            db.session.commit()
        self.assertEqual(self.metadata[-1]['name'],'Session name - 17/11/2026 - Speaking.pdf')
        self.assertEqual(self.metadata[-1]['parents'],['absence-folder-12345'])
        self.assertEqual(document.filename,'Session name - 17/11/2026 - Speaking.pdf')
        self.assertEqual(AttendanceDocument.query.count(),1)
        self.assertEqual(GoogleDriveUpload.query.count(),0)

    def test_absence_folder_authorization_and_fixed_lists_destination(self):
        from app.google_drive import DESTINATIONS
        url='/integrations/google/drive/absence-documentation/authorize'
        folder='absence-folder-12345'
        values={'csrf_token':'test','folder_url':'https://drive.google.com/drive/folders/'+folder,'folder_id':folder}
        self.assertEqual(self.client.post(url,data=values).status_code,200)
        self.assertEqual(GoogleDriveDestination.query.count(),0)
        self.assertEqual(self.client.post(url,data={**values,'folder_id':'different-folder-12345'}).status_code,400)
        self.assertEqual(self.client.post(url,data={**values,'csrf_token':'bad'}).status_code,400)
        target='/integrations/google/drive/folders/attendance_lists'
        self.assertEqual(self.client.post(target,data={'csrf_token':'test','folder_id':folder}).status_code,400)
        ident=DESTINATIONS['attendance_lists']['suggested_id']
        self.assertEqual(self.client.post(target,data={'csrf_token':'test','folder_id':ident}).status_code,200)
        self.assertEqual(GoogleDriveDestination.query.one().folder_id,ident)

    def test_drive_scope_is_added_without_losing_email_authorization(self):
        response=self.client.post('/integrations/google/connect',data={'csrf_token':'test','enable_drive':'1'})
        values=parse_qs(urlsplit(response.location).query)
        self.assertIn(SEND_SCOPE,values['scope'][0]);self.assertIn(DRIVE_SCOPE,values['scope'][0])
        state=values['state'][0]
        with patch('app.google_mail.google_json',side_effect=[
            {'access_token':'new-access','refresh_token':'new-refresh','scope':SEND_SCOPE+' '+DRIVE_SCOPE},
            {'email':'pablo.demarchi@pathexaminations.com','email_verified':True}]):
            response=self.client.get('/integrations/google/callback',query_string={'state':state,'code':'test'})
        self.assertEqual(response.status_code,302)
        self.assertEqual(set(read_connection()['scopes']),{SEND_SCOPE,DRIVE_SCOPE})
        self.assertEqual(read_connection()['refresh_token'],'new-refresh')

    def test_refusing_drive_permission_preserves_the_working_connection(self):
        response=self.client.post('/integrations/google/connect',data={'csrf_token':'test','enable_drive':'1'})
        state=parse_qs(urlsplit(response.location).query)['state'][0]
        with patch('app.google_mail.google_json',return_value={'access_token':'new-access','refresh_token':'new-refresh','scope':SEND_SCOPE}):
            self.client.get('/integrations/google/callback',query_string={'state':state,'code':'test'})
        self.assertEqual(read_connection()['refresh_token'],'refresh-test')

    def test_picker_access_is_admin_only_and_requires_csrf(self):
        url='/integrations/google/drive/picker-token'
        self.assertEqual(self.client.post(url).status_code,400)
        self.assertEqual(self.app.test_client().post(url,data={'csrf_token':'test'}).status_code,302)
        with self.client.session_transaction() as state:state['user_department']='Finance'
        self.assertEqual(self.client.post(url,data={'csrf_token':'test'}).status_code,403)
        with self.client.session_transaction() as state:state['user_department']='Admin'
        response=self.client.post(url,data={'csrf_token':'test'})
        self.assertEqual(response.status_code,200);self.assertEqual(response.json['access_token'],'access-test')
        self.assertEqual(response.headers['Cache-Control'],'private, no-store')
        page=self.client.get('/integrations/google').get_data(as_text=True)
        for secret in ('access-test','refresh-test','secret-test'):self.assertNotIn(secret,page)

    def test_authorize_session_pictures_does_not_change_document_destinations(self):
        self.folder()
        url='/integrations/google/drive/session-pictures/authorize'
        folder_id='18096T-jqNPLqKQrCSg-FrbYiVo5QOFWU'
        link='https://drive.google.com/drive/folders/'+folder_id+'?usp=drive_link'
        response=self.client.post(url,data={'csrf_token':'test','folder_url':link,'folder_id':folder_id})
        self.assertEqual(response.status_code,200)
        self.assertEqual(response.json['name'],'Chosen folder')
        self.assertEqual(GoogleDriveDestination.query.count(),1)
        self.assertEqual(GoogleDriveDestination.query.one().folder_id,'chosen-folder-12345')
        self.assertEqual(response.headers['Cache-Control'],'private, no-store')
        response=self.client.post(url,data={'csrf_token':'test','folder_url':link,'folder_id':'different-folder-12345'})
        self.assertEqual(response.status_code,400)
        self.assertEqual(self.client.post(url,data={'csrf_token':'test','folder_url':'https://example.com/folders/abc','folder_id':folder_id}).status_code,400)

    def test_session_pictures_authorization_is_next_to_planner_field(self):
        from datetime import date
        from app.models import ExamSession
        folder='https://drive.google.com/drive/folders/18096T-jqNPLqKQrCSg-FrbYiVo5QOFWU'
        record=ExamSession(exam_session_name='Pictures authorization',category='Path School',status='Pending',
            session_date=date(2026,11,20),format='Onsite',shifts='Morning',modules='Speaking',session_pictures_folder_url=folder)
        db.session.add(record);db.session.commit()
        response=self.client.get('/exam-session-planner?session_year=2026')
        self.assertEqual(response.status_code,200)
        page=response.get_data(as_text=True)
        self.assertIn('Authorize Drive access',page)
        self.assertIn('Authorize Session pictures folders',page)
        self.assertIn('data-drive-bulk-session',page)
        self.assertIn('data-drive-folder-link',page)
        self.assertIn('value="'+folder+'"',page)
        self.assertNotIn('data-drive-destination="session_pictures"',self.client.get('/integrations/google').get_data(as_text=True))

    def test_session_pictures_authorization_requires_admin_csrf_and_editor_access(self):
        url='/integrations/google/drive/session-pictures/authorize'
        fields={'csrf_token':'test','folder_id':'pictures-folder-12345','folder_url':'https://drive.google.com/drive/folders/pictures-folder-12345'}
        self.assertEqual(self.client.post(url).status_code,400)
        with self.client.session_transaction() as state:state['user_department']='Finance'
        self.assertEqual(self.client.post(url,data=fields).status_code,403)
        with self.client.session_transaction() as state:state['user_department']='Admin'
        with patch('app.google_drive.folder_metadata',side_effect=DriveStorageError('Editor access required')):
            response=self.client.post(url,data=fields)
        self.assertEqual(response.status_code,400)
        self.assertIn('Editor access required',response.json['error'])

    def test_folders_are_separate_persistent_and_verified_with_google(self):
        for key,ident in [('finance_supporting_documents','support-folder-12345'),('finance_payment_receipts','receipt-folder-12345')]:
            response=self.client.post('/integrations/google/drive/folders/'+key,data={'csrf_token':'test','folder_id':ident})
            self.assertEqual(response.status_code,200)
        self.assertEqual(GoogleDriveDestination.query.count(),2)
        self.assertEqual(db.session.get(GoogleDriveDestination,'finance_payment_receipts').folder_id,'receipt-folder-12345')
        with patch('app.google_drive.google_json',return_value={'id':'readonly-folder-12345','name':'Read only','mimeType':FOLDER_MIME,'capabilities':{'canAddChildren':False}}):
            response=self.client.post('/integrations/google/drive/folders/finance_payment_receipts',data={'csrf_token':'test','folder_id':'readonly-folder-12345'})
        self.assertEqual(response.status_code,400)
        self.assertEqual(db.session.get(GoogleDriveDestination,'finance_payment_receipts').folder_id,'receipt-folder-12345')
        self.assertEqual(self.client.post('/integrations/google/drive/folders/unknown',data={'csrf_token':'test','folder_id':'x'}).status_code,404)

    def test_uploads_go_to_each_configured_destination_and_remain_portal_private(self):
        self.folder();self.folder('finance_payment_receipts','receipt-folder-12345')
        for category,folder_id in [('payment_requests','chosen-folder-12345'),('payment_proofs','receipt-folder-12345')]:
            response=self.client.post('/test-drive-upload/'+category,data={'files':(io.BytesIO(b'%PDF-test'),'invoice.pdf')},content_type='multipart/form-data')
            self.assertEqual(response.status_code,200,response.json)
            self.assertEqual(self.metadata[-1]['parents'],[folder_id])
            self.assertTrue(self.metadata[-1]['name'].startswith('PAY-2026-0001 - '))
            url=response.json['urls'][0];self.assertIn('/finance-requests/drive-documents/',url)
            self.assertEqual(self.app.test_client().get(url).status_code,302)
            opened=self.client.get(url)
            self.assertEqual(opened.data,b'private document')
            self.assertEqual(opened.headers['Cache-Control'],'private, no-store')
        self.assertEqual(GoogleDriveUpload.query.count(),2)
        self.assertEqual(self.trashed,[])

    def test_invoice_documents_use_supporting_folder_and_invoice_access(self):
        self.folder()
        invoice=BillingRequest(request_number="INVOICE-2026-0001", requester_user_id=self.payment.requester_user_id,
            requester_department="Admissions", client_name_snapshot="Client", concept_id=self.payment.concept_id,
            concept_name_snapshot="Drive test", description="Invoice", amount=Decimal("100"), currency="ARS", status="Requested")
        db.session.add(invoice);db.session.commit()
        self.payment=invoice
        response=self.client.post('/test-drive-upload/billing_requests',data={'files':(io.BytesIO(b'pdf'),'invoice.pdf')},content_type='multipart/form-data')
        self.assertEqual(response.status_code,200,response.json)
        self.assertEqual(self.metadata[-1]['parents'],['chosen-folder-12345'])
        self.assertEqual(GoogleDriveUpload.query.count(),0)
        self.assertEqual(GoogleDriveInvoiceUpload.query.one().billing_request_id,invoice.id)
        url=response.json['urls'][0]
        with self.client.get(url) as opened:
            self.assertEqual(opened.data,b'private document')
        self.assertEqual(self.app.test_client().get(url).status_code,302)
        with patch('app.routes.can_view_billing_request',return_value=False):
            self.assertEqual(self.client.get(url).status_code,404)

    def test_missing_drive_authorization_never_silently_falls_back_to_local_storage(self):
        self.folder()
        save_connection({'account':'pablo.demarchi@pathexaminations.com','client_id':'client-test','refresh_token':'mail-only','scopes':[SEND_SCOPE]})
        response=self.client.post('/test-drive-upload/payment_requests',data={'files':(io.BytesIO(b'data'),'invoice.pdf')},content_type='multipart/form-data')
        self.assertEqual(response.status_code,503)
        self.assertEqual(GoogleDriveUpload.query.count(),0)
        self.assertEqual(self.metadata,[])

    def test_failed_batch_rolls_back_records_and_trashes_only_this_requests_files(self):
        self.folder()
        original=self.http.side_effect
        def fail_second(req,**kwargs):
            if req.get_method()=='PUT' and self.generated==2:raise OSError('Network interrupted')
            return original(req,**kwargs)
        self.http.side_effect=fail_second
        response=self.client.post('/test-drive-upload/payment_requests',data={'files':[(io.BytesIO(b'first'),'one.pdf'),(io.BytesIO(b'second'),'two.pdf')]},content_type='multipart/form-data')
        self.assertEqual(response.status_code,503)
        self.assertEqual(GoogleDriveUpload.query.count(),0)
        self.assertEqual(len(self.trashed),2)

    def test_report_media_preserves_original_names_and_bytes(self):
        from datetime import date
        from types import SimpleNamespace
        from werkzeug.datastructures import FileStorage
        from app import models as m
        from app.staff_report_media import ReportMediaTarget
        record=m.ExamSession(exam_session_name='Media upload',category='Path School',status='Pending',session_date=date(2026,11,17),format='Onsite')
        share=m.StaffExamSessionsShare(person_ref='media-test',token='media-test')
        db.session.add_all([record,share]);db.session.flush()
        submission=m.StaffExamSessionSubmission(exam_session_id=record.id,share_id=share.id,assignment_type='supervisor',assignment_id=1)
        db.session.add(submission);db.session.commit()
        with self.app.test_request_context():
            target=ReportMediaTarget(submission.id,'Session marketing material')
            file=FileStorage(stream=io.BytesIO(b'original media bytes'),filename='Fotografía 1.jpg',content_type='image/jpeg')
            upload_document(file,target,SimpleNamespace(folder_id='pictures-folder-12345'))
            db.session.commit()
        self.assertEqual(self.metadata[-1]['name'],'Fotografía 1.jpg')
        self.assertEqual(self.metadata[-1]['parents'],['pictures-folder-12345'])
        self.assertEqual(b''.join(self.parts),b'original media bytes')
        document=m.StaffSessionReportMedia.query.one()
        self.assertEqual(document.filename,'Fotografía 1.jpg')
        self.assertEqual(document.mime_type,'image/jpeg')

    def bulk_sessions(self):
        from datetime import date
        from app.models import ExamSession
        rows=[]
        for index,folder in enumerate(['https://drive.google.com/drive/folders/shared-folder-12345',
                                     'https://drive.google.com/drive/folders/shared-folder-12345',
                                     'https://drive.google.com/drive/folders/other-folder-12345',None,'https://example.com/not-drive']):
            record=ExamSession(exam_session_name=f'Bulk session {index}',category='Path School',status='Pending',session_date=date(2026,11,20),format='Onsite',session_pictures_folder_url=folder)
            db.session.add(record);rows.append(record)
        db.session.commit()
        return rows

    def test_bulk_drive_plan_groups_shared_folders_without_changing_links(self):
        records=self.bulk_sessions()
        original=[row.session_pictures_folder_url for row in records]
        self.network.reset_mock()
        response=self.client.post('/integrations/google/drive/session-pictures/bulk/prepare',data={'csrf_token':'test','session_ids':[str(row.id) for row in records]})
        self.assertEqual(response.status_code,200)
        self.assertEqual(len(response.json['folders']),2)
        self.assertEqual(len(response.json['issues']),2)
        shared=next(folder for folder in response.json['folders'] if folder['folder_id']=='shared-folder-12345')
        self.assertEqual(shared['session_ids'],[records[0].id,records[1].id])
        self.network.assert_not_called()
        self.assertEqual([row.session_pictures_folder_url for row in records],original)

    def test_bulk_verification_is_per_folder_and_rechecks_current_configuration(self):
        records=self.bulk_sessions()
        url='/integrations/google/drive/session-pictures/bulk/verify'
        fields={'csrf_token':'test','session_ids':[str(row.id) for row in records],'folder_ids':['shared-folder-12345','other-folder-12345']}
        def metadata(folder_id):
            if folder_id=='other-folder-12345':raise DriveStorageError('Editor access required')
            return {'id':folder_id,'name':'Session photos'}
        with patch('app.google_drive.folder_metadata',side_effect=metadata) as check:
            response=self.client.post(url,data=fields)
        self.assertEqual(response.status_code,200)
        self.assertEqual([row['status'] for row in response.json['results']],['authorized','failed'])
        self.assertEqual(check.call_count,2)
        self.assertEqual(GoogleDriveDestination.query.count(),0)
        for record in records[:2]:record.session_pictures_folder_url='https://drive.google.com/drive/folders/changed-folder-12345'
        db.session.commit()
        with patch('app.google_drive.folder_metadata') as check:
            response=self.client.post(url,data={**fields,'folder_ids':['shared-folder-12345','unrelated-folder-12345']})
        check.assert_not_called()
        self.assertTrue(all(row['status']=='not_configured' for row in response.json['results']))

    def test_bulk_authorization_requires_admin_csrf_and_valid_selection(self):
        url='/integrations/google/drive/session-pictures/bulk/prepare'
        self.assertEqual(self.client.post(url).status_code,400)
        self.assertEqual(self.client.post(url,data={'csrf_token':'test'}).status_code,400)
        self.assertEqual(self.client.post(url,data={'csrf_token':'test','session_ids':['999999']}).status_code,400)
        with self.client.session_transaction() as state:state['user_department']='Finance'
        self.assertEqual(self.client.post(url,data={'csrf_token':'test','session_ids':['1']}).status_code,403)

    def test_unconfigured_destination_keeps_existing_local_uploads_working(self):
        root=Path(self.temp.name)/'uploads'
        with patch('app.routes.finance_upload_root',return_value=str(root)):
            response=self.client.post('/test-drive-upload/payment_requests',data={'files':(io.BytesIO(b'local'),'old.pdf')},content_type='multipart/form-data')
            self.assertEqual(response.status_code,200)
            self.assertIn('/finance-requests/uploads/',response.json['urls'][0])
            with self.client.get(response.json['urls'][0]) as download:
                self.assertEqual(download.data,b'local')
        self.assertEqual(self.metadata,[])

    def test_uploaded_html_is_downloaded_not_executed_on_the_portal_origin(self):
        self.folder()
        response=self.client.post('/test-drive-upload/payment_requests',data={'files':(io.BytesIO(b'<script>bad()</script>'),'page.html')},content_type='multipart/form-data')
        download=self.client.get(response.json['urls'][0])
        self.assertTrue(download.headers['Content-Disposition'].startswith('attachment;'))
        self.assertEqual(download.headers['X-Content-Type-Options'],'nosniff')
        self.assertEqual(download.headers['Content-Security-Policy'],'sandbox allow-downloads')

    def test_documents_honor_the_payment_visibility_policy(self):
        self.folder()
        result=self.client.post('/test-drive-upload/payment_requests',data={'files':(io.BytesIO(b'private'),'proof.pdf')},content_type='multipart/form-data')
        url=result.json['urls'][0]
        with patch('app.routes.can_view_payment_request',return_value=False):
            self.assertEqual(self.client.get(url).status_code,404)
        self.assertEqual(self.client.get('/finance-requests/drive-documents/not-a-portal-document').status_code,404)
