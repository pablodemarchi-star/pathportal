"""Persistent, non-overlapping process intervals. Operational states are read-only."""
import hashlib
import hmac
import json
import os
from collections import defaultdict
from datetime import datetime, timezone
from statistics import median
from flask import abort, current_app, g, jsonify, request, session
from sqlalchemy import or_, and_
from app import db, login_required, validate_csrf
from app import models as m
from app.quality_control import quality_bp, PROCESSES, load_rows, utc

ACTIVE = {'Path time': 'path_seconds', 'Waiting external': 'external_seconds', 'Incident time': 'incident_seconds'}
REASONS = ['Institution', 'Staff member', 'Provider', 'Courier', 'Recipient', 'Other']
BLOCKS = dict(PROCESSES)
ACTIVE_INCIDENTS = {'Open','In progress','Waiting external'}


def actor():
    return (getattr(getattr(g, 'current_user', None), 'email', None) or session.get('user', 'System')) if request else 'System'


def require_superadmin():
    if not getattr(getattr(g, 'current_user', None), 'is_superadmin', False):
        abort(403)


def choose_category(c, source, manual_reason=None, incident_ids=()):
    # Terminal/ineligible periods never count, even in the presence of incidents.
    if not c['applicable']:
        return 'N/A', '', 'operational'
    if c['complete']:
        return 'Completed', '', 'operational'
    if not c['enabled'] or not source.get('begun'):
        return 'Blocked', '', 'operational'
    if incident_ids:
        return 'Incident time', 'Linked incident', 'incident'
    if source.get('waiting'):
        return 'Waiting external', source.get('reason', 'Other'), 'automatic'
    if manual_reason:
        return 'Waiting external', manual_reason, 'manual'
    return 'Path time', '', 'operational'


def owner_key(row, key, components):
    sid = row['session'].id
    if key == 'schedule':
        members = sorted(components.get(sid, {sid}))
        token = str(sid) if len(members) == 1 else hashlib.sha256(','.join(map(str, members)).encode()).hexdigest()[:32]
        return 'schedule:' + token
    if key == 'shipment':
        bundle_id = row['timing_sources'][key].get('bundle_id')
        return f'bundle:{bundle_id}' if bundle_id else None
    return f'session:{sid}:{key}'


def expanded_records(ids, unit=None):
    unit = unit or db.session()
    ids = set(ids)
    if not ids:
        return []
    from app.routes import exam_session_concat_component_map
    components = exam_session_concat_component_map()
    ids.update(peer for sid in list(ids) for peer in components.get(sid, {sid}))
    bundle_ids = unit.query(m.ExamSessionShipmentBundleSession.bundle_id).filter(m.ExamSessionShipmentBundleSession.exam_session_id.in_(ids))
    ids.update(sid for sid, in unit.query(m.ExamSessionShipmentBundleSession.exam_session_id).filter(
        m.ExamSessionShipmentBundleSession.bundle_id.in_(bundle_ids)))
    return unit.query(m.ExamSession).filter(m.ExamSession.id.in_(ids)).order_by(m.ExamSession.id).populate_existing().all()


def lock_clocks(keys, now, unit):
    from sqlalchemy.dialects.sqlite import insert as sqlite_insert
    from sqlalchemy.dialects.postgresql import insert as pg_insert
    insert = pg_insert if unit.get_bind().dialect.name == 'postgresql' else sqlite_insert
    # Write first serializes SQLite writers; row locks serialize PostgreSQL writers.
    values = [dict(owner_key=key, block=block, category='Blocked', tracked_from=now,
        coverage_complete=False, path_seconds=0, external_seconds=0, incident_seconds=0, revision=0, reopenings=0, created_at=now)
        for key, block in sorted(keys.items())]
    for offset in range(0,len(values),60):
        unit.execute(insert(m.ProcessClock).values(values[offset:offset+60]).on_conflict_do_nothing(index_elements=['owner_key']))
    return {clock.owner_key:clock for clock in unit.query(m.ProcessClock).filter(m.ProcessClock.owner_key.in_(keys)).order_by(m.ProcessClock.id).populate_existing().with_for_update().all()}


