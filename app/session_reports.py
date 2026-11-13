"""Read-only, batch-loaded reports overview; full answers are loaded on demand."""
import json
from datetime import datetime
from sqlalchemy import extract
from sqlalchemy.orm import joinedload, load_only
from flask import abort, current_app, g, render_template, request, url_for
from app import db
from app import models as m
from app.exam_centre_feedback_text import QUESTIONS, OPEN_QUESTIONS
from app.staff_report_review import CRITERIA


def decoded(value):
    try:
        result = json.loads(value or '[]')
        return result if isinstance(result, list) else []
    except (ValueError, TypeError):
        return []


def author(report):
    if report.author_name:
        return report.author_name
    ref = report.submission.share.person_ref
    model = m.PotentialEntry if ref.startswith('potential:') else m.AcademicStaff
    person = db.session.get(model, int(ref.split(':')[-1])) if ref.split(':')[-1].isdigit() else None
    return person.full_name if person else 'Staff member'


def author_names(reports):
    names = {report.id: report.author_name for report in reports if report.author_name}
    missing = [report for report in reports if not report.author_name]
    if not missing:
        return names
    refs = dict(db.session.query(m.StaffExamSessionSubmission.id, m.StaffExamSessionsShare.person_ref)
                .join(m.StaffExamSessionsShare).filter(m.StaffExamSessionSubmission.id.in_([report.submission_id for report in missing])).all())
    people = {}
    for prefix,model in [('',m.AcademicStaff),('potential:',m.PotentialEntry)]:
        ids = [int(ref.split(':')[-1]) for ref in refs.values() if ref.startswith('potential:') == bool(prefix) and ref.split(':')[-1].isdigit()]
        if ids:
            people.update({prefix+str(ident):name for ident,name in db.session.query(model.id,model.full_name).filter(model.id.in_(ids)).all()})
    names.update({report.id:people.get(refs.get(report.submission_id),'Staff member') for report in missing})
    return names


