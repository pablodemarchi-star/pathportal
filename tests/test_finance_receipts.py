import io
import json
import unittest
from unittest.mock import patch
from sqlalchemy.exc import SQLAlchemyError

from app import db, models as m
from app.google_drive import DriveStorageError, remember_uncommitted, set_document_trashed
from tests import test_finance_requests as fixtures


class ReceiptReplacementTest(unittest.TestCase):
    setUpBase = fixtures.FinanceRequestsTest.setUp
    tearDown = fixtures.FinanceRequestsTest.tearDown
    create_user = fixtures.FinanceRequestsTest.create_user
    payment = fixtures.FinanceRequestsTest.payment
    client_for = fixtures.FinanceRequestsTest.client_for

    def setUp(self):
        self.setUpBase()
        self.admin = self.create_user('receipt-admin@example.com', department='Admin', is_superadmin=True)
        self.requester = self.create_user('receipt-requester@example.com')
        self.record = self.payment(self.requester, status='Payment completed')
        self.old_link = 'http://localhost/finance-requests/drive-documents/old-receipt-id'
        self.record.payment_proof_url = self.old_link
        db.session.add_all([
            m.GoogleDriveDestination(key='finance_payment_receipts', folder_id='receipt-folder-id', folder_name='Receipts'),
            m.GoogleDriveUpload(file_id='old-receipt-id', payment_request_id=self.record.id, destination_key='finance_payment_receipts', filename='old.pdf', mime_type='application/pdf')])
        db.session.commit()
        self.url = f'/finance-requests/payment-requests/{self.record.id}/receipt'
        self.client = self.client_for(self.admin)
        self.operations = []
        self.upload_patch = patch('app.routes.save_finance_supporting_document', side_effect=self.upload)
        self.upload_mock = self.upload_patch.start(); self.addCleanup(self.upload_patch.stop)
        self.trash_patch = patch('app.finance_receipts.set_document_trashed', side_effect=lambda ident, trashed=True: self.operations.append(('trash', ident, trashed)))
        self.trash_mock = self.trash_patch.start(); self.addCleanup(self.trash_patch.stop)
        token_patch = patch('app.google_drive.access_token', return_value='test-token'); token_patch.start(); self.addCleanup(token_patch.stop)
        cleanup_patch = patch('app.google_drive.urlopen', side_effect=self.cleanup)
        cleanup_patch.start(); self.addCleanup(cleanup_patch.stop)

    def cleanup(self, request, **kwargs):
        self.operations.append(('cleanup', request.full_url, json.loads(request.data)))
        return io.BytesIO(b'{}')

    def upload(self, file, payment, category):
        self.assertEqual(category, 'payment_proofs')
        self.assertEqual(file.stream.read(), b'new receipt')
        self.operations.append(('upload', file.filename))
        db.session.add(m.GoogleDriveUpload(file_id='new-receipt-id', payment_request_id=payment.id,
            destination_key='finance_payment_receipts', filename=file.filename, mime_type=file.mimetype))
        remember_uncommitted('new-receipt-id')
        return 'http://localhost/finance-requests/drive-documents/new-receipt-id'

    def post(self, **extra):
        data = dict(csrf_token='token', tab='finance_payments', previous_receipt=self.old_link,
            payment_proof_file=(io.BytesIO(b'new receipt'), 'new.pdf'))
        data.update(extra)
        return self.client.post(self.url, data=data)

    def assert_old_retained(self):
        db.session.refresh(self.record)
        self.assertEqual(self.record.payment_proof_url, self.old_link)
        self.assertIsNotNone(db.session.get(m.GoogleDriveUpload, 'old-receipt-id'))
        self.assertIsNone(db.session.get(m.GoogleDriveUpload, 'new-receipt-id'))
        self.assertEqual(m.PaymentRequestEvent.query.filter_by(event_type='Payment receipt updated').count(), 0)

    def test_replacement_uploads_then_trashes_old_receipt_and_keeps_payment_status(self):
        response = self.post()
        self.assertEqual(response.status_code, 302)
        self.assertIn('open_staff_modal=archived-payment-request-', response.location)
        db.session.refresh(self.record)
        self.assertTrue(self.record.payment_proof_url.endswith('/new-receipt-id'))
        self.assertEqual(self.record.status, 'Payment completed')
        self.assertIsNone(db.session.get(m.GoogleDriveUpload, 'old-receipt-id'))
        self.assertIsNotNone(db.session.get(m.GoogleDriveUpload, 'new-receipt-id'))
        self.assertEqual(self.operations, [('upload', 'new.pdf'), ('trash', 'old-receipt-id', True)])
        self.assertEqual(m.PaymentRequestEvent.query.filter_by(event_type='Payment receipt updated').count(), 1)

    def test_upload_failure_leaves_old_file_and_reference_unchanged(self):
        self.upload_mock.side_effect = DriveStorageError('Upload failed')
        self.assertEqual(self.post().status_code, 302)
        self.assert_old_retained()
        self.trash_mock.assert_not_called()

    def test_trash_failure_restores_old_and_cleans_new_uncommitted_drive_file(self):
        def trash(ident, trashed=True):
            self.operations.append(('trash', ident, trashed))
            if trashed:
                raise DriveStorageError('Trash failed')
        self.trash_mock.side_effect = trash
        self.assertEqual(self.post().status_code, 302)
        self.assert_old_retained()
        self.assertIn(('trash', 'old-receipt-id', False), self.operations)
        self.assertTrue(any(item[0] == 'cleanup' and '/new-receipt-id?' in item[1] for item in self.operations))

    def test_commit_failure_restores_old_receipt_and_rolls_back_audit_event(self):
        with patch.object(db.session, 'commit', side_effect=SQLAlchemyError('Commit failed')):
            self.assertEqual(self.post().status_code, 302)
        self.assert_old_retained()
        self.assertIn(('trash', 'old-receipt-id', False), self.operations)
        self.assertTrue(any(item[0] == 'cleanup' for item in self.operations))

    def test_stale_form_missing_file_multiple_files_and_empty_file_do_not_touch_drive(self):
        for extra in [dict(previous_receipt='outdated'), dict(payment_proof_file=(io.BytesIO(b''), 'empty.pdf')),
                      dict(payment_proof_file=[(io.BytesIO(b'a'), 'one.pdf'), (io.BytesIO(b'b'), 'two.pdf')])]:
            self.assertEqual(self.post(**extra).status_code, 302)
            self.assert_old_retained()
        response = self.client.post(self.url, data=dict(csrf_token='token', previous_receipt=self.old_link, payment_proof_url='https://example.com/url-only'))
        self.assertEqual(response.status_code, 302)
        self.upload_mock.assert_not_called(); self.trash_mock.assert_not_called()

    def test_foreign_or_supporting_document_reference_is_never_trashed(self):
        old = db.session.get(m.GoogleDriveUpload, 'old-receipt-id')
        old.destination_key = 'finance_supporting_documents'; db.session.commit()
        self.assertEqual(self.post().status_code, 302)
        self.assert_old_retained()
        self.upload_mock.assert_not_called(); self.trash_mock.assert_not_called()

    def test_another_payments_receipt_cannot_be_trashed(self):
        other = self.payment(self.requester, status='Payment completed')
        db.session.get(m.GoogleDriveUpload, 'old-receipt-id').payment_request_id = other.id
        db.session.commit()
        self.assertEqual(self.post().status_code, 302)
        self.assert_old_retained()
        self.upload_mock.assert_not_called(); self.trash_mock.assert_not_called()

    def test_missing_drive_destination_never_falls_back_for_existing_drive_receipt(self):
        db.session.delete(db.session.get(m.GoogleDriveDestination, 'finance_payment_receipts'))
        db.session.commit()
        self.assertEqual(self.post().status_code, 302)
        self.assert_old_retained()
        self.upload_mock.assert_not_called(); self.trash_mock.assert_not_called()

    def test_partial_trash_failure_restores_all_previous_receipts(self):
        db.session.add(m.GoogleDriveUpload(file_id='second-old-receipt', payment_request_id=self.record.id,
            destination_key='finance_payment_receipts', filename='second.pdf', mime_type='application/pdf'))
        self.old_link += '\nhttp://localhost/finance-requests/drive-documents/second-old-receipt'
        self.record.payment_proof_url = self.old_link
        db.session.commit()
        def trash(ident, trashed=True):
            self.operations.append(('trash', ident, trashed))
            if ident == 'second-old-receipt' and trashed:
                raise DriveStorageError('Second file could not be trashed')
        self.trash_mock.side_effect = trash
        self.assertEqual(self.post().status_code, 302)
        self.assert_old_retained()
        self.assertIsNotNone(db.session.get(m.GoogleDriveUpload, 'second-old-receipt'))
        self.assertIn(('trash', 'old-receipt-id', False), self.operations)
        self.assertIn(('trash', 'second-old-receipt', False), self.operations)

    def test_csrf_and_non_superadmin_protection(self):
        self.assertEqual(self.post(csrf_token='wrong').status_code, 400)
        self.client = self.client_for(self.requester)
        self.assertEqual(self.post().status_code, 403)
        self.upload_mock.assert_not_called(); self.trash_mock.assert_not_called()

    def test_legacy_direct_drive_receipt_is_verified_before_replacing(self):
        db.session.delete(db.session.get(m.GoogleDriveUpload, 'old-receipt-id'))
        self.old_link = self.record.payment_proof_url = 'https://drive.google.com/file/d/legacy-receipt-id/view'
        db.session.commit()
        with patch('app.finance_receipts.access_token', return_value='test'), patch('app.finance_receipts.google_json', return_value={
            'id': 'legacy-receipt-id', 'parents': ['receipt-folder-id'], 'trashed': False, 'capabilities': {'canTrash': True}}):
            self.assertEqual(self.post().status_code, 302)
        self.trash_mock.assert_called_once_with('legacy-receipt-id')
        db.session.refresh(self.record)
        self.assertTrue(self.record.payment_proof_url.endswith('/new-receipt-id'))


class DriveReceiptTrashTest(unittest.TestCase):
    def test_patch_requires_drive_confirmation_and_supports_restore(self):
        for trashed in [True, False]:
            response = io.BytesIO(json.dumps({'id': 'receipt-id', 'trashed': trashed}).encode())
            with patch('app.google_drive.access_token', return_value='test'), patch('app.google_drive.urlopen', return_value=response) as http:
                set_document_trashed('receipt-id', trashed)
                self.assertEqual(http.call_args.args[0].get_method(), 'PATCH')
                self.assertEqual(json.loads(http.call_args.args[0].data), {'trashed': trashed})
        with patch('app.google_drive.access_token', return_value='test'), patch('app.google_drive.urlopen', return_value=io.BytesIO(b'{}')):
            with self.assertRaises(DriveStorageError):
                set_document_trashed('receipt-id')
