"""Authenticated Quality control corrections using the supervisor's own form."""
import json
from datetime import datetime, timezone
from flask import abort, g, jsonify, render_template, request, session, url_for
from app import db
from app import models as m


def require_editor():
    if not getattr(getattr(g, 'current_user', None), 'is_superadmin', False):
        abort(403)


def snapshot(report):
    return {column.name: (getattr(report, column.name).isoformat() if isinstance(getattr(report, column.name), datetime)
                          else getattr(report, column.name))
            for column in report.__table__.columns if column.name != 'edit_history'}


def report_values(report):
    values = snapshot(report)
    for key in ('return_verification', 'component_absences', 'it_absences'):
        values[key] = json.loads(getattr(report, key) or '[]')
    values['it_issues'] = '1' if report.it_issues else '0'
    for key, value in json.loads(report.module_comments or '{}').items():
        values['optional_comments' if key == 'overall' else 'comments_' + key] = value
    for key, value in json.loads(report.important_considerations or '{}').items():
        values['important_considerations_' + key] = json.dumps(value)
    for row in json.loads(report.staff_assessments or '[]'):
        prefix = 'review.' + row['key'] + '.'
        values.update({prefix + key: value for key, value in row['criteria'].items()})
        values[prefix + 'notes'] = row.get('notes', '')
        values.update({prefix + 'comments.' + key: value for key, value in row.get('comments', {}).items()})
    return values


def edit_report(session_id):
    require_editor()
    record = db.get_or_404(m.ExamSession, session_id)
    report = m.StaffExamSessionReport.query.filter_by(exam_session_id=record.id).first_or_404()
    submission = report.submission
    if request.method == 'POST':
        from app.staff_report_media import lock_submission
        lock_submission(submission.id)
        db.session.refresh(report)
        if request.form.get('_report_revision') != str(len(json.loads(report.edit_history or '[]'))):
            return jsonify(ok=False, error='This report changed since you opened it. Close the editor and reopen it to load the latest version.'), 409
        from app.routes import submit_staff_session_report
        return submit_staff_session_report(submission.share.token, submission.id, _editing=report)
    from app import routes as r
    from app.post_attendance import EXAMS
    from app.staff_report_components import it_module_options
    from app.staff_report_review import assessment_criteria
    from app.staff_report_media import media_view
    from app.staff_return_materials import report_return_view
    checks = dict(
        session_report_url=url_for('quality_control.edit_session_report', session_id=record.id),
        session_report_media_url=url_for('quality_control.edit_session_report_media', session_id=record.id),
        session_report_media=media_view(record, submission),
        institutional_feedback_submitted=r.staff_report_feedback_submitted(record) if record.format != 'Online' else True,
        digitalised_url=record.digitalised_exams_url or '',
        module_sections=r.staff_report_module_sections(record),
        comment_sections=r.staff_report_comment_sections(record),
        component_completion_applicable=record.format == 'Online' and 'listening and speaking' in {v.lower() for v in record.modules_list()},
        component_exams=EXAMS, it_module_options=it_module_options(record) if record.format == 'Online' else {},
        speaking_documents=r.staff_report_speaking_documents(record) if record.format == 'Online' else [],
        return_materials=report_return_view(
            record, r.staff_submission_assignment(record, submission.assignment_type, submission.assignment_id)[0], submission.share),
        report_recordings_required=r.staff_report_recordings_required(record),
        assessment_roster=json.loads(report.staff_assessments or '[]'), assessment_criteria=assessment_criteria(record))
    detail = dict(format=record.format, session_date=record.session_date.strftime('%d/%m/%Y') if record.session_date else '',
                  confirmation_csrf=session.get('csrf_token', ''), end_checks=checks)
    initial_values = report_values(report)
    if checks['return_materials'] and json.loads(report.return_instructions_context or '{}') != checks['return_materials']['context']:
        initial_values['return_instructions_confirmed'] = False
    response = render_template('session_report_edit.html', detail=detail, exam_session=record,
                               initial_values=initial_values, revision=len(json.loads(report.edit_history or '[]')))
    return response, 200, {'Cache-Control': 'private, no-store'}


def apply_edit(report, values, record, components, it_rows):
    before = snapshot(report)
    old_components, old_it = json.loads(report.component_absences or '[]'), json.loads(report.it_absences or '[]')
    reconcile_absences(record, old_components, old_it, components, it_rows)
    for key, value in values.items():
        if key not in {'submission_id', 'exam_session_id', 'author_name', 'author_person_ref'}:
            setattr(report, key, value)
    history = json.loads(report.edit_history or '[]')
    history.append(dict(edited_at=datetime.now(timezone.utc).isoformat(), user_id=g.current_user.id,
                        editor=g.current_user.full_name, email=g.current_user.email,
                        before=before, after=snapshot(report)))
    report.edit_history = json.dumps(history)


def reconcile_absences(record, old_components, old_it, components, it_rows):
    """Remove superseded report evidence before the normal merge adds the corrected evidence."""
    from app.post_attendance import reset_review, touch, workflow_state
    from app.attendance_tracking import sync_milestones
    old = {}
    for field, rows in [('component_reason', old_components), ('it_reason', old_it)]:
        for row in rows:
            item = old.setdefault(row['number'], dict(modules=set(), fields=set()))
            item['modules'].update(row.get('modules') or [row['component']])
            item['fields'].add(field)
    new_numbers = {row['number'] for row in components + it_rows}
    before = workflow_state(record)
    changed = False
    for number, contribution in old.items():
        candidate = m.AbsenceCandidate.query.filter_by(exam_session_id=record.id, number_key=number).first()
        if candidate is None:
            continue
        new_component = next((row for row in components if row['number'] == number), None)
        new_it = next((row for row in it_rows if row['number'] == number), None)
        old_component = next((row for row in old_components if row['number'] == number), None)
        old_it_row = next((row for row in old_it if row['number'] == number), None)
        if new_component == old_component and new_it == old_it_row:
            continue
        changed = True
        candidate.absent_modules = json.dumps([module for module in json.loads(candidate.absent_modules or '[]') if module not in contribution['modules']])
        for field in contribution['fields']:
            setattr(candidate, field, '')
        if number not in new_numbers and not candidate.document_id and not json.loads(candidate.absent_modules) and not candidate.component_reason and not candidate.it_reason:
            m.AbsenceSubmissionEvent.query.filter_by(candidate_id=candidate.id).delete(synchronize_session=False)
            db.session.delete(candidate)
        else:
            reset_review(candidate)
    if changed:
        state = touch(record, reset=True)
        state.review_completed_at = None
        db.session.flush()
        sync_milestones(record, before, True, 'quality_report_correction')
