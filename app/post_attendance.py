"""Shared onsite and online post-session attendance and absence management."""
import hashlib
import json
import re
import secrets
from datetime import datetime, timezone
from decimal import Decimal
from flask import Blueprint, abort, jsonify, render_template, request, session, url_for, current_app
from sqlalchemy import extract
from sqlalchemy.orm import joinedload, load_only
from app import db, login_required, validate_csrf
from app import models as m
from app import attendance_drive as drive

attendance_bp=Blueprint('attendance',__name__)
CURRENCIES=['ARS','EUR','GBP','USD','UYU']
SPEAKING_EXAMS=['Ready','Steady','Go!','SPA level 1','SPA level 2','SPA level 3']
EXAMS=SPEAKING_EXAMS+['A1- Entry','A1 Access','A1+ Achiever','A2 Preliminary','A2+ Elementary','B1 Progress','B1+ Onwards','B2 Competency','B2+ Forward','C1 | C1+ | C2 Multi-level Proficiency Test']
ONLINE_FORMATS = {'Online', 'Online at exam centre'}
ATTENDANCE_FORMATS = {'Onsite', *ONLINE_FORMATS}
PLACEHOLDERS={'next_july_online':'July - Online - Next year','next_novdec_online':'Nov/Dec - Online - Next year','next_novdec_onsite':'Nov/Dec - Onsite - Next year'}


def local_today():
    from app.routes import LOCAL_TZ
    return datetime.now(LOCAL_TZ).date()


def modules(record):
    return [module for module in ['Speaking','Listening and speaking','Reading and writing'] if module in record.modules_list()]


def exam_modules(exam):
    if exam not in EXAMS:return []
    return ['Speaking'] if exam in SPEAKING_EXAMS else ['Listening and speaking','Reading and writing']


def absence_cards(record):
    institutions=m.AttendanceInstitution.query.filter_by(exam_session_id=record.id).all()
    rows=m.AttendanceModule.query.filter(m.AttendanceModule.institution_id.in_([item.id for item in institutions]),m.AttendanceModule.document_id.isnot(None)).all() if institutions else []
    present={(item.institution_id,item.module) for item in rows}
    return [dict(id=str(item.id),name=record.exam_session_name if item.is_main else item.name,
        modules={module:(item.id,module) in present for module in modules(record)}) for item in institutions]


def absence_choices(record,name,cards=None):
    cards=absence_cards(record) if cards is None else cards
    matches=[card for card in cards if institution_key(card['name'])==institution_key(name)] if name.strip() else []
    if len(matches)!=1:return dict(institution_id=None,modules=[],exams=[],reason='Match Institution to one Absence records card before choosing an exam.')
    card=matches[0]
    allowed=[module for module in modules(record) if card['modules'].get(module)]
    return dict(institution_id=card['id'],modules=allowed,exams=[exam for exam in EXAMS if set(exam_modules(exam))&set(allowed)],
        reason='' if allowed else 'No absent modules with an uploaded list are recorded for this institution.')


def has_report_evidence(candidate):
    return bool(candidate.component_reason or candidate.it_reason)


def candidate_exam_modules(candidate):
    values = exam_modules(candidate.exam)
    if candidate.component_reason:
        values = list(dict.fromkeys(values + ['Listening', 'Speaking']))
    return values


def candidate_choices(record, candidate, cards=None):
    choices = absence_choices(record, candidate.institution_name, cards)
    if has_report_evidence(candidate) and record.format == 'Online' and choices['institution_id']:
        choices = dict(institution_id=choices['institution_id'], modules=list(dict.fromkeys(choices['modules'] +
            [module for module in json.loads(candidate.absent_modules or '[]') if module in modules(record)] +
            (["Listening", "Speaking"] if candidate.component_reason else []) + [module for module in candidate_exam_modules(candidate) if module in modules(record)])),
            exams=[exam for exam in EXAMS if set(exam_modules(exam)) & set(modules(record)) or candidate.component_reason], reason='')
    return choices


def reconcile_absence_candidates(record):
    cards=absence_cards(record)
    changed=False
    for candidate in m.AbsenceCandidate.query.filter_by(exam_session_id=record.id).all():
        choices=candidate_choices(record,candidate,cards)
        if choices['institution_id']:candidate.institution_id=int(choices['institution_id'])
        allowed=set(choices['modules'])&set(candidate_exam_modules(candidate))
        selected=json.loads(candidate.absent_modules or '[]')
        remaining=[module for module in selected if module in allowed]
        invalid=bool(candidate.exam and candidate.exam not in choices['exams'])
        if invalid or remaining!=selected:
            if invalid:candidate.exam=''
            candidate.absent_modules=json.dumps([] if invalid else remaining)
            reset_review(candidate);changed=True
    if changed:
        value=control(record,True);value.review_results_notified=False;value.review_completed_at=None
    return changed


def credit_exempt_session_id(record):
    latest=(m.ExamSession.query.filter(extract('year',m.ExamSession.session_date)==record.session_date.year)
        .order_by(m.ExamSession.session_date.desc(),m.ExamSession.id.desc()).first())
    return latest.id if latest else None


def credit_applicable(record,selection):
    last_id=credit_exempt_session_id(record)
    return not (last_id and str(last_id)==str(selection))


def credit_values(amount,currency,applicable,required=False):
    if not applicable:return '',None
    amount=(amount or '').replace(',','.').strip()
    currency=(currency or '').strip()
    if currency and currency not in CURRENCIES:raise ValueError('Choose a valid currency.')
    if required and (not amount or currency not in CURRENCIES):raise ValueError('Complete Credit balance with currency and amount before confirming.')
    if not amount:return currency,None
    if not re.fullmatch(r'\d{1,14}(?:\.\d{1,2})?',amount):raise ValueError('Enter a non-negative amount with up to two decimals.')
    return currency,Decimal(amount)


def candidate_credit_applicable(candidate):
    record=db.session.get(m.ExamSession,candidate.exam_session_id)
    return credit_applicable(record,candidate.rescheduled_for or candidate.requested_rescheduled_for)


