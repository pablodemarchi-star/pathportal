"""Small, batch-loaded quality dashboard. No tower modals or external requests."""
import json
from collections import defaultdict
from datetime import date, datetime, time, timedelta, timezone
from types import SimpleNamespace
from flask import Blueprint, abort, current_app, g, has_app_context, render_template, request, url_for
from sqlalchemy import event, extract, inspect
from sqlalchemy.orm import Session, joinedload, selectinload, load_only
from app import db, login_required
from app import models as m

quality_bp = Blueprint('quality_control', __name__)
PROCESSES = [('date', 'Date'), ('registrations', 'Registrations'), ('schedule', 'Schedule'),
             ('staffing', 'Staffing'), ('package', 'Package'), ('shipment', 'Shipment'),
             ('logistics', 'Logistics'), ('finance', 'Finance'), ('final_checks', 'Final checks')]
FORMATS = ['Onsite', 'Online', 'Online at exam centre']
ASSIGNMENTS = [m.ExamSessionSupervisorAssignment, m.ExamSessionExaminerAssignment, m.ExamSessionInternAssignment]


def utc(value):
    return value.replace(tzinfo=timezone.utc) if value and value.tzinfo is None else value


def cell(key, label, *, complete=False, active=False, enabled=True, applicable=True,
         near=False, issue=False, deadline=None, today=None, detail='', action_at=None, completed_at=None):
    overdue = bool(applicable and enabled and not complete and deadline and deadline < today)
    state = ('na' if not applicable else 'complete' if complete else 'blocked' if not enabled
             else 'issue' if issue or overdue else 'near' if near else 'progress' if active else 'pending')
    return dict(key=key, label=label, state=state, complete=complete, enabled=enabled and applicable,
                applicable=applicable, active=active, overdue=overdue, issue=issue,
                deadline=deadline, detail=detail, action_at=action_at, completed_at=completed_at)


