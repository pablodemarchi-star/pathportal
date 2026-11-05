"""Private single-file shipping labels, shared by combined return sessions."""
from dataclasses import dataclass
from types import SimpleNamespace

from flask import Blueprint, abort, current_app, jsonify, request, url_for
from sqlalchemy import or_
from app import db, login_required, validate_csrf
from app.models import ExamSession, ExamSessionSinapsisControl, ReturnShippingLabel
from app.google_drive import DriveStorageError, upload_document, stream_document
from app.staff_invoices import trash_document

return_labels_bp = Blueprint('return_labels', __name__)
FOLDER_ID = '1bzB2g3XWlISXh606AzCQtvKdJPpDvtJD'
FIELDS = {'immediate_dispatch': 'return_shipping_label', 'combined_dispatch': 'combined_return_shipping_label'}


@dataclass
class ReturnLabelTarget:
    request_number: str
    document: object = None


def document_data(document):
    return {'file_id': document.file_id, 'filename': document.filename,
            'url': url_for('return_labels.preview', file_id=document.file_id)} if document else None


def linked_controls(file_id):
    return ExamSessionSinapsisControl.query.filter(or_(
        ExamSessionSinapsisControl.return_shipping_label_id == file_id,
        ExamSessionSinapsisControl.combined_return_shipping_label_id == file_id)).all()


@return_labels_bp.route('/pre-session-control-tower/sessions/<int:session_id>/return-label/<method>', methods=['GET', 'POST'])
@login_required
def manage(session_id, method):
    from app.routes import require_menu_edit, require_menu_view
    from app.final_checks import final_checks_state
    require_menu_view('pre_session_control_tower')
    record = db.session.get(ExamSession, session_id)
    if not record or method not in FIELDS:
        abort(404)
    if request.method == 'POST':
        if db.engine.dialect.name == 'sqlite':
            connection = db.session.connection()
            if not connection.connection.driver_connection.in_transaction:
                connection.exec_driver_sql('BEGIN IMMEDIATE')
        else:
            db.session.query(ExamSession.id).filter_by(id=session_id).with_for_update().first()
    control = ExamSessionSinapsisControl.query.filter_by(exam_session_id=session_id).first()
    field = FIELDS[method]
    if request.method == 'GET':
        return jsonify(ok=True, document=document_data(getattr(control, field)) if control else None)
    require_menu_edit('pre_session_control_tower')
    if not validate_csrf():
        return jsonify(ok=False, error='Security token expired. Reload the page and try again.'), 403
    if not final_checks_state(record)['return_enabled']:
        return jsonify(ok=False, error='Return of exam materials is blocked until the shipment recipient confirms participation.'), 403
    if not control:
        abort(404)
    if control.return_materials_method != method:
        return jsonify(ok=False, error='Select this return option before uploading or removing its shipping label.'), 409
    document = getattr(control, field)
    if request.form.get('previous_file_id', '') != (document.file_id if document else ''):
        return jsonify(ok=False, error='The shipping label was updated by another user. Reopen the session to continue.'), 409
    affected = [control]
    trashed_id = None
    try:
        if request.form.get('action') == 'delete':
            if document:
                affected = linked_controls(document.file_id)
                # Drive must confirm trashing before any portal references are removed.
                for peer in affected:
                    for kind, attr in FIELDS.items():
                        if getattr(peer, attr + '_id') == document.file_id:
                            setattr(peer, attr, None)
                            if peer.return_materials_method == kind:
                                peer.return_completed_at = None
                db.session.delete(document)
                db.session.flush()
                trash_document(document)
                trashed_id = document.file_id
        else:
            if document:
                return jsonify(ok=False, error='Delete the current shipping label before uploading a new file.'), 409
            files = [file for file in request.files.getlist('document') if file.filename]
            if len(files) != 1:
                return jsonify(ok=False, error='Please select exactly one shipping label file.'), 400
            target = ReturnLabelTarget('Return shipping label - ' + record.exam_session_name)
            destination = SimpleNamespace(key='return_shipping_labels', folder_id=FOLDER_ID)
            upload_document(files[0], target, destination)
            setattr(control, field, target.document)
            if method == 'combined_dispatch':
                peers = ExamSessionSinapsisControl.query.filter(
                    ExamSessionSinapsisControl.exam_session_id.in_(control.combined_return_session_ids),
                    ExamSessionSinapsisControl.return_materials_method == 'combined_dispatch',
                    ExamSessionSinapsisControl.return_materials_local_override.is_(False)).all()
                for peer in peers:
                    if session_id in peer.combined_return_session_ids:
                        setattr(peer, field, target.document)
                        affected.append(peer)
        db.session.commit()
    except DriveStorageError as exc:
        db.session.rollback()
        return jsonify(ok=False, error=str(exc).replace('invoice', 'shipping label')), 503
    except Exception:
        db.session.rollback()
        if trashed_id:
            try:
                restore_document(trashed_id)
            except Exception:
                current_app.logger.exception('Return shipping label needs Drive recovery: %s', trashed_id)
        current_app.logger.exception('Return shipping label update failed')
        return jsonify(ok=False, error='The shipping label could not be updated. Please retry.'), 500
    return jsonify(ok=True, document=document_data(getattr(control, field)), session_ids=[peer.exam_session_id for peer in affected])


def restore_document(file_id):
    import json
    from urllib.request import Request, urlopen
    from app.google_drive import API, access_token
    with urlopen(Request(API + '/files/' + file_id + '?supportsAllDrives=true', method='PATCH',
        data=json.dumps({'trashed': False}).encode(), headers={
            'Authorization': 'Bearer ' + access_token(), 'Content-Type': 'application/json'}), timeout=15) as response:
        result = json.load(response)
    if result.get('trashed') is not False:
        raise DriveStorageError('The shipping label could not be restored after a database error.')


@return_labels_bp.get('/pre-session-control-tower/return-labels/<file_id>')
@login_required
def preview(file_id):
    from app.routes import require_menu_view
    require_menu_view('pre_session_control_tower')
    document = db.session.get(ReturnShippingLabel, file_id)
    if not document or not linked_controls(file_id):
        abort(404)
    return stream_document(document)


@return_labels_bp.after_request
def private(response):
    response.headers['Cache-Control'] = 'private, no-store'
    response.headers['Referrer-Policy'] = 'no-referrer'
    return response
