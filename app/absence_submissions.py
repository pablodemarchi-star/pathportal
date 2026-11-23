"""Institutional absence submissions and their link to internal Attendance."""
import json
from datetime import timezone
from flask import abort, jsonify, request, current_app
from app import db, login_required, validate_csrf
from app import models as m
from app.post_attendance import ATTENDANCE_FORMATS,attendance_bp,lock_session,main_institution,institution_for,touch,local_today,retire,restore,reschedule_options,reset_review,EXAMS,exam_modules,credit_applicable,credit_values,workflow_state,modules
from app import attendance_drive as drive
from app.staff_report_media import session_pictures_folder
from types import SimpleNamespace

COPY={
'en':{'title':'Exam absence documentation','number':'Candidate number','name':'Candidate name','document':'Absence documentation','drop':'Drop one file here or click to select','submit':'Submit request','cancel':'Cancel','replace':'Replace file','cancel_request':'Cancel request',
'required':'Candidate number, candidate name and one document are required.','duplicate':'A request already exists for this candidate number. Cancel this request or replace the previous file?','changed':'The file changed while you were completing the request. Please review and confirm again.','success':'Your absence documentation has been submitted.','error':'The documentation could not be submitted. Please retry.','closed':'The documentation submission window is closed.','csrf':'Security token expired. Reload the page and retry.','folder':'The documentation folder is not available. Please contact Path Examinations.','see':'See absence documentation','replaced':'Replaced','saving':'Uploading…','single':'Select exactly one file.','window_pending':'Available for 2 days after the exam date','window_open':'Upload your documentation now. Time is running out!','window_expired':'Upload deadline expired'},
'es':{'title':'Documentación de ausencia a examen','number':'Número de candidato','name':'Nombre del candidato','document':'Documentación de ausencia','drop':'Arrastre un archivo aquí o haga clic para seleccionarlo','submit':'Enviar solicitud','cancel':'Cancelar','replace':'Reemplazar archivo','cancel_request':'Cancelar solicitud',
'required':'El número de candidato, el nombre y un documento son obligatorios.','duplicate':'Ya existe una solicitud para este número de candidato. ¿Desea cancelar esta solicitud o reemplazar el archivo anterior?','changed':'El archivo cambió mientras completaba la solicitud. Revise y confirme nuevamente.','success':'La documentación de ausencia fue enviada.','error':'No se pudo enviar la documentación. Inténtelo nuevamente.','closed':'El plazo para enviar documentación está cerrado.','csrf':'La sesión de seguridad venció. Actualice la página e inténtelo nuevamente.','folder':'La carpeta de documentación no está disponible. Comuníquese con Path Examinations.','see':'Ver documentación de ausencia','replaced':'Reemplazado','saving':'Cargando…','single':'Seleccione un único archivo.','window_pending':'Disponible por 2 días luego de la fecha de examen','window_open':'Carga ahora tu justificativo. ¡Termina pronto!','window_expired':'Plazo de carga vencido'}}


COPY['en'].update(pending='Pending',confirmed='Confirmed',declined='Declined',review_notes='Notes',decline_title='Reason for declining',reschedule='Select rescheduled exam date',select_date='Select an option',
    reschedule_required='Select a valid rescheduled exam date.',
    approval_notice='Submitting absence documentation does not guarantee approval. You will be notified once your submission has been reviewed.')
COPY['es'].update(pending='Pendiente',confirmed='Confirmado',declined='Rechazado',review_notes='Notas',decline_title='Motivo del rechazo',reschedule='Selecciona la fecha del examen reprogramado',select_date='Selecciona una opción',
    reschedule_required='Selecciona una fecha válida para el examen reprogramado.',
    approval_notice='La presentación de documentación de ausencia no garantiza su aprobación. Se te notificará una vez que tu solicitud haya sido revisada.')


def institutional_reschedule_options(record,language='en'):
    latest=(m.ExamSession.query.filter(db.extract('year',m.ExamSession.session_date)==record.session_date.year,
        m.ExamSession.session_date>local_today()).order_by(m.ExamSession.session_date.desc(),m.ExamSession.id.desc()).first())
    options=[{'value':str(latest.id),'label':f'{latest.exam_session_name} | {latest.session_date:%d/%m/%Y} | {latest.format}'}] if latest else []
    labels=(['Julio, próximo año | Online | Solo certificado digital','Nov/Dic, próximo año | Online','Nov/Dic, próximo año | Presencial'] if language=='es' else
        ['July, next year | Online | Digital certificate only','Nov/Dec, next year | Online','Nov/Dec, next year | Onsite'])
    return options+[{'value':key,'label':label} for key,label in zip(['next_july_online','next_novdec_online','next_novdec_onsite'],labels)]


