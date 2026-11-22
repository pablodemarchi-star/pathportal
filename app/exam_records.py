"""Speaking records for the online session control tower."""
from dataclasses import dataclass
from datetime import timedelta
from pathlib import PurePosixPath
from types import SimpleNamespace
from urllib.parse import urlsplit
import hashlib
import json
import re

from flask import Blueprint, abort, current_app, jsonify, request, session, send_file
from sqlalchemy import event, inspect
from sqlalchemy.orm import Session
from app import db, login_required, validate_csrf
from app.models import (ExamSession, ExamRecordsControl, ExaminerSpeakingRecord, BeyondSetupControl, RWMarkingRecord, SpeakingRecordsSetup,
    ListeningRecordsSetup, ListeningMarkingRecord, ExamSessionScheduleWorkflow, ExamSessionSupervisorAssignment,
    ExamSessionExaminerAssignment, ExamSessionInternAssignment, ExamSessionStaffingControl)
from app.google_drive import DriveStorageError, folder_metadata, upload_document

exam_records_bp = Blueprint('exam_records', __name__)


@dataclass
class ExamRecordTarget:
    session_id: int
    person_ref: str
    document: object = None


@dataclass
class RWMarkingRecordTarget:
    session_id: int
    document: object = None
    kind: str = 'beyond'


def examiners(record):
    people = {}
    for assignment in record.examiner_assignments:
        person = assignment.team_member or assignment.potential_entry
        if person:
            ref = ('staff:' if assignment.team_member_id else 'potential:') + str(person.id)
            item = people.setdefault(ref, dict(ref=ref, name=person.full_name, confirmed=False))
            item['confirmed'] |= assignment.participation_status == 'Confirmed'
    return sorted(people.values(), key=lambda person: person['name'].casefold())


def revision(record):
    workflow = record.schedule_workflow
    value = [record.exam_session_name, str(record.session_date), record.schedule_folder_url, record.details_url,
             [workflow.status, workflow.review_round, str(workflow.approved_at), str(workflow.last_sent_at)] if workflow else None,
             [(a.id, a.team_member_id, a.potential_entry_id, a.participation_status,
               a.start_time, a.end_time, a.time_ranges) for a in record.examiner_assignments]]
    return hashlib.sha256(json.dumps(value, default=str).encode()).hexdigest()


def speaking_state(record):
    setup = db.session.get(SpeakingRecordsSetup, record.id)
    current_revision = revision(record)
    count = setup.completed_steps if setup and setup.revision == current_revision else 0
    return dict(count=count, revision=current_revision)


@exam_records_bp.route('/pre-online-session-control-tower/sessions/<int:session_id>/speaking-template')
@login_required
def speaking_template(session_id):
    from app.routes import require_menu_view, PRE_SESSION_SESSIONS_VIEW_EXCLUDED_FORMATS
    require_menu_view('pre_session_control_tower')
    record = db.session.get(ExamSession, session_id)
    if not record or record.format not in PRE_SESSION_SESSIONS_VIEW_EXCLUDED_FORMATS:
        abort(404)
    if not state(record)['unlocked']:
        abort(403)
    from pathlib import Path
    return send_file(Path(current_app.root_path) / 'downloads' / 'Speaking import Excel template.xlsx',
                     as_attachment=True, download_name='Speaking import Excel template.xlsx', max_age=0)


def beyond_revision(record):
    value = [record.exam_session_name, str(record.session_date), record.schedule_folder_url, record.details_url]
    return hashlib.sha256(json.dumps(value).encode()).hexdigest()


def beyond_state(record, kind='beyond'):
    setup_model, document_model, prefix = (ListeningRecordsSetup, ListeningMarkingRecord, 'L - ') if kind == 'listening' else (BeyondSetupControl, RWMarkingRecord, 'RW - ')
    control = db.session.get(setup_model, record.id)
    current_revision = beyond_revision(record)
    count = control.completed_steps if control and control.revision == current_revision else 0
    return dict(count=count, revision=current_revision, name=prefix + record.exam_session_name, document=db.session.get(document_model, record.id))


@exam_records_bp.route('/pre-online-session-control-tower/sessions/<int:session_id>/beyond-template')
@login_required
def beyond_template(session_id):
    from app.routes import require_menu_view, PRE_SESSION_SESSIONS_VIEW_EXCLUDED_FORMATS
    require_menu_view('pre_session_control_tower')
    record = db.session.get(ExamSession, session_id)
    if not record or record.format not in PRE_SESSION_SESSIONS_VIEW_EXCLUDED_FORMATS:
        abort(404)
    if not state(record)['unlocked']:
        abort(403)
    from pathlib import Path
    filename = 'Listening import Excel template.xlsx' if request.args.get('kind') == 'listening' else 'Reading and Writing import Excel template.xlsx'
    return send_file(Path(current_app.root_path) / 'downloads' / filename,
                     as_attachment=True, download_name=filename, max_age=0)


