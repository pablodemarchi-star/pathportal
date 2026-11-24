"""Per-person Logistics cards shared across selected concatenated sessions."""
import json
from flask import Blueprint, abort, g, jsonify, request, url_for
from sqlalchemy import event, inspect
from sqlalchemy.orm import Session
from app import db, login_required, validate_csrf
from app import models as m

bp = Blueprint('staff_logistics', __name__)
FORMATS = {'Onsite', 'Online at exam centre'}
TYPES = {'Uber ride', 'Complex Uber ride', 'Carpooling', 'Complex logistics'}
MODELS = (m.ExamSessionSupervisorAssignment, m.ExamSessionExaminerAssignment, m.ExamSessionInternAssignment)


def cancel_payments(payments, reason):
    for payment in payments:
        if payment.status == 'Payment completed' or payment.payment_completed_at:
            if reason not in (payment.logistics_alert or ''):
                payment.logistics_alert = ((payment.logistics_alert or '') + '\n' + reason + ' — payment already completed; review required.').strip()
                db.session.add(m.PaymentRequestEvent(payment_request_id=payment.id, event_type='Logistics alert', previous_status=payment.status, new_status=payment.status, comment=reason, created_by_department='Logistics'))
        elif payment.status not in {'Payment cancelled', 'Rejected'}:
            previous = payment.status
            payment.status = 'Payment cancelled'
            payment.hold_comment = reason
            db.session.add(m.PaymentRequestEvent(payment_request_id=payment.id, event_type='Payment cancelled', previous_status=previous, new_status=payment.status, comment=reason, created_by_department='Logistics'))


def ensure_schema():
    """Add card references before any ORM payment queries run."""
    card_columns = {column['name'] for column in inspect(db.engine).get_columns('staff_logistics_card')}
    from sqlalchemy import text
    if 'instructions_html' not in card_columns:
        db.session.execute(text("ALTER TABLE staff_logistics_card ADD COLUMN instructions_html TEXT NOT NULL DEFAULT ''"))
    columns = {column['name'] for column in inspect(db.engine).get_columns('payment_request')}
    from sqlalchemy import text
    for name, definition in [('logistics_card_id', 'INTEGER REFERENCES staff_logistics_card(id)'), ('logistics_alert', "TEXT NOT NULL DEFAULT ''")]:
        if name not in columns:
            db.session.execute(text(f'ALTER TABLE payment_request ADD COLUMN {name} {definition}'))
    db.session.execute(text('CREATE INDEX IF NOT EXISTS ix_payment_request_logistics_card_id ON payment_request(logistics_card_id)'))
    db.session.execute(text('CREATE UNIQUE INDEX IF NOT EXISTS uq_active_staff_logistics_card ON staff_logistics_card(person_ref, group_session_ids) WHERE active = true'))
    db.session.commit()


def migrate():
    """One-time authorized reset; retain paid requests with an alert."""
    ensure_schema()
    if db.session.get(m.StaffLogisticsMigration, 1):
        return
    ids = [row.id for row in m.ExamSession.query.filter(m.ExamSession.format.in_(FORMATS))]
    concepts = m.ExamSessionLogisticsConcept.query.filter(m.ExamSessionLogisticsConcept.exam_session_id.in_(ids)).all()
    concept_ids = [row.id for row in concepts]
    payments = m.PaymentRequest.query.filter(m.PaymentRequest.logistics_concept_id.in_(concept_ids)).all() if concept_ids else []
    cancel_payments(payments, 'Previous Logistics management reset')
    for payment in payments:
        payment.logistics_concept_id = None
    db.session.flush()
    for model in (m.ExamSessionLogisticsConceptProvider, m.ExamSessionLogisticsConceptStaffMember, m.ExamSessionLogisticsConceptNote):
        model.query.filter(model.logistics_concept_id.in_(concept_ids)).delete(synchronize_session=False)
    for concept in concepts:
        db.session.delete(concept)
    for config in m.ExamSessionLogistics.query.filter(m.ExamSessionLogistics.exam_session_id.in_(ids)):
        config.logistics_files_url = None
        config.logistics_planned = False
    for control in m.ExamSessionLogisticsControl.query.filter(m.ExamSessionLogisticsControl.exam_session_id.in_(ids)):
        control.note = None
        control.logistics_due_at = None
    db.session.add(m.StaffLogisticsMigration(id=1))
    db.session.flush()
    sync_cards()
    db.session.commit()


