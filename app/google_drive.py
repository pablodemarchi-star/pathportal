"""Administrator-selected Drive folders; private Finance uploads and downloads."""
import json
import os
import re
from datetime import datetime, timezone
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode, urlsplit
from urllib.request import Request, urlopen

from flask import Blueprint, Response, abort, current_app, g, jsonify, request, session, stream_with_context, url_for
from sqlalchemy import event
from sqlalchemy.orm import Session
from werkzeug.utils import secure_filename

from app import db, login_required, validate_csrf
from app.google_mail import administrator, configuration, configured, google_json, read_connection, save_connection, EXPECTED_ACCOUNT
from app.models import GoogleDriveDestination, GoogleDriveUpload, GoogleDriveInvoiceUpload, GoogleDriveStaffInvoiceUpload, BillingRequest

DRIVE_SCOPE = 'https://www.googleapis.com/auth/drive.file'
API = 'https://www.googleapis.com/drive/v3'
FOLDER_MIME = 'application/vnd.google-apps.folder'
DESTINATIONS = {
    'staff_portal_invoices': {'label': 'Staff invoices', 'section': 'Staff portal', 'category': 'staff_invoices',
        'suggested_id': '1_VrUoXNBbVT_hSo_vAbL7prSj8hBAUNV'},
    'finance_supporting_documents': {'label': 'Supporting documentation', 'category': 'payment_requests',
        'suggested_id': '1HcsKcutlFFGchNeVQASqhijb78OfIXhr'},
    'finance_invoice_proofs': {'label': 'Invoice proofs', 'category': 'invoice_proofs',
        'suggested_id': '1gc-nDU2H5eEG98FWb6B7X7ZAJ1ajZYBq'},
    'finance_payment_receipts': {'label': 'Payment receipts', 'category': 'payment_proofs',
        'suggested_id': '1OlfHITet8YS2HU07y1GUkvCFE6GGF0_X'},
}
drive_bp = Blueprint('google_drive', __name__)


class DriveStorageError(OSError):
    """A safe message to display without exposing Google responses or tokens."""


def picker_configuration():
    return {'api_key': os.getenv('GOOGLE_PICKER_API_KEY', '').strip(),
            'project_number': os.getenv('GOOGLE_CLOUD_PROJECT_NUMBER', '').strip()}


def drive_connected(saved=None):
    saved = read_connection() if saved is None else saved
    return bool(saved.get('refresh_token') and DRIVE_SCOPE in saved.get('scopes', [])
                and saved.get('account') == os.getenv('GMAIL_ACCOUNT_EMAIL', EXPECTED_ACCOUNT).lower()
                and saved.get('client_id') == configuration()['GOOGLE_OAUTH_CLIENT_ID'])


def settings_context(saved):
    config = picker_configuration()
    folders = {row.key: row for row in GoogleDriveDestination.query.all()}
    return {'drive_connected': drive_connected(saved), 'picker_configured': bool(config['api_key'] and config['project_number'].isdigit()),
            'drive_destinations': [{**details, 'key': key, 'folder': folders.get(key)} for key, details in DESTINATIONS.items()],
            'picker_project_number': config['project_number']}


def access_token():
    if current_app.testing and not current_app.config.get('DRIVE_API_IN_TESTS'):
        raise DriveStorageError('Google Drive network access is disabled in tests.')
    if getattr(g, '_drive_access_token', None):
        return g._drive_access_token
    try:
        saved = read_connection()
        if not configured() or not drive_connected(saved):
            raise DriveStorageError('Reconnect Google Drive from Email connection before uploading documents.')
        config = configuration()
        result = google_json('https://oauth2.googleapis.com/token', fields={
            'grant_type': 'refresh_token', 'client_id': config['GOOGLE_OAUTH_CLIENT_ID'],
            'client_secret': config['GOOGLE_OAUTH_CLIENT_SECRET'], 'refresh_token': saved['refresh_token'],
        }, timeout=10)
        token = result['access_token']
        if result.get('refresh_token'):
            save_connection({**saved, 'refresh_token': result['refresh_token']})
        g._drive_access_token = token
        return token
    except DriveStorageError:
        raise
    except (OSError, ValueError, KeyError) as exc:
        raise DriveStorageError('Google Drive could not be connected. Ask an administrator to check the connection.') from exc