def candidate_ready(candidate,credit_enabled=None,choices=None):
    if credit_enabled is None:credit_enabled=candidate_credit_applicable(candidate)
    absent=json.loads(candidate.absent_modules or '[]')
    choices=choices if choices is not None else candidate_choices(db.session.get(m.ExamSession,candidate.exam_session_id),candidate)
    return bool(candidate.exam in choices['exams'] and absent and all(module in candidate_exam_modules(candidate) and module in choices['modules'] for module in absent) and (not credit_enabled or (candidate.currency in CURRENCIES and candidate.credit_balance is not None)))


def reset_review(candidate):
    candidate.review_status='Pending';candidate.approved=False;candidate.decline_reason=''


def candidate_whatsapp_message(candidate,credit_enabled=None,language='en',choices=None):
    if candidate.review_status not in {'Confirmed','Declined'}:return ''
    if credit_enabled is None and candidate.review_status=='Confirmed':credit_enabled=candidate_credit_applicable(candidate)
    if candidate.review_status=='Confirmed' and not candidate_ready(candidate,credit_enabled,choices):return ''
    if language=='es':
        lines=[f'- *Estado:* {"Confirmado" if candidate.review_status=="Confirmed" else "Rechazado"}',f'- *Número de candidato:* {candidate.number}',f'- *Nombre del candidato:* {candidate.name}']
        if candidate.review_status=='Confirmed':
            lines.append(f'- *Fecha del examen reprogramado:* {requested_date_label(candidate,language="es")}')
            if credit_enabled:
                amount=f'{candidate.credit_balance:,.2f}'.translate(str.maketrans({',':'.','.':','}))
                lines.append(f'- *Saldo a favor:* {candidate.currency} {amount}')
            paragraphs=['Confirmamos que la documentación presentada para justificar la ausencia de este candidato ha sido *revisada y aprobada por Path Examinations*.',
                'La ausencia se considera justificada y *el candidato ha sido reprogramado para la sesión de examen seleccionada*.']
        else:
            paragraphs=['Confirmamos que la documentación presentada para justificar la ausencia de este candidato ha sido revisada. Lamentablemente, *la solicitud no ha sido aprobada*, ya que la documentación no cumple con los requisitos establecidos.',
                'Por lo tanto, la ausencia del candidato continuará registrada como Ausente.']
        return '\n'.join(lines)+'\n\n'+'\n\n'.join(paragraphs)+'\n\n*Path International Examinations*'
    lines=[f'- *Status:* {candidate.review_status}',f'- *Candidate number:* {candidate.number}',f'- *Candidate name:* {candidate.name}']
    if candidate.review_status=='Confirmed':
        lines.append(f'- *Rescheduled exam date:* {requested_date_label(candidate)}')
        if credit_enabled:lines.append(f'- *Credit balance:* {candidate.currency} {candidate.credit_balance:,.2f}')
        paragraphs=["We confirm that the supporting documentation submitted for this candidate's absence has been *reviewed and approved by Path Examinations*.",
            'The absence is now considered justified, and *the candidate has been rescheduled for the selected exam session*.']
    else:
        paragraphs=["We confirm that the supporting documentation submitted for this candidate's absence has been reviewed. Unfortunately, *the request has not been approved*, as the documentation does not meet the established requirements.",
            "The candidate's absence will therefore remain recorded as Absent."]
    return '\n'.join(lines)+'\n\n'+'\n\n'.join(paragraphs)+'\n\n*Path International Examinations*'


def institution_key(name):
    return ' '.join((name or '').split()).casefold()


def institutional_journey_link(record):
    from app.routes import monthly_unified_total_session_ids
    share=(m.ExamSessionJourneyShare.query.filter(m.ExamSessionJourneyShare.exam_session_id.in_(monthly_unified_total_session_ids(record)),
        m.ExamSessionJourneyShare.audience=='institution',m.ExamSessionJourneyShare.is_enabled.is_(True),m.ExamSessionJourneyShare.revoked_at.is_(None))
        .order_by((m.ExamSessionJourneyShare.exam_session_id==record.id).desc(),m.ExamSessionJourneyShare.id.desc()).first())
    return url_for('staff.shared_path_session_journey',token=share.token,audience='institution',_external=True) if share else ''


