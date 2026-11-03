"""Private, single-file ID documentation managed independently of ID issued."""
from dataclasses import dataclass
from datetime import datetime, time, timedelta, timezone
import re
from types import SimpleNamespace
from flask import Blueprint, abort, jsonify, request
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm.exc import StaleDataError
from app import db, login_required, validate_csrf
from app.models import AcademicStaff, StaffIdDocument
from app.google_drive import DriveStorageError, upload_document, stream_document
from app.staff_invoices import trash_document

staff_id_documents_bp = Blueprint('staff_id_documents', __name__)
FOLDER_ID = '1Ff__Dc0ZirrtefiDlBw6ovZtION2OsnV'
PREVIEW_TYPES = {'application/pdf', 'image/jpeg', 'image/png', 'image/gif', 'image/webp', 'text/plain'}


@dataclass
class StaffIdTarget:
    member_id: int
    request_number: str
    document: object = None
    expiry_date: object = None


LOCAL_TZ = timezone(timedelta(hours=-3))


def expiry_instant(document):
    return datetime.combine(document.expiry_date, time.min, tzinfo=LOCAL_TZ) if document.expiry_date else None


def card_expired(document, now=None):
    expires = expiry_instant(document)
    return bool(expires and (now or datetime.now(timezone.utc)) >= expires)


def document_data(document):
    if not document:
        return None
    expires = expiry_instant(document)
    return {'file_id': document.file_id, 'filename': document.filename, 'mime_type': document.mime_type,
            'previewable': document.mime_type in PREVIEW_TYPES,
            'expiry_date': document.expiry_date.strftime('%d/%m/%Y') if document.expiry_date else None,
            'expires_at': expires.isoformat() if expires else None, 'expired': card_expired(document)}


@staff_id_documents_bp.after_request
def private(response):
    response.headers['Cache-Control'] = 'private, no-store'
    response.headers['Referrer-Policy'] = 'no-referrer'
    return response


@staff_id_documents_bp.route('/staff-members/<int:member_id>/id-document', methods=['GET', 'POST', 'DELETE'])
@login_required
def manage(member_id):
    from app.routes import require_menu_view, require_menu_edit
    require_menu_view('staff_members')
    member = db.session.get(AcademicStaff, member_id)
    if member is None:
        abort(404)
    document = db.session.get(StaffIdDocument, member_id)
    if request.method == 'GET':
        return jsonify(ok=True, read_only=member.id_issued, document=document_data(document))
    require_menu_edit('staff_members')
    unissue = request.method == 'POST' and request.form.get('action') == 'unissue'
    if unissue and not (member.id_issued and document and card_expired(document)):
        return jsonify(ok=False, error='Only an expired issued ID card can use this action.'), 400
    if member.id_issued and not unissue:
        return jsonify(ok=False, error='Issued ID cards are available for viewing only.'), 403
    if not validate_csrf():
        return jsonify(ok=False, error='Security token expired. Reload the page and try again.'), 400
    try:
        if (document.file_id if document else '') != request.form.get('previous_file_id', ''):
            return jsonify(ok=False, error='This document was updated by another user. Close and reopen this window.'), 409
        if unissue:
            set_member_id_issued(member, False)
        elif request.method == 'DELETE':
            if document:
                trash_document(document)
                db.session.delete(document)
        else:
            files = [file for file in request.files.getlist('document') if file.filename]
            if len(files) != 1:
                return jsonify(ok=False, error='Please select exactly one file.'), 400
            expiry_input = request.form.get('expiry_date', '').strip()
            try:
                if not re.fullmatch(r'\d{2}/\d{2}/\d{4}', expiry_input):
                    raise ValueError()
                expiry_date = datetime.strptime(expiry_input, '%d/%m/%Y').date()
            except ValueError:
                return jsonify(ok=False, error='Enter a valid Expiry date in dd/mm/yyyy format.'), 400
            old = SimpleNamespace(file_id=document.file_id) if document else None
            destination = SimpleNamespace(key='staff_id_documents', folder_id=FOLDER_ID)
            upload_document(files[0], StaffIdTarget(member.id, 'Staff ID - ' + member.full_name, document, expiry_date), destination)
            if old:
                trash_document(old)
        db.session.commit()
    except (IntegrityError, StaleDataError):
        db.session.rollback()
        return jsonify(ok=False, error='This document was updated by another user. Close and reopen this window.'), 409
    except OSError as exc:
        db.session.rollback()
        return jsonify(ok=False, error=str(exc).replace('invoice', 'document') if isinstance(exc, DriveStorageError) else 'The document could not be saved. Please try again.'), 503
    return jsonify(ok=True, read_only=member.id_issued, id_issued=member.id_issued, document=document_data(db.session.get(StaffIdDocument, member_id)))


@staff_id_documents_bp.get('/staff-members/<int:member_id>/id-document/preview')
@login_required
def preview(member_id):
    from app.routes import require_menu_view
    require_menu_view('staff_members')
    document = db.session.get(StaffIdDocument, member_id)
    if document is None:
        abort(404)
    response = stream_document(document)
    if request.args.get('download') == '1':
        response.headers['Content-Disposition'] = response.headers['Content-Disposition'].replace('inline;', 'attachment;', 1)
    response.headers['Content-Security-Policy'] = "sandbox allow-downloads; frame-ancestors 'self'; base-uri 'none'"
    return response


def set_member_id_issued(member, issued):
    """Retire an issued card before changing the flag; a Drive failure retains it."""
    if member.id_issued and not issued:
        document = db.session.get(StaffIdDocument, member.id)
        if document:
            trash_document(document)
            db.session.delete(document)
    member.id_issued = issued


@staff_id_documents_bp.get('/pre-session-control-tower/sessions/<int:session_id>/staff-id-cards/<int:member_id>/download')
@login_required
def package_download(session_id, member_id):
    from app.routes import require_menu_view, staff_member_confirmation_by_id
    from app.models import ExamSession
    require_menu_view('pre_session_control_tower')
    record = db.session.get(ExamSession, session_id)
    if record is None:
        abort(404)
    assignments = list(record.supervisor_assignments) + list(record.examiner_assignments) + list(record.intern_assignments)
    if not staff_member_confirmation_by_id(record, assignments).get(member_id, False):
        abort(403, description='The staff member has not been confirmed yet.')
    document = db.session.get(StaffIdDocument, member_id)
    if document is None:
        abort(404)
    if card_expired(document):
        abort(409, description='ID card file update required before issuance.')
    response = stream_document(document)
    response.headers['Content-Disposition'] = response.headers['Content-Disposition'].replace('inline;', 'attachment;', 1)
    return response
