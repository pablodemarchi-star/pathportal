"""Session-wide drafts for Onsite reports completed with a remote supervisor."""
import json
import re
from flask import Blueprint, abort, jsonify, request
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm.exc import StaleDataError
from app import db, validate_csrf
from app.models import StaffExamSessionsShare, StaffExamSessionSubmission, StaffSharedSessionReportDraft, StaffExamSessionEndChecks, ExamSession
from app.staff_report_media import lock_submission, report_for_session

bp = Blueprint('shared_staff_report', __name__)


def discard_legacy_checks():
    """Discard only the old checklist responses replaced by the new shared report."""
    from app.routes import staff_remote_report_participant, staff_submission_assignment
    rows = (StaffExamSessionEndChecks.query.join(StaffExamSessionSubmission).join(ExamSession)
            .filter(ExamSession.format == 'Onsite').all())
    for row in rows:
        submission = row.submission
        assignment, _ = staff_submission_assignment(submission.exam_session, submission.assignment_type, submission.assignment_id)
        if staff_remote_report_participant(submission.exam_session, assignment, submission.assignment_type):
            db.session.delete(row)
    db.session.commit()


@bp.after_request
def private(response):
    response.headers['Cache-Control'] = 'private, no-store'
    response.headers['Referrer-Policy'] = 'no-referrer'
    response.headers['X-Robots-Tag'] = 'noindex, nofollow'
    return response


@bp.route('/my-exam-sessions/<token>/submissions/<int:submission_id>/report/draft', methods=['GET', 'POST'])
def draft(token, submission_id):
    from app.routes import staff_submission_assignment, staff_report_assignment_eligible, staff_shared_onsite_report, staff_report_available
    share = StaffExamSessionsShare.query.filter_by(token=token).first_or_404()
    if request.method == 'POST' and not validate_csrf():
        return jsonify(ok=False, error='Security token expired. Reload this page and try again.'), 400
    submission = lock_submission(submission_id) if request.method == 'POST' else db.session.get(StaffExamSessionSubmission, submission_id)
    if not submission or submission.share_id != share.id:
        abort(404)
    record = submission.exam_session
    assignment, ref = staff_submission_assignment(record, submission.assignment_type, submission.assignment_id)
    if not assignment or ref != share.person_ref:
        abort(404)
    if not staff_report_assignment_eligible(record, assignment, submission.assignment_type) or not staff_shared_onsite_report(record) or not staff_report_available(record):
        return jsonify(ok=False, error='This shared report is only available to confirmed eligible staff on the exam day.'), 403
    report = report_for_session(record)
    if report:
        return jsonify(ok=True, submitted=True, author_name=report.author_name)
    row = db.session.get(StaffSharedSessionReportDraft, record.id)
    values = json.loads(row.values_json) if row else {}
    if request.method == 'POST':
        if request.content_length and request.content_length > 512000:
            return jsonify(ok=False, error='The report draft is too large.'), 400
        try:
            changes, base = json.loads(request.form.get('changes', '{}')), json.loads(request.form.get('base', '{}'))
        except (ValueError, TypeError):
            return jsonify(ok=False, error='Invalid report draft.'), 400
        if not isinstance(changes, dict) or not isinstance(base, dict) or len(changes) > 500:
            return jsonify(ok=False, error='Invalid report draft.'), 400
        for key, value in changes.items():
            if (not re.fullmatch(r'[a-zA-Z_][a-zA-Z0-9_.:-]{0,240}', key)
                    or key in {'csrf_token', 'shared_report_revision'}
                    or not (isinstance(value, str) or isinstance(value, list) and all(isinstance(item, str) for item in value))
                    or len(json.dumps(value)) > 200000):
                return jsonify(ok=False, error='Invalid report draft field.'), 400
            if values.get(key) != base.get(key) and values.get(key) != value:
                return jsonify(ok=False, conflict=True, error='Someone else changed the same answer. Reopen the report to review their changes before continuing.'), 409
        values.update(changes)
        if len(json.dumps(values)) > 400000:
            return jsonify(ok=False, error='The report draft is too large.'), 400
        if row is None:
            row = StaffSharedSessionReportDraft(exam_session_id=record.id)
            db.session.add(row)
        row.values_json = json.dumps(values)
        row.revision = (row.revision or 0) + 1
        try:
            db.session.commit()
        except (IntegrityError, StaleDataError):
            db.session.rollback()
            return jsonify(ok=False, conflict=True, error='The shared report changed while saving. Reopen the report before continuing.'), 409
    return jsonify(ok=True, submitted=False, values=values, revision=row.revision if row else 0)