def approved_group_message(record,candidates,credits,last_id,language):
    from app.attendance_notifications import MONTHS_EN,MONTHS_ES
    from app.routes import argentina_subtract_business_days
    spanish=language=='es'
    def date_label(value):
        return f'{value.day} de {MONTHS_ES[value.month-1]} de {value.year}' if spanish else f'{value.day} {MONTHS_EN[value.month-1]} {value.year}'
    selected={candidate.id:candidate.rescheduled_for or candidate.requested_rescheduled_for for candidate in candidates}
    ids={int(value) for value in selected.values() if value and value.isdigit()}
    sessions={item.id:item for item in m.ExamSession.query.filter(m.ExamSession.id.in_(ids)).all()} if ids else {}
    blocks=[]
    for index,candidate in enumerate(candidates,1):
        value=selected[candidate.id]
        target=sessions.get(int(value)) if value and value.isdigit() else None
        name=target.exam_session_name if target else requested_date_label(candidate,language=language)
        date=date_label(target.session_date) if target and target.session_date else 'Fecha a confirmar' if spanish else 'Date to be confirmed'
        exam_time='A confirmar el próximo año' if spanish else 'To be confirmed next year'
        if target and target.session_date and target.id==last_id:
            due=date_label(argentina_subtract_business_days(target.session_date,4))
            exam_time=f'A confirmar a más tardar el {due}' if spanish else f'To be confirmed by {due}'
        labels=['Número de candidato','Nombre del candidato','Sesión de examen reprogramada','Fecha del examen reprogramado','Horario del examen'] if spanish else ['Candidate number','Candidate name','Rescheduled exam session','Rescheduled exam date','Exam time']
        lines=[f'*{index}. {labels[0]}:* {candidate.number}',f'*{labels[1]}:* {candidate.name}',
            f'*{labels[2]}:* {name}',f'*{labels[3]}:* {date}',f'*{labels[4]}:* {exam_time}']
        if credits[candidate.id]:
            amount=f'{candidate.credit_balance:,.2f}'
            if spanish:amount=amount.translate(str.maketrans({',':'.','.':','}))
            lines.append(f'*{"Saldo a favor" if spanish else "Credit balance"}:* {candidate.currency} {amount}')
        blocks.append('\n'.join(lines))
    count=len(candidates)
    same=len(set(selected.values()))==1
    if spanish:
        intro=f'Confirmamos que la documentación presentada para justificar {"la ausencia del siguiente candidato" if count==1 else "las ausencias de los siguientes candidatos"} de la sesión de examen *{record.exam_session_name}*, realizada el *{date_label(record.session_date)}*, ha sido *revisada y aprobada por Path Examinations*.'
        quantity={2:'dos',3:'tres',4:'cuatro',5:'cinco',6:'seis',7:'siete',8:'ocho',9:'nueve',10:'diez'}.get(count,str(count))
        target='la sesión de examen indicada anteriormente' if same else 'las sesiones de examen indicadas para cada candidato'
        closing=f'La ausencia se considera justificada y *el candidato ha sido reprogramado correctamente para {target}*.' if count==1 else f'Las ausencias se consideran justificadas y *los {quantity} candidatos han sido reprogramados correctamente para {target}*.'
        return '\n\n'.join(['¡Hola!','Esperamos que se encuentren bien. 😊',intro,'\n\n'.join(blocks),closing,'Si tienen alguna consulta, no duden en contactarnos.','Gracias,\nBrenda\n*Path International Examinations*'])
    intro=f'We confirm that the supporting documentation submitted for the {"absence of the following candidate" if count==1 else "absences of the following candidates"} from the *{record.exam_session_name}* examination session, held on *{date_label(record.session_date)}*, has been *reviewed and approved by Path Examinations*.'
    quantity={2:'two',3:'three',4:'four',5:'five',6:'six',7:'seven',8:'eight',9:'nine',10:'ten'}.get(count,str(count))
    target='the examination session indicated above' if same else 'the examination sessions indicated for each candidate above'
    subject='both candidates' if count==2 else f'all {quantity} candidates'
    closing=f'This candidate’s absence is now considered justified, and *the candidate has been successfully rescheduled for {target}*.' if count==1 else f'Their absences are now considered justified, and *{subject} have been successfully rescheduled for {target}*.'
    return '\n\n'.join(['Hello!',"We hope you're well. 😊",intro,'\n\n'.join(blocks),closing,'If you have any questions, please let us know!','Thanks,\nBrenda\n*Path International Examinations*'])


def grouped_whatsapp_message(record,candidates,language='en'):
    if language not in {'en','es'}:raise ValueError('Select Spanish or English.')
    if not candidates:raise ValueError('Select at least one candidate.')
    statuses={candidate.review_status for candidate in candidates}
    institutions={institution_key(candidate.institution_name) for candidate in candidates}
    if len(statuses)!=1 or not statuses.issubset({'Confirmed','Declined'}):raise ValueError('Select candidates with the same Confirmed or Declined status.')
    if len(institutions)!=1 or '' in institutions:raise ValueError('Select candidates from one institution with a completed institution name.')
    if any(candidate.exam_session_id!=record.id for candidate in candidates):raise ValueError('All candidates must belong to this exam session.')
    status=candidates[0].review_status
    last_id=credit_exempt_session_id(record)
    credits={candidate.id:str(candidate.rescheduled_for or candidate.requested_rescheduled_for)!=str(last_id) for candidate in candidates}
    cards=absence_cards(record)
    if status=='Confirmed' and any(not candidate_ready(candidate,credits[candidate.id],candidate_choices(record,candidate,cards)) for candidate in candidates):raise ValueError('Complete all required candidate and Credit balance fields before copying.')
    if status=='Confirmed':return approved_group_message(record,candidates,credits,last_id,language)
    blocks=[]
    for index,candidate in enumerate(candidates,1):
        lines=[f'{index}. *Candidate number:* {candidate.number}',f'   *Candidate name:* {candidate.name}']
        if language=='es':lines=[f'{index}. *Número de candidato:* {candidate.number}',f'   *Nombre del candidato:* {candidate.name}']
        blocks.append('\n'.join(lines))
    journey=institutional_journey_link(record)
    if not journey:raise ValueError('Enable the institutional Exam session journey for this session before copying the declined message.')
    intro='We confirm that the supporting documentation submitted for the absences of the candidates listed below has been reviewed. Unfortunately, *the requests have not been approved*, as the documentation does not meet the established requirements.'
    closing="The candidates' absences will therefore remain recorded as Absent.\n\nThe reasons for the rejection can be viewed in the corresponding *_Exam session journey_*: "+journey
    if language=='es':
        intro='Confirmamos que la documentación presentada para justificar las ausencias de los candidatos que se detallan a continuación ha sido revisada. Lamentablemente, *las solicitudes no han sido aprobadas*, ya que la documentación no cumple con los requisitos establecidos.'
        closing='Por lo tanto, las ausencias de los candidatos continuarán registradas como Ausente.\n\nLos motivos del rechazo pueden consultarse en el correspondiente *_Exam session journey_*: '+journey
    greeting=['¡Hola!','Esperamos que se encuentren bien. 😊'] if language=='es' else ['Hello!',"We hope you're well. 😊"]
    invitation='Si tienen alguna consulta, no duden en contactarnos.' if language=='es' else 'If you have any questions, please let us know!'
    signature='Gracias,\nBrenda\n*Path International Examinations*' if language=='es' else 'Thanks,\nBrenda\n*Path International Examinations*'
    return '\n\n'.join(greeting+[intro,'\n\n'.join(blocks),closing,invitation,signature])