def load_rows(records, today=None):
    """Fixed batches, restricted to the chosen year or sessions touched by a write."""
    from app import routes as r
    from app.final_checks import final_checks_state
    today = today or datetime.now(r.LOCAL_TZ).date()
    ids = [item.id for item in records]
    if not ids:
        return []
    def by_session(model, options=()):
        grouped = defaultdict(list)
        for item in model.query.options(*options).filter(model.exam_session_id.in_(ids)).populate_existing().all():
            grouped[item.exam_session_id].append(item)
        return grouped
    groups = []
    for model in ASSIGNMENTS:
        groups.append(by_session(model, (joinedload(model.team_member).load_only(m.AcademicStaff.id, m.AcademicStaff.title, m.AcademicStaff.full_name, m.AcademicStaff.status, m.AcademicStaff.roles),
                                         joinedload(model.potential_entry))))
    workflows = by_session(m.ExamSessionScheduleWorkflow)
    schedule_groups = r.bundle_schedule_presentations(records)
    missing_primary_ids = {item['primary_session_id'] for item in schedule_groups.values()} - set(ids)
    if missing_primary_ids:
        for workflow in m.ExamSessionScheduleWorkflow.query.filter(m.ExamSessionScheduleWorkflow.exam_session_id.in_(missing_primary_ids)).all():
            workflows[workflow.exam_session_id].append(workflow)
    staffing_controls = by_session(m.ExamSessionStaffingControl)
    finance = by_session(m.ExamSessionFinanceControl)
    logistics = by_session(m.ExamSessionLogistics)
    # Provider details are unnecessary for readiness; pass only the status and provider label.
    concepts = by_session(m.ExamSessionLogisticsConcept)
    controls = by_session(m.ExamSessionSinapsisControl, (
        selectinload(m.ExamSessionSinapsisControl.checklist_items),
        joinedload(m.ExamSessionSinapsisControl.return_shipping_label),
        joinedload(m.ExamSessionSinapsisControl.combined_return_shipping_label)))
    links = by_session(m.ExamSessionShipmentBundleSession, (joinedload(m.ExamSessionShipmentBundleSession.bundle),))
    candidates, latest_month, registration_activity = {}, {}, set()
    for sid, month, registrations in db.session.query(m.ExamSessionMonthlyRegistration.exam_session_id,
            db.func.max(m.ExamSessionMonthlyRegistration.month), db.func.sum(m.ExamSessionMonthlyRegistration.registration_number)).filter(
            m.ExamSessionMonthlyRegistration.exam_session_id.in_(ids)).group_by(m.ExamSessionMonthlyRegistration.exam_session_id):
        latest_month[sid] = month
        if registrations:
            registration_activity.add(sid)
    totals = db.session.query(m.ExamSessionMonthlyCandidateTotal.exam_session_id, m.ExamSessionMonthlyCandidateTotal.month,
        m.ExamSessionMonthlyCandidateTotal.total_candidates).filter(m.ExamSessionMonthlyCandidateTotal.exam_session_id.in_(ids)).all()
    for sid, month, total in totals:
        latest_month[sid] = max(latest_month.get(sid, month), month)
    for sid, month, total in totals:
        if month == latest_month[sid]:
            candidates[sid] = total
    latest_approvals = dict(db.session.query(m.ExamSessionScheduleWorkflow.exam_session_id, db.func.max(m.ExamSessionScheduleEvent.created_at)).join(
        m.ExamSessionScheduleEvent).filter(m.ExamSessionScheduleWorkflow.exam_session_id.in_(set(ids) | missing_primary_ids),
        m.ExamSessionScheduleEvent.new_status == 'Approved').group_by(m.ExamSessionScheduleWorkflow.exam_session_id).all())
    incidents = dict(db.session.query(m.ExamSessionIncident.exam_session_id, db.func.count(m.ExamSessionIncident.id)).filter(
        m.ExamSessionIncident.exam_session_id.in_(ids), m.ExamSessionIncident.status.in_(r.INCIDENT_ACTIVE_STATUSES)).group_by(m.ExamSessionIncident.exam_session_id).all())
    # ID-card ownership is one shared batch; no card files or download URLs are loaded.
    from app.staff_id_allocation import staff_id_session_owners
    owners = staff_id_session_owners(today=today)
    from app.staff_id_documents import card_expired
    pending_ids = set()
    if owners:
        members = m.AcademicStaff.query.options(load_only(m.AcademicStaff.id, m.AcademicStaff.id_issued)).filter(m.AcademicStaff.id.in_(owners)).all()
        documents = {doc.member_id: doc for doc in m.StaffIdDocument.query.filter(m.StaffIdDocument.member_id.in_(owners)).all()}
        pending_ids = {member.id for member in members if not member.id_issued or (member.id in documents and card_expired(documents[member.id]))}
    first = lambda mapping, sid: next(iter(mapping.get(sid, [])), None)
    # The existing readiness function can reuse all assignments/checks from these batches.
    event_types = defaultdict(list)
    for sid, event_type in db.session.query(m.ExamSessionSinapsisControl.exam_session_id, m.ExamSessionSinapsisEvent.event_type).join(
            m.ExamSessionSinapsisEvent).filter(m.ExamSessionSinapsisControl.exam_session_id.in_(ids)).distinct():
        event_types[sid].append(SimpleNamespace(event_type=event_type))
    combined_eligible = {sid: set() for sid in ids}
    peer_ids = {peer for values in controls.values() for control in values for peer in control.combined_return_session_ids}
    if peer_ids:
        peers = m.ExamSession.query.options(selectinload(m.ExamSession.supervisor_assignments),
            selectinload(m.ExamSession.examiner_assignments), selectinload(m.ExamSession.intern_assignments)).filter(m.ExamSession.id.in_(peer_ids)).all()
        eligible_by_supervisor = defaultdict(set)
        for peer in peers:
            supervisor = r.shipment_recipient_supervisor_assignment([a for a in peer.supervisor_assignments if a.participation_status not in {'Declined','Cancelled'}])
            if peer.format == 'Onsite' and supervisor and r.combined_return_examiner_confirmed(peer):
                eligible_by_supervisor[supervisor.team_member_id].add(peer.id)
        for record in records:
            supervisor = r.shipment_recipient_supervisor_assignment([a for a in groups[0].get(record.id, []) if a.participation_status not in {'Declined','Cancelled'}])
            if supervisor:
                combined_eligible[record.id] = eligible_by_supervisor[supervisor.team_member_id] - {record.id}
    old_cache = {}
    if has_app_context():
        for name, value in {'_final_checks_assignment_rows': {sid: sum((group.get(sid, []) for group in groups), []) for sid in ids},
                            '_final_checks_controls': {sid: first(controls, sid) for sid in ids},
                            '_final_checks_events': {sid: event_types[sid] for sid in ids},
                            '_quality_combined_eligible': combined_eligible}.items():
            old_cache[name] = getattr(g, name, None)
            setattr(g, name, value)
    rows = []
    try:
        for record in records:
            sid = record.id
            roles = [group.get(sid, []) for group in groups]
            assignments = sum(roles, [])
            control = first(controls, sid)
            # Seed a loaded relationship required by the shared staffing contract.
            from sqlalchemy.orm.attributes import set_committed_value
            set_committed_value(record, 'staffing_control', first(staffing_controls, sid))
            staff = r.staffing_readiness_contract(*roles, session_record=record)
            primary_id = schedule_groups[sid]['primary_session_id']
            workflow = first(workflows, primary_id)
            schedule_status = r.schedule_workflow_status(workflow)
            preparation_enabled = bool(record.monthly_registrations_closed and (record.date_confirmation_status == 'Confirmed' or schedule_status != 'Not started'))
            staffing_ready = staff['status'] == 'confirmed'
            counts = staff['totals']
            candidate_total = record.unified_candidate_total if record.unified_candidate_total is not None and record.concat_session_ids not in ('', '[]') else candidates.get(sid)
            candidate_detail = f'{candidate_total}/{record.minimum_candidates_required or 0} candidates · latest monthly total' if candidate_total is not None else 'Latest monthly candidate total not loaded'
            active_concepts = [SimpleNamespace(id=c.id, status=c.status, provider=c.provider) for c in concepts.get(sid, [])]
            log = r.logistics_readiness_contract(assignments, active_concepts, first(logistics, sid))
            log_state = r.logistics_presentation_state(log)
            # Intern assignments activate the section even without selecting Complex logistics.
            if any(a.team_member_id or a.potential_entry_id for a in roles[2]) and not log['applies']:
                log_state = 'configuration_required'
                log['applies'] = True
            requirements = ([True] if any(owners.get(mid) == sid for mid in pending_ids) else [])
            if record.staff_member_ids_status == 'completed':
                requirements = r.staff_member_id_snapshot_for_session(record)
            package = r.package_preparation_status_contract(record, requirements)
            package_stages = r.package_preparation_stage_statuses(record, requirements)
            done_stages = sum(status == 'completed' for _, status in package_stages)
            onsite = record.format == 'Onsite'
            fin = r.finance_readiness_contract(first(finance, sid), today=today, session_date=record.session_date)
            gate = final_checks_state(record, control=control, today=today) if onsite else None
            total_checks = len(r.SINAPSIS_CHECKLIST_ITEMS)
            checked = sum(item.is_checked and item.item_key in {c['key'] for c in r.SINAPSIS_CHECKLIST_ITEMS} for item in (control.checklist_items if control else []))
            link = first(links, sid)
            bundle = link.bundle if link else None
            bundle_status = bundle.status if bundle else 'Not bundled'
            recipient = next((a for a in assignments if a.is_shipment_recipient and (a.team_member_id or a.potential_entry_id)), None)
            person = (recipient.team_member or recipient.potential_entry) if recipient else None
            staffing_completed = r.staffing_completed_date(assignments=assignments, session_record=record) if staffing_ready else None
            deadline_workflow = SimpleNamespace(status=workflow.status, approved_at=workflow.approved_at or latest_approvals.get(primary_id), updated_at=workflow.updated_at, events=[]) if workflow else None
            package_deadline = r.package_gate_deadline(schedule_workflow=deadline_workflow, staffing_completed_at=staffing_completed)
            cells = [
                cell('date', record.date_confirmation_status, complete=record.date_confirmation_status == 'Confirmed', today=today,
                     active=record.date_confirmation_status not in {'Pending', 'Confirmed'}, detail='Exam date confirmation'),
                cell('registrations', 'Closed' if record.monthly_registrations_closed else 'Open', complete=record.monthly_registrations_closed,
                     active=bool(candidate_total) or sid in registration_activity, near=bool(candidate_total is not None and candidate_total >= (record.minimum_candidates_required or 0)), today=today, detail=candidate_detail, completed_at=record.monthly_registrations_closed_at),
                cell('schedule', schedule_status, complete=schedule_status == 'Approved', active=schedule_status != 'Not started', enabled=preparation_enabled,
                     near=schedule_status == 'Sent for review', issue=schedule_status == 'Changes requested', deadline=workflow.next_action_due_at if workflow else None,
                     today=today, detail=(f'Shared schedule · managed from session #{primary_id}' if primary_id != sid else 'Schedule approval'), action_at=None, completed_at=workflow.approved_at if workflow else None),
                cell('staffing', 'Confirmed' if staffing_ready else f"{counts['confirmed']}/{counts['required']} confirmed", complete=staffing_ready,
                     active=bool(counts['assigned']), enabled=preparation_enabled, near=bool(counts['required'] and counts['confirmed'] + counts['sent'] == counts['required']),
                     issue=staff['status'] == 'invalid' or any(b['code'] in {'STAFF_DECLINED', 'STAFF_CANCELLED'} for b in staff['blockers']),
                     deadline=(r.staffing_deadline_badge_contract(first(staffing_controls,sid), staff, assignments, [], record, today=today) or {}).get('date'),
                     today=today, detail='; '.join(b['message'] for b in staff['blockers']), action_at=None),
                cell('package', package['label'], complete=package['status'] == 'completed', active=package['status'] != 'not_started',
                     enabled=schedule_status == 'Approved', applicable=onsite, near=done_stages == len(package_stages)-1,
                     issue=package['status'] == 'incident', deadline=package_deadline, today=today, detail=package['table_summary']),
                cell('shipment', bundle_status, complete=bundle_status == 'Recipient review successful', active=bool(bundle), applicable=onsite,
                     enabled=staffing_ready, near=bundle_status == 'Delivered successfully', issue=bundle_status in {'Delayed', 'Recipient review with discrepancy'},
                     deadline=bundle.dispatch_due_at if bundle and bundle_status in {'Preparing bundle', 'Ready to dispatch'} else None,
                     today=today, detail=f'Shared bundle {bundle.bundle_number or bundle.id}' if bundle else 'No shipment bundle assigned',
                     action_at=bundle.dispatched_at if bundle else None, completed_at=bundle.recipient_reviewed_at if bundle else None),
                cell('logistics', 'Configuration required' if log_state == 'configuration_required' else
                     'Not applicable' if not log['applies'] else f"{log['confirmed_concepts']}/{log['total_concepts']} confirmed",
                     complete=log_state == 'completed', active=bool(active_concepts), enabled=staffing_ready,
                     applicable=log['applies'] and record.format != 'Online', near=bool(log['total_concepts'] > 1 and log['confirmed_concepts'] == log['total_concepts']-1),
                     issue=log_state == 'needs_review', deadline=r.logistics_session_deadline(record), today=today,
                     detail='; '.join(b['message'] for b in log['blockers']) or 'All Logistics concepts confirmed'),
                cell('finance', fin['readiness_label'], complete=fin['can_proceed'], active=fin['standing_selected'] or bool(fin['additional_institutions']),
                     enabled=preparation_enabled, applicable=onsite, near=fin['readiness_label'] == 'Verification missing',
                     issue=fin['readiness_label'] == 'Close monitoring required', deadline=fin['deadline'], today=today, detail=fin['action_label'], action_at=None, completed_at=fin['cleared_at'] if fin['can_proceed'] else None),
                cell('final_checks', gate['progress'].replace('_', ' ').title() if gate else 'Not applicable',
                     complete=bool(gate and gate['progress'] == 'completed'), active=bool(gate and gate['progress'] != 'not_started'),
                     enabled=bool(gate and gate['return_enabled']), applicable=onsite,
                     near=bool(gate and gate['return_complete'] and checked == total_checks-1),
                     issue=bool(gate and gate['review_required']),
                     deadline=min([b['date'] for b in [gate['return_deadline_badge'] if not gate['return_complete'] else None,
                         gate['checks_deadline_badge'] if gate['checks_enabled'] and not gate['checks_complete'] else None] if b and b.get('date')], default=None) if gate else None,
                     today=today, detail=f"{checked}/{total_checks} Sinapsis checks · Return {'complete' if gate and gate['return_complete'] else 'pending'}" +
                         (f" · {gate['message']}" if gate and gate['message'] else '')),
            ]
            if gate and gate['return_enabled'] and control and control.return_recipient_confirmed_on:
                opening = record.session_date - timedelta(days=29)
                if control.return_recipient_confirmed_on < opening:
                    cells[-1]['available_at'] = datetime.combine(opening, time.min, tzinfo=r.LOCAL_TZ).astimezone(timezone.utc)
            if package['status'] == 'completed':
                stamps = [getattr(record, field, None) for field in ['package_label_verification_updated_at', 'package_label_printing_updated_at', 'room_package_sealing_updated_at', 'return_packages_updated_at', 'staff_member_ids_updated_at', 'inclusion_final_items_updated_at', 'session_box_sealing_updated_at']]
                cells[4]['completed_at'] = max((utc(stamp) for stamp in stamps if stamp), default=None)
            days = (record.session_date - today).days
            business = r.argentina_business_days_until(record.session_date, today=today) if days >= 0 else r.argentina_business_days_until(today, today=record.session_date)
            timing_sources = {
                'date': {'begun': True},
                'registrations': {'begun': sid in latest_month or record.monthly_registrations_closed},
                'schedule': {'begun': preparation_enabled or schedule_status != 'Not started', 'primary_id': primary_id,
                             'waiting': schedule_status == 'Sent for review', 'reason': 'Institution'},
                'staffing': {'begun': bool(counts['required']), 'waiting': bool(counts['sent'] and not counts['open_positions'] and not counts['pending_assigned'] and staff['schedule_notification_confirmed'] and staff['status'] != 'invalid'), 'reason': 'Staff member'},
                'package': {'begun': schedule_status == 'Approved'},
                'shipment': {'begun': bool(bundle), 'bundle_id': bundle.id if bundle else None,
                             'waiting': bundle_status in {'Dispatched','Recipient notified','In transit to post office','In transit to recipient','Delayed','Delivered successfully'},
                             'reason': 'Recipient' if bundle_status == 'Delivered successfully' else 'Courier'},
                'logistics': {'begun': bool(log['applies'])},
                'finance': {'begun': bool(first(finance, sid) and (fin['standing_selected'] or fin['additional_institutions']))},
                'final_checks': {'begun': bool(gate and gate['return_enabled'])},
            }
            rows.append(dict(session=record, cells=cells, timing_sources=timing_sources, days=days, business_days=business,
                             recipient=(' '.join(filter(None, [getattr(person, 'title', ''), getattr(person, 'full_name', '')])) if person else None),
                             recipient_status=recipient.participation_status if recipient else None,
                             incident_count=incidents.get(sid, 0),
                             attention=bool(incidents.get(sid)) or any(c['overdue'] or c['issue'] for c in cells if c['applicable']),
                             ready=all(c['complete'] for c in cells if c['applicable']),
                             concatenated=bool(record.concat_session_ids_list() if hasattr(record, 'concat_session_ids_list') else record.concat_session_ids not in ('', '[]'))))
    finally:
        if has_app_context():
            for name, previous in old_cache.items():
                if previous is None:
                    g.pop(name, None)
                else:
                    setattr(g, name, previous)
    return rows