def assignment_groups():
    from app.routes import exam_session_concat_component_map, normalize_assignment_logistics_type, staffing_assignment_person_ref
    records = {record.id: record for record in m.ExamSession.query.filter(m.ExamSession.format.in_(FORMATS))}
    components = exam_session_concat_component_map()
    groups = {}
    for model in MODELS:
        for assignment in model.query.filter(model.exam_session_id.in_(records)):
            person = assignment.team_member or assignment.potential_entry
            kind = normalize_assignment_logistics_type(assignment.logistics_type, assignment.logistics_enabled)
            if not person or assignment.participation_status in {'Declined', 'Cancelled'} or kind not in TYPES:
                continue
            ref = staffing_assignment_person_ref(assignment)
            unavailable = set(records[assignment.exam_session_id].non_available_refs()) | set(assignment.non_available_refs())
            if ref in unavailable or ('staff:' + ref if ref.isdigit() else ref) in unavailable:
                continue
            group = tuple(sorted(set(components.get(assignment.exam_session_id, {assignment.exam_session_id})) & records.keys()))
            item = groups.setdefault((group, ref), dict(name=person.full_name, assignments={}, participation={}))
            item['assignments'][f'{model.__name__}:{assignment.id}'] = dict(session=assignment.exam_session_id, type=kind)
            item['participation'][assignment.exam_session_id] = assignment.participation_status or 'Pending'
    return records, groups


def sync_cards():
    records, groups = assignment_groups()
    existing = m.StaffLogisticsCard.query.filter_by(active=True).all()
    used = set()
    for (group, ref), info in groups.items():
        card = next((row for row in existing if row.id not in used and row.person_ref == ref and set(json.loads(row.group_session_ids)) & set(group)), None)
        eligible = sorted(info['participation'])
        signature = json.dumps(info['assignments'], sort_keys=True)
        if card is not None and not (set(json.loads(card.session_ids)) & set(eligible)):
            card = None
        if card is None:
            card = m.StaffLogisticsCard(person_ref=ref, staff_name=info['name'], group_session_ids=json.dumps(group), session_ids=json.dumps(eligible), assignment_signature=signature, status='Pending', active=True)
            db.session.add(card)
        else:
            used.add(card.id)
            selected = sorted(set(json.loads(card.session_ids)) & set(eligible))
            if not selected:
                selected = eligible
            if card.assignment_signature != signature or json.loads(card.session_ids) != selected or json.loads(card.group_session_ids) != list(group):
                card.status = 'Pending'
            card.session_ids = json.dumps(selected)
            card.group_session_ids = json.dumps(group)
            card.assignment_signature = signature
            card.staff_name = info['name']
    for card in existing:
        if card.id not in used:
            card.active = False
            card.status = 'Pending'
            cancel_payments(m.PaymentRequest.query.filter_by(logistics_card_id=card.id).all(), 'Logistics card removed: ' + card.staff_name)


def state(record, assignments=None):
    if record.format not in FORMATS:
        return None
    if assignments is None:
        assignments = [row for model in MODELS for row in model.query.filter_by(exam_session_id=record.id)]
    if 'staff_logistics_active_cards' not in db.session.info:
        db.session.info['staff_logistics_active_cards'] = m.StaffLogisticsCard.query.filter_by(active=True).all()
    all_cards = db.session.info['staff_logistics_active_cards'] + [card for card in db.session.new if isinstance(card, m.StaffLogisticsCard)]
    cards = [card for card in all_cards if card.active and record.id in json.loads(card.session_ids)]
    open_roles = any(not (row.team_member_id or row.potential_entry_id) or row.participation_status in {'Declined', 'Cancelled'} for row in assignments)
    if record.emergency_contact_required and not record.emergency_contact_not_required and not record.emergency_contact_member_id:
        open_roles = True
    from app.routes import normalize_assignment_logistics_type
    pending_definition = any((row.team_member_id or row.potential_entry_id) and not normalize_assignment_logistics_type(row.logistics_type, row.logistics_enabled) for row in assignments)
    required = {row.team_member_id for row in assignments if row.team_member_id and row.logistics_enabled}
    pending = [dict(id=card.id, status=card.status, provider=card.staff_name) for card in cards if card.status != 'Completed']
    ready = not pending and not open_roles and not pending_definition
    applies = bool(cards or open_roles or pending_definition)
    return dict(staff_cards=True, cards=cards, open_roles=open_roles, pending_definition=pending_definition, applies=applies, status='not_applicable' if not applies else 'confirmed' if ready else 'in_progress', ready=ready, final_email_ready=ready,
                required_member_ids=sorted(required), total_concepts=len(cards), confirmed_concepts=len(cards)-len(pending), blocking_concepts=pending, has_files_url=False,
                blockers=[] if ready else [dict(code='LOGISTICS_CONCEPTS_PENDING', message='Complete all Logistics cards and fill all roles.')])


