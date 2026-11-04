"""Choose one upcoming, unfinished Onsite session for each staff ID card."""
from flask import has_request_context, request
from sqlalchemy.orm import load_only
from app.models import (ExamSession, ExamSessionSupervisorAssignment,
                        ExamSessionExaminerAssignment, ExamSessionInternAssignment)

SHIFT_PRIORITY = {'Morning': 0, 'All day': 1, 'Afternoon': 2, 'Evening': 3}


def session_priority(record):
    shifts = record.shifts_list()
    return (record.session_date, min((SHIFT_PRIORITY.get(shift, 4) for shift in shifts), default=4),
            (record.exam_session_name or '').casefold(), record.id)


def staff_id_session_owners(today=None):
    from app.routes import pre_session_control_tower_today
    today = today or pre_session_control_tower_today()
    # Reuse one batch on read-only pages, never across a request or during writes.
    cacheable = has_request_context() and request.method == 'GET'
    cached = getattr(request, '_staff_id_session_owners', None) if cacheable else None
    if cached and cached[0] == today:
        return cached[1]
    records = ExamSession.query.options(load_only(ExamSession.id, ExamSession.session_date,
        ExamSession.shifts, ExamSession.exam_session_name, ExamSession.staff_member_ids_status,
        ExamSession.emergency_contact_member_id)).filter(
        ExamSession.format == 'Onsite', ExamSession.session_date >= today).all()
    records = [record for record in records if record.staff_member_ids_status != 'completed']
    by_id = {record.id: record for record in records}
    assignments = [(record.emergency_contact_member_id, record.id) for record in records
                   if record.emergency_contact_member_id]
    if by_id:
        for model in (ExamSessionSupervisorAssignment, ExamSessionExaminerAssignment, ExamSessionInternAssignment):
            assignments.extend(model.query.with_entities(model.team_member_id, model.exam_session_id).filter(
                model.exam_session_id.in_(by_id), model.team_member_id.isnot(None)).all())
    owners = {}
    for member_id, record_id in assignments:
        current = owners.get(member_id)
        if current is None or session_priority(by_id[record_id]) < session_priority(by_id[current]):
            owners[member_id] = record_id
    if cacheable:
        request._staff_id_session_owners = (today, owners)
    return owners