def initialize_quality_tracking():
    missing = m.ExamSession.query.filter(~m.ExamSession.id.in_(db.session.query(m.QualityProcessTiming.exam_session_id))).all()
    for offset in range(0, len(missing), 100):
        observe(load_rows(missing[offset:offset+100]))
    if missing:
        db.session.commit()


def observe(rows, unit=None, now=None, fresh_ids=()):
    """Store real transitions, within the same transaction as the underlying change."""
    unit = unit or db.session()
    now = now or datetime.now(timezone.utc)
    ids = [row['session'].id for row in rows]
    if not ids:
        return {}
    # INSERT first acquires the SQLite write lock; ON CONFLICT avoids duplicate baselines.
    dialect = unit.get_bind().dialect.name
    from sqlalchemy.dialects.sqlite import insert as sqlite_insert
    from sqlalchemy.dialects.postgresql import insert as pg_insert
    insert = pg_insert if dialect == 'postgresql' else sqlite_insert
    values = [dict(exam_session_id=row['session'].id, process_key=c['key'], state=c['state'],
                   enabled=c['enabled'], observed_at=now, reopenings=0, history_json='[]')
              for row in rows for c in row['cells']]
    for offset in range(0, len(values), 100):
        unit.execute(insert(m.QualityProcessTiming).values(values[offset:offset+100]).on_conflict_do_nothing(
            index_elements=['exam_session_id', 'process_key']))
    saved = {(item.exam_session_id, item.process_key): item for item in unit.query(m.QualityProcessTiming).filter(
        m.QualityProcessTiming.exam_session_id.in_(ids)).with_for_update().all()}
    for row in rows:
        for c in row['cells']:
            metric = saved[row['session'].id, c['key']]
            history = json.loads(metric.history_json)
            baseline = not history
            previous_length = len(history)
            def log(kind):
                history.append({'event': kind, 'at': now.isoformat(), 'state': c['state']})
            if baseline:
                log('Tracking started; earlier milestones may be unavailable')
                if row['session'].id in fresh_ids and c['enabled']:
                    metric.enabled_at = now
                if c.get('action_at'):
                    metric.first_action_at = c['action_at']
                # Explicit completion timestamps are useful even if the start is unknown.
                if c['complete'] and c.get('completed_at'):
                    metric.completed_at = c['completed_at']
            else:
                if c['enabled'] and not metric.enabled:
                    if not metric.enabled_at:
                        metric.enabled_at = c.get('available_at') or now
                    log('Enabled')
                if (c['active'] or c['complete']) and not metric.first_action_at and metric.state in {'pending', 'blocked'}:
                    metric.first_action_at = now
                    log('First recorded action')
                if c['complete'] and metric.state != 'complete':
                    metric.completed_at = now
                    log('Completed')
                elif metric.state == 'complete' and not c['complete']:
                    metric.reopenings += 1
                    metric.completed_at = None
                    log('Reopened')
                elif metric.state != c['state']:
                    log('Status updated')
            metric.state, metric.enabled = c['state'], c['enabled']
            if len(history) != previous_length:
                metric.observed_at = now
                metric.history_json = json.dumps(history)
    return saved