def state(record):
    from app.routes import staffing_readiness_contract, schedule_gate_status, deadline_badge_contract
    staffing = staffing_readiness_contract(record.supervisor_assignments, record.examiner_assignments,
                                          record.intern_assignments, session_record=record)
    people = examiners(record)
    documents = {d.person_ref: d for d in ExaminerSpeakingRecord.query.filter_by(exam_session_id=record.id)}
    control = db.session.get(ExamRecordsControl, record.id)
    confirmed = [p for p in people if p['confirmed']]
    unlocked = bool(confirmed and staffing['ready'] and schedule_gate_status(record.schedule_workflow)['is_ready'])
    for person in people:
        person['document'] = documents.get(person['ref'])
    sections = dict(listening=beyond_state(record, 'listening'), speaking=speaking_state(record), beyond=beyond_state(record))
    modules = {module.lower() for module in record.modules_list()}
    required = []
    if modules & {'speaking', 'listening and speaking'}:
        required.append(('speaking', 3))
    if 'reading and writing' in modules:
        required.append(('beyond', 6))
    if 'listening and speaking' in modules:
        required.append(('listening', 6))
    started = bool(control and control.started) or any(sections[key]['count'] for key, _ in required)
    completed = bool(required) and all(sections[key]['count'] == total for key, total in required)
    status = 'completed' if completed else 'in_progress' if required and started else 'not_started'
    label = {'completed': 'Completed', 'in_progress': 'In progress', 'not_started': 'Not started'}[status]
    action = None
    if unlocked and required and not completed:
        action = dict(department='LOGISTICS', section='exam_records',
                      description='Finalise the exam record configuration for the session' if status == 'in_progress' else 'Configure exam records for the session')
    return dict(**sections, unlocked=unlocked, people=people, count=sum(p['ref'] in documents for p in confirmed),
                total=len(confirmed), started=started, status=status, label=label, action=action,
                status_class={'completed': 'confirmed', 'in_progress': 'awaiting-confirmations', 'not_started': 'not-configured'}[status],
                deadline=deadline_badge_contract(record.session_date - timedelta(days=7) if record.session_date else None))


def online_session_readiness(record, schedule, staffing, finance, final_checks):
    records = state(record)
    requirements = [
        dict(key='schedule', label='Schedule', ready=bool(schedule.get('is_ready'))),
        dict(key='staffing', label='Staffing', ready=bool(staffing.get('ready'))),
        dict(key='finance', label='Finance', ready=bool(finance.get('can_proceed') and finance.get('block_label') == 'Cleared')),
        dict(key='exam_records', label='Exam records', ready=records['unlocked'] and records['status'] == 'completed'),
        dict(key='sinapsis', label='Final checks', ready=final_checks.get('progress') == 'completed'),
    ]
    for item in requirements:
        item['status'] = 'Completed' if item['ready'] else 'Pending'
        item['message'] = item['label'] + (' is complete.' if item['ready'] else ' must be confirmed or completed.')
    ready = all(item['ready'] for item in requirements)
    message = 'Schedule, Staffing, Finance, Exam records and Final checks are complete.' if ready else 'Pending: ' + ', '.join(item['label'] for item in requirements if not item['ready']) + '.'
    status = 'session_ready' if ready else 'in_progress'
    return dict(status=status, label='Session ready' if ready else 'In progress', is_ready=ready,
                ready_requirements=sum(item['ready'] for item in requirements), total_requirements=5,
                summary='5 / 5 requirements complete' if ready else message, message=message,
                requirements=requirements, blockers=[dict(source=item['key'], code=item['key'].upper() + '_NOT_READY', message=item['message']) for item in requirements if not item['ready']],
                tooltip=message, scope_note='This status covers Schedule, Staffing, Finance, Exam records and Final checks.')


@exam_records_bp.app_context_processor
def template_helpers():
    cache = {}
    def presentation(record):
        if record.id not in cache:
            cache[record.id] = state(record)
        return cache[record.id]
    return dict(exam_records_state=presentation)


