"""Independent Return and Sinapsis gates, deadlines and recipient review."""
from datetime import datetime, timedelta, timezone
from sqlalchemy import event
from sqlalchemy.orm import Session
from flask import g, has_app_context
from app import db
from app.models import (ExamSession, ExamSessionSupervisorAssignment, ExamSessionExaminerAssignment,
                        ExamSessionInternAssignment, ExamSessionSinapsisControl, ExamSessionSinapsisEvent)

ASSIGNMENTS = (ExamSessionSupervisorAssignment, ExamSessionExaminerAssignment, ExamSessionInternAssignment)


def recipient(record, unit=None):
    cached = getattr(g, '_final_checks_assignment_rows', {}) if has_app_context() and unit is None else {}
    unit = unit or db.session()
    rows = list(cached.get(record.id, []))
    for model in ASSIGNMENTS:
        if record.id not in cached:
            rows.extend(unit.query(model).filter_by(exam_session_id=record.id).all())
        rows.extend(item for item in unit.new if isinstance(item, model) and item.exam_session_id == record.id and item not in rows)
    return next((item for item in rows if item not in unit.deleted and item.is_shipment_recipient
                 and (item.team_member_id or item.potential_entry_id)), None)


def recipient_ref(assignment):
    if not assignment:
        return ''
    return f'staff:{assignment.team_member_id}' if assignment.team_member_id else f'potential:{assignment.potential_entry_id}'


def combined_sessions_selected(record, control):
    from app.routes import combined_return_session_options, combined_return_examiner_confirmed
    cache = getattr(g, '_quality_combined_eligible', {}) if has_app_context() else {}
    eligible = cache[record.id] if record.id in cache else {peer.id for peer in combined_return_session_options(record) if combined_return_examiner_confirmed(peer)}
    return bool(control and set(control.combined_return_session_ids) & eligible)


def shared_return_controls(record, control):
    if control.return_materials_method not in {'combined_dispatch', 'combined_location_drop_off'} or control.return_materials_local_override:
        return [control]
    peers = ExamSessionSinapsisControl.query.filter(
        ExamSessionSinapsisControl.exam_session_id.in_(control.combined_return_session_ids),
        ExamSessionSinapsisControl.return_materials_method == control.return_materials_method,
        ExamSessionSinapsisControl.return_materials_local_override.is_(False)).all()
    return [control] + [peer for peer in peers if record.id in peer.combined_return_session_ids]


def return_instructions_payload(record, control):
    return {'title': control.return_instructions_title or '' if control else '',
            'html': control.return_instructions_html or '' if control else '',
            'session_ids': [peer.exam_session_id for peer in shared_return_controls(record, control)] if control else [record.id]}


def return_configuration_complete(record, control):
    from app.routes import is_valid_url
    if not control or control.return_review_required:
        return False
    method = control.return_materials_method
    if method == 'immediate_dispatch':
        return bool(control.return_shipping_label)
    if method == 'combined_dispatch':
        return bool(control.combined_return_shipping_label) and combined_sessions_selected(record, control)
    fields = {'location_drop_off': 'return_drop_off_address_url',
              'combined_location_drop_off': 'combined_return_drop_off_address_url'}
    if method == 'staff_handover':
        return bool(control.return_handover_staff_id)
    url = (getattr(control, fields.get(method, ''), '') or '').strip() if method in fields else ''
    if not url or not is_valid_url(url):
        return False
    if method in {'combined_dispatch', 'combined_location_drop_off'}:
        return combined_sessions_selected(record, control)
    return True


