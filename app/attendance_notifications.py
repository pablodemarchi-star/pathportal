"""Bilingual absence notices with journey-scoped access to absence lists."""
import re
from urllib.parse import quote, urlencode
from flask import abort, url_for
from app import db
from app import models as m
from app.post_attendance import attendance_bp

MODULE_KEYS={'Speaking':'speaking','Listening and speaking':'listening-and-speaking','Reading and writing':'reading-and-writing'}
MODULE_LABELS={'Speaking':'Speaking','Listening and speaking':'Listening and Speaking','Reading and writing':'Reading and Writing'}
MONTHS_EN='January February March April May June July August September October November December'.split()
MONTHS_ES='enero febrero marzo abril mayo junio julio agosto septiembre octubre noviembre diciembre'.split()


def international_phone(value):
    value=(value or '').strip()
    if not re.fullmatch(r'\+?[0-9\s().-]+',value):return ''
    digits=re.sub(r'[^0-9]','',value)
    if digits.startswith('00'):digits=digits[2:]
    return digits if re.fullmatch(r'[1-9][0-9]{7,14}',digits) else ''


def notification_message(record,lists,journey,language,name=''):
    first=name.split()[0] if name.split() else ''
    date=record.session_date
    if language=='es':
        greeting=f'¡Hola, {first}! 👋' if first else '¡Hola! 👋'
        intro=f'Les compartimos la *lista de candidatos ausentes* de la sesión de examen *{record.exam_session_name}*, realizada el *{date.day} de {MONTHS_ES[date.month-1]} de {date.year}*.'
        files='\n\n'.join(f'📋 Lista de ausentes del módulo *{MODULE_LABELS[module]}*: {link}' for module,link in lists)
        reminder='Les recordamos que cuentan con *dos días hábiles posteriores a la sesión de examen* para cargar la documentación respaldatoria en su *Session Journey*, dentro de la sección *Justificativos de ausencia a examen*.'
        journey_line=f'👉 Enlace a su Session journey: {journey}'
        closing='⏳ *Esta sección se cerrará automáticamente una vez finalizado el plazo de presentación.*'
        thanks='¡Muchas gracias!'
    else:
        greeting=f'Hello, {first}! 👋' if first else 'Hello! 👋'
        intro=f'We’re sharing the *list of absent candidates* for the *{record.exam_session_name}* exam session held on *{date.day} {MONTHS_EN[date.month-1]} {date.year}*.'
        files='\n\n'.join(f'📋 Absence list for the *{MODULE_LABELS[module]}* module: {link}' for module,link in lists)
        reminder='Please remember that you have *two business days after the exam session* to upload the supporting documentation through your *Session journey*, in the *Exam absence documentation* section.'
        journey_line=f'👉 Your session journey link: {journey}'
        closing='⏳ *This section closes automatically once the submission deadline has passed.*'
        thanks='Thank you!'
    return '\n\n'.join([greeting,intro,files,reminder,journey_line,closing,thanks,'*Path International Examinations*'])


def decorate_notifications(record,cards,contacts,session_ids,blocked_by_reports=False):
    shares=m.ExamSessionJourneyShare.query.filter(m.ExamSessionJourneyShare.exam_session_id.in_(session_ids),
        m.ExamSessionJourneyShare.audience.in_(['institution','external']),m.ExamSessionJourneyShare.is_enabled.is_(True),
        m.ExamSessionJourneyShare.revoked_at.is_(None)).order_by((m.ExamSessionJourneyShare.exam_session_id==record.id).desc(),m.ExamSessionJourneyShare.id.desc()).all()
    by_audience={}
    for share in shares:by_audience.setdefault(share.audience,share)
    for card in cards:
        audience='institution' if card['main'] else 'external'
        share=by_audience.get(audience)
        def actions(contact=None):
            result=[]
            for language,label in [('en','English'),('es','Spanish')]:
                reason=''
                phone=international_phone(contact.get('phone')) if contact else ''
                if blocked_by_reports:reason='Confirm or decline all supervisor-reported online examination incidents before notifying institutions of absences.'
                elif not share:reason=f'Enable the {"institutional" if card["main"] else "external institution"} Session journey before notifying absences.'
                elif contact and not phone:reason='Configure a valid international phone number, including the country code, for this contact point.'
                lists=[(module,url_for('attendance.notification_list',token=share.token,audience=audience,session_id=record.id,
                    institution_id=card['id'],module_key=MODULE_KEYS[module],_external=True)) for module,file in card['modules'].items() if file] if share else []
                if not lists and not reason:reason='No absence lists have been uploaded for this institution.'
                message=''
                if not reason:
                    journey=url_for('staff.shared_path_session_journey',token=share.token,audience=audience,lang=language,_external=True)
                    message=notification_message(record,lists,journey,language,contact.get('full_name','') if contact else '')
                target='https://api.whatsapp.com/send?'+urlencode({'phone':phone,'text':message},quote_via=quote,encoding='utf-8',errors='strict') if message and contact else ''
                result.append(dict(language=language,label=f'Notify {contact["name"]} of absences ({label})' if contact else f'Copy absence notification ({label})',message=message,url=target,disabled_reason=reason))
            return result
        if card['main']:card['notification_contacts']=[dict(key=contact['key'],actions=actions(contact)) for contact in contacts]
        else:card['notification_actions']=actions()


@attendance_bp.get('/path-session-journey/<token>/<audience>/absence-records/<int:session_id>/<int:institution_id>/<module_key>')
def notification_list(token,audience,session_id,institution_id,module_key):
    from app.routes import monthly_unified_total_session_ids
    from app.google_drive import stream_document
    from app.post_attendance import modules,local_today
    if audience not in {'institution','external'}:abort(404)
    share=m.ExamSessionJourneyShare.query.filter_by(token=token,audience=audience).first_or_404()
    if not share.is_enabled or share.revoked_at:abort(410)
    if session_id not in monthly_unified_total_session_ids(share.exam_session):abort(404)
    record=db.session.get(m.ExamSession,session_id)
    institution=db.session.get(m.AttendanceInstitution,institution_id)
    module=next((name for name,key in MODULE_KEYS.items() if key==module_key),None)
    if not record or not record.session_date or record.session_date>local_today() or not institution or institution.exam_session_id!=session_id or institution.is_main!=(audience=='institution') or module not in modules(record):abort(404)
    item=m.AttendanceModule.query.filter_by(institution_id=institution_id,module=module).first()
    if not item or not item.document:abort(404)
    return stream_document(item.document)
