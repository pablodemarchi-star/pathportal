"""Private Onsite session announcements, autosaved independently of staff cards."""
from dataclasses import dataclass
from types import SimpleNamespace
import re
from flask import Blueprint, abort, jsonify, request, url_for
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm.exc import StaleDataError
from werkzeug.exceptions import HTTPException
from app import db, login_required, validate_csrf
from app.models import ExamSession, ExamSessionAnnouncement as Announcement, ExamSessionAnnouncementControl as Control, StaffExamSessionsShare
from app.google_drive import upload_document, stream_document, DriveStorageError
from app.staff_invoices import trash_document

bp = Blueprint('announcements', __name__)
FOLDER_ID = '18WLG_ySfTwpSbFOcAPp8pkqBSZlPUI-L'


@dataclass
class AnnouncementTarget:
    request_number: str
    document: object


def state(record):
    control = db.session.get(Control, record.id)
    rows = Announcement.query.filter_by(exam_session_id=record.id).order_by(Announcement.created_at, Announcement.id).all()
    return dict(revision=control.revision if control else 0, enabled=bool(control and control.enabled),
                ready=bool(control and control.enabled and control.ready and rows),
                announcements=[dict(id=row.id, title=row.title, filename=row.filename,
                    audio_url=url_for('announcements.audio', session_id=record.id, announcement_id=row.id)) for row in rows])


def pending_action(record, today=None):
    control = db.session.get(Control, record.id) if record.format == 'Onsite' else None
    if not control or not control.enabled or control.ready:
        return []
    from app.routes import logistics_session_deadline, LOCAL_TZ
    from datetime import datetime
    deadline = logistics_session_deadline(record)
    return [dict(department='LOGISTICS', description='Upload session announcements', section='logistics',
                 overdue=bool(deadline and deadline < (today or datetime.now(LOCAL_TZ).date())))]


def load(session_id, write=False):
    from app.routes import require_menu_edit, require_menu_view, logistics_actions_are_blocked
    (require_menu_edit if write else require_menu_view)('pre_session_control_tower')
    if write:
        if not validate_csrf():
            abort(403, description='Security token expired. Reload the page and try again.')
        if db.engine.dialect.name == 'sqlite':
            connection = db.session.connection()
            if not connection.connection.driver_connection.in_transaction:
                connection.exec_driver_sql('BEGIN IMMEDIATE')
        else:
            db.session.query(ExamSession.id).filter_by(id=session_id).with_for_update().first()
    record = db.session.get(ExamSession, session_id)
    if not record or record.format != 'Onsite':
        abort(404)
    if write and logistics_actions_are_blocked(record):
        abort(403, description='Logistics is blocked. Complete the required staffing checks first.')
    return record


@bp.errorhandler(HTTPException)
def error(exc):
    return jsonify(ok=False, error=exc.description), exc.code


@bp.after_request
def private(response):
    response.headers['Cache-Control'] = 'private, no-store'
    response.headers['Referrer-Policy'] = 'no-referrer'
    response.headers['X-Robots-Tag'] = 'noindex, nofollow'
    return response


@bp.get('/pre-session-control-tower/sessions/<int:session_id>/announcements')
@login_required
def listing(session_id):
    from app.routes import user_can_edit, logistics_actions_are_blocked
    record = load(session_id)
    return jsonify(ok=True, can_edit=user_can_edit('pre_session_control_tower') and not logistics_actions_are_blocked(record), **state(record))


def valid_audio(upload):
    extension = (upload.filename or '').rsplit('.', 1)[-1].lower()
    header = upload.stream.read(12)
    upload.stream.seek(0)
    if extension == 'wav' and len(header) >= 12 and header[:4] == b'RIFF' and header[8:12] == b'WAVE':
        return 'audio/wav'
    if extension == 'mp3' and (header.startswith(b'ID3') or len(header) >= 2 and header[0] == 255 and header[1] & 0xe0 == 0xe0):
        return 'audio/mpeg'
    abort(400, description='Choose a valid MP3 or WAV audio file.')


