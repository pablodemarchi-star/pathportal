"""Read-only return configuration for invitations and Onsite supervisor reports."""
import hashlib
import json
from flask import url_for
from app import db
from app.models import AcademicStaff, ExamSessionSinapsisControl
from app.final_checks import return_configuration_complete
from app.rich_text import sanitize_instructions


def return_view(record, assignment, share):
    if not getattr(assignment, 'is_shipment_recipient', False) or getattr(assignment, 'participation_status', '') != 'Confirmed':
        return None
    return configuration_view(record, share)


def configuration_view(record, share):
    """Management configuration, shared by the invitation and supervisor report."""
    from app.routes import RETURN_MATERIALS_OPTIONS, combined_return_session_options, combined_return_examiner_confirmed
    control = ExamSessionSinapsisControl.query.filter_by(exam_session_id=record.id).first()
    complete = return_configuration_complete(record, control)
    method = control.return_materials_method if control else ''
    option = next((item for item in RETURN_MATERIALS_OPTIONS if item['key'] == method), {})
    result = dict(status='Completed' if complete else 'Pending', complete=complete,
        method=method, label=option.get('label', '').replace('Inmediate', 'Immediate'), description=option.get('description', ''),
        instructions_title=control.return_instructions_title or '' if control else '',
        instructions_html=sanitize_instructions(control.return_instructions_html or '') if control else '',
        address_url='', label_url='', sessions=[], handover=None, shipping=None)
    if not complete:
        return result
    if method in {'combined_dispatch', 'combined_location_drop_off'}:
        result['sessions'] = [dict(name=peer.exam_session_name, date=peer.session_date.strftime('%d/%m/%Y') if peer.session_date else '')
            for peer in combined_return_session_options(record)
            if peer.id in control.combined_return_session_ids and combined_return_examiner_confirmed(peer)]
    if method in {'immediate_dispatch', 'combined_dispatch'}:
        result['label_url'] = url_for('staff.staff_return_shipping_label', token=share.token, session_id=record.id)
        count = 1 + len(result['sessions'])
        result['shipping'] = dict(height=count * 7, weight=1 if count <= 3 else 2 if count <= 6 else 3 if count <= 12 else 4)
    elif method in {'location_drop_off', 'combined_location_drop_off'}:
        result['address_url'] = control.return_drop_off_address_url if method == 'location_drop_off' else control.combined_return_drop_off_address_url
    elif method == 'staff_handover':
        person = db.session.get(AcademicStaff, control.return_handover_staff_id)
        if person:
            result['handover'] = dict(name=person.full_name, phone=person.phone or '')
    return result


RECIPIENT_CONFIRMATION = "I confirm that I have read and understood the instructions for returning this exam session’s materials."
SUPERVISOR_CONFIRMATION = "I confirm that the staff member responsible for returning the exam materials has been notified and has acknowledged understanding of the required procedures and deadlines, as outlined in this section."


def report_return_view(record, assignment, share):
    """All Onsite supervisors must acknowledge the configured return procedure."""
    if record.format != 'Onsite':
        return None
    from app.final_checks import recipient, recipient_ref
    assigned = recipient(record)
    info = configuration_view(record, share)
    person = (assigned.team_member or assigned.potential_entry) if assigned else None
    is_recipient = bool(assigned and assignment and recipient_ref(assigned) == recipient_ref(assignment))
    complete = bool(assigned and info['complete'])
    error = ''
    if not assigned:
        error = 'No staff member is marked Receives shipment. Please contact Logistics. This report cannot be submitted until a responsible staff member has been assigned and the return instructions are ready.'
    elif not complete:
        error = 'Return instructions are pending. Please contact Logistics. This report cannot be submitted until the return of exam session materials has been configured.'
    # Store what was acknowledged, independent of subsequent Management changes.
    context = {key: info[key] for key in ('method', 'label', 'description', 'instructions_title', 'instructions_html',
                                        'address_url', 'sessions', 'handover', 'shipping')}
    control = ExamSessionSinapsisControl.query.filter_by(exam_session_id=record.id).first()
    context['shipping_label_id'] = (control.return_shipping_label_id if info['method'] == 'immediate_dispatch'
                                  else control.combined_return_shipping_label_id if info['method'] == 'combined_dispatch' else None) if control else None
    context.update(recipient_ref=recipient_ref(assigned), recipient_name=person.full_name if person else '',
                   acknowledged_by_recipient=is_recipient, complete=complete)
    version = hashlib.sha256(json.dumps(context, sort_keys=True).encode()).hexdigest()
    return dict(info=info, complete=complete, recipient_name=context['recipient_name'], is_recipient=is_recipient,
                confirmation=RECIPIENT_CONFIRMATION if is_recipient else SUPERVISOR_CONFIRMATION,
                error=error, context=context, version=version)
