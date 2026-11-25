"""Private, independently autosaved PEN arrangements in Final checks."""
import json
import hashlib
from datetime import datetime, timezone
import re
from dataclasses import dataclass
from types import SimpleNamespace

from flask import Blueprint, abort, g, has_app_context, jsonify, request, session, url_for
from werkzeug.exceptions import HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm.exc import StaleDataError
from app import db, login_required, validate_csrf
from app.models import ExamSession, ExamSessionPenCandidate, ExamSessionPenControl
from app.rich_text import sanitize_instructions
from app.google_drive import DriveStorageError, stream_document, upload_document
from app.staff_invoices import trash_document

pen_bp = Blueprint('pen_arrangements', __name__)
FOLDER_ID = '1eAMGIptHmy7O9sgeyqon3UTQ8c32gsXu'


@dataclass
class PenReportTarget:
    request_number: str
    document: object


def _completion(rows, control):
    snapshot = hashlib.sha256(json.dumps(sorted((row.id, row.revision) for row in rows)).encode()).hexdigest()
    no_arrangements = bool(control and control.no_arrangements_required)
    valid_mode = not rows if no_arrangements else bool(rows)
    complete = bool(valid_mode and control and control.confirmed_at and control.confirmed_snapshot == snapshot)
    return dict(count=len(rows), complete=complete, no_arrangements_required=bool(complete and no_arrangements), snapshot=snapshot,
                completed_at=control.confirmed_at if complete else None)


def completion_state(record):
    cache = getattr(g, '_pen_arrangement_states', {}) if has_app_context() else {}
    if record.id in cache:
        return cache[record.id]
    rows = db.session.query(ExamSessionPenCandidate.id, ExamSessionPenCandidate.revision).filter_by(exam_session_id=record.id).all()
    return _completion(rows, db.session.get(ExamSessionPenControl, record.id))


def completion_states(records):
    """Batch the PEN requirements used by Quality control's session grid."""
    ids = [record.id for record in records if record.pen_enabled]
    if not ids:
        return {}
    controls = {control.exam_session_id: control for control in ExamSessionPenControl.query.filter(ExamSessionPenControl.exam_session_id.in_(ids)).all()}
    rows = {sid: [] for sid in ids}
    for row in db.session.query(ExamSessionPenCandidate.exam_session_id, ExamSessionPenCandidate.id, ExamSessionPenCandidate.revision).filter(ExamSessionPenCandidate.exam_session_id.in_(ids)).all():
        rows[row.exam_session_id].append(row)
    return {sid: _completion(rows[sid], controls.get(sid)) for sid in ids}


def mark_pending(record):
    control = db.session.get(ExamSessionPenControl, record.id)
    if control:
        control.confirmed_snapshot = ''
        control.no_arrangements_required = False
        control.confirmed_at = None
        control.confirmed_by = ''
    if has_app_context():
        getattr(g, '_pen_arrangement_states', {}).pop(record.id, None)


def completion_data(record):
    result = dict(completion_state(record))
    result['completed_at'] = result['completed_at'].isoformat() if result['completed_at'] else None
    return result


def examiner_options(record):
    if record.format == 'Online at exam centre':
        return []
    from app.routes import staffing_assignment_person_ref
    options = {}
    for assignment in record.examiner_assignments:
        person = assignment.team_member or assignment.potential_entry
        if person:
            ref = staffing_assignment_person_ref(assignment)
            options[ref] = dict(value=ref, label=person.full_name)
    return sorted(options.values(), key=lambda item: item['label'].casefold())


def candidate_data(row):
    return dict(id=row.id, revision=row.revision, candidate_no=row.candidate_no, candidate_name=row.candidate_name,
                recommendations_html=sanitize_instructions(row.recommendations_html), examiner_refs=json.loads(row.examiner_refs),
                document=dict(filename=row.filename, url=url_for('pen_arrangements.document', session_id=row.exam_session_id, candidate_id=row.id)) if row.file_id else None)


def load_record(session_id, write=False):
    from app.routes import require_menu_view, require_menu_edit
    require_menu_edit('pre_session_control_tower') if write else require_menu_view('pre_session_control_tower')
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
    if record is None or record.format not in {'Online', 'Onsite', 'Online at exam centre'}:
        abort(404)
    if write and not record.pen_enabled:
        abort(409, description='PEN has been deactivated for this session. Your saved arrangements have been retained.')
    return record


@pen_bp.errorhandler(HTTPException)
def api_error(error):
    return jsonify(ok=False, error=error.description), error.code


@pen_bp.after_request
def private(response):
    response.headers['Cache-Control'] = 'private, no-store'
    response.headers['Referrer-Policy'] = 'no-referrer'
    return response