@bp.post('/pre-session-control-tower/sessions/<int:session_id>/announcements')
@login_required
def update(session_id):
    record = load(session_id, write=True)
    control = db.session.get(Control, session_id)
    try:
        revision = int(request.form.get('revision', ''))
    except ValueError:
        abort(400, description='The announcement version is missing. Reload this session.')
    if revision != (control.revision if control else 0):
        abort(409, description='Announcements were changed by another user. Reopen this session to load the latest version.')
    if control is None:
        control = Control(exam_session_id=session_id, enabled=False, ready=False)
        db.session.add(control)
    action = request.form.get('action')
    try:
        if action == 'toggle':
            if request.form.get('enabled') not in {'0', '1'}:
                abort(400)
            control.enabled = request.form['enabled'] == '1'
            control.ready = False
        elif action in {'ready', 'pending'}:
            if not control.enabled:
                abort(409, description='Enable Announcements first.')
            if action == 'ready' and not Announcement.query.filter_by(exam_session_id=session_id).first():
                abort(400, description='Add at least one announcement with a title and audio before marking it ready.')
            control.ready = action == 'ready'
        elif action in {'save', 'delete'}:
            if not control.enabled:
                abort(409, description='Announcements has been disabled. Saved announcements have been retained.')
            key = request.form.get('id', '')
            if not re.fullmatch(r'[a-f0-9-]{36}', key):
                abort(400)
            row = Announcement.query.filter_by(exam_session_id=session_id, id=key).first()
            if action == 'delete':
                if row is None:
                    abort(409, description='This announcement has already been removed.')
                trash_document(row)
                db.session.delete(row)
            else:
                title = request.form.get('title', '').strip()
                uploads = [file for file in request.files.getlist('audio') if file.filename]
                if not title or len(title) > 300:
                    abort(400, description='Enter a title of at most 300 characters.')
                if len(uploads) > 1 or (row is None and not uploads):
                    abort(400, description='Choose one MP3 or WAV audio file for this announcement.')
                mime = valid_audio(uploads[0]) if uploads else None
                old = SimpleNamespace(file_id=row.file_id) if row else None
                if row is None:
                    row = Announcement(id=key, exam_session_id=session_id)
                    db.session.add(row)
                row.title = title
                if uploads:
                    uploads[0].headers['Content-Type'] = mime
                    upload_document(uploads[0], AnnouncementTarget('Announcement - ' + record.exam_session_name + ' - ' + title, row),
                                    SimpleNamespace(key='session_announcements', folder_id=FOLDER_ID))
                db.session.flush()
                if old and uploads:
                    trash_document(old)
            control.ready = False
        else:
            abort(400)
        control.revision = revision + 1
        db.session.commit()
    except (IntegrityError, StaleDataError):
        db.session.rollback()
        abort(409, description='Announcements were changed by another user. Reopen this session before continuing.')
    except OSError as exc:
        db.session.rollback()
        message = str(exc).replace('invoice', 'audio') if isinstance(exc, DriveStorageError) else 'The audio could not be saved. Please retry.'
        return jsonify(ok=False, error=message), 503
    return jsonify(ok=True, **state(record))


@bp.get('/pre-session-control-tower/sessions/<int:session_id>/announcements/<announcement_id>/audio')
@login_required
def audio(session_id, announcement_id):
    load(session_id)
    return stream_document(Announcement.query.filter_by(exam_session_id=session_id, id=announcement_id).first_or_404())


def staff_allowed(record, share):
    from app.routes import staff_submission_assignment
    if not record or record.format != 'Onsite':
        return False
    control = db.session.get(Control, record.id)
    if not control or not control.enabled or not control.ready:
        return False
    for submission in share.submissions:
        if submission.exam_session_id != record.id or submission.assignment_type != 'supervisor':
            continue
        assignment, ref = staff_submission_assignment(record, 'supervisor', submission.assignment_id)
        if assignment and ref == share.person_ref and assignment.participation_status == 'Confirmed':
            return True
    return False


def staff_view(record, role, assignment, share):
    if role != 'supervisor' or assignment.participation_status != 'Confirmed' or not staff_allowed(record, share):
        return None
    rows = Announcement.query.filter_by(exam_session_id=record.id).order_by(Announcement.created_at, Announcement.id).all()
    return [dict(title=row.title, audio_url=url_for('announcements.staff_audio', token=share.token, session_id=record.id, announcement_id=row.id)) for row in rows] or None


@bp.get('/my-exam-sessions/<token>/sessions/<int:session_id>/announcements/<announcement_id>/audio')
def staff_audio(token, session_id, announcement_id):
    share = StaffExamSessionsShare.query.filter_by(token=token).first_or_404()
    if not staff_allowed(db.session.get(ExamSession, session_id), share):
        abort(404)
    return stream_document(Announcement.query.filter_by(exam_session_id=session_id, id=announcement_id).first_or_404())