def timing_view(metric, now=None):
    now = now or datetime.now(timezone.utc)
    enabled = utc(metric.enabled_at)
    action = utc(metric.first_action_at)
    completed = utc(metric.completed_at)
    elapsed = max(0, ((completed or now) - enabled).total_seconds() / 86400) if enabled else None
    wait = max(0, (action - enabled).total_seconds() / 86400) if action and enabled else None
    duration = max(0, (completed - action).total_seconds() / 86400) if completed and action else None
    return dict(enabled_at=enabled.isoformat() if enabled else None, first_action_at=action.isoformat() if action else None,
                completed_at=completed.isoformat() if completed else None, elapsed=round(elapsed, 1) if elapsed is not None else None,
                wait=round(wait, 1) if wait is not None else None, duration=round(duration, 1) if duration is not None else None,
                reopenings=metric.reopenings, history=json.loads(metric.history_json))


def dashboard_rows(year):
    records = m.ExamSession.query.filter(extract('year', m.ExamSession.session_date) == year).order_by(
        m.ExamSession.session_date, m.ExamSession.exam_session_name, m.ExamSession.id).all()
    return load_rows(records)


@quality_bp.route('/quality-control')
@login_required
def index():
    if not getattr(getattr(g, 'current_user', None), 'is_superadmin', False):
        abort(403)
    years = [int(year) for year, in db.session.query(extract('year', m.ExamSession.session_date)).distinct().order_by(
        extract('year', m.ExamSession.session_date).desc())]
    year = request.args.get('session_year', type=int) or (years[0] if years else datetime.now().year)
    if years and year not in years:
        abort(400)
    rows = dashboard_rows(year)
    tab = request.args.get('tab', 'readiness')
    if tab not in {'readiness','timing'}:
        abort(400)
    if tab == 'timing':
        from app.process_timing import attach_clocks, reconcile_due
        reconcile_due()
        attach_clocks(rows)
    from app.routes import LOCAL_TZ
    for row in rows:
        record = row['session']
        for c in row['cells']:
            if c['key'] == 'date':
                c['url'] = url_for('staff.exam_session_planner', session_year=year, open_session_modal=record.id)
            elif c['key'] == 'registrations':
                c['url'] = url_for('staff.monthly_exam_session_registrations', session_year=year, q=record.exam_session_name)
            elif record.format != 'Onsite':
                c['url'] = url_for('staff.pre_online_session_control_tower', session_year=year,
                                   open_schedule_modal=record.id, open_modal_target='staffing' if c['key'] == 'staffing' else 'schedule-actions') if c['key'] in {'schedule', 'staffing'} else None
            else:
                target = {'schedule':'schedule-actions', 'staffing':'staffing', 'package':'packages',
                          'shipment':'shipments', 'logistics':'logistics', 'finance':'finance', 'final_checks':'sinapsis'}[c['key']]
                c['url'] = url_for('staff.pre_session_control_tower', session_year=year, view='sessions' if c['key'] in {'logistics','finance','final_checks'} else 'bundles',
                                   open_schedule_modal=record.id, open_modal_target=target)
    response = current_app.make_response(render_template('quality_control.html', rows=rows, processes=PROCESSES,
        formats=FORMATS, years=years, selected_year=year, tab=tab,
        readiness_url=url_for('quality_control.index', **{**request.args.to_dict(), 'tab':'readiness'}),
        timing_url=url_for('quality_control.index', **{**request.args.to_dict(), 'tab':'timing'}), measured_at=datetime.now(LOCAL_TZ)))
    response.headers['Cache-Control'] = 'no-store'
    return response