def transition(clock, category, now, *, reason='', note='', incident_ids=(), source='operational', created_by='System', interval=None, unit=None):
    unit = unit or db.session()
    incident_json = json.dumps(sorted(incident_ids)) if category not in {'Completed','N/A'} else '[]'
    if not interval and clock.category == 'N/A' and category == 'N/A' and clock.revision:
        return False
    if interval and (interval.category,interval.reason,interval.note,interval.incident_ids_json,interval.source) == (category,reason,note,incident_json,source):
        return False
    at = max(utc(now), utc(interval.started_at)) if interval else utc(now)
    if interval:
        interval.ended_at = at
        if interval.category in ACTIVE:
            field = ACTIVE[interval.category]
            setattr(clock, field, getattr(clock,field) + max(0,(at-utc(interval.started_at)).total_seconds()))
        # Release the unique open-interval key before adding the next interval.
        unit.flush([interval])
    previous = clock.category
    clock.category = category
    clock.revision += 1
    if category in {'Completed','N/A'}:
        clock.manual_reason = None
        clock.manual_note = None
        clock.manual_by = None
    if category == 'Completed':
        clock.completed_at = at
    elif previous == 'Completed' and category != 'N/A':
        clock.completed_at = None
        clock.reopenings += 1
    if category in ACTIVE and clock.started_at is None and clock.coverage_complete:
        clock.started_at = at
    if category != 'N/A':
        unit.add(m.ProcessInterval(clock_id=clock.id, category=category, started_at=at,
            reason=reason, note=note, incident_ids_json=incident_json, source=source, created_by=created_by))
    return True