@attendance_bp.post('/pre-session-control-tower/post/sessions/<int:session_id>/absence-message')
@login_required
def grouped_message(session_id):
    from app.routes import require_menu_view
    require_menu_view('pre_session_control_tower')
    if not validate_csrf():return jsonify(ok=False,error='Security token expired. Reload the page.'),400
    record=db.session.get(m.ExamSession,session_id)
    if not record or record.format not in ATTENDANCE_FORMATS or not record.session_date or record.session_date>local_today():abort(404)
    raw=request.form.getlist('candidate_ids')
    if not raw or any(not value.isdigit() for value in raw):return jsonify(ok=False,error='Select at least one valid candidate.'),400
    ids={int(value) for value in raw}
    candidates=m.AbsenceCandidate.query.filter(m.AbsenceCandidate.exam_session_id==record.id,m.AbsenceCandidate.id.in_(ids)).order_by(m.AbsenceCandidate.id).all()
    if len(candidates)!=len(ids):abort(404)
    if not workflow_state(record)['review_allowed']:return jsonify(ok=False,error='Review notifications are available only after all absence notifications are Sent and the institution submission window has closed.'),400
    try:message=grouped_whatsapp_message(record,candidates,language=request.form.get('language','en'))
    except ValueError as error:return jsonify(ok=False,error=str(error)),400
    return jsonify(ok=True,message=message)


def requested_date_label(candidate,language='en'):
    value=candidate.rescheduled_for or candidate.requested_rescheduled_for
    labels=({'next_july_online':'Julio, próximo año | Online | Solo certificado digital','next_novdec_online':'Nov/Dic, próximo año | Online','next_novdec_onsite':'Nov/Dic, próximo año | Presencial'} if language=='es' else {'next_july_online':'July, next year | Online | Digital certificate only','next_novdec_online':'Nov/Dec, next year | Online','next_novdec_onsite':'Nov/Dec, next year | Onsite'})
    if value in labels:return labels[value]
    record=db.session.get(m.ExamSession,int(value)) if value and value.isdigit() else None
    return f'{record.exam_session_name} · {record.session_date:%d/%m/%Y}' if record and record.session_date else ('La sesión ya no está disponible' if language=='es' else 'Session no longer available') if value else ('Sin seleccionar' if language=='es' else 'Not selected')


def contacts(record):
    return [dict(item,key=hashlib.sha256(json.dumps(item,sort_keys=True).encode()).hexdigest()[:20],name=item['full_name'] or item['email'] or item['phone']) for item in record.contact_points_list()]


def lock_session(record):
    if db.engine.dialect.name=='sqlite':
        connection=db.session.connection()
        if not connection.connection.driver_connection.in_transaction:connection.exec_driver_sql('BEGIN IMMEDIATE')
    db.session.query(m.ExamSession.id).filter_by(id=record.id).with_for_update().first()


def control(record,create=False):
    value=db.session.get(m.PostAttendance,record.id)
    if value is None and create:
        value=m.PostAttendance(exam_session_id=record.id);db.session.add(value);db.session.flush()
    return value


def main_institution(record,create=False):
    item=m.AttendanceInstitution.query.filter_by(exam_session_id=record.id,is_main=True).first()
    if item is None and create:
        item=m.AttendanceInstitution(exam_session_id=record.id,name=record.exam_session_name,is_main=True)
        db.session.add(item);db.session.flush()
    return item


def touch(record,institution=None,reset=False,internal=True):
    from app.attendance_tracking import now_utc
    value=control(record,True)
    if internal and not value.internal_activity:value.internal_activity=True;value.internal_started_at=now_utc()
    value.revision+=1;value.updated_at=datetime.now(timezone.utc)
    if reset:
        value.verified=False
        value.review_results_notified=False
        value.no_documentation_received=False
        if institution:institution.notifications='{}'
    return value


def institution_for(record,raw):
    if str(raw)=='main':return main_institution(record,True)
    item=db.session.get(m.AttendanceInstitution,int(raw)) if str(raw).isdigit() else None
    if not item or item.exam_session_id!=record.id:abort(404)
    return item


def reschedule_options(record):
    rows=m.ExamSession.query.filter(m.ExamSession.session_date>local_today()).order_by(m.ExamSession.session_date,m.ExamSession.exam_session_name,m.ExamSession.id).all()
    options=[{'value':str(item.id),'label':f'{item.exam_session_name} · {item.session_date:%d/%m/%Y} · {item.format}'} for item in rows]
    same_year=[item for item in rows if item.session_date.year==record.session_date.year]
    default=str(same_year[-1].id) if same_year else 'next_july_online'
    return options+[{'value':key,'label':label} for key,label in PLACEHOLDERS.items()],default


def document_data(document,record):
    return {'id':document.file_id,'filename':document.filename,'url':url_for('attendance.document',session_id=record.id,file_id=document.file_id)} if document else None


WORKFLOW_CONTROL_UNSET=object()