def folder_id(record):
    return session_pictures_folder(SimpleNamespace(session_pictures_folder_url=record.absence_documentation_folder_url or ''))


def conflict(candidate,text):
    return jsonify(ok=False,duplicate=True,error=text['duplicate'],previous_file_id=candidate.document_id or ''),409


def store_candidate(record,text,trashed,internal=False):
    number=request.form.get('candidate_number','').strip();name=request.form.get('candidate_name','').strip()
    files=[file for file in request.files.getlist('document') if file.filename]
    if not number or not name or len(number)>80 or len(name)>250 or len(files)!=1:raise ValueError(text['required'])
    requested=request.form.get('rescheduled_for','').strip()
    if requested not in {option['value'] for option in institutional_reschedule_options(record)}:
        raise ValueError(text['reschedule_required'])
    before=workflow_state(record)
    details={}
    if internal:
        from app.post_attendance import absence_choices
        institution_name=request.form.get('institution_name','').strip()
        exam=request.form.get('exam','')
        absent=list(dict.fromkeys(request.form.getlist('modules')))
        approval=request.form.get('approval','')
        reason=request.form.get('reason','').strip()
        if not institution_name or len(institution_name)>250:raise ValueError('Enter an institution name (maximum 250 characters).')
        choices=absence_choices(record,institution_name)
        if not choices['institution_id'] or not choices['modules']:raise ValueError(choices['reason'])
        if exam not in choices['exams']:raise ValueError('Select an Exam with recorded absences for this institution.')
        if not absent or any(module not in exam_modules(exam) or module not in choices['modules'] for module in absent):raise ValueError('Select the absent modules recorded for this institution and allowed for this Exam.')
        flow=workflow_state(record)
        if not flow['documentation_enabled']:raise ValueError('Verify absence records and mark all applicable notifications as Sent before adding documentation.')
        if not flow['review_allowed']:
            if approval not in {'','Pending'}:raise ValueError('Reviews must remain Pending until the institutional submission window closes.')
            approval='Pending'
        elif approval not in {'Pending','Confirmed','Declined'}:raise ValueError('Select Pending, Confirmed or Declined.')
        if approval=='Declined' and (not reason or len(reason)>10000):raise ValueError('Enter a reason for declining (maximum 10,000 characters).')
        currency,amount=credit_values(request.form.get('credit_balance',''),request.form.get('currency',''),credit_applicable(record,requested),approval=='Confirmed')
        details=dict(currency=currency,credit_balance=amount,institution_name=institution_name,exam=exam,absent_modules=json.dumps(absent),review_status=approval,
            approved=approval=='Confirmed',decline_reason=reason if approval=='Declined' else '')
    destination=folder_id(record)
    if not destination:raise ValueError(text['folder'])
    candidate=m.AbsenceCandidate.query.filter_by(exam_session_id=record.id,number_key=number.casefold()).first()
    if candidate and (request.form.get('replace')!='1' or request.form.get('confirmed')!='1' or request.form.get('previous_file_id', '')!=(candidate.document_id or '')):
        return conflict(candidate,text)
    institution=institution_for(record,request.form.get('institution_id','main')) if internal and not candidate else main_institution(record,True) if not candidate else db.session.get(m.AttendanceInstitution,candidate.institution_id)
    if internal:institution=institution_for(record,choices['institution_id'])
    old=candidate.document if candidate else None
    document=drive.upload(files[0],destination,f'{number} - {name} - Absence documentation')
    if not candidate:
        candidate=m.AbsenceCandidate(exam_session_id=record.id,institution_id=institution.id,number=number,number_key=number.casefold(),name=name,document=document,rescheduled_for=reschedule_options(record)[1])
        db.session.add(candidate)
    else:
        candidate.number=number;candidate.name=name;candidate.document=document
    candidate.rescheduled_for=requested;candidate.requested_rescheduled_for=requested
    if internal:candidate.institution_id=institution.id
    reset_review(candidate)
    if not credit_applicable(record,requested):candidate.currency='';candidate.credit_balance=None
    for key,value in details.items():setattr(candidate,key,value)
    db.session.flush()
    db.session.add(m.AbsenceSubmissionEvent(candidate_id=candidate.id,file_id=document.file_id,action='replaced' if old else 'submitted'))
    retire(old,trashed)
    value=touch(record,internal=internal);value.review_results_notified=False;value.no_documentation_received=False
    has_recorded_absences=m.AttendanceModule.query.filter_by(institution_id=institution.id).filter(
        m.AttendanceModule.module.in_(modules(record)),m.AttendanceModule.document_id.isnot(None)).first()
    if not has_recorded_absences:value.verified=False
    from app.attendance_tracking import sync_milestones
    sync_milestones(record,before,internal,'certificate_replaced' if old else 'certificate_uploaded')
    return None