def reconcile_rows(rows, unit=None, fresh_ids=(), fresh_owners=(), now=None, created_by=None, manual_clock_id=None, initialization=False):
    """Consume the exact same completeness/applicability cells as Live readiness."""
    unit = unit or db.session()
    now = utc(now or datetime.now(timezone.utc))
    if not rows:
        return
    from app.routes import exam_session_concat_component_map
    components = exam_session_concat_component_map()
    groups = defaultdict(list)
    keys = {}
    membership = {}
    for row in rows:
        for c in row['cells']:
            key = owner_key(row,c['key'],components)
            if key is None:
                membership[row['session'].id,c['key']] = None
                continue
            groups[key].append((row,c))
            keys[key] = c['key']
            membership[row['session'].id,c['key']] = key
    if not keys:
        return
    clocks = lock_clocks(keys,now,unit)
    clock_ids = [clock.id for clock in clocks.values()]
    opened = {item.clock_id:item for item in unit.query(m.ProcessInterval).filter(m.ProcessInterval.clock_id.in_(clock_ids),m.ProcessInterval.ended_at.is_(None)).all()}
    existing_links = unit.query(m.ProcessClockSession).filter(or_(m.ProcessClockSession.clock_id.in_(clock_ids),
        m.ProcessClockSession.exam_session_id.in_([row['session'].id for row in rows]))).all()
    links = {(link.clock_id,link.exam_session_id):link for link in existing_links}
    retired_clock_ids = set()
    for link in existing_links:
        lookup = (link.exam_session_id,link.block)
        if lookup in membership and (membership[lookup] is None or clocks[membership[lookup]].id != link.clock_id):
            if link.is_current:
                retired_clock_ids.add(link.clock_id)
            link.is_current = False
    incidents = unit.query(m.ExamSessionIncident).filter(m.ExamSessionIncident.exam_session_id.in_(
        [row['session'].id for row in rows]),m.ExamSessionIncident.affected_block.in_(BLOCKS)).populate_existing().all()
    linked_pairs = {(item.clock_id,item.incident_id) for item in unit.query(m.ProcessClockIncident).filter(m.ProcessClockIncident.clock_id.in_(clock_ids))}
    for key, entries in groups.items():
        clock = clocks[key]
        block = keys[key]
        member_ids = {row['session'].id for row,c in entries}
        for sid in member_ids:
            link = links.get((clock.id,sid))
            if link:
                link.is_current = True
            else:
                unit.add(m.ProcessClockSession(clock_id=clock.id,exam_session_id=sid,block=block,is_current=True))
        if block == 'schedule':
            primary_id = entries[0][0]['timing_sources'][block]['primary_id']
            selected = next(((row,c) for row,c in entries if row['session'].id == primary_id),entries[0])
        else:
            selected = entries[0]
        row,c = selected
        aggregate = dict(c)
        source_info = dict(row['timing_sources'][block])
        if block == 'shipment':
            aggregate['enabled'] = all(item['enabled'] for _,item in entries)
        related = [incident for incident in incidents if incident.exam_session_id in member_ids and incident.affected_block == block]
        active_ids = [incident.id for incident in related if incident.status in ACTIVE_INCIDENTS]
        for incident in related:
            if (clock.id,incident.id) not in linked_pairs:
                unit.add(m.ProcessClockIncident(clock_id=clock.id,incident_id=incident.id))
                linked_pairs.add((clock.id,incident.id))
        # A new clock has no intervals. Previously N/A clocks can also be empty;
        # revisions distinguish those from an actual first baseline.
        baseline = clock.revision == 0
        if baseline:
            is_new = member_ids.issubset(set(fresh_ids)) or key in fresh_owners
            clock.coverage_complete = is_new or not source_info.get('begun')
            # Prior working periods cannot be recovered from a readiness snapshot.
            if aggregate['active'] or aggregate['complete']:
                clock.coverage_complete = is_new
            if not aggregate['applicable']:
                clock.coverage_complete = True
        category,reason,origin = choose_category(aggregate,source_info,clock.manual_reason,active_ids)
        note = (clock.manual_note or '') if origin == 'manual' else (f'Manual waiting request: {clock.manual_reason}. {clock.manual_note or ""}'.strip() if clock.manual_reason else '')
        if category == 'Incident time':
            note = '; '.join(incident.title for incident in related if incident.id in active_ids) + (' · ' + note if note else '')
        available = c.get('available_at')
        previous_interval = opened.get(clock.id)
        # A calendar opening is a distinct, known event. Classify the period
        # before today's mutation using the previously recorded waiting/incident
        # context, then classify the mutation at its actual timestamp.
        if (available and clock.category == 'Blocked' and not baseline and clock.next_check_at
                and utc(clock.next_check_at) == utc(available) and utc(available) <= now):
            prior_ids = json.loads(previous_interval.incident_ids_json) if previous_interval else []
            prior_category = 'Incident time' if prior_ids else 'Waiting external' if clock.manual_reason else 'Path time'
            transition(clock,prior_category,max(utc(available),utc(clock.tracked_from)),
                reason='Linked incident' if prior_ids else clock.manual_reason or '',
                note=clock.manual_note or '',incident_ids=prior_ids,source='calendar',
                created_by='Scheduled calendar gate',interval=previous_interval,unit=unit)
            unit.flush()
            previous_interval = unit.query(m.ProcessInterval).filter_by(clock_id=clock.id,ended_at=None).one()
        transition(clock,category,now,reason=reason,note=note,incident_ids=active_ids,
            source=origin, created_by=created_by or 'System', interval=previous_interval,unit=unit)
        if aggregate['applicable'] and source_info.get('begun') and not clock.has_begun:
            if clock.coverage_complete and not initialization and clock.started_at is None:
                clock.started_at = now
            clock.has_begun = True
        if baseline and block == 'date' and row['session'].created_on:
            clock.started_at = utc(row['session'].created_on)
        if baseline and category == 'Completed':
            clock.completed_at = now if clock.coverage_complete else c.get('completed_at')
            if clock.coverage_complete:
                clock.started_at = now
        if block == 'final_checks' and category == 'Blocked':
            record = row['session']
            from app.routes import LOCAL_TZ
            from datetime import timedelta,time
            opens = datetime.combine(record.session_date-timedelta(days=29),time.min,tzinfo=LOCAL_TZ).astimezone(timezone.utc)
            clock.next_check_at = opens if opens > now else None
        else:
            clock.next_check_at = None
    unit.flush()
    # Discontinued ownership (new concat group, a changed bundle, or N/A) keeps
    # its history but must not continue accumulating time in the background.
    for cid in sorted(retired_clock_ids):
        if not unit.query(m.ProcessClockSession.id).filter_by(clock_id=cid,is_current=True).first():
            clock = unit.query(m.ProcessClock).filter_by(id=cid).with_for_update().one()
            interval = unit.query(m.ProcessInterval).filter_by(clock_id=cid,ended_at=None).first()
            transition(clock,'N/A',now,reason='Process ownership changed',source='operational',interval=interval,unit=unit)


