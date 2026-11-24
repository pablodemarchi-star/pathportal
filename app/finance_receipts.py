"""Replace archived receipts with compensating cleanup for Drive failures."""
import os
import re
from urllib.parse import unquote, urlsplit, parse_qs, quote, urlencode

from flask import current_app
from werkzeug.security import safe_join
from app import db
from app.models import PaymentRequest, GoogleDriveUpload
from app.google_drive import destination_for_category, set_document_trashed, DriveStorageError, google_json, access_token, API


def locked_payment(payment_id):
    if db.engine.dialect.name == 'sqlite':
        connection = db.session.connection()
        if not connection.connection.driver_connection.in_transaction:
            connection.exec_driver_sql('BEGIN IMMEDIATE')
    return PaymentRequest.query.filter_by(id=payment_id).populate_existing().with_for_update().first_or_404()


def previous_drive_receipts(payment):
    documents = {}
    for link in (payment.payment_proof_url or '').splitlines():
        parsed = urlsplit(link.strip())
        internal = re.fullmatch(r'/finance-requests/drive-documents/([A-Za-z0-9_-]+)', parsed.path)
        direct = re.match(r'/file/d/([A-Za-z0-9_-]+)', parsed.path) if parsed.hostname == 'drive.google.com' else None
        file_id = internal.group(1) if internal else direct.group(1) if direct else (
            parse_qs(parsed.query).get('id', [''])[0] if parsed.hostname == 'drive.google.com' else '')
        if not file_id:
            continue
        document = db.session.get(GoogleDriveUpload, file_id)
        if document and document.payment_request_id == payment.id and document.destination_key == 'finance_payment_receipts':
            documents[file_id] = document
        elif internal or document:
            raise ValueError('The previous receipt is unavailable or does not belong to this payment. Reload before replacing it.')
        else:
            # Legacy direct Drive links have no upload row. Verify that the file
            # is in the configured receipt folder before touching it.
            destination = destination_for_category('payment_proofs')
            if destination is None:
                raise DriveStorageError('Configure the Payment receipts Drive folder before replacing this receipt.')
            try:
                metadata = google_json(API + '/files/' + quote(file_id, safe='') + '?' + urlencode({
                    'fields': 'id,parents,trashed,capabilities(canTrash)', 'supportsAllDrives': 'true'}), bearer=access_token())
            except (OSError, ValueError) as exc:
                raise DriveStorageError('The current Drive receipt could not be verified. Please retry.') from exc
            if metadata.get('id') != file_id or destination.folder_id not in metadata.get('parents', []) or metadata.get('trashed') or not metadata.get('capabilities', {}).get('canTrash'):
                raise DriveStorageError('The current receipt must be in the Payment receipts Drive folder and allow moving to trash.')
            documents[file_id] = None
    return list(documents.items())


def replace_receipt(payment, upload, previous):
    from app.routes import save_finance_supporting_document, add_payment_event, finance_upload_root
    if previous is None or previous != (payment.payment_proof_url or ''):
        raise ValueError('The payment receipt changed. Reload and review the current receipt before replacing it.')
    if not upload or not upload.filename:
        raise ValueError('Select exactly one replacement receipt file.')
    upload.stream.seek(0, 2)
    size = upload.stream.tell()
    upload.stream.seek(0)
    if not size:
        raise ValueError('The selected receipt file is empty.')
    old_documents = previous_drive_receipts(payment)
    if old_documents and destination_for_category('payment_proofs') is None:
        raise DriveStorageError('Configure the Payment receipts Drive folder before replacing this receipt.')
    attempted_trash = []
    new_link = ''
    try:
        new_link = save_finance_supporting_document(upload, payment, category='payment_proofs')
        if not new_link:
            raise ValueError('The replacement receipt could not be saved.')
        for file_id, document in old_documents:
            # Include ambiguous Drive failures in recovery: the PATCH may have succeeded.
            attempted_trash.append(file_id)
            set_document_trashed(file_id)
            if document is not None:
                db.session.delete(document)
        payment.payment_proof_url = new_link
        add_payment_event(payment, 'Payment receipt updated', previous_status=payment.status, new_status=payment.status)
        db.session.commit()
    except Exception:
        db.session.rollback()
        restore_failed = False
        for file_id in reversed(attempted_trash):
            try:
                set_document_trashed(file_id, False)
            except Exception:
                restore_failed = True
                current_app.logger.exception('Could not restore a receipt after failed replacement: %s', file_id)
        # Drive uploads use the existing uncommitted-upload cleanup hook.
        # Remove only this request's new local file if local storage was used.
        path = unquote(urlsplit(new_link).path)
        prefix = '/finance-requests/uploads/'
        if path.startswith(prefix):
            local_path = safe_join(finance_upload_root(), path[len(prefix):])
            if local_path:
                try:
                    os.remove(local_path)
                except OSError:
                    current_app.logger.warning('Could not clean up an uncommitted replacement receipt.')
        if restore_failed:
            raise DriveStorageError('Replacement failed. The original receipt reference was retained, but its Drive file could not be restored. Check Drive trash before retrying.')
        raise