def workflow_state(record,cards=None,candidates=None,window=None,attendance_control=WORKFLOW_CONTROL_UNSET,today=None):
    from app.routes import journey_absence_upload_window
    value=control(record) if attendance_control is WORKFLOW_CONTROL_UNSET else attendance_control
    if cards is None:
        institutions=m.AttendanceInstitution.query.filter_by(exam_session_id=record.id).all()
        rows=m.AttendanceModule.query.filter(m.AttendanceModule.institution_id.in_([item.id for item in institutions]),m.AttendanceModule.module.in_(modules(record)),m.AttendanceModule.document_id.isnot(None)).all() if institutions else []
        absent_ids={row.institution_id for row in rows}
        cards=[dict(id=str(item.id),main=item.is_main,sent=json.loads(item.notifications or '{}'),modules={'present':item.id in absent_ids}) for item in institutions]
    if candidates is None:candidates=m.AbsenceCandidate.query.filter_by(exam_session_id=record.id).all()
    window=window or journey_absence_upload_window(record)
    reported_institutions = {str(candidate.institution_id) for candidate in candidates if has_report_evidence(candidate)}
    absent_cards=[card for card in cards if any(card['modules'].values()) or str(card.get('id')) in reported_institutions]
    has_absences=bool(absent_cards)
    unblocked=(today or local_today())>record.session_date
    records_enabled=bool(unblocked and value and value.submission_status=='completed')
    notifications_enabled=bool(records_enabled and has_absences and value and value.verified)
    contact_keys=[contact['key'] for contact in contacts(record)]
    all_sent=has_absences
    notification_total=0;notification_sent=0;missing_contacts=False
    for card in absent_cards:
        keys=contact_keys if card['main'] else ['external']
        notification_total+=len(keys);notification_sent+=sum(card['sent'].get(key) is True for key in keys)
        if not keys:missing_contacts=True
        if not keys or not all(card['sent'].get(key) is True for key in keys):all_sent=False
    documentation_enabled=bool(notifications_enabled and all_sent)
    review_allowed=bool(documentation_enabled and window['state']=='expired')
    results_enabled=bool(review_allowed and candidates and all((candidate.document_id or has_report_evidence(candidate)) and candidate.review_status in {'Confirmed','Declined'} for candidate in candidates))
    records_completed=bool(records_enabled and value and value.verified)
    notifications_completed=bool(notifications_enabled and all_sent)
    no_documents_enabled=bool(review_allowed and not candidates)
    documentation_completed=bool(value and (results_enabled and value.review_results_notified or no_documents_enabled and value.no_documentation_received))
    reviewed=sum(candidate.review_status in {'Confirmed','Declined'} for candidate in candidates)
    not_applicable=records_completed and not has_absences
    records_status='locked' if not records_enabled else 'completed' if records_completed else 'in_progress' if value and value.internal_activity else 'ready'
    notifications_status='not_applicable' if not_applicable else 'locked' if not notifications_enabled else 'completed' if notifications_completed else 'in_progress' if notification_sent else 'ready'
    documentation_status='not_applicable' if not_applicable else 'locked' if not documentation_enabled else 'completed' if documentation_completed else 'in_progress' if candidates else 'ready'
    labels={'completed':'Completed','in_progress':'In progress','ready':'Ready','locked':'Locked','not_applicable':'Not applicable'}
    notification_detail='No absences recorded.' if not_applicable else 'Verify the absence records first.' if not notifications_enabled else 'Configure contact points before completing notifications.' if missing_contacts else f'Notifications sent: {notification_sent}/{notification_total}'
    documentation_detail='No absences recorded.' if not_applicable else 'Verify the absence records first.' if not records_completed else 'Mark every applicable Sent checkbox to enable this step.' if not documentation_enabled else f'Reviews completed: {reviewed}/{len(candidates)}'
    if documentation_completed and not candidates:documentation_detail='No absence documentation received — confirmed.'
    steps={'records':dict(status=records_status,label=labels[records_status],detail='Absence records verified.' if records_completed else 'Complete the records and verify them in Sinapsis.'),
        'notifications':dict(status=notifications_status,label=labels[notifications_status],detail=notification_detail),
        'documentation':dict(status=documentation_status,label=labels[documentation_status],detail=documentation_detail)}
    progress='Completed' if unblocked and (not_applicable or records_completed and notifications_completed and documentation_completed) else 'In progress' if value and value.internal_activity else 'Not started'
    return dict(records_enabled=records_enabled,submission_status=value.submission_status if value else '',notifications_enabled=notifications_enabled,documentation_enabled=documentation_enabled,review_allowed=review_allowed,
        records_complete=records_completed,no_documentation_confirmation_enabled=no_documents_enabled,results_notification_enabled=results_enabled,all_absence_notifications_sent=bool(all_sent),has_absences=has_absences,steps=steps,attendance_progress=progress,
        notifications_sent=notification_sent,notifications_total=notification_total,reviews_completed=reviewed,reviews_total=len(candidates))


def attendance_presentation(record,flow,value,window):
    from app.attendance_tracking import presentation
    return presentation(record,flow,value,window)


def state(record):
    from app.routes import journey_absence_upload_window,monthly_unified_total_session_ids,user_can_edit
    value=control(record)
    institutions=m.AttendanceInstitution.query.filter_by(exam_session_id=record.id).order_by(m.AttendanceInstitution.is_main.desc(),m.AttendanceInstitution.id).all()
    module_rows=m.AttendanceModule.query.options(joinedload(m.AttendanceModule.document)).filter(m.AttendanceModule.institution_id.in_([item.id for item in institutions])).all() if institutions else []
    documents={(item.institution_id,item.module):item.document for item in module_rows}
    cards=[{'id':str(item.id),'name':record.exam_session_name if item.is_main else item.name,'main':item.is_main,
            'modules':{module:document_data(documents.get((item.id,module)),record) for module in modules(record)},'sent':json.loads(item.notifications or '{}')} for item in institutions]
    if not any(card['main'] for card in cards):cards.insert(0,{'id':'main','name':record.exam_session_name,'main':True,'modules':{module:None for module in modules(record)},'sent':{}})
    candidates=m.AbsenceCandidate.query.options(joinedload(m.AbsenceCandidate.document)).filter_by(exam_session_id=record.id).order_by(m.AbsenceCandidate.id).all()
    reported_institutions = {str(candidate.institution_id) for candidate in candidates if has_report_evidence(candidate)}
    for card in cards:
        card['reported_absence'] = card['id'] in reported_institutions
    options,default=reschedule_options(record)
    from app.absence_submissions import institutional_reschedule_options
    internal_options=institutional_reschedule_options(record)
    last_id=credit_exempt_session_id(record)
    candidate_rows=[]
    for candidate in candidates:
        choices=candidate_choices(record,candidate,cards)
        absent=json.loads(candidate.absent_modules or '[]')
        credit_enabled=str(candidate.rescheduled_for or candidate.requested_rescheduled_for)!=str(last_id)
        candidate_rows.append(dict(id=candidate.id,number=candidate.number,name=candidate.name,exam=candidate.exam,institution_id=str(candidate.institution_id),
            modules=absent,approved=candidate.review_status=='Confirmed',review_status=candidate.review_status,decline_reason=candidate.decline_reason,institution_name=candidate.institution_name,institution_key=institution_key(candidate.institution_name),allowed_modules=[module for module in candidate_exam_modules(candidate) if module in choices['modules']],allowed_exams=choices['exams'],selection_hint=choices['reason'],rescheduled_label=requested_date_label(candidate),notes=candidate.notes,rescheduled_for=candidate.rescheduled_for or default,
            whatsapp_message=candidate_whatsapp_message(candidate,credit_enabled,choices=choices),whatsapp_message_es=candidate_whatsapp_message(candidate,credit_enabled,language='es',choices=choices),currency=candidate.currency if credit_enabled else '',credit_balance=str(candidate.credit_balance) if credit_enabled and candidate.credit_balance is not None else '',credit_applicable=credit_enabled,
            component_reason=candidate.component_reason,it_reason=candidate.it_reason,document=document_data(candidate.document,record),actionable=bool(candidate.review_status=='Confirmed' and candidate_ready(candidate,credit_enabled,choices))))
    window=journey_absence_upload_window(record)
    flow=workflow_state(record,cards,candidates,window)
    from app.attendance_notifications import decorate_notifications
    concat_ids=monthly_unified_total_session_ids(record)-{record.id}
    decorate_notifications(record,cards,contacts(record),concat_ids|{record.id})
    concatenated=[{'id':item.id,'name':item.exam_session_name,'date':item.session_date.strftime('%d/%m/%Y')} for item in m.ExamSession.query.filter(m.ExamSession.id.in_(concat_ids)).order_by(m.ExamSession.session_date).all()] if concat_ids else []
    return dict(id=record.id,name=record.exam_session_name,date=record.session_date.strftime('%d/%m/%Y'),format=record.format,
        enabled=local_today()>record.session_date,**flow,progress=flow['attendance_progress'],revision=value.revision if value else 0,
        verified=bool(value and value.verified),review_results_notified=bool(value and value.review_results_notified and flow['results_notification_enabled']),modules=modules(record),institutions=cards,candidates=candidate_rows,contacts=contacts(record),
        window=window,
        documentation_url=record.absence_documentation_folder_url or '',reschedule_options=options,reschedule_default=default,currencies=CURRENCIES,exams=EXAMS,exam_module_options={exam:exam_modules(exam) for exam in EXAMS},internal_reschedule_options=internal_options,credit_exempt_options=[item['value'] for item in internal_options if item['value']==str(last_id)],concatenated=concatenated,
        tracking=attendance_presentation(record,flow,value,window),
        no_documentation_received=bool(value and value.no_documentation_received),can_edit=user_can_edit('pre_session_control_tower'))