def retire_orphan_clocks(clock_ids, unit=None, now=None):
    unit = unit or db.session()
    now = now or datetime.now(timezone.utc)
    for cid in sorted(clock_ids):
        if unit.query(m.ProcessClockSession.id).filter_by(clock_id=cid,is_current=True).first():
            continue
        clock = unit.query(m.ProcessClock).filter_by(id=cid).with_for_update().first()
        if clock and clock.category != 'N/A':
            opened = unit.query(m.ProcessInterval).filter_by(clock_id=cid,ended_at=None).first()
            transition(clock,'N/A',now,reason='Session removed',source='operational',interval=opened,unit=unit)


def initialize_process_timing():
    # Only current source state is reconciled at startup, never historical intervals.
    records = db.session.query(m.ExamSession).order_by(m.ExamSession.id).all()
    if records:
        reconcile_rows(load_rows(records), initialization=True)
        db.session.commit()


def reconcile_due(now=None):
    """A scheduled backend sweep handles calendar gates, without any open page."""
    now = utc(now or datetime.now(timezone.utc))
    due = db.session.query(m.ProcessClockSession.exam_session_id).join(m.ProcessClock).filter(
        m.ProcessClockSession.is_current.is_(True),m.ProcessClock.next_check_at <= now).distinct().all()
    if due:
        from app.routes import LOCAL_TZ
        records = expanded_records([sid for sid, in due])
        reconcile_rows(load_rows(records,today=now.astimezone(LOCAL_TZ).date()),now=now,created_by='Scheduled job')
        db.session.commit()
    return len(due)


def totals(clock, interval=None, now=None):
    now = utc(now or datetime.now(timezone.utc))
    result = {'Path time':clock.path_seconds,'Waiting external':clock.external_seconds,'Incident time':clock.incident_seconds}
    if interval and interval.category in ACTIVE:
        result[interval.category] += max(0,(now-utc(interval.started_at)).total_seconds())
    return {'total':sum(result.values()),'path':result['Path time'],'external':result['Waiting external'],'incident':result['Incident time']}


def clock_data(clock, interval=None, now=None):
    stamp = lambda value:utc(value).isoformat() if value else None
    return dict(id=clock.id,block=clock.block,category=clock.category,started_at=stamp(clock.started_at),
        completed_at=stamp(clock.completed_at),tracked_from=stamp(clock.tracked_from),coverage_complete=clock.coverage_complete,
        reopenings=clock.reopenings,revision=clock.revision,manual_reason=clock.manual_reason,manual_note=clock.manual_note,
        totals=totals(clock,interval,now),as_of=stamp(now or datetime.now(timezone.utc)))


def attach_clocks(rows, now=None):
    ids = [row['session'].id for row in rows]
    if not ids:
        return
    links = m.ProcessClockSession.query.filter(m.ProcessClockSession.exam_session_id.in_(ids),m.ProcessClockSession.is_current.is_(True)).all()
    pairs = db.session.query(m.ProcessClock,m.ProcessInterval).outerjoin(m.ProcessInterval,and_(
        m.ProcessInterval.clock_id==m.ProcessClock.id,m.ProcessInterval.ended_at.is_(None))).filter(m.ProcessClock.id.in_({link.clock_id for link in links})).all()
    clocks = {clock.id:clock for clock,interval in pairs}
    opened = {clock.id:interval for clock,interval in pairs}
    by_session = {(link.exam_session_id,link.block):clocks[link.clock_id] for link in links}
    for row in rows:
        for c in row['cells']:
            clock = by_session.get((row['session'].id,c['key']))
            c['clock'] = clock_data(clock,opened.get(clock.id),now) if c['applicable'] and clock else None
            if c['clock']:
                c['clock'].pop('manual_note',None)
                c['clock'].pop('manual_reason',None)


def cohort_medians(clock_dicts):
    unique = {item['id']:item for item in clock_dicts if item and item['category']=='Completed' and item['coverage_complete']}
    values = list(unique.values())
    return {key:median([item['totals'][key] for item in values]) if values else None for key in ['total','path','external','incident']},len(values)


