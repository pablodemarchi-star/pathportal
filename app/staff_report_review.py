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

COMMENT_RULES = {
    'arrival': ('Comment on Arrival', ['Too risky']),
    'attitude': ('Comment on Attitude', ['Too doubtful', 'Not helpful']),
    'responsibilities': ('Comment on Responsibilities', ['Needed guidance', 'Made mistakes']),
    'dress_code': ('Comment on Dress code', ['Could improve', 'Inappropriate']),
    'overall': ('Comment on Overall performance', ['Unsatisfactory']),
}
for criterion in CRITERIA:
    criterion['best'] = criterion['options'][0]
    if criterion['key'] in COMMENT_RULES:
        criterion['comment_title'], criterion['comment_when'] = COMMENT_RULES[criterion['key']]


def assessment_criteria(record):
    if record.format != 'Online':
        return CRITERIA
    replacements = {
        'staff_id': dict(key='exam_environment', label='Exam environment', options=['Appropriate', 'Inappropriate'],
                         best='Appropriate',
                         comment_title='Comment on Exam environment', comment_when=['Inappropriate']),
        'language': dict(key='it_skills', label='IT skills', options=['Limited', 'Adequate', 'Proficient'],
                         best='Proficient',
                         comment_title='Comment on IT skills', comment_when=['Limited']),
    }
    return [replacements.get(criterion['key'], criterion) for criterion in CRITERIA]


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
        for criterion in assessment_criteria(record):
            value = form.get(f"review.{row['key']}.{criterion['key']}", '').strip()
            if value not in criterion['options']:
                raise ValueError(f"Please complete all seven assessment criteria for {row['name']} ({row['role']}). If the session team changed, reload the page to see the current staff list.")
            values[criterion['key']] = value
        perfect = all(values[c['key']] == c['best'] for c in assessment_criteria(record) if c['key'] != 'overall')
        if (values['overall'] == 'Remarkable' and not perfect) or (values['overall'] == 'Unsatisfactory' and perfect):
            raise ValueError(f"Please select an Overall rating consistent with the other assessment criteria for {row['name']} ({row['role']}).")
        notes = form.get(f"review.{row['key']}.notes", '').strip()
        if len(notes) > 10000:
            raise ValueError(f"Notes for {row['name']} must not exceed 10,000 characters.")
        comments = {}
        for criterion in assessment_criteria(record):
            if not criterion.get('comment_when'):
                continue
            key, title, required_values = criterion['key'], criterion['comment_title'], criterion['comment_when']
            if values[key] not in required_values:
                continue
            comment = form.get(f"review.{row['key']}.comments.{key}", '').strip()
            if not comment:
                raise ValueError(f"{title} is required for {row['name']} ({row['role']}).")
            if len(comment) > 10000:
                raise ValueError(f"{title} for {row['name']} must not exceed 10,000 characters.")
            comments[key] = comment
        assessments.append(dict(exam_session_id=record.id, **row, criteria=values, notes=notes, comments=comments))
    return assessments