def card_views(record):
    from app.routes import can_view_payment_request
    records, groups = assignment_groups()
    result = []
    for card in m.StaffLogisticsCard.query.filter_by(active=True).order_by(m.StaffLogisticsCard.staff_name):
        if record.id not in json.loads(card.session_ids):
            continue
        info = next((info for (group, ref), info in groups.items() if ref == card.person_ref and set(group) & set(json.loads(card.group_session_ids))), None)
        if info is None:
            continue
        sessions = [dict(id=sid, name=records[sid].exam_session_name, url=url_for('staff.exam_session_planner', session_year=records[sid].session_date.year if records[sid].session_date else None, open_session_modal=sid, session_fullscreen=1), selected=sid in json.loads(card.session_ids)) for sid in sorted(info['participation'])]
        member_id = int(card.person_ref) if card.person_ref.isdigit() else None
        person = db.session.get(m.AcademicStaff, member_id) if member_id else db.session.get(m.PotentialEntry, int(card.person_ref.split(':')[-1]))
        document = (getattr(person, 'govt_id', '') or '').strip()
        from urllib.parse import urlsplit
        if urlsplit(document).scheme not in {'http', 'https'}:
            document = ''
        if not document.startswith(('https://', 'http://')): document = ''
        document = document.replace('/view', '/preview') if document.startswith('https://drive.google.com/') else document
        payments = m.PaymentRequest.query.filter_by(logistics_card_id=card.id).order_by(m.PaymentRequest.id).all()
        visible = [payment for payment in payments if can_view_payment_request(getattr(g, 'current_user', None), payment)]
        from markupsafe import Markup, escape
        from app.rich_text import sanitize_instructions
        instructions = Markup(sanitize_instructions(card.instructions_html)) if card.instructions_html else escape(card.description).replace('\n', Markup('<br>'))
        logistics_types = sorted({assignment['type'] for assignment in info['assignments'].values() if assignment['session'] == record.id})
        result.append(dict(record=card, logistics_types=logistics_types, instructions_html=instructions, sessions=sessions, participation=info['participation'].get(record.id, 'Pending'), links=json.loads(card.links), document=document, payments=visible))
    return result


def authorize(edit=False):
    from app.routes import require_menu_edit, require_menu_view
    (require_menu_edit if edit else require_menu_view)('pre_session_control_tower')
    if edit and not validate_csrf():
        abort(400, description='Security token expired. Reload and try again.')