@exam_records_bp.route('/pre-online-session-control-tower/sessions/<int:session_id>/exam-records', methods=['POST'])
@login_required
def update(session_id):
    from app.routes import require_menu_edit, PRE_SESSION_SESSIONS_VIEW_EXCLUDED_FORMATS
    require_menu_edit('pre_session_control_tower')
    if not validate_csrf():
        return jsonify(ok=False, error='Security token expired. Reload the page.'), 403
    # Serialize replacements and state transitions for a session.
    if db.engine.dialect.name == 'sqlite':
        connection = db.session.connection()
        if not connection.connection.driver_connection.in_transaction:
            connection.exec_driver_sql('BEGIN IMMEDIATE')
    else:
        db.session.query(ExamSession.id).filter_by(id=session_id).with_for_update().first()
    record = db.session.get(ExamSession, session_id)
    if not record or record.format not in PRE_SESSION_SESSIONS_VIEW_EXCLUDED_FORMATS:
        abort(404)
    current = state(record)
    if not current['unlocked']:
        return jsonify(ok=False, error='Exam records is blocked until Schedule and Staffing are confirmed and at least one Examiner is confirmed.'), 409
    control = db.session.get(ExamRecordsControl, session_id)
    if not control:
        control = ExamRecordsControl(exam_session_id=session_id)
        db.session.add(control)
    action = request.form.get('action')
    if action in {'upload', 'rw_upload', 'listening_upload'}:
        rw_upload = action in {'rw_upload', 'listening_upload'}
        kind = 'listening' if action == 'listening_upload' else 'beyond'
        setup_model = ListeningRecordsSetup if kind == 'listening' else BeyondSetupControl
        if rw_upload and (current[kind]['count'] < 5 or request.form.get('revision') != current[kind]['revision']):
            return jsonify(ok=False, error='Complete the first five setup steps before uploading records. Reload if session details changed.'), 409
        if not rw_upload and (current['speaking']['count'] < 2 or request.form.get('revision') != current['speaking']['revision']):
            return jsonify(ok=False, error='Complete the first two Speaking steps before uploading records. Reload if session details changed.'), 409
        if not record.session_date:
            return jsonify(ok=False, error='Set the exam session date before uploading records.'), 400
        person = next((p for p in current['people'] if p['ref'] == request.form.get('person_ref') and p['confirmed']), None)
        files = request.files.getlist('record')
        if (not rw_upload and not person) or len(files) != 1 or not files[0].filename:
            return jsonify(ok=False, error='Select exactly one Excel file.' if rw_upload else 'Select one file for a confirmed Examiner.'), 400
        previous = current[kind]['document'] if rw_upload else person['document']
        if request.form.get('previous_file_id', '') != (previous.file_id if previous else ''):
            return jsonify(ok=False, error='This record has changed. Reload the page before replacing it.'), 409
        folder_url = urlsplit(record.digitalised_exams_url or '')
        match = re.search(r'/folders/([A-Za-z0-9_-]{10,160})(?:/|$)', folder_url.path)
        if folder_url.scheme != 'https' or folder_url.hostname != 'drive.google.com' or not match:
            return jsonify(ok=False, error='Configure a Digitalised exams Drive folder in Exam sessions first.'), 400
        upload = files[0]
        suffix = PurePosixPath(upload.filename.replace('\\', '/')).suffix
        if rw_upload and suffix.lower() not in {'.xlsx', '.xls'}:
            return jsonify(ok=False, error='Choose an Excel file (.xlsx or .xls).'), 400
        prefix = ('Listening marking record' if kind == 'listening' else 'RW marking record') if rw_upload else person['name']
        upload.filename = f"{prefix} - {record.exam_session_name} - {record.session_date:%d-%m-%Y}{suffix}"
        # Replace path separators in generated names without losing spaces or accents.
        upload.filename = upload.filename.replace('/', '-').replace('\\', '-')
        try:
            folder_metadata(match[1])
            target = RWMarkingRecordTarget(session_id, previous, kind) if rw_upload else ExamRecordTarget(session_id, person['ref'], previous)
            upload_document(upload, target, SimpleNamespace(folder_id=match[1]))
            control.started = True
            if rw_upload:
                setup = db.session.get(setup_model, session_id)
                setup.completed_steps = 5
                setup.updated_by = str(session.get('user', ''))
            if not rw_upload:
                setup = db.session.get(SpeakingRecordsSetup, session_id)
                setup.completed_steps = 2
                setup.updated_by = str(session.get('user', ''))
        except DriveStorageError as exc:
            db.session.rollback()
            return jsonify(ok=False, error=str(exc)), 503
    elif action in {'beyond', 'listening'}:
        kind = action
        setup_model = ListeningRecordsSetup if kind == 'listening' else BeyondSetupControl
        if request.form.get('revision') != current[kind]['revision']:
            return jsonify(ok=False, error='Session details changed. Reload the page and review Beyond setup.'), 409
        try:
            step = int(request.form.get('step', ''))
            previous = int(request.form.get('previous_steps', ''))
        except ValueError:
            return jsonify(ok=False, error='Choose a valid Beyond setup step.'), 400
        checked = request.form.get('checked')
        count = current[kind]['count']
        if previous != count:
            return jsonify(ok=False, error='Beyond setup was updated. Reload the page to continue.'), 409
        if step not in range(1, 7) or checked not in {'0', '1'}:
            return jsonify(ok=False, error='Choose a valid Beyond setup step.'), 400
        if (checked == '1' and step != count + 1) or (checked == '0' and step > count):
            return jsonify(ok=False, error='Complete the previous Beyond setup step first.'), 409
        if step == 6 and checked == '1' and not current[kind]['document']:
            return jsonify(ok=False, error='Upload the Excel file before completing step 6.'), 409
        setup = db.session.get(setup_model, session_id)
        if not setup:
            setup = setup_model(exam_session_id=session_id)
            db.session.add(setup)
        setup.completed_steps = step if checked == '1' else step - 1
        setup.revision = current[kind]['revision']
        setup.updated_by = str(session.get('user', ''))
        if checked == '1':
            control.started = True
    elif action == 'speaking':
        if request.form.get('revision') != current['speaking']['revision']:
            return jsonify(ok=False, error='Session details changed. Reload the page and review Speaking records.'), 409
        try:
            step = int(request.form.get('step', ''))
            previous = int(request.form.get('previous_steps', ''))
        except ValueError:
            return jsonify(ok=False, error='Choose a valid Speaking step.'), 400
        checked = request.form.get('checked')
        count = current['speaking']['count']
        if previous != count:
            return jsonify(ok=False, error='Speaking records was updated. Reload the page.'), 409
        if step not in range(1, 4) or checked not in {'0', '1'}:
            return jsonify(ok=False, error='Choose a valid Speaking step.'), 400
        if (checked == '1' and step != count + 1) or (checked == '0' and step > count):
            return jsonify(ok=False, error='Complete the previous Speaking step first.'), 409
        if step == 3 and checked == '1' and (not current['total'] or current['count'] != current['total']):
            return jsonify(ok=False, error='Upload a record for every confirmed Examiner before completing step 3.'), 409
        setup = db.session.get(SpeakingRecordsSetup, session_id)
        if not setup:
            setup = SpeakingRecordsSetup(exam_session_id=session_id)
            db.session.add(setup)
        setup.completed_steps = step if checked == '1' else step - 1
        setup.revision = current['speaking']['revision']
        setup.updated_by = str(session.get('user', ''))
        if checked == '1':
            control.started = True
    else:
        return jsonify(ok=False, error='Unknown action.'), 400
    control.updated_by = str(session.get('user', ''))
    db.session.commit()
    return jsonify(ok=True)