def folder_metadata(folder_id):
    if not re.fullmatch(r'[A-Za-z0-9_-]{10,160}', folder_id):
        raise DriveStorageError('Select a valid folder using Google Picker.')
    try:
        data = google_json(API + '/files/' + folder_id + '?' + urlencode({
            'fields': 'id,name,mimeType,trashed,capabilities(canAddChildren)', 'supportsAllDrives': 'true'
        }), bearer=access_token())
    except (OSError, ValueError, KeyError) as exc:
        raise DriveStorageError('This folder could not be accessed. Choose it in Google Picker and check Editor access.') from exc
    if data.get('id') != folder_id or data.get('mimeType') != FOLDER_MIME or data.get('trashed') or not data.get('capabilities', {}).get('canAddChildren'):
        raise DriveStorageError('Choose a folder where the connected account can add files.')
    return data


@drive_bp.after_request
def private(response):
    response.headers['Cache-Control'] = 'private, no-store'
    response.headers['Referrer-Policy'] = 'no-referrer'
    return response


@drive_bp.post('/integrations/google/drive/picker-token')
@administrator
def picker_token():
    if not validate_csrf():
        abort(400)
    config = picker_configuration()
    if not config['api_key'] or not config['project_number'].isdigit():
        return jsonify(ok=False, error='Configure the Google Picker API key and project number on this server.'), 400
    try:
        return jsonify(ok=True, access_token=access_token(), api_key=config['api_key'], app_id=config['project_number'])
    except DriveStorageError as exc:
        return jsonify(ok=False, error=str(exc)), 503


@drive_bp.post('/integrations/google/drive/folders/<key>')
@administrator
def save_folder(key):
    if not validate_csrf():
        abort(400)
    if key not in DESTINATIONS:
        abort(404)
    try:
        folder = folder_metadata(request.form.get('folder_id', '').strip())
    except DriveStorageError as exc:
        return jsonify(ok=False, error=str(exc)), 400
    row = db.session.get(GoogleDriveDestination, key)
    if row is None:
        row = GoogleDriveDestination(key=key)
        db.session.add(row)
    row.folder_id, row.folder_name = folder['id'], folder['name']
    row.updated_at = datetime.now(timezone.utc)
    row.updated_by = session.get('user_email') or session.get('user')
    db.session.commit()
    return jsonify(ok=True, name=row.folder_name, url='https://drive.google.com/drive/folders/' + row.folder_id)


def destination_for_category(category):
    if category == "billing_requests":
        category = "payment_requests"
    key = next((key for key, details in DESTINATIONS.items() if details['category'] == category), None)
    return db.session.get(GoogleDriveDestination, key) if key else None


def remember_uncommitted(file_id):
    if not hasattr(g, '_uncommitted_drive_files'):
        g._uncommitted_drive_files = []
    g._uncommitted_drive_files.append(file_id)


@event.listens_for(Session, 'after_commit')
def drive_uploads_committed(unit_of_work):
    from flask import has_request_context
    if has_request_context() and unit_of_work is db.session():
        g.pop('_uncommitted_drive_files', None)


@drive_bp.after_app_request
def cleanup_failed_uploads(response):
    pending = g.pop('_uncommitted_drive_files', [])
    if pending:
        # None of these files belongs to a committed request. Do not leave a
        # completed file behind when a multi-file upload or DB transaction fails.
        db.session.rollback()
        for file_id in pending:
            try:
                token = access_token()
                payload = json.dumps({'trashed': True}).encode()
                with urlopen(Request(API + '/files/' + file_id + '?supportsAllDrives=true', data=payload,
                    headers={'Authorization': 'Bearer ' + token, 'Content-Type': 'application/json'}, method='PATCH'), timeout=15):
                    pass
            except Exception:
                current_app.logger.warning('Could not clean up an uncommitted Drive upload (%s).', file_id)
    return response


