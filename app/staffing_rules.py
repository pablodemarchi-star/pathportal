"""Remote supervision applies only to sessions with physical supervision support."""
from sqlalchemy import event, inspect
from sqlalchemy.orm import Session
from app.models import ExamSession, ExamSessionSupervisorAssignment, ExamSessionExaminerAssignment, ExamSessionInternAssignment

ONLINE_FORMATS = {'Online', 'Online at exam centre'}


@event.listens_for(Session, 'before_flush')
def prevent_online_remote_supervisors(unit, *_):
    for item in list(unit.new) + list(unit.dirty):
        if isinstance(item, ExamSessionSupervisorAssignment) and item.is_remote:
            record = item.exam_session or unit.get(ExamSession, item.exam_session_id)
            if record and record.format in ONLINE_FORMATS:
                item.is_remote = False
        elif isinstance(item, ExamSession) and item.format in ONLINE_FORMATS and inspect(item).attrs.format.history.has_changes():
            if item.id:
                for assignment in unit.query(ExamSessionSupervisorAssignment).filter_by(exam_session_id=item.id, is_remote=True).all():
                    assignment.is_remote = False


def normalize_existing_online_supervisors():
    from app import db
    from sqlalchemy import text
    db.session.execute(text("""
        UPDATE exam_session_supervisor_assignment SET is_remote = 0
        WHERE is_remote = 1 AND exam_session_id IN (
            SELECT id FROM exam_session WHERE format IN ('Online', 'Online at exam centre')
        )
    """))
    db.session.commit()


TRAVEL_MODELS = (ExamSessionSupervisorAssignment, ExamSessionExaminerAssignment, ExamSessionInternAssignment)
TRAVEL_FIELDS = tuple(prefix + suffix for prefix in ('commuting', 'fuel', 'vehicle_dep')
                     for suffix in ('', '_currency', '_base_value', '_unit'))


def clear_online_travel(assignment):
    assignment.logistics_type = "Does not apply"
    assignment.logistics_enabled = False
    assignment.km = None
    assignment.fuel_enabled = False
    for name in TRAVEL_FIELDS:
        setattr(assignment, name, '')


@event.listens_for(Session, 'before_flush')
def prevent_online_travel_fees(unit, *_):
    for item in list(unit.new) + list(unit.dirty):
        if isinstance(item, TRAVEL_MODELS):
            record = item.exam_session or unit.get(ExamSession, item.exam_session_id)
            if record and record.format == 'Online':
                clear_online_travel(item)
        elif isinstance(item, ExamSession) and item.format == 'Online' and inspect(item).attrs.format.history.has_changes() and item.id:
            for model in TRAVEL_MODELS:
                for assignment in unit.query(model).filter_by(exam_session_id=item.id).all():
                    clear_online_travel(assignment)


def normalize_existing_online_travel_fees():
    from app import db
    for model in TRAVEL_MODELS:
        values = {name: '' for name in TRAVEL_FIELDS}
        values.update(km=None, fuel_enabled=False, logistics_type="Does not apply", logistics_enabled=False)
        model.query.filter(model.exam_session_id.in_(db.session.query(ExamSession.id).filter_by(format='Online'))).update(values, synchronize_session=False)
    db.session.commit()


def update_online_supervisor_role_fee(assignment):
    if assignment.manual_fee_override:
        return
    from app.routes import role_fee_for_role, apply_role_fee_calculation, apply_seniority_calculation
    from datetime import datetime, timezone
    fee = role_fee_for_role('Supervisor')
    if fee:
        now = datetime.now(timezone.utc)
        apply_role_fee_calculation(assignment, fee, now)
        if assignment.team_member is None and assignment.team_member_id:
            from app import db
            from app.models import AcademicStaff
            assignment.team_member = db.session.get(AcademicStaff, assignment.team_member_id)
        apply_seniority_calculation(assignment, now)


@event.listens_for(Session, 'before_flush')
def apply_online_supervisor_rate(unit, *_):
    for item in list(unit.new) + list(unit.dirty):
        if isinstance(item, ExamSessionSupervisorAssignment):
            record = item.exam_session or unit.get(ExamSession, item.exam_session_id)
            if record and record.format == 'Online':
                update_online_supervisor_role_fee(item)
        elif isinstance(item, ExamSession) and item.id and item.format == 'Online' and inspect(item).attrs.format.history.has_changes():
            for assignment in unit.query(ExamSessionSupervisorAssignment).filter_by(exam_session_id=item.id).all():
                update_online_supervisor_role_fee(assignment)


def normalize_online_supervisor_role_fees():
    from app import db
    for assignment in ExamSessionSupervisorAssignment.query.join(ExamSession).filter(ExamSession.format == 'Online').all():
        update_online_supervisor_role_fee(assignment)
    db.session.commit()


def remove_examiner_assignment(unit, assignment):
    from app.models import StaffExamSessionSubmission
    if assignment in unit.deleted:
        return
    if assignment in unit.new:
        unit.expunge(assignment)
        return
    submissions = unit.query(StaffExamSessionSubmission).filter_by(
        exam_session_id=assignment.exam_session_id, assignment_type='examiner', assignment_id=assignment.id).all()
    for submission in submissions:
        unit.delete(submission)
    unit.delete(assignment)


@event.listens_for(Session, 'before_flush')
def prevent_online_centre_examiners(unit, *_):
    for item in list(unit.new) + list(unit.dirty):
        if isinstance(item, ExamSessionExaminerAssignment):
            record = item.exam_session or unit.get(ExamSession, item.exam_session_id)
            if record and record.format == 'Online at exam centre':
                remove_examiner_assignment(unit, item)
        elif isinstance(item, ExamSession) and item.format == 'Online at exam centre' and item.id:
            if inspect(item).attrs.format.history.has_changes():
                for assignment in unit.query(ExamSessionExaminerAssignment).filter_by(exam_session_id=item.id).all():
                    remove_examiner_assignment(unit, assignment)


def remove_existing_online_centre_examiners():
    from app import db
    assignments = ExamSessionExaminerAssignment.query.join(ExamSession).filter(ExamSession.format == 'Online at exam centre').all()
    for assignment in assignments:
        remove_examiner_assignment(db.session(), assignment)
    db.session.commit()