def public_scope(token,session_id):
    from app.routes import monthly_unified_total_session_ids
    share=m.ExamSessionJourneyShare.query.filter_by(token=token,audience='institution').first_or_404()
    if not share.is_enabled or share.revoked_at:abort(410)
    if session_id not in monthly_unified_total_session_ids(share.exam_session):abort(404)
    record=db.session.get(m.ExamSession,session_id)
    if not record:abort(404)
    return share,record


def submission_list(record):
    from app.post_attendance import requested_date_label
    from app.routes import LOCAL_TZ
    rows=(db.session.query(m.AbsenceSubmissionEvent,m.AbsenceCandidate).join(m.AbsenceCandidate)
        .filter(m.AbsenceCandidate.exam_session_id==record.id).order_by(m.AbsenceSubmissionEvent.created_at,m.AbsenceSubmissionEvent.id).all())
    labels={}
    def rescheduled_label(candidate,language):
        key=(candidate.rescheduled_for or candidate.requested_rescheduled_for,language)
        if key not in labels:labels[key]=requested_date_label(candidate,language=language)
        return labels[key]
    return [dict(id=event.id,candidate_id=candidate.id,number=candidate.number,name=candidate.name,action=event.action,
                 rescheduled_label=rescheduled_label(candidate,'en'),rescheduled_label_es=rescheduled_label(candidate,'es'),
                 current=event.file_id==candidate.document_id,review_status=candidate.review_status,decline_reason=candidate.decline_reason,created_at=event.created_at.replace(tzinfo=event.created_at.tzinfo or timezone.utc).isoformat(),date_label=event.created_at.replace(tzinfo=event.created_at.tzinfo or timezone.utc).astimezone(LOCAL_TZ).strftime('%d/%m/%Y %H:%M')) for event,candidate in rows]


@attendance_bp.route('/path-session-journey/<token>/institution/absences/<int:session_id>',methods=['GET','POST'])
def public_submit(token,session_id):
    from app.routes import journey_absence_upload_window
    share,record=public_scope(token,session_id)
    text=COPY['es' if request.values.get('language')=='es' else 'en']
    if request.method=='GET':return jsonify(ok=True,entries=submission_list(record),window=journey_absence_upload_window(record),folder_configured=bool(folder_id(record)))
    if not validate_csrf():return jsonify(ok=False,error=text['csrf']),400
    lock_session(record)
    if journey_absence_upload_window(record)['state']!='open':return jsonify(ok=False,error=text['closed']),403
    trashed=[]
    try:
        duplicate=store_candidate(record,text,trashed)
        if duplicate:return duplicate
        db.session.commit()
    except drive.DriveStorageError as error:
        db.session.rollback();restore(trashed)
        return jsonify(ok=False,error=text['error'] if request.form.get('language')=='es' else str(error)),400
    except ValueError as error:
        db.session.rollback();restore(trashed);return jsonify(ok=False,error=str(error)),400
    except Exception:
        db.session.rollback();restore(trashed)
        current_app.logger.exception('Absence submission failed')
        return jsonify(ok=False,error=text['error']),500
    return jsonify(ok=True,message=text['success'],entries=submission_list(record))


@attendance_bp.get('/path-session-journey/<token>/institution/absences/<int:session_id>/<int:candidate_id>/document')
def public_document(token,session_id,candidate_id):
    from app.google_drive import stream_document
    public_scope(token,session_id)
    candidate=m.AbsenceCandidate.query.filter_by(id=candidate_id,exam_session_id=session_id).first_or_404()
    return stream_document(candidate.document)


@attendance_bp.post('/pre-session-control-tower/post/sessions/<int:session_id>/candidates')
@login_required
def internal_submit(session_id):
    from app.routes import require_menu_edit
    from app.post_attendance import state
    require_menu_edit('pre_session_control_tower')
    record=db.session.get(m.ExamSession,session_id)
    if not record or record.format not in ATTENDANCE_FORMATS or not record.session_date:abort(404)
    if not validate_csrf():return jsonify(ok=False,error=COPY['en']['csrf']),400
    if local_today()<=record.session_date:return jsonify(ok=False,error='Attendance is read-only until the day after the exam session (GMT-3).'),403
    lock_session(record);trashed=[]
    try:
        duplicate=store_candidate(record,COPY['en'],trashed,True)
        if duplicate:return duplicate
        db.session.commit()
    except (ValueError,drive.DriveStorageError) as error:
        db.session.rollback();restore(trashed);return jsonify(ok=False,error=str(error)),400
    except Exception:
        db.session.rollback();restore(trashed);current_app.logger.exception('Attendance candidate upload failed')
        return jsonify(ok=False,error=COPY['en']['error']),500
    return jsonify(ok=True,state=state(record))
