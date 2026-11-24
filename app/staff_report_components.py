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
        if any(not item[key] or len(item[key]) > maximum for key, maximum in (('name', 250), ('reason', 10000))):
            raise ValueError('Complete Candidate name and Reason for every candidate (Reason: maximum 10,000 characters).')
        if item['exam'] not in EXAMS or item['component'] not in {'Listening', 'Speaking'}:
            raise ValueError('Choose a valid Exam and one Absent component: Listening or Speaking.')
        clean.append(item)
    return choice, clean


def it_module_options(record):
    from app.post_attendance import EXAMS, exam_modules
    canonical = {'speaking': 'Speaking', 'listening and speaking': 'Listening and speaking', 'reading and writing': 'Reading and writing'}
    session_modules = {canonical[value.lower()] for value in record.modules_list() if value.lower() in canonical}
    return {exam: [module for module in exam_modules(exam) if module in session_modules] for exam in EXAMS
            if session_modules.intersection(exam_modules(exam))}


def validate_it(record, form, component_rows=()):
    if record.format != 'Online':
        return None, []
    if form.get('it_issues') not in ('0', '1'):
        raise ValueError('Please select whether candidate IT issues were reported during the exam session.')
    checked = form.get('it_issues') == '1'
    if not checked:
        return False, []
    try:
        rows = json.loads(form.get('it_absences', '[]'))
    except (ValueError, TypeError):
        raise ValueError('Enter valid candidate IT issues.')
    if not isinstance(rows, list) or not 1 <= len(rows) <= 500:
        raise ValueError('Add at least one candidate with IT issues (maximum 500).')
    options, clean, numbers = it_module_options(record), [], set()
    components = {row['number']: row for row in component_rows}
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError('Complete every candidate with IT issues.')
        item = {key: row.get(key, '').strip() if isinstance(row.get(key, ''), str) else ''
                for key in ('number', 'name', 'institution', 'exam', 'reason')}
        if not re.fullmatch(r'[0-9]{1,80}', item['number']):
            raise ValueError('Enter the original numeric candidate number, preserving initial zeroes.')
        if item['number'] in numbers:
            raise ValueError('Enter each candidate number only once in Candidate IT issues.')
        numbers.add(item['number'])
        if any(not item[key] or len(item[key]) > maximum for key, maximum in (('name', 250), ('reason', 10000))):
            raise ValueError('Complete Candidate name and Reason for every candidate (Reason: maximum 10,000 characters).')
        modules = row.get('modules')
        if not isinstance(modules, list) or not modules or any(not isinstance(value, str) or value not in options.get(item['exam'], []) for value in modules):
            raise ValueError('Choose an Exam and Absent exam modules allowed for this session and exam level.')
        if 'Speaking' in modules and len(set(modules)) > 1:
            raise ValueError('Speaking cannot be combined with another absent exam module.')
        item['modules'] = list(dict.fromkeys(modules))
        previous = components.get(item['number'])
        if previous and (previous['name'].casefold() != item['name'].casefold() or previous['exam'] != item['exam']):
            raise ValueError('Candidate name and Exam must match in both report sections for candidate ' + item['number'] + '.')
        clean.append(item)
    return True, clean


def merge(record, rows, reason_field='component_reason'):
    if not rows:
        return
    from app.post_attendance import main_institution, reset_review, reschedule_options, touch, workflow_state
    before = workflow_state(record)
    existing = {candidate.number_key: candidate for candidate in m.AbsenceCandidate.query.filter_by(exam_session_id=record.id).all()}
    default = reschedule_options(record)[1]
    changed_ids = []
    for item in rows:
        candidate = existing.get(item['number'])
        if candidate is None:
            # Keep the required session-owned FK, but leave the actual institution
            # unassigned until an internal user completes it in Attendance.
            institution = main_institution(record, True)
            candidate = m.AbsenceCandidate(exam_session_id=record.id, institution_id=institution.id,
                number=item['number'], number_key=item['number'], name=item['name'], institution_name='', absent_modules='[]',
                rescheduled_for=default, requested_rescheduled_for=default)
            db.session.add(candidate)
            existing[item['number']] = candidate
        modules = json.loads(candidate.absent_modules or '[]')
        incoming_modules = item.get('modules') or [item['component']]
        changed = (any(value not in modules for value in incoming_modules) or getattr(candidate, reason_field) != item['reason'] or
                   candidate.name != item['name'] or candidate.exam != item['exam'])
        for value in incoming_modules:
            if value not in modules:
                modules.append(value)
        candidate.absent_modules = json.dumps(modules)
        setattr(candidate, reason_field, item['reason'])
        candidate.name, candidate.exam = item['name'], item['exam']
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
        sync_milestones(record, before, True, 'supervisor_it_absences' if reason_field == 'it_reason' else 'supervisor_component_absences')
