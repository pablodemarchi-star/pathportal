"""Session-specific staff assessment roster and final submission validation."""
from sqlalchemy.orm import joinedload
from app.models import ExamSessionExaminerAssignment, ExamSessionInternAssignment

CRITERIA = [
    {'key': 'arrival', 'label': 'Arrival', 'options': ['Early enough', 'Too risky']},
    {'key': 'attitude', 'label': 'Attitude', 'options': ['Truly proactive', 'Satisfactory', 'Too doubtful', 'Not helpful']},
    {'key': 'responsibilities', 'label': 'Responsibilities', 'options': ['Fully understood', 'Needed guidance', 'Made mistakes']},
    {'key': 'staff_id', 'label': 'Staff ID', 'options': ['Worn', 'Not worn']},
    {'key': 'dress_code', 'label': 'Dress Code', 'options': ['Appropriate', 'Could improve', 'Inappropriate']},
    {'key': 'language', 'label': 'Language', 'options': ['English', 'Mother tongue']},
    {'key': 'overall', 'label': 'Overall', 'options': ['Remarkable', 'Satisfactory', 'Unsatisfactory']},
]


def assessment_roster(record):
    from app.routes import staffing_assignment_person_ref
    rows = {}
    for role, model in [('Examiner', ExamSessionExaminerAssignment), ('Intern', ExamSessionInternAssignment)]:
        assignments = model.query.options(joinedload(model.team_member), joinedload(model.potential_entry)).filter_by(exam_session_id=record.id).all()
        for assignment in assignments:
            person = assignment.team_member or assignment.potential_entry
            ref = staffing_assignment_person_ref(assignment)
            if not person or not ref:
                continue
            key = f'{role.lower()}:{ref}'
            rows[key] = dict(key=key, person_ref=ref, name=person.full_name, role=role)
    return sorted(rows.values(), key=lambda row: (row['role'] != 'Examiner', row['name'].casefold(), row['key']))


def validate_assessments(record, form):
    """Re-read assignments on submit, so stale/missing rows cannot bypass validation."""
    assessments = []
    for row in assessment_roster(record):
        values = {}
        for criterion in CRITERIA:
            value = form.get(f"review.{row['key']}.{criterion['key']}", '').strip()
            if value not in criterion['options']:
                raise ValueError(f"Please complete all seven assessment criteria for {row['name']} ({row['role']}). If the session team changed, reload the page to see the current staff list.")
            values[criterion['key']] = value
        notes = form.get(f"review.{row['key']}.notes", '').strip()
        if len(notes) > 10000:
            raise ValueError(f"Notes for {row['name']} must not exceed 10,000 characters.")
        assessments.append(dict(exam_session_id=record.id, **row, criteria=values, notes=notes))
    return assessments