def load_report_rows(year):
    from app.routes import LOCAL_TZ
    today = datetime.now(LOCAL_TZ).date()
    records = m.ExamSession.query.options(load_only(m.ExamSession.id,m.ExamSession.exam_session_name,m.ExamSession.session_date,m.ExamSession.format)).filter(
        extract('year',m.ExamSession.session_date)==year).order_by(m.ExamSession.session_date,m.ExamSession.exam_session_name,m.ExamSession.id).all()
    ids = [record.id for record in records]
    reports = m.StaffExamSessionReport.query.options(load_only(
        m.StaffExamSessionReport.id,m.StaffExamSessionReport.exam_session_id,m.StaffExamSessionReport.submission_id,
        m.StaffExamSessionReport.author_name,m.StaffExamSessionReport.author_person_ref,m.StaffExamSessionReport.submitted_at,
        m.StaffExamSessionReport.schedule_outcome,m.StaffExamSessionReport.facilities_outcome,m.StaffExamSessionReport.emergency_pack_outcome,
        m.StaffExamSessionReport.staff_assessments)).filter(m.StaffExamSessionReport.exam_session_id.in_(ids)).all() if ids else []
    feedbacks = m.ExamCentreFeedback.query.options(load_only(
        m.ExamCentreFeedback.id,m.ExamCentreFeedback.exam_session_id,m.ExamCentreFeedback.submitted_at,
        *[getattr(m.ExamCentreFeedback,key+'_score') for key,*_ in QUESTIONS]
    )).filter(m.ExamCentreFeedback.exam_session_id.in_(ids)).all() if ids else []
    supervisors = m.ExamSessionSupervisorAssignment.query.options(joinedload(m.ExamSessionSupervisorAssignment.team_member),joinedload(m.ExamSessionSupervisorAssignment.potential_entry)).filter(m.ExamSessionSupervisorAssignment.exam_session_id.in_(ids)).all() if ids else []
    by_session = {}
    for assignment in supervisors:
        by_session.setdefault(assignment.exam_session_id,[]).append(assignment)
    report_by_id = {item.exam_session_id:item for item in reports}
    names = author_names(reports)
    feedback_by_id = {item.exam_session_id:item for item in feedbacks}
    rows=[]
    for record in records:
        report,feedback = report_by_id.get(record.id),feedback_by_id.get(record.id)
        assignments=by_session.get(record.id,[])
        applicable = bool(report) or record.format=='Onsite' and (not assignments or any(not a.is_remote for a in assignments))
        past = record.session_date < today
        status = lambda saved, applies=True: 'Submitted' if saved else 'Not applicable' if not applies else 'Not submitted — exam date passed' if past else 'Pending'
        alerts=[]
        if not report and applicable and past: alerts.append('Supervisor report not submitted')
        if not feedback and past: alerts.append('Institution feedback not submitted')
        reviews=decoded(report.staff_assessments) if report else []
        if report:
            if report.schedule_outcome != 'There were no delays': alerts.append(report.schedule_outcome)
            if report.facilities_outcome != 'Satisfactory': alerts.append('Facilities: '+report.facilities_outcome)
            if report.emergency_pack_outcome != 'No, it was not needed': alerts.append('Emergency pack opened')
            concerning={'Too risky','Too doubtful','Not helpful','Needed guidance','Made mistakes','Not worn','Could improve','Inappropriate','Mother tongue','Unsatisfactory'}
            flagged=sum(any(value in concerning for value in row.get('criteria',{}).values()) for row in reviews)
            if flagged: alerts.append(f'{flagged} staff assessment(s) need attention')
        scores=[dict(key=key,label=title,value=getattr(feedback,key+'_score')) for key,title,*_ in QUESTIONS] if feedback else []
        low=[score['label'] for score in scores if score['value']<=7]
        alerts += [label+': score ≤ 7' for label in low]
        people=[]
        for assignment in assignments:
            person=assignment.team_member or assignment.potential_entry
            if not assignment.is_remote and person and person.full_name not in people: people.append(person.full_name)
        rows.append(dict(session=record,report=report,feedback=feedback,report_status=status(report,applicable),feedback_status=status(feedback),
            report_applicable=applicable,report_author=names[report.id] if report else '',supervisors=people,reviews_count=len(reviews),
            scores=scores,average=round(sum(score['value'] for score in scores)/4,1) if scores else None,
            alerts=alerts,complete=bool(feedback and (report or not applicable))))
    return rows


def render_index(year, years):
    from app.quality_control import FORMATS
    rows=load_report_rows(year)
    urls={key:url_for('quality_control.index',session_year=year,tab=key) for key in ('readiness','timing','reports')}
    response=current_app.make_response(render_template('session_reports.html',rows=rows,years=years,selected_year=year,formats=FORMATS,urls=urls))
    response.headers['Cache-Control']='private, no-store'
    return response


def render_detail(session_id):
    if not getattr(getattr(g,'current_user',None),'is_superadmin',False): abort(403)
    record=db.session.get(m.ExamSession,session_id)
    if not record: abort(404)
    reports=m.StaffExamSessionReport.query.join(m.StaffExamSessionSubmission).filter(m.StaffExamSessionSubmission.exam_session_id==record.id).order_by(m.StaffExamSessionReport.id).all()
    report_views=[]
    for report in reports:
        file_ids=decoded(report.marketing_media)
        files=m.StaffSessionReportMedia.query.filter(m.StaffSessionReportMedia.file_id.in_(file_ids)).all() if file_ids else []
        report_views.append(dict(record=report,author=author(report),reviews=decoded(report.staff_assessments),return_steps=decoded(report.return_verification),files=files,historical=report.exam_session_id is None))
    feedback=m.ExamCentreFeedback.query.filter_by(exam_session_id=record.id).first()
    response=current_app.make_response(render_template('_session_reports_detail.html',session_record=record,reports=report_views,feedback=feedback,criteria=CRITERIA,questions=QUESTIONS,open_questions=OPEN_QUESTIONS))
    response.headers['Cache-Control']='private, no-store'
    return response
