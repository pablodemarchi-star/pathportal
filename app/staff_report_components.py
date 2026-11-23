"""Validate supervisor component absences and merge them atomically into Attendance."""
import json
import re
from app import db
from app import models as m


def applicable(record):
    return record.format == 'Online' and 'listening and speaking' in {module.lower() for module in record.modules_list()}


def validate(record, form):
    if not applicable(record):
        return '', []
    choice = form.get('component_completion', '')
    if choice not in {'complete', 'component_absences'}:
        raise ValueError('Select a Listening and Speaking module completion option.')
    if choice == 'complete':
        return choice, []
    try:
        rows = json.loads(form.get('component_absences', '[]'))
    except (ValueError, TypeError):
        raise ValueError('Enter valid candidate component absences.')
    if not isinstance(rows, list) or not 1 <= len(rows) <= 500:
        raise ValueError('Add at least one candidate component absence (maximum 500).')
    from app.post_attendance import EXAMS
    clean, numbers = [], set()
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError('Complete every candidate component absence.')
        item = {key: str(row.get(key, '')).strip() if isinstance(row.get(key, ''), str) else ''
                for key in ('number', 'name', 'institution', 'exam', 'component', 'reason')}
        if not re.fullmatch(r'[0-9]{1,80}', item['number']):
            raise ValueError('Enter a numeric candidate number, excluding the appended digit. Initial zeroes are preserved.')
        if item['number'] in numbers:
            raise ValueError('Enter each candidate number only once in this report.')
        numbers.add(item['number'])
        if any(not item[key] or len(item[key]) > maximum for key, maximum in (('name', 250), ('institution', 250), ('reason', 10000))):
            raise ValueError('Complete Candidate name, Institution and Reason for every candidate (Reason: maximum 10,000 characters).')
        if item['exam'] not in EXAMS or item['component'] not in {'Listening', 'Speaking'}:
            raise ValueError('Choose a valid Exam and one Absent component: Listening or Speaking.')
        clean.append(item)
    return choice, clean


def merge(record, rows):
    if not rows:
        return
    from app.post_attendance import institution_key, reset_review, reschedule_options, touch, workflow_state
    before = workflow_state(record)
    institutions = m.AttendanceInstitution.query.filter_by(exam_session_id=record.id).all()
    existing = {candidate.number_key: candidate for candidate in m.AbsenceCandidate.query.filter_by(exam_session_id=record.id).all()}
    default = reschedule_options(record)[1]
    changed_ids = []
    for item in rows:
        candidate = existing.get(item['number'])
        institution = next((value for value in institutions if institution_key(value.name) == institution_key(item['institution'])), None)
        if institution is None:
            institution = m.AttendanceInstitution(exam_session_id=record.id, name=item['institution'], is_main=False)
            db.session.add(institution); db.session.flush()
            institutions.append(institution)
        if candidate is None:
            candidate = m.AbsenceCandidate(exam_session_id=record.id, institution_id=institution.id,
                number=item['number'], number_key=item['number'], name=item['name'], absent_modules='[]',
                rescheduled_for=default, requested_rescheduled_for=default)
            db.session.add(candidate)
            existing[item['number']] = candidate
        modules = json.loads(candidate.absent_modules or '[]')
        changed = (item['component'] not in modules or candidate.component_reason != item['reason'] or
                   candidate.name != item['name'] or candidate.exam != item['exam'] or
                   institution_key(candidate.institution_name or '') != institution_key(item['institution']))
        if item['component'] not in modules:
            modules.append(item['component'])
        candidate.absent_modules = json.dumps(modules)
        candidate.component_reason = item['reason']
        candidate.name, candidate.exam = item['name'], item['exam']
        candidate.institution_id, candidate.institution_name = institution.id, item['institution']
        if changed:
            reset_review(candidate)
            changed_ids.append(item['number'])
    if changed_ids:
        value = touch(record)
        value.review_results_notified = False
        value.review_completed_at = None
        value.no_documentation_received = False
        db.session.flush()
        from app.attendance_tracking import sync_milestones
        sync_milestones(record, before, True, 'supervisor_component_absences')