# Collect affected sessions during flush (including explicit flushes before commit).
# Never recalculate all sessions or perform network calls while saving a session.
TRACKED_MODELS = {m.ExamSession, *ASSIGNMENTS, m.ExamSessionScheduleWorkflow,
                 m.ExamSessionStaffingControl, m.ExamSessionFinanceControl, m.ExamSessionSinapsisControl,
                 m.ExamSessionLogistics, m.ExamSessionLogisticsConcept, m.ExamSessionMonthlyCandidateTotal,
                 m.ExamSessionMonthlyRegistration, m.ExamSessionShipmentBundleSession, m.ExamSessionStaffingEvent, m.ExamSessionIncident}


@event.listens_for(Session, 'before_flush')
def collect_quality_changes(unit, *_):
    if not has_app_context() or not current_app.config.get('QUALITY_CONTROL_TRACKING_READY') or unit.info.get('quality_observing'):
        return
    ids = unit.info.setdefault('quality_session_ids', set())
    for obj in list(unit.new) + list(unit.dirty) + list(unit.deleted):
        if isinstance(obj, m.ExamSession) and obj in unit.deleted:
            affected = {cid for cid, in unit.query(m.ProcessClockSession.clock_id).filter_by(exam_session_id=obj.id,is_current=True)}
            unit.info.setdefault('process_timing_retire_ids', set()).update(affected)
            ids.update(sid for sid, in unit.query(m.ProcessClockSession.exam_session_id).filter(m.ProcessClockSession.clock_id.in_(affected),m.ProcessClockSession.is_current.is_(True)))
        if isinstance(obj, (m.ExamSessionScheduleEvent, m.ExamSessionStaffingEvent, m.ExamSessionFinanceEvent)) and obj.previous_status == obj.new_status:
            continue
        if obj in unit.dirty:
            changed = {attr.key for attr in inspect(obj).attrs if attr.history.has_changes()}
            watched = None
            if isinstance(obj, m.ExamSession):
                watched = {'date_confirmation_status','monthly_registrations_closed','monthly_registrations_closed_at',
                           'session_date','format','concat_session_ids','emergency_contact_required','emergency_contact_not_required',
                           'emergency_contact_member_id','emergency_contact_participation_status','emergency_contact_additional_contacts',
                           'emergency_contact_status_due_at','staff_member_ids_snapshot'} | {field for field in changed if field.endswith('_status')}
            elif type(obj) in ASSIGNMENTS:
                watched = {'team_member_id','potential_entry_id','participation_status','is_shipment_recipient',
                           'logistics_enabled','logistics_type','staffing_status_due_at','is_remote','exam_session_id'}
            elif isinstance(obj, m.ExamSessionFinanceControl):
                watched = {'status','additional_institutions','institutions_confirmed_with_admin'}
            elif isinstance(obj, m.AcademicStaff):
                watched = {'status','roles','id_issued'}
            if watched is not None and not changed & watched:
                continue
        if type(obj) in TRACKED_MODELS:
            sid = obj.id if isinstance(obj, m.ExamSession) else obj.exam_session_id
            if sid:
                ids.add(sid)
            if isinstance(obj, m.ExamSession) and obj in unit.new:
                unit.info.setdefault('quality_new_records', []).append(obj)
        elif isinstance(obj, (m.ExamSessionScheduleEvent, m.ExamSessionFinanceEvent, m.ExamSessionSinapsisEvent)):
            parent_model, fk = {m.ExamSessionScheduleEvent:(m.ExamSessionScheduleWorkflow,'workflow_id'),
                m.ExamSessionFinanceEvent:(m.ExamSessionFinanceControl,'finance_control_id'),
                m.ExamSessionSinapsisEvent:(m.ExamSessionSinapsisControl,'sinapsis_control_id')}[type(obj)]
            parent = unit.get(parent_model, getattr(obj, fk)) if getattr(obj, fk) else None
            if parent:
                ids.add(parent.exam_session_id)
        elif isinstance(obj, m.ExamSessionShipmentEvent):
            unit.info.setdefault('quality_bundle_ids', set()).add(obj.bundle_id)
        elif isinstance(obj, m.ExamSessionSinapsisChecklistItem):
            control = obj.sinapsis_control or unit.get(m.ExamSessionSinapsisControl, obj.sinapsis_control_id)
            if control:
                ids.add(control.exam_session_id)
        elif isinstance(obj, m.ExamSessionShipmentBundle):
            unit.info.setdefault('quality_bundle_ids', set()).add(obj.id)
            if obj in unit.new:
                unit.info.setdefault('process_timing_fresh_bundles', []).append(obj)
        elif isinstance(obj, (m.AcademicStaff, m.StaffIdDocument)):
            # Role/ID changes can affect several staffing/package summaries. These
            # sessions are collected in one query per assignment model below.
            member_id = obj.id if isinstance(obj, m.AcademicStaff) else obj.member_id
            if member_id:
                unit.info.setdefault('quality_member_ids', set()).add(member_id)