def sync_lifecycle(record, unit, today=None):
    if not record or record in unit.deleted or record.format != 'Onsite':
        return
    from app.routes import LOCAL_TZ
    today = today or datetime.now(LOCAL_TZ).date()
    assigned = recipient(record, unit)
    confirmed = bool(assigned and assigned.participation_status == 'Confirmed')
    control = next((item for item in unit.new if isinstance(item, ExamSessionSinapsisControl)
                    and item.exam_session_id == record.id), None)
    control = control or unit.query(ExamSessionSinapsisControl).filter_by(exam_session_id=record.id).first()
    if control in unit.deleted:
        return
    if not control:
        if not confirmed:
            return
        control = ExamSessionSinapsisControl(exam_session_id=record.id, status='Not reviewed')
        unit.add(control)
    opens_on = record.session_date - timedelta(days=29) if record.session_date else None
    # Materialize the original start even when the next edit removes a confirmed
    # recipient after the date window opened. Later changes must not restart it.
    if not control.return_started_on and control.return_recipient_confirmed_on and opens_on and today >= opens_on:
        control.return_started_on = max(control.return_recipient_confirmed_on, opens_on)
    ref = recipient_ref(assigned)
    if ref and ref != control.return_recipient_ref:
        if control.return_recipient_ref and (control.return_started_on or control.return_materials_method):
            control.return_review_required = True
            control.return_reviewed_at = None
            control.return_completed_at = None
            unit.add(ExamSessionSinapsisEvent(sinapsis_control=control, event_type='return_recipient_changed',
                new_status=control.status or 'Not reviewed',
                note='Return of exam materials must be reviewed because the shipment recipient changed.'))
        control.return_recipient_ref = ref
        control.return_recipient_confirmed_on = None
    if confirmed:
        if not control.return_recipient_confirmed_on:
            control.return_recipient_confirmed_on = today
        if not control.return_started_on and opens_on and today >= opens_on:
            control.return_started_on = max(control.return_recipient_confirmed_on, opens_on)
    else:
        control.return_recipient_confirmed_on = None
    if return_configuration_complete(record, control):
        if not control.return_completed_at:
            control.return_completed_at = datetime.now(timezone.utc)
    else:
        control.return_completed_at = None


@event.listens_for(Session, 'before_flush')
def track_final_checks_recipient(unit, *_):
    ids = {item.exam_session_id for item in list(unit.new) + list(unit.dirty) + list(unit.deleted)
           if isinstance(item, (*ASSIGNMENTS, ExamSessionSinapsisControl)) and item.exam_session_id}
    ids.update(item.id for item in unit.dirty if isinstance(item, ExamSession) and item.id)
    for session_id in ids:
        sync_lifecycle(unit.get(ExamSession, session_id), unit)


def initialize_existing_final_checks():
    # The first deployment starts already-confirmed recipients today, not at their historical confirmation.
    for record in ExamSession.query.filter_by(format='Onsite').all():
        sync_lifecycle(record, db.session())
    db.session.commit()