def render_index(online=False):
    from app.routes import selected_exam_session_year,require_menu_view
    require_menu_view('pre_session_control_tower')
    year,years=selected_exam_session_year()
    formats = ONLINE_FORMATS if online else {'Onsite'}
    records=m.ExamSession.query.filter(m.ExamSession.format.in_(formats),m.ExamSession.session_date<=local_today(),extract('year',m.ExamSession.session_date)==year).order_by(m.ExamSession.session_date.desc(),m.ExamSession.exam_session_name).all()
    values={item.exam_session_id:item for item in m.PostAttendance.query.filter(m.PostAttendance.exam_session_id.in_([r.id for r in records])).all()} if records else {}
    ids=[record.id for record in records]
    institutions=m.AttendanceInstitution.query.filter(m.AttendanceInstitution.exam_session_id.in_(ids)).all() if ids else []
    module_rows=m.AttendanceModule.query.filter(m.AttendanceModule.institution_id.in_([item.id for item in institutions]),m.AttendanceModule.document_id.isnot(None)).all() if institutions else []
    by_institution={}
    for item in module_rows:by_institution.setdefault(item.institution_id,set()).add(item.module)
    by_session={}
    for candidate in m.AbsenceCandidate.query.options(load_only(m.AbsenceCandidate.id,m.AbsenceCandidate.exam_session_id,m.AbsenceCandidate.document_id,m.AbsenceCandidate.review_status,m.AbsenceCandidate.component_reason,m.AbsenceCandidate.it_reason,m.AbsenceCandidate.institution_id)).filter(m.AbsenceCandidate.exam_session_id.in_(ids)).all() if ids else []:by_session.setdefault(candidate.exam_session_id,[]).append(candidate)
    cards_by_session={}
    for item in institutions:cards_by_session.setdefault(item.exam_session_id,[]).append(item)
    progress={}
    for record in records:
        cards=[dict(id=str(item.id),main=item.is_main,sent=json.loads(item.notifications or '{}'),modules={'present':bool(by_institution.get(item.id,set())&set(modules(record)))}) for item in cards_by_session.get(record.id,[])]
        flow=workflow_state(record,cards,by_session.get(record.id,[]),attendance_control=values.get(record.id))
        from app.routes import journey_absence_upload_window
        progress[record.id]=dict(progress=flow['attendance_progress'],**attendance_presentation(record,flow,values.get(record.id),journey_absence_upload_window(record)))
    from app.routes import exam_session_concat_component_map
    components=exam_session_concat_component_map()
    peers={item.id:item for item in m.ExamSession.query.filter(m.ExamSession.id.in_(set().union(*(components.get(r.id,set()) for r in records)))).all()} if records else {}
    response=current_app.make_response(render_template('post_attendance.html',is_online_tower=online,tower_title='Online session control tower' if online else 'Onsite session control tower',tower_endpoint='staff.pre_online_session_control_tower' if online else 'staff.pre_session_control_tower',records=records,controls=values,progress_by_session=progress,selected_year=year,years=years,today=local_today(),
        components=components,peers=peers,csrf_token=session.setdefault('csrf_token',secrets.token_hex(32))))
    response.headers['Cache-Control']='private, no-store'
    return response


@attendance_bp.route('/pre-session-control-tower/post/sessions/<int:session_id>/attendance',methods=['GET','POST'])
@login_required
def manage(session_id):
    from app.routes import require_menu_view,require_menu_edit
    require_menu_view('pre_session_control_tower')
    record=db.session.get(m.ExamSession,session_id)
    if not record or record.format not in ATTENDANCE_FORMATS or not record.session_date or record.session_date>local_today():abort(404)
    if request.method=='GET':return jsonify(ok=True,state=state(record))
    require_menu_edit('pre_session_control_tower')
    if not validate_csrf():return jsonify(ok=False,error='Security token expired. Reload the page.'),400
    if local_today()<=record.session_date:return jsonify(ok=False,error='Attendance is read-only until the day after the exam session (GMT-3).'),403
    lock_session(record)
    before=workflow_state(record)
    trashed=[]
    try:
        mutate(record,trashed)
        from app.attendance_tracking import sync_milestones
        sync_milestones(record,before,True,request.form.get('action',''))
        db.session.commit()
    except (ValueError,drive.DriveStorageError) as error:
        db.session.rollback();restore(trashed)
        return jsonify(ok=False,error=str(error)),400
    except Exception:
        db.session.rollback();restore(trashed)
        current_app.logger.exception('Attendance update failed')
        return jsonify(ok=False,error='Attendance could not be saved. Please retry.'),500
    return jsonify(ok=True,state=state(record))


