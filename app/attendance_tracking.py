"""Attendance deadlines and milestones shared by Post and Quality control."""
import json
from datetime import datetime, time, timedelta, timezone
from app import db
from app import models as m


def now_utc():
    return datetime.now(timezone.utc)


def aware(value):
    return value.replace(tzinfo=timezone.utc) if value and value.tzinfo is None else value


def badge(due,complete,finished,now):
    status=('unknown' if not finished else 'met' if aware(finished)<=due else 'missed') if complete else 'overdue' if now>due else 'on-track'
    return dict(date=due.strftime('%d/%m/%Y'),due_at=due.isoformat(),status=status,
        label={'unknown':'Timing unavailable','met':'Deadline met','missed':'Deadline not met','overdue':'Deadline overdue','on-track':'Deadline on track'}[status])


def presentation(record,flow,value,window,now=None):
    from app.routes import LOCAL_TZ,argentina_add_business_days
    now=aware(now or now_utc()).astimezone(LOCAL_TZ)
    opens=datetime.combine(record.session_date+timedelta(days=1),time.min,tzinfo=LOCAL_TZ)
    closed=datetime.fromisoformat(window['expires_at']).astimezone(LOCAL_TZ)
    first_due=datetime.combine(argentina_add_business_days(record.session_date,1),time.max,tzinfo=LOCAL_TZ)
    review_due=datetime.combine(argentina_add_business_days(closed.date(),2),time.max,tzinfo=LOCAL_TZ)
    first_complete=bool(flow['records_enabled'] and value and value.verified and not flow.get('pending_supervisor_reviews') and (not flow['has_absences'] or flow['all_absence_notifications_sent']))
    complete=flow['attendance_progress']=='Completed'
    badges=[dict(stage='Records & notifications',**badge(first_due,first_complete,value.notifications_completed_at if value else None,now))]
    if flow['has_absences'] and (first_complete or value and value.review_completed_at):
        badges.append(dict(stage='Documentation review',**badge(review_due,complete,value.review_completed_at if value else None,now)))
    blocked=now<opens
    if complete:department='';action=''
    elif blocked:department='-';action='Exam session in progress'
    elif flow['submission_status']=='pending':department='ADMIN';action='Resolve Sinapsis issues with Supervisor and Logistics, if applicable'
    elif not flow['submission_status']:department='ADMIN';action='Verify attendance submission status in Sinapsis'
    elif not first_complete:department='ADMIN';action='Perform attendance review and notify institutions'
    elif now<closed:department='-';action='Awaiting absence documentation from institution'
    elif not flow['reviews_total']:department='ADMIN';action='Confirm no absence documentation was received'
    elif flow['reviews_completed']==flow['reviews_total']:department='ADMIN';action='Notify institutions of absence documentation review results'
    else:department='ADMIN';action='Review absence documentation'
    applicable=1 if flow['records_enabled'] and value and value.verified and not flow['has_absences'] else 3
    done=sum(step['status']=='completed' for step in flow['steps'].values())
    active_due=first_due if not first_complete or not flow['has_absences'] else review_due
    completed_at=(value.review_completed_at if flow['has_absences'] else value.notifications_completed_at) if complete and value else None
    review_start=max(closed,aware(value.notifications_completed_at).astimezone(LOCAL_TZ)) if value and value.notifications_completed_at and first_complete and flow['has_absences'] else None
    if review_start and review_start>now:review_start=None
    return dict(blocked=blocked,opens_at=opens.isoformat(),window_closed=now>=closed,
        controls_completed=done,controls_total=applicable,department=department,action=action,
        deadlines=badges,deadline_date=active_due.date(),overdue=any(item['status']=='overdue' for item in badges),
        waiting_external=bool(first_complete and flow['has_absences'] and now<closed),
        completed_at=aware(completed_at).isoformat() if completed_at else None,
        timing_stages=[dict(name='Records & notifications',started_at=aware(value.internal_started_at).isoformat() if value and value.internal_started_at else None,
            completed_at=aware(value.notifications_completed_at).isoformat() if value and value.notifications_completed_at else None,deadline=badges[0]),
            dict(name='Documentation review',started_at=review_start.isoformat() if review_start else None,completed_at=aware(value.review_completed_at).isoformat() if value and value.review_completed_at else None,
                deadline=dict(stage='Documentation review',**badge(review_due,complete,value.review_completed_at if value else None,now)))])


def sync_milestones(record,before,internal,action):
    from app.post_attendance import workflow_state,control
    value=control(record,True)
    after=workflow_state(record)
    flags=lambda flow:[flow['records_complete'],
        flow['records_complete'] and not flow.get('pending_supervisor_reviews') and (not flow['has_absences'] or flow['all_absence_notifications_sent']),
        flow['has_absences'] and flow['steps']['documentation']['status']=='completed']
    old,new=flags(before),flags(after)
    for field,previous,current in zip(['records_completed_at','notifications_completed_at','review_completed_at'],old,new):
        if action=='submission_status':continue
        if current and not previous:setattr(value,field,now_utc())
        elif not current:setattr(value,field,None)
    db.session.add(m.AttendanceEvent(exam_session_id=record.id,source='internal' if internal else 'institution',action=action,
        payload=json.dumps({'before':old,'after':new}),created_at=now_utc()))


def batch_presentations(records,today=None):
    """Bounded query batches, including when called by Quality control observers."""
    from collections import defaultdict
    from sqlalchemy.orm import load_only
    from app.post_attendance import ATTENDANCE_FORMATS, workflow_state
    from app.routes import LOCAL_TZ,journey_absence_upload_window
    records=[record for record in records if record.format in ATTENDANCE_FORMATS]
    if not records:return {}
    ids=[record.id for record in records]
    now=now_utc().astimezone(LOCAL_TZ)
    if today and today!=now.date():now=datetime.combine(today,time(hour=12),tzinfo=LOCAL_TZ)
    controls={item.exam_session_id:item for item in m.PostAttendance.query.filter(m.PostAttendance.exam_session_id.in_(ids)).all()}
    institutions=m.AttendanceInstitution.query.filter(m.AttendanceInstitution.exam_session_id.in_(ids)).all()
    by_session=defaultdict(list);by_institution=defaultdict(set);candidates=defaultdict(list)
    for item in institutions:by_session[item.exam_session_id].append(item)
    if institutions:
        for item in m.AttendanceModule.query.filter(m.AttendanceModule.institution_id.in_([i.id for i in institutions]),m.AttendanceModule.document_id.isnot(None)).all():by_institution[item.institution_id].add(item.module)
    for item in m.AbsenceCandidate.query.options(load_only(m.AbsenceCandidate.id,m.AbsenceCandidate.exam_session_id,m.AbsenceCandidate.document_id,m.AbsenceCandidate.review_status,m.AbsenceCandidate.component_reason,m.AbsenceCandidate.it_reason,m.AbsenceCandidate.institution_id,m.AbsenceCandidate.institution_name)).filter(m.AbsenceCandidate.exam_session_id.in_(ids)).all():candidates[item.exam_session_id].append(item)
    result={}
    for record in records:
        cards=[dict(id=str(i.id),main=i.is_main,sent=json.loads(i.notifications or '{}'),modules={'present':bool(by_institution[i.id]&set(record.modules_list()))}) for i in by_session[record.id]]
        window=journey_absence_upload_window(record,now=now)
        value=controls.get(record.id)
        flow=workflow_state(record,cards,candidates[record.id],window,attendance_control=value,today=now.date())
        result[record.id]=dict(flow=flow,tracking=presentation(record,flow,value,window,now=now),control=value,window=window)
    return result