def final_checks_state(record, control=None, today=None):
    from app.routes import (LOCAL_TZ, argentina_business_days_until, argentina_subtract_business_days,
                            deadline_badge_contract, local_date, SINAPSIS_CHECKLIST_ITEMS)
    today = today or datetime.now(LOCAL_TZ).date()
    cached = getattr(g, '_final_checks_controls', {}) if has_app_context() else {}
    if control is None:
        control = cached[record.id] if record.id in cached else db.session.query(ExamSessionSinapsisControl).filter_by(exam_session_id=record.id).first()
    assigned = recipient(record)
    opens_on = record.session_date - timedelta(days=29) if record.session_date else None
    confirmed = bool(assigned and assigned.participation_status == 'Confirmed')
    enabled = bool(record.format == 'Onsite' and confirmed and opens_on and today >= opens_on)
    days = 0 if record.session_date and record.session_date < today else argentina_business_days_until(record.session_date, today=today)
    checks_enabled = enabled and days is not None and days <= 8
    status = 'unblocked' if checks_enabled else 'semi_unblocked' if enabled else 'blocked'
    started = control.return_started_on if control else None
    if not started and enabled:
        started = max(control.return_recipient_confirmed_on or today, opens_on) if control else today
    checks_opens_on = argentina_subtract_business_days(record.session_date, 8) if record.session_date else None
    reasons = []
    if status == 'blocked':
        if not assigned:
            reasons.append('Assign a staff member with Receives shipment.')
        elif not confirmed:
            reasons.append('The staff member marked Receives shipment must confirm participation.')
        if not record.session_date:
            reasons.append('Set an exam session date.')
        elif today < opens_on:
            reasons.append(f'Return of exam materials becomes available 29 calendar days before the exam, on {opens_on:%d/%m/%Y}.')
    elif status == 'semi_unblocked':
        reasons.append(f'Sinapsis checks becomes available 8 Argentine business days before the exam, on {checks_opens_on:%d/%m/%Y}.')
    deadline = min(started + timedelta(days=10), record.session_date - timedelta(days=7)) if started and record.session_date else None
    complete = return_configuration_complete(record, control)
    required_keys = {item['key'] for item in SINAPSIS_CHECKLIST_ITEMS}
    items = [item for item in (control.checklist_items if control else []) if item.item_key in required_keys]
    all_checked = len({item.item_key for item in items if item.is_checked}) == len(required_keys)
    events_cache = getattr(g, '_final_checks_events', {}) if has_app_context() else {}
    events = events_cache.get(record.id, []) if record.id in events_cache else (control.events if control else [])
    activity_types = {'checklist_checked', 'checklist_unchecked', 'checklist_updated', 'checklist_issue',
                      'return_materials_method', 'return_review_confirmed', 'return_instructions_updated'}
    has_activity = bool((control and (control.return_materials_method or control.reviewed_at or control.return_reviewed_at or control.return_instructions_html))
                        or any(item.is_checked or item.note or item.needs_review for item in items)
                        or any(event.event_type in activity_types for event in events))
    progress = 'completed' if complete and all_checked else 'in_progress' if has_activity else 'not_started'
    finished = max((local_date(item.checked_at) for item in items if item.checked_at), default=None) if all_checked else None
    checks_deadline = argentina_subtract_business_days(record.session_date, 4) if record.session_date else None
    actions = []
    def return_action(department, description):
        actions.append({'department': department, 'description': description, 'section': 'sinapsis',
                        'overdue': bool(deadline and today > deadline), 'deadline': deadline})
    if enabled and not complete:
        if control and control.return_review_required:
            return_action('MANAGEMENT', 'Review package return due to staff change')
        elif control and control.return_materials_method == 'combined_dispatch':
            if not combined_sessions_selected(record, control):
                return_action('MANAGEMENT', 'Select sessions for combined return')
            if not control.combined_return_shipping_label:
                return_action('ADMIN', 'Issue return shipping label')
        elif control and control.return_materials_method == 'immediate_dispatch':
            return_action('ADMIN', 'Issue return shipping label')
        else:
            return_action('MANAGEMENT', 'Finalise return of exam material configuration' if control and control.return_materials_method else 'Configure exam material return')
    if checks_enabled and not all_checked:
        description = 'Continue with pre-session Sinapsis checks' if any(item.is_checked for item in items) else 'Start pre-session Sinapsis checks'
        actions.append({'department': 'ADMIN', 'description': description, 'section': 'sinapsis',
                        'overdue': bool(checks_deadline and today > checks_deadline), 'deadline': checks_deadline})
    return {'status': status, 'label': status.upper().replace('_', '-'), 'return_enabled': enabled,
            'message': ' '.join(reasons), 'return_opens_on': opens_on, 'checks_opens_on': checks_opens_on,
            'progress': progress,
            'checks_enabled': checks_enabled, 'within_window': days is not None and days <= 8,
            'business_days_until_session': days, 'return_complete': complete,
            'review_required': bool(control and control.return_review_required), 'actions': actions,
            'return_deadline_badge': deadline_badge_contract(deadline, completed=complete,
                completed_date=local_date(control.return_completed_at) if complete and control else None, today=today) if started else None,
            'checks_deadline_badge': deadline_badge_contract(checks_deadline, completed=all_checked, completed_date=finished, today=today),
            'checks_complete': all_checked}