def restore(file_ids):
    for ident in file_ids:
        try:drive.trash(ident,False)
        except Exception:current_app.logger.exception('Attendance Drive file needs recovery: %s',ident)


def confirmed():
    if request.form.get('confirmed')!='1':raise ValueError('Please confirm this deletion or replacement.')


def retire(document,trashed):
    if document:
        drive.trash(document.file_id);trashed.append(document.file_id);db.session.delete(document)


def single_file():
    files=[file for file in request.files.getlist('document') if file.filename]
    if len(files)!=1:raise ValueError('Select exactly one document.')
    return files[0]


def mutate(record,trashed):
    action=request.form.get('action')
    if action=='submission_status':
        status=request.form.get('value','')
        if status not in {'completed','pending'}:raise ValueError('Select a valid Sinapsis submission status.')
        control(record,True).submission_status=status
        touch(record);return
    if not workflow_state(record)['records_enabled']:
        raise ValueError('Confirm Submissions completed in Sinapsis before editing Attendance.')
    if action=='add_institution':
        name=request.form.get('name','').strip()
        if not name or len(name)>250:raise ValueError('Enter an institution name (maximum 250 characters).')
        main_institution(record,True)
        db.session.add(m.AttendanceInstitution(exam_session_id=record.id,name=name,is_main=False))
        touch(record,reset=True);return
    if action in {'module_upload','module_clear','delete_institution','sent'}:
        institution=institution_for(record,request.form.get('institution_id'))
        if action=='delete_institution':
            if institution.is_main:raise ValueError('The original institution cannot be deleted.')
            confirmed()
            entries=m.AttendanceModule.query.filter_by(institution_id=institution.id).all()
            candidates=m.AbsenceCandidate.query.filter_by(institution_id=institution.id).all()
            for item in entries:retire(item.document,trashed);db.session.delete(item)
            for candidate in candidates:
                retire(candidate.document,trashed)
                m.AbsenceSubmissionEvent.query.filter_by(candidate_id=candidate.id).delete(synchronize_session=False)
                db.session.delete(candidate)
            db.session.delete(institution);touch(record,reset=True);return
        if action=='sent':
            if not workflow_state(record)['notifications_enabled']:raise ValueError('Verify the absence records before marking notifications as Sent.')
            has_absents=m.AttendanceModule.query.filter_by(institution_id=institution.id).filter(m.AttendanceModule.document_id.isnot(None)).first()
            if not has_absents:raise ValueError('No absent candidates were recorded for this institution.')
            key=request.form.get('key','')
            allowed={contact['key'] for contact in contacts(record)} if institution.is_main else {'external'}
            if key not in allowed:raise ValueError('Select an existing contact point.')
            values=json.loads(institution.notifications or '{}');values[key]=request.form.get('value')=='1';institution.notifications=json.dumps(values)
            if request.form.get('value')!='1':
                control(record,True).review_results_notified=False;control(record,True).no_documentation_received=False
            touch(record);return
        module=request.form.get('module')
        if module not in modules(record):raise ValueError('Select a configured exam module.')
        item=m.AttendanceModule.query.filter_by(institution_id=institution.id,module=module).first()
        old=item.document if item else None
        if request.form.get('previous_file_id','')!=(old.file_id if old else ''):raise ValueError('This file was changed by another user. Reopen Attendance before continuing.')
        if old:confirmed()
        if action=='module_clear':
            retire(old,trashed)
            if item:db.session.delete(item)
        else:
            document=drive.upload(single_file(),drive.LISTS_FOLDER,f'{record.exam_session_name} - {record.session_date:%d/%m/%Y}'+(' - '+institution.name if not institution.is_main else '')+' - '+module)
            if not item:item=m.AttendanceModule(institution_id=institution.id,module=module);db.session.add(item)
            item.document=document
            retire(old,trashed)
        db.session.flush()
        reconcile_absence_candidates(record)
        touch(record,institution,True);return
    if action=='no_documentation_received':
        selected=request.form.get('value')=='1'
        if selected and not workflow_state(record)['no_documentation_confirmation_enabled']:raise ValueError('Confirm no documentation only after the institutional window closes and when no certificates have been submitted.')
        touch(record).no_documentation_received=selected
        return
    if action=='review_results_notified':
        if request.form.get('value') not in {'0','1'}:raise ValueError('Select a valid notification confirmation.')
        if request.form['value']=='1' and not workflow_state(record)['results_notification_enabled']:raise ValueError('Complete every absence review after the institutional submission window closes before confirming notifications.')
        control(record,True).review_results_notified=request.form['value']=='1'
        touch(record);return
    if action=='verified':
        selected=request.form.get('value')=='1'
        # Yes is represented only by an uploaded document; no pending Yes can be persisted.
        value=control(record,True);value.verified=selected
        if not selected:value.review_results_notified=False;value.no_documentation_received=False
        touch(record);return
    if action=='candidate':
        flow=workflow_state(record)
        if not flow['documentation_enabled']:raise ValueError('Verify the absence records and mark all applicable notifications as Sent before editing documentation.')
        candidate=db.session.get(m.AbsenceCandidate,request.form.get('candidate_id',type=int))
        if not candidate or candidate.exam_session_id!=record.id:abort(404)
        field=request.form.get('field');value=request.form.get('value','')
        reviewed=candidate.review_status in {'Confirmed','Declined'}
        if field=='reopen':
            if not reviewed:raise ValueError('This candidate is already Pending. Refresh the review.')
            if not flow['review_allowed']:raise ValueError('Wait until the documentation review is available.')
            if request.form.get('confirmed')!='1':raise ValueError('Please confirm reopening this review.')
            if request.form.get('previous_file_id', '')!=(candidate.document_id or '') or request.form.get('previous_status')!=candidate.review_status:
                raise ValueError('This review changed. Refresh and try again.')
            reset_review(candidate)
            value=touch(record);value.review_results_notified=False
            return
        if reviewed and field!='notes':
            raise ValueError('This review is read-only. Use Review to return it to Pending before editing.')
        choices=candidate_choices(record,candidate)
        if field=='exam':
            if value not in choices['exams']+['']:raise ValueError('Select a valid exam level.')
            if candidate.exam!=value:
                candidate.exam=value
                candidate.absent_modules=json.dumps([module for module in json.loads(candidate.absent_modules or '[]') if module in candidate_exam_modules(candidate) and module in choices['modules']])
                reset_review(candidate)
        elif field=='modules':
            selected=request.form.getlist('modules')
            if not candidate.exam:raise ValueError('Select Exam before choosing absent modules.')
            if any(module not in candidate_exam_modules(candidate) or module not in choices['modules'] for module in selected):raise ValueError('Select the modules allowed for this exam.')
            value_json=json.dumps(list(dict.fromkeys(selected)))
            if value_json!=candidate.absent_modules:reset_review(candidate)
            candidate.absent_modules=value_json
        elif field=='institution_id':
            institution=institution_for(record,value)
            candidate.institution_id=institution.id
            candidate.institution_name=record.exam_session_name if institution.is_main else institution.name
            reset_review(candidate)
            db.session.flush();reconcile_absence_candidates(record)
        elif field=='institution_name':
            value=value.strip()
            if len(value)>250:raise ValueError('Institution name must not exceed 250 characters.')
            if value!=candidate.institution_name:reset_review(candidate)
            candidate.institution_name=value
            db.session.flush()
            reconcile_absence_candidates(record)
        elif field=='review':
            if not flow['review_allowed']:raise ValueError('Reviews can only be confirmed or declined after the institutional submission window closes.')
            if request.form.get('previous_file_id', '')!=(candidate.document_id or ''):raise ValueError('This document was replaced. Review the current file before continuing.')
            if value not in {'Confirmed','Declined'}:raise ValueError('Choose Confirm or Decline.')
            reason=request.form.get('reason','').strip()
            if value=='Confirmed':
                candidate.currency,candidate.credit_balance=credit_values(str(candidate.credit_balance) if candidate.credit_balance is not None else '',candidate.currency,candidate_credit_applicable(candidate),True)
                if not candidate_ready(candidate):raise ValueError('Complete Institution, Exam and Absent modules before confirming.')
            if value=='Declined' and (not reason or len(reason)>10000):raise ValueError('Enter a reason for declining (maximum 10,000 characters).')
            candidate.review_status=value;candidate.approved=value=='Confirmed';candidate.decline_reason=reason if value=='Declined' else ''
        elif field=='notes':
            if len(value)>10000:raise ValueError('Notes must not exceed 10,000 characters.')
            candidate.notes=value
        elif field in {'name','number'}:
            value=value.strip()
            if not value or len(value)>(80 if field=='number' else 250):raise ValueError('Enter a valid candidate number and name.')
            if field=='number':
                key=value.casefold()
                if m.AbsenceCandidate.query.filter(m.AbsenceCandidate.exam_session_id==record.id,m.AbsenceCandidate.number_key==key,m.AbsenceCandidate.id!=candidate.id).first():raise ValueError('This candidate number already exists.')
                candidate.number_key=key
            setattr(candidate,field,value)
        elif field=='rescheduled_for':
            options,_=reschedule_options(record)
            if value not in {option['value'] for option in options}:raise ValueError('Choose a future exam session or a next-year option.')
            candidate.rescheduled_for=value
            if not candidate_credit_applicable(candidate):candidate.currency='';candidate.credit_balance=None
            elif candidate.review_status=='Confirmed' and not candidate_ready(candidate):reset_review(candidate)
        elif field in {'currency','credit_balance'}:
            applicable=candidate_credit_applicable(candidate)
            currency=value if field=='currency' else candidate.currency
            amount=value if field=='credit_balance' else str(candidate.credit_balance) if candidate.credit_balance is not None else ''
            candidate.currency,candidate.credit_balance=credit_values(amount,currency,applicable)
            if candidate.review_status=='Confirmed' and not candidate_ready(candidate):reset_review(candidate)
        else:raise ValueError('Unknown candidate field.')
        value=touch(record)
        if field!='notes':value.review_results_notified=False
        return
    raise ValueError('Unknown attendance action.')