@event.listens_for(Session, 'before_commit')
def save_quality_changes(unit):
    if not has_app_context() or not current_app.config.get('QUALITY_CONTROL_TRACKING_READY') or unit.info.get('quality_observing'):
        return
    unit.flush()
    ids = unit.info.pop('quality_session_ids', set())
    deleted_sessions = unit.info.pop('process_timing_deleted_sessions', set())
    if deleted_sessions:
        unit.query(m.ProcessClockSession).filter(m.ProcessClockSession.exam_session_id.in_(deleted_sessions)).update({'is_current':False}, synchronize_session='fetch')
    fresh = {obj.id for obj in unit.info.pop('quality_new_records', []) if obj not in unit.deleted and obj.id}
    bundle_ids = unit.info.pop('quality_bundle_ids', set())
    if bundle_ids:
        ids.update(sid for sid, in unit.query(m.ExamSessionShipmentBundleSession.exam_session_id).filter(m.ExamSessionShipmentBundleSession.bundle_id.in_(bundle_ids)))
    member_ids = unit.info.pop('quality_member_ids', set())
    if member_ids:
        for model in ASSIGNMENTS:
            ids.update(sid for sid, in unit.query(model.exam_session_id).filter(model.team_member_id.in_(member_ids)))
        ids.update(sid for sid, in unit.query(m.ExamSession.id).filter(m.ExamSession.emergency_contact_member_id.in_(member_ids)))
    if not ids and not fresh:
        return
    if ids:
        from app.routes import exam_session_concat_component_map
        components = exam_session_concat_component_map()
        ids.update(peer for sid in list(ids) for peer in components.get(sid, {sid}))
    unit.info['quality_observing'] = True
    try:
        # Only previously tracked sessions need a baseline update on ordinary edits.
        from app.process_timing import expanded_records
        records = expanded_records(ids | fresh, unit=unit)
        if records:
            from app.process_timing import reconcile_rows
            fresh_owners = {f'bundle:{obj.id}' for obj in unit.info.pop('process_timing_fresh_bundles', []) if obj.id}
            from flask import has_request_context
            who = (getattr(getattr(g, 'current_user', None), 'email', None) or request.environ.get('REMOTE_USER') or 'Portal user') if has_request_context() else 'System'
            reconcile_rows(load_rows(records), unit=unit, fresh_ids=fresh, fresh_owners=fresh_owners, created_by=who)
        from app.process_timing import retire_orphan_clocks
        retire_orphan_clocks(unit.info.pop('process_timing_retire_ids', set()), unit=unit)
        unit.flush()
    finally:
        unit.info.pop('quality_observing', None)


