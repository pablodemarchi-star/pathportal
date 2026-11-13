"""Private session report uploads into each session's configured pictures folder."""
import re
from dataclasses import dataclass
from types import SimpleNamespace
from urllib.parse import urlsplit
from flask import abort, jsonify, request
from app import db, validate_csrf
from app.models import StaffExamSessionsShare, StaffExamSessionSubmission, StaffSessionReportMedia
from app.google_drive import folder_metadata, upload_document, DriveStorageError


@dataclass
class ReportMediaTarget:
    submission_id: int
    request_number: str
    document: object = None


def session_pictures_folder(record):
    try:
        parsed = urlsplit((record.session_pictures_folder_url or '').strip())
        if parsed.scheme != 'https' or parsed.hostname != 'drive.google.com' or parsed.username or parsed.password:
            return ''
        match = re.fullmatch(r'/(?:drive/(?:u/\d+/)?)?folders/([A-Za-z0-9_-]{10,160})/?', parsed.path)
        return match.group(1) if match else ''
    except ValueError:
        return ''


def lock_submission(submission_id):
    if db.engine.dialect.name == 'sqlite':
        connection = db.session.connection()
        if not connection.connection.driver_connection.in_transaction:
            connection.exec_driver_sql('BEGIN IMMEDIATE')
    return StaffExamSessionSubmission.query.filter_by(id=submission_id).with_for_update().populate_existing().first()


def media_for_submission(record, submission):
    folder_id = session_pictures_folder(record)
    return StaffSessionReportMedia.query.filter_by(submission_id=submission.id, folder_id=folder_id).order_by(StaffSessionReportMedia.id).all() if folder_id else []


def media_view(record, submission):
    return {'folder_configured': bool(session_pictures_folder(record)),
            'files': [{'id': item.id, 'filename': item.filename} for item in media_for_submission(record, submission)]}


def upload_media(token, submission_id):
    from app.routes import staff_submission_assignment, staff_report_available
    share = StaffExamSessionsShare.query.filter_by(token=token).first_or_404()
    if not validate_csrf():
        return jsonify(ok=False, error='Security token expired. Please reload and try again.'), 400
    submission = lock_submission(submission_id)
    if not submission or submission.share_id != share.id:
        abort(404)
    record = submission.exam_session
    assignment, person_ref = staff_submission_assignment(record, submission.assignment_type, submission.assignment_id)
    if not assignment or person_ref != share.person_ref:
        abort(404)
    if (submission.assignment_type != 'supervisor' or assignment.is_remote or record.format != 'Onsite'
            or assignment.participation_status != 'Confirmed' or not staff_report_available(record)):
        return jsonify(ok=False, error='Uploads are only available to confirmed onsite Supervisors on the exam day.'), 403
    if submission.session_report:
        return jsonify(ok=False, error='This report has already been submitted. Uploads are locked.'), 409
    folder_id = session_pictures_folder(record)
    if not folder_id:
        return jsonify(ok=False, error='Session pictures folder is not configured. Please contact Path Examinations.'), 400
    files = [item for item in request.files.getlist('file') if item.filename]
    if len(files) != 1:
        return jsonify(ok=False, error='Please upload one file per upload request.'), 400
    target = ReportMediaTarget(submission.id, f'{record.exam_session_name} - Marketing material')
    try:
        folder_metadata(folder_id)
        upload_document(files[0], target, SimpleNamespace(folder_id=folder_id))
        db.session.commit()
    except OSError as error:
        db.session.rollback()
        return jsonify(ok=False, error=str(error) if isinstance(error, DriveStorageError) else 'The file could not be uploaded. Please try again.'), 502
    return jsonify(ok=True, files=media_view(record, submission)['files'])