@pen_bp.get('/pre-session-control-tower/sessions/<int:session_id>/pen-candidates')
@login_required
def listing(session_id):
    from app.routes import user_can_edit
    record = load_record(session_id)
    rows = ExamSessionPenCandidate.query.filter_by(exam_session_id=session_id).order_by(ExamSessionPenCandidate.created_at, ExamSessionPenCandidate.id).all()
    return jsonify(ok=True, enabled=bool(record.pen_enabled), can_edit=user_can_edit('pre_session_control_tower'),
                   examiners_disabled=record.format == 'Online at exam centre', examiners=examiner_options(record),
                   candidates=[candidate_data(row) for row in rows], completion=completion_data(record))


@pen_bp.post('/pre-session-control-tower/sessions/<int:session_id>/pen-candidates/<candidate_id>')
@login_required
def save(session_id, candidate_id):
    record = load_record(session_id, write=True)
    if not re.fullmatch(r'[a-f0-9-]{36}', candidate_id):
        abort(400)
    row = ExamSessionPenCandidate.query.filter_by(exam_session_id=session_id, id=candidate_id).first()
    try:
        revision = int(request.form.get('revision', ''))
    except ValueError:
        return jsonify(ok=False, error='The candidate version is missing. Reload this session.'), 400
    if (row.revision if row else 0) != revision:
        return jsonify(ok=False, error='This candidate was changed or removed by another user. Reopen the session to load the latest version.'), 409
    deleting = request.form.get('action') == 'delete'
    if deleting and row is None:
        return jsonify(ok=False, error='This candidate has already been removed.'), 409
    try:
        if deleting:
            if row.file_id:
                trash_document(row)
            db.session.delete(row)
            mark_pending(record)
            db.session.commit()
            return jsonify(ok=True, deleted=True, completion=completion_data(record))
        number, name = request.form.get('candidate_no', '').strip(), request.form.get('candidate_name', '').strip()
        if not number or not name:
            return jsonify(ok=False, error='Complete Candidate no. and Candidate name before this card can be saved.'), 400
        if len(number) > 80 or len(name) > 300:
            return jsonify(ok=False, error='Candidate no. must be at most 80 characters and Candidate name at most 300 characters.'), 400
        refs = sorted(set(request.form.getlist('examiner_refs')))
        if record.format == 'Online at exam centre':
            refs = []
        elif not refs or not set(refs).issubset({item['value'] for item in examiner_options(record)}):
            return jsonify(ok=False, error='Select at least one Examiner currently assigned to this session.'), 400
        recommendations = request.form.get('recommendations_html', '')
        if len(recommendations) > 50000:
            return jsonify(ok=False, error='Recommendations must be shorter than 50,000 characters.'), 400
        uploads = [file for file in request.files.getlist('document') if file.filename]
        if len(uploads) > 1:
            return jsonify(ok=False, error='Select a single Specialist assessment report per candidate.'), 400
        if uploads and request.form.get('remove_document') == '1':
            return jsonify(ok=False, error='Choose either replacing or removing the report.'), 400
        if row is None:
            row = ExamSessionPenCandidate(id=candidate_id, exam_session_id=session_id)
            db.session.add(row)
        old = SimpleNamespace(file_id=row.file_id) if row.file_id else None
        row.candidate_no, row.candidate_name = number, name
        row.recommendations_html = sanitize_instructions(recommendations)
        row.examiner_refs = json.dumps(refs)
        # Bump even for identical text so overlapping file changes never reuse a version.
        row.revision = revision + 1
        if uploads:
            target = PenReportTarget('PEN - ' + record.exam_session_name + ' - ' + number, row)
            upload_document(uploads[0], target, SimpleNamespace(key='pen_assessment_reports', folder_id=FOLDER_ID))
        elif request.form.get('remove_document') == '1':
            row.file_id = row.filename = row.mime_type = None
        mark_pending(record)
        db.session.flush()
        if old and (uploads or request.form.get('remove_document') == '1'):
            trash_document(old)
        db.session.commit()
    except (IntegrityError, StaleDataError):
        db.session.rollback()
        return jsonify(ok=False, error='This candidate was updated by another user. Reopen the session before continuing.'), 409
    except OSError as error:
        db.session.rollback()
        message = str(error).replace('invoice', 'report') if isinstance(error, DriveStorageError) else 'The assessment report could not be saved. Please retry.'
        return jsonify(ok=False, error=message), 503
    return jsonify(ok=True, candidate=candidate_data(row), completion=completion_data(record))


@pen_bp.get('/pre-session-control-tower/sessions/<int:session_id>/pen-candidates/<candidate_id>/document')
@login_required
def document(session_id, candidate_id):
    load_record(session_id)
    row = ExamSessionPenCandidate.query.filter_by(exam_session_id=session_id, id=candidate_id).first_or_404()
    if not row.file_id:
        abort(404)
    return stream_document(row)