@event.listens_for(Session, 'before_flush')
def invalidate_check(unit, flush_context, instances):
    sessions = set()
    for obj in list(unit.dirty) + list(unit.new) + list(unit.deleted):
        if isinstance(obj, (ExamSessionScheduleWorkflow, ExamSessionSupervisorAssignment,
                            ExamSessionExaminerAssignment, ExamSessionInternAssignment)):
            keys = ('status', 'review_round', 'approved_at', 'last_sent_at') if isinstance(obj, ExamSessionScheduleWorkflow) else (
                'team_member_id', 'potential_entry_id', 'participation_status', 'start_time', 'end_time', 'time_ranges')
            if obj in unit.new or obj in unit.deleted or any(inspect(obj).attrs[key].history.has_changes() for key in keys):
                sessions.add(obj.exam_session_id)
        elif isinstance(obj, ExamSessionStaffingControl):
            if inspect(obj).attrs.schedule_notification_confirmed.history.has_changes():
                sessions.add(obj.exam_session_id)
        elif isinstance(obj, ExamSession):
            if any(inspect(obj).attrs[key].history.has_changes() for key in
                   ('exam_session_name', 'session_date', 'schedule_folder_url', 'details_url')):
                for setup_model in (BeyondSetupControl, ListeningRecordsSetup):
                    setup = unit.get(setup_model, obj.id) if obj.id else None
                    if setup:
                        setup.completed_steps = 0
                        setup.revision = beyond_revision(obj)
            if any(inspect(obj).attrs[key].history.has_changes() for key in
                   ('exam_session_name', 'session_date', 'schedule_folder_url', 'details_url')):
                sessions.add(obj.id)
    for sid in sessions - {None}:
        setup = unit.get(SpeakingRecordsSetup, sid)
        if setup:
            setup.completed_steps = 0