@event.listens_for(Session, 'after_rollback')
@event.listens_for(Session, 'after_commit')
def clear_quality_changes(unit):
    for key in ['quality_session_ids', 'quality_new_records', 'quality_bundle_ids', 'quality_member_ids', 'process_timing_fresh_bundles', 'process_timing_retire_ids', 'process_timing_deleted_sessions']:
        unit.info.pop(key, None)


@event.listens_for(Session, 'do_orm_execute')
def collect_quality_bulk_changes(execution):
    """Query.update/delete also occur in operational bulk actions."""
    if (not (execution.is_update or execution.is_delete) or not has_app_context()
            or not current_app.config.get('QUALITY_CONTROL_TRACKING_READY')
            or execution.session.info.get('quality_observing')):
        return
    mapper = execution.bind_mapper
    if mapper is None:
        return
    model = mapper.class_
    unit = execution.session
    clauses = execution.statement._where_criteria
    if model in TRACKED_MODELS:
        field = model.id if model is m.ExamSession else model.exam_session_id
        affected_ids = {sid for sid, in unit.query(field).filter(*clauses)}
        unit.info.setdefault('quality_session_ids', set()).update(affected_ids)
        if model is m.ExamSession and execution.is_delete:
            unit.info.setdefault('process_timing_deleted_sessions', set()).update(affected_ids)
            clock_ids = {cid for cid, in unit.query(m.ProcessClockSession.clock_id).filter(m.ProcessClockSession.exam_session_id.in_(affected_ids),m.ProcessClockSession.is_current.is_(True))}
            unit.info.setdefault('process_timing_retire_ids',set()).update(clock_ids)
            unit.info.setdefault('quality_session_ids',set()).update(sid for sid, in unit.query(m.ProcessClockSession.exam_session_id).filter(m.ProcessClockSession.clock_id.in_(clock_ids),m.ProcessClockSession.is_current.is_(True)))
    elif model is m.AcademicStaff:
        unit.info.setdefault('quality_member_ids', set()).update(mid for mid, in unit.query(model.id).filter(*clauses))
    elif model is m.ExamSessionShipmentBundle:
        unit.info.setdefault('quality_bundle_ids', set()).update(bid for bid, in unit.query(model.id).filter(*clauses))