@pen_bp.post('/pre-session-control-tower/sessions/<int:session_id>/pen-candidates/confirmation')
@login_required
def confirm(session_id):
    record = load_record(session_id, write=True)
    current = completion_state(record)
    if request.form.get('confirmed') not in {'0', '1'}:
        return jsonify(ok=False, error='Choose a valid PEN verification status.'), 400
    if request.form.get('snapshot') != current['snapshot']:
        return jsonify(ok=False, error='The PEN candidates have changed. Reopen the session and review the current arrangements before confirming.'), 409
    checked = request.form['confirmed'] == '1'
    mode = request.form.get('no_arrangements_required', '0')
    if mode not in {'0', '1'}:
        return jsonify(ok=False, error='Choose a valid PEN confirmation option.'), 400
    no_arrangements = mode == '1'
    if no_arrangements and current['count']:
        return jsonify(ok=False, error='No specific arrangements can only be confirmed when there are no candidate cards.'), 400
    if checked and not no_arrangements and not current['count']:
        return jsonify(ok=False, error='Add and save at least one candidate before confirming the PEN arrangements.'), 400
    control = db.session.get(ExamSessionPenControl, session_id)
    if control is None:
        control = ExamSessionPenControl(exam_session_id=session_id)
        db.session.add(control)
    control.confirmed_snapshot = current['snapshot'] if checked else ''
    control.no_arrangements_required = checked and no_arrangements
    control.confirmed_at = datetime.now(timezone.utc) if checked else None
    control.confirmed_by = session.get('user', '') if checked else ''
    db.session.commit()
    return jsonify(ok=True, completion=completion_data(record))


def staff_pen_view(record, role, assignment, share):
    """Confirmed supervisors see all cases; examiners see only their assignments."""
    if role not in {'examiner', 'supervisor'} or not record.pen_enabled or assignment.participation_status != 'Confirmed':
        return None
    from app.routes import staffing_assignment_person_ref
    if staffing_assignment_person_ref(assignment) != share.person_ref:
        return None
    supervisor = role == 'supervisor'
    names = {item['value']: item['label'] for item in examiner_options(record)} if supervisor else {}
    rows = ExamSessionPenCandidate.query.filter_by(exam_session_id=record.id).order_by(ExamSessionPenCandidate.created_at, ExamSessionPenCandidate.id).all()
    candidates = []
    for row in rows:
        refs = json.loads(row.examiner_refs)
        if not supervisor and share.person_ref not in refs:
            continue
        candidates.append(dict(id=row.id, number=row.candidate_no, name=row.candidate_name,
            recommendations_html=sanitize_instructions(row.recommendations_html),
            examiner_names=list(dict.fromkeys(names.get(ref, 'Examiner no longer assigned to this session') for ref in refs)) if supervisor and record.format != 'Online at exam centre' else [],
            examiner_assignment_note='Examiner assignment does not apply to this session format' if supervisor and record.format == 'Online at exam centre' else '',
            document=dict(filename=row.filename, url=url_for('pen_arrangements.staff_document', token=share.token,
                session_id=record.id, candidate_id=row.id)) if row.file_id else None))
    if not candidates:
        return None
    return dict(status='Completed' if completion_state(record)['complete'] else 'Pending', supervisor=supervisor, candidates=candidates)


@pen_bp.get('/my-exam-sessions/<token>/sessions/<int:session_id>/pen-candidates/<candidate_id>/document')
def staff_document(token, session_id, candidate_id):
    from app.models import StaffExamSessionsShare
    from app.routes import staff_submission_assignment
    share = StaffExamSessionsShare.query.filter_by(token=token).first_or_404()
    record = db.session.get(ExamSession, session_id)
    if record is None or not record.pen_enabled:
        abort(404)
    authorized = False
    supervisor = False
    for submission in share.submissions:
        if submission.exam_session_id != session_id or submission.assignment_type not in {'examiner', 'supervisor'}:
            continue
        assignment, person_ref = staff_submission_assignment(record, submission.assignment_type, submission.assignment_id)
        if assignment and person_ref == share.person_ref and assignment.participation_status == 'Confirmed':
            authorized = True
            if submission.assignment_type == 'supervisor':
                supervisor = True
                break
    if not authorized:
        abort(404)
    row = ExamSessionPenCandidate.query.filter_by(exam_session_id=session_id, id=candidate_id).first_or_404()
    if not row.file_id or (not supervisor and share.person_ref not in json.loads(row.examiner_refs)):
        abort(404)
    response = stream_document(row)
    response.headers['X-Robots-Tag'] = 'noindex, nofollow'
    return response