def upload_document(upload, payment, destination):
    """Resumable chunks bound memory use and preserve the supplied Drive permissions."""
    token = access_token()
    filename = secure_filename(upload.filename) or 'document'
    mime = upload.mimetype or 'application/octet-stream'
    stream = upload.stream
    try:
        stream.seek(0, 2); size = stream.tell(); stream.seek(0)
        if size <= 0:
            raise DriveStorageError('The selected document is empty.')
        # Preallocate an ID so failed/ambiguous uploads can be cleaned up safely.
        generated = google_json(API + '/files/generateIds?count=1&space=drive&type=files', bearer=token)
        file_id = generated['ids'][0]
        if not re.fullmatch(r'[A-Za-z0-9_-]{10,160}', file_id):
            raise ValueError('Invalid file ID')
        remember_uncommitted(file_id)
        metadata = {'id': file_id, 'name': f'{payment.request_number} - {filename}', 'parents': [destination.folder_id]}
        uri = 'https://www.googleapis.com/upload/drive/v3/files?' + urlencode({
            'uploadType': 'resumable', 'supportsAllDrives': 'true', 'fields': 'id'
        })
        headers = {'Authorization': 'Bearer ' + token, 'Content-Type': 'application/json; charset=UTF-8',
                   'X-Upload-Content-Type': mime, 'X-Upload-Content-Length': str(size)}
        with urlopen(Request(uri, data=json.dumps(metadata).encode(), headers=headers, method='POST'), timeout=20) as response:
            upload_uri = response.headers.get('Location', '')
        parsed = urlsplit(upload_uri)
        if parsed.scheme != 'https' or parsed.hostname not in {'www.googleapis.com', 'drive.googleapis.com', 'content.googleapis.com'} or parsed.port not in (None, 443) or parsed.username or parsed.password or not parsed.path.startswith('/upload/drive/v3/files'):
            raise ValueError('Invalid upload endpoint')
        offset = 0
        result = None
        while offset < size:
            data = stream.read(8 * 1024 * 1024)
            if not data:
                raise ValueError('Unexpected end of file')
            end = offset + len(data) - 1
            try:
                with urlopen(Request(upload_uri, data=data, headers={
                    'Authorization': 'Bearer ' + token, 'Content-Type': mime,
                    'Content-Range': f'bytes {offset}-{end}/{size}',
                }, method='PUT'), timeout=60) as response:
                    result = json.load(response)
            except HTTPError as exc:
                if exc.code != 308 or exc.headers.get('Range') != f'bytes=0-{end}':
                    raise
            offset = end + 1
        if not result or result.get('id') != file_id:
            raise ValueError('Upload not confirmed')
        from app.staff_invoices import StaffInvoiceTarget
        if isinstance(payment, StaffInvoiceTarget):
            model, owner = GoogleDriveStaffInvoiceUpload, {"share_id": payment.share_id, "year": payment.year}
        else:
            model, owner = (GoogleDriveInvoiceUpload, {"billing_request_id": payment.id}) if isinstance(payment, BillingRequest) else (GoogleDriveUpload, {"payment_request_id": payment.id})
        db.session.add(model(file_id=file_id, **owner,
            destination_key=destination.key, filename=filename, mime_type=mime))
        if isinstance(payment, StaffInvoiceTarget):
            return url_for('staff_invoices.download', token=payment.token, file_id=file_id, _external=True)
        return url_for('google_drive.download', file_id=file_id, _external=True)
    except DriveStorageError:
        raise
    except (OSError, ValueError, KeyError, IndexError) as exc:
        raise DriveStorageError('The document could not be saved in Google Drive. Please retry or ask an administrator to check the destination folder.') from exc


@drive_bp.get('/finance-requests/drive-documents/<file_id>')
@login_required
def download(file_id):
    from app.routes import require_menu_view, can_view_payment_request, can_view_billing_request
    require_menu_view('finance_requests')
    document = db.session.get(GoogleDriveUpload, file_id)
    if document is not None:
        allowed = document.payment_request is not None and can_view_payment_request(getattr(g, 'current_user', None), document.payment_request)
    else:
        document = db.session.get(GoogleDriveInvoiceUpload, file_id)
        allowed = document is not None and document.billing_request is not None and can_view_billing_request(getattr(g, 'current_user', None), document.billing_request)
    if not allowed:
        abort(404)
    return stream_document(document)


def stream_document(document):
    file_id = document.file_id
    try:
        upstream = urlopen(Request(API + '/files/' + file_id + '?alt=media&supportsAllDrives=true',
            headers={'Authorization': 'Bearer ' + access_token()}), timeout=30)
    except (OSError, ValueError):
        abort(503, description='The document could not be retrieved from Google Drive. Please try again.')
    def chunks():
        try:
            while True:
                data = upstream.read(64 * 1024)
                if not data:
                    break
                yield data
        finally:
            upstream.close()
    safe_inline = document.mime_type in {'application/pdf', 'image/jpeg', 'image/png', 'image/gif', 'image/webp', 'text/plain'}
    response = Response(stream_with_context(chunks()), mimetype=document.mime_type if safe_inline else 'application/octet-stream')
    response.headers['Content-Disposition'] = ('inline' if safe_inline else 'attachment') + "; filename*=UTF-8''" + quote(document.filename, safe='')
    response.headers['Cache-Control'] = 'private, no-store'
    response.headers['Referrer-Policy'] = 'no-referrer'
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['Content-Security-Policy'] = 'sandbox allow-downloads'
    return response
