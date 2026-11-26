"""Responsibilities and authoritative answers for reports shared with a remote supervisor."""
from werkzeug.datastructures import MultiDict
from app.models import ExamSessionExaminerAssignment

SUPERVISOR_FIELDS = {'absent_candidates_checked', 'submitted_candidates_checked', 'session_completed_checked',
                     'centre_feedback_confirmed', 'recordings_reminder_confirmed'}
EXAMINER_FIELDS = {'schedule_outcome', 'reasons', 'facilities_outcome', 'facilities_comments', 'return_verification',
                   'emergency_pack_outcome', 'emergency_pack_reasons', 'marketing_confirmed', 'optional_comments',
                   'return_instructions_confirmed', '_return_instructions_version'}
RETURN_STEPS = ['submitted_papers', 'submitted_packages', 'absent_packages', 'sealing', 'labelling', 'institutional_verification']


def examiner(record):
    return ExamSessionExaminerAssignment.query.filter_by(exam_session_id=record.id, is_shipment_recipient=True, participation_status='Confirmed').first()


def roster(record):
    from app.routes import staffing_assignment_person_ref
    from app.staff_report_review import assessment_roster
    assigned = examiner(record)
    ref = staffing_assignment_person_ref(assigned) if assigned else None
    return [row for row in assessment_roster(record) if row['person_ref'] != ref]


def owner(record, key, review_roster=None):
    if key in SUPERVISOR_FIELDS:
        return 'supervisor'
    if key in EXAMINER_FIELDS:
        return 'examiner'
    if key.startswith('review.') and any(key.startswith('review.' + row['key'] + '.') for row in (roster(record) if review_roster is None else review_roster)):
        return 'examiner'
    return None


def role(assignment, assignment_type):
    if assignment_type == 'supervisor' and assignment.is_remote:
        return 'supervisor'
    if assignment_type == 'examiner' and assignment.is_shipment_recipient:
        return 'examiner'
    return None


def form_values(values):
    result = MultiDict()
    for key, value in values.items():
        if key == '_return_instructions_version':
            key = 'return_instructions_version'
        for item in value if isinstance(value, list) else [value]:
            result.add(key, item)
    return result


def return_view(record, share):
    from app.staff_return_materials import report_return_view
    return report_return_view(record, examiner(record), share)


def completion(record, values, submission, share):
    from app.routes import staff_report_feedback_submitted, staff_report_recordings_required
    from app.staff_report_media import media_for_submission, session_pictures_folder
    from app.staff_report_review import validate_assessments
    form = form_values(values)
    checked = lambda key: form.get(key) == '1'
    outcome = form.get('schedule_outcome')
    facilities = form.get('facilities_outcome')
    emergency = form.get('emergency_pack_outcome')
    return_info = return_view(record, share)
    try:
        validate_assessments(record, form, roster=roster(record))
        reviews = True
    except ValueError:
        reviews = False
    blocks = dict(
        schedule=bool(outcome in {'The session finished ahead of schedule', 'There were no delays', 'There were minor delays', 'There were significant delays'}
                      and len(form.get('reasons', '')) <= 10000 and (outcome == 'There were no delays' or form.get('reasons', '').strip())),
        attendance=checked('absent_candidates_checked') and checked('submitted_candidates_checked'),
        facilities=bool(facilities in {'Satisfactory', 'Satisfactory, with comments', 'Unsatisfactory'} and (facilities == 'Satisfactory' or form.get('facilities_comments', '').strip())),
        materials=form.getlist('return_verification') == RETURN_STEPS,
        emergency=bool(emergency in {'No, it was not needed', 'Yes, it was opened and used', 'It was opened but not used'} and (emergency == 'No, it was not needed' or form.get('emergency_pack_reasons', '').strip())),
        review=reviews,
        media=bool(session_pictures_folder(record) and media_for_submission(record, submission) and checked('marketing_confirmed')),
        feedback=bool(staff_report_feedback_submitted(record) and checked('centre_feedback_confirmed') and (not staff_report_recordings_required(record) or checked('recordings_reminder_confirmed'))),
        return_materials=bool(examiner(record) and return_info['complete'] and checked('return_instructions_confirmed') and form.get('return_instructions_version') == return_info['version']),
        comments=len(form.get('optional_comments', '')) <= 10000,
    )
    examiner_complete = all(blocks[key] for key in ('schedule', 'facilities', 'materials', 'emergency', 'review', 'media', 'return_materials', 'comments'))
    supervisor_complete = blocks['attendance'] and blocks['feedback']
    return dict(blocks=blocks, examiner=examiner_complete, supervisor=supervisor_complete, ready=examiner_complete and supervisor_complete)