@attendance_bp.get('/pre-session-control-tower/post/sessions/<int:session_id>/files/<file_id>')
@login_required
def document(session_id,file_id):
    from app.routes import require_menu_view
    from app.google_drive import stream_document
    require_menu_view('pre_session_control_tower')
    record=db.session.get(m.ExamSession,session_id)
    allowed=m.AbsenceCandidate.query.filter_by(exam_session_id=session_id,document_id=file_id).first() or db.session.query(m.AttendanceModule.id).join(m.AttendanceInstitution).filter(m.AttendanceInstitution.exam_session_id==session_id,m.AttendanceModule.document_id==file_id).first()
    if not record or not allowed:abort(404)
    return stream_document(db.session.get(m.AttendanceDocument,file_id))


@attendance_bp.after_request
def private(response):
    response.headers['Cache-Control']='private, no-store';response.headers['Referrer-Policy']='no-referrer'
    return response


def delete_session_data(session_id):
    """Remove session-owned rows when the planner permanently deletes a session."""
    institutions=m.AttendanceInstitution.query.filter_by(exam_session_id=session_id).all()
    candidates=m.AbsenceCandidate.query.filter_by(exam_session_id=session_id).all()
    entries=m.AttendanceModule.query.filter(m.AttendanceModule.institution_id.in_([item.id for item in institutions])).all() if institutions else []
    documents={item.document_id for item in entries+candidates if item.document_id}
    if candidates:
        m.AbsenceSubmissionEvent.query.filter(m.AbsenceSubmissionEvent.candidate_id.in_([item.id for item in candidates])).delete(synchronize_session=False)
    for item in entries+candidates:db.session.delete(item)
    db.session.flush()
    for institution in institutions:db.session.delete(institution)
    value=db.session.get(m.PostAttendance,session_id)
    if value:db.session.delete(value)
    m.AttendanceEvent.query.filter_by(exam_session_id=session_id).delete(synchronize_session=False)
    for ident in documents:
        document=db.session.get(m.AttendanceDocument,ident)
        if document:db.session.delete(document)