@quality_bp.get('/quality-control/process-timing/<int:clock_id>')
@login_required
def timing_detail(clock_id):
    require_superadmin()
    pair = db.session.query(m.ProcessClock,m.ProcessInterval).outerjoin(m.ProcessInterval,and_(m.ProcessInterval.clock_id==m.ProcessClock.id,m.ProcessInterval.ended_at.is_(None))).filter(m.ProcessClock.id==clock_id).first()
    if not pair:
        abort(404)
    clock,opened = pair
    before = request.args.get('before',type=int)
    query = m.ProcessInterval.query.filter_by(clock_id=clock.id)
    if before:
        query = query.filter(m.ProcessInterval.id < before)
    intervals = query.order_by(m.ProcessInterval.id.desc()).limit(101).all()
    has_more = len(intervals)>100
    intervals = intervals[:100]
    incident_rows = db.session.query(m.ExamSessionIncident).join(m.ProcessClockIncident).filter(m.ProcessClockIncident.clock_id==clock.id).all()
    links = db.session.query(m.ExamSession.id,m.ExamSession.exam_session_name).join(m.ProcessClockSession).filter(
        m.ProcessClockSession.clock_id==clock.id,m.ProcessClockSession.is_current.is_(True)).all()
    data = clock_data(clock,opened)
    data['sessions'] = [{'id':sid,'name':name} for sid,name in links]
    data['incidents'] = [{'id':item.id,'title':item.title,'status':item.status,'affected_block':item.affected_block} for item in incident_rows]
    data['waiting_reasons'] = [reason for reason, in db.session.query(m.ProcessInterval.reason).filter_by(clock_id=clock.id,category='Waiting external').distinct()]
    data['history'] = [dict(id=item.id,category=item.category,started_at=utc(item.started_at).isoformat(),
        ended_at=utc(item.ended_at).isoformat() if item.ended_at else None,reason=item.reason,note=item.note,
        source=item.source,created_by=item.created_by,incidents=json.loads(item.incident_ids_json)) for item in reversed(intervals)]
    data['next_before'] = intervals[-1].id if has_more else None
    response = jsonify(data)
    response.headers['Cache-Control']='no-store'
    return response


@quality_bp.post('/quality-control/process-timing/<int:clock_id>/waiting')
@login_required
def timing_waiting(clock_id):
    require_superadmin()
    if not validate_csrf():
        return jsonify(error='Security token expired. Reload the page.'),400
    clock = db.session.get(m.ProcessClock,clock_id) or abort(404)
    if request.form.get('action') not in {'wait','resume'}:
        return jsonify(error='Invalid timing action.'),400
    reason,note=request.form.get('reason','').strip(),request.form.get('note','').strip()
    if request.form['action']=='wait' and (reason not in REASONS or reason=='Other' and not note or len(note)>1000):
        return jsonify(error='Select a reason. Other requires a note (maximum 1000 characters).'),400
    records = expanded_records([sid for sid, in db.session.query(m.ProcessClockSession.exam_session_id).filter_by(clock_id=clock.id,is_current=True)])
    if not records:
        return jsonify(error='This shared process is no longer assigned to a session.'),409
    now=datetime.now(timezone.utc)
    rows=load_rows(records)
    reconcile_rows(rows,now=now)
    db.session.flush()
    clock = m.ProcessClock.query.filter_by(id=clock_id).with_for_update().one()
    revision=request.form.get('revision',type=int)
    if revision != clock.revision:
        db.session.rollback()
        return jsonify(error='This process was updated. Reopen its detail and try again.'),409
    if clock.category not in ACTIVE:
        db.session.rollback()
        return jsonify(error='This process is blocked, completed or not applicable.'),409
    if request.form['action']=='resume':
        clock.manual_reason=None;clock.manual_note=None;clock.manual_by=None
    else:
        clock.manual_reason=reason;clock.manual_note=note;clock.manual_by=actor()
    clock.revision += 1
    # Same source rows; only the timing classification changes.
    reconcile_rows(rows,now=now,created_by=actor(),manual_clock_id=clock_id)
    db.session.flush()
    db.session.commit()
    return timing_detail(clock_id=clock_id)


@quality_bp.post('/internal/jobs/process-timing')
def timing_job():
    expected=os.getenv('QUALITY_TIMING_JOB_TOKEN') or os.getenv('FINANCE_AGENDA_JOB_TOKEN','')
    if len(expected)<32 or not hmac.compare_digest(request.headers.get('Authorization',''),'Bearer '+expected):
        abort(403)
    response=jsonify(status='ok',sessions_reconciled=reconcile_due())
    response.headers['Cache-Control']='no-store'
    return response