@bp.post('/pre-session-control-tower/logistics/cards/<int:card_id>')
@login_required
def save(card_id):
    authorize(True)
    card = db.get_or_404(m.StaffLogisticsCard, card_id)
    if not card.active:
        abort(409, description='This Logistics card is no longer active.')
    from app.routes import logistics_actions_are_blocked, is_valid_url
    selected = request.form.getlist('session_ids')
    try:
        selected = sorted({int(value) for value in selected})
        links = json.loads(request.form.get('links', '[]'))
    except (ValueError, TypeError):
        abort(400)
    allowed = {value['session'] for value in json.loads(card.assignment_signature).values()}
    if not selected or not set(selected) <= allowed:
        abort(400, description='Choose at least one applicable session.')
    if any(logistics_actions_are_blocked(db.session.get(m.ExamSession, sid)) for sid in set(selected) | set(json.loads(card.session_ids))):
        abort(403, description='Staffing must be confirmed before editing Logistics.')
    description = request.form.get('description', '').strip()
    instructions_html = ''
    if 'instructions_html' in request.form:
        from app.rich_text import sanitize_instructions, InstructionsParser
        raw_html = request.form.get('instructions_html', '')
        if len(raw_html) > 50000: abort(400, description='Instructions must not exceed 50,000 characters of formatted content.')
        instructions_html = sanitize_instructions(raw_html)
        parser = InstructionsParser(); parser.feed(instructions_html); parser.close()
        description = ''.join(parser.text).strip()
    status = request.form.get('status')
    if len(description) > 10000 or status not in {'Pending', 'In process', 'Completed'} or not isinstance(links, list) or len(links)>200:
        abort(400)
    clean = []
    from urllib.parse import urlsplit
    for link in links:
        if not isinstance(link, dict): abort(400)
        name, url = link.get('name', ''), link.get('url', '')
        if not isinstance(name, str) or not isinstance(url, str): abort(400)
        if not name.strip() or len(name)>200 or len(url)>2000 or not is_valid_url(url.strip()) or urlsplit(url.strip()).scheme not in {'http','https'}:
            abort(400, description='Every link requires a name and a valid http(s) URL.')
        clean.append(dict(name=name.strip(), url=url.strip()))
    changed_scope = json.loads(card.session_ids) != selected
    card.session_ids = json.dumps(selected)
    card.description, card.links = description, json.dumps(clean)
    card.instructions_html = instructions_html
    card.status = 'Pending' if changed_scope else status
    card.updated_by = getattr(getattr(g, 'current_user', None), 'email', '')
    db.session.commit()
    return jsonify(ok=True, status=card.status, scope_changed=changed_scope)


@bp.get('/pre-session-control-tower/logistics/payments/<int:payment_id>')
@login_required
def payment_detail(payment_id):
    authorize()
    from app.routes import can_view_payment_request
    from flask import render_template
    payment = db.get_or_404(m.PaymentRequest, payment_id)
    if not payment.logistics_card_id or not can_view_payment_request(getattr(g, 'current_user', None), payment):
        abort(403)
    return render_template('pre_session_control_tower/_logistics_payment_detail.html', payment=payment)


@event.listens_for(Session, 'before_flush')
def collect_changes(unit, *_):
    unit.info.pop('staff_logistics_active_cards', None)
    for card in list(unit.new) + list(unit.dirty) + list(unit.deleted):
        if isinstance(card, m.StaffLogisticsCard):
            unit.info.setdefault('quality_session_ids', set()).update(json.loads(card.group_session_ids or '[]'))
            for previous in inspect(card).attrs.group_session_ids.history.deleted:
                unit.info.setdefault('quality_session_ids', set()).update(json.loads(previous or '[]'))
    if not unit.info.get('staff_logistics_syncing') and any(isinstance(row, (*MODELS, m.ExamSession)) for row in list(unit.new)+list(unit.dirty)+list(unit.deleted)):
        unit.info['staff_logistics_sync_needed'] = True


@event.listens_for(Session, 'before_commit')
def reconcile_changes(unit):
    relevant = any(isinstance(row, (*MODELS, m.ExamSession)) for row in list(unit.new)+list(unit.dirty)+list(unit.deleted))
    if not unit.info.get('staff_logistics_sync_needed') and not relevant:
        return
    # Reconcile only the final assignment set; intermediate planner flushes must
    # not retire a card or cancel payments while a role is being replaced.
    unit.flush()
    if not unit.info.pop('staff_logistics_sync_needed', False):
        return
    unit.info['staff_logistics_syncing'] = True
    try:
        sync_cards()
        unit.flush()
    finally:
        unit.info.pop('staff_logistics_syncing', None)


@event.listens_for(Session, 'after_commit')
@event.listens_for(Session, 'after_rollback')
def clear_card_cache(unit):
    unit.info.pop('staff_logistics_active_cards', None)
    unit.info.pop('staff_logistics_sync_needed', None)


@event.listens_for(Session, 'do_orm_execute')
def collect_bulk_changes(execution):
    mapper = execution.bind_mapper
    if (execution.is_update or execution.is_delete) and mapper is not None and mapper.class_ in (*MODELS, m.ExamSession):
        execution.session.info['staff_logistics_sync_needed'] = True
