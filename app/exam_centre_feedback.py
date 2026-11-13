"""Immutable bilingual institutional feedback, available on each exam date only."""
from datetime import datetime, time, timezone
from flask import Blueprint, abort, jsonify, request
from sqlalchemy.exc import IntegrityError
from app import db, validate_csrf
from app.models import ExamCentreFeedback, ExamSession, ExamSessionJourneyShare
from app.exam_centre_feedback_text import feedback_copy, QUESTIONS, OPEN_QUESTIONS

feedback_bp = Blueprint('exam_centre_feedback', __name__)


def feedback_available(record, now=None):
    from app.routes import LOCAL_TZ
    now = now or datetime.now(timezone.utc)
    return bool(record.session_date and now.astimezone(LOCAL_TZ).date() == record.session_date)


def feedback_states(cards, now=None):
    from app.routes import LOCAL_TZ
    ids = [card['session_id'] for card in cards]
    submitted = {row.exam_session_id for row in ExamCentreFeedback.query.filter(ExamCentreFeedback.exam_session_id.in_(ids)).all()} if ids else set()
    today = (now or datetime.now(timezone.utc)).astimezone(LOCAL_TZ).date()
    return [dict(card, feedback_submitted=card['session_id'] in submitted,
                 feedback_available=card['session_date'] == today,
                 feedback_opens_at=datetime.combine(card['session_date'], time.min, tzinfo=LOCAL_TZ).isoformat() if card['session_date'] else '') for card in cards]


@feedback_bp.post('/path-session-journey/<token>/institution/feedback/<int:session_id>')
def submit(token, session_id):
    from app.routes import monthly_unified_total_session_ids
    share = ExamSessionJourneyShare.query.filter_by(token=token, audience='institution').first_or_404()
    if not share.is_enabled or share.revoked_at:
        abort(410)
    text = feedback_copy(request.form.get('language'))
    if not validate_csrf():
        return jsonify(ok=False, error=text['csrf']), 400
    if session_id not in monthly_unified_total_session_ids(share.exam_session):
        abort(404)
    record = db.session.get(ExamSession, session_id)
    if not record:
        abort(404)
    if not feedback_available(record):
        return jsonify(ok=False, error=text['expired']), 403
    if ExamCentreFeedback.query.filter_by(exam_session_id=record.id).first():
        return jsonify(ok=False, error=text['locked']), 409
    values, errors = {}, {}
    for key, *_ in QUESTIONS:
        raw = request.form.get(key + '_score', '')
        score = int(raw) if raw in {str(number) for number in range(1, 11)} else None
        if score is None:
            errors[key + '_score'] = text['invalid_score']
        comment = request.form.get(key + '_comment', '').strip()
        if score is not None and score <= 7 and not comment:
            errors[key + '_comment'] = text['missing_comment']
        if len(comment) > 10000:
            errors[key + '_comment'] = text['too_long']
        values[key + '_score'] = score
        values[key + '_comment'] = comment if score is not None and score <= 7 else ''
    for key, *_ in OPEN_QUESTIONS:
        values[key] = request.form.get(key, '').strip()
        if len(values[key]) > 10000:
            errors[key] = text['too_long']
    if errors:
        return jsonify(ok=False, error=text['missing'], fields=errors), 400
    db.session.add(ExamCentreFeedback(exam_session_id=record.id, share_id=share.id,
        session_year=record.session_date.year, session_name=record.exam_session_name,
        language='es' if request.form.get('language') == 'es' else 'en', **values))
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return jsonify(ok=False, error=text['locked']), 409
    return jsonify(ok=True, message=text['thanks'])
