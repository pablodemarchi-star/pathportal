"""Persist completion notices with the status change and send only after commit."""
import json
from datetime import datetime, timezone

from flask import Blueprint, abort, current_app, g, has_request_context, render_template, session, url_for
from sqlalchemy import event
from sqlalchemy.orm import Session

from app import db
from app.google_mail import MailNotSent, MailDeliveryUnknown, send_notification_email
from app.models import FinanceCompletionNotification, PaymentRequest, BillingRequest

completion_bp = Blueprint('finance_completion', __name__)


def queue_completion(item, kind, previous, status, transition):
    completed = 'Payment completed' if kind == 'payment' else 'Invoice issued'
    payee_notice_id = None
    client_notice_id = None
    if kind == 'payment':
        from app.payee_notifications import queue_payee_notification
        payee_notice_id = queue_payee_notification(item, previous, status, transition)
    elif kind == 'invoice':
        from app.payee_notifications import queue_client_notification
        client_notice_id = queue_client_notification(item, previous, status, transition)
    if status not in {completed, 'Rejected', 'Needs correction'} or previous == status or not item.requester or not item.requester.email:
        return
    db.session.flush()
    if FinanceCompletionNotification.query.filter_by(request_kind=kind, event_id=transition.id).first():
        return
    from app.routes import payment_whatsapp_copy_contract, billing_whatsapp_copy_contract
    db.session.expire(item, ['events'])
    contract = payment_whatsapp_copy_contract if kind == 'payment' else billing_whatsapp_copy_contract
    payload = {'requester': item.requester.full_name or item.requester.email,
               'amount': f'{item.currency} {item.amount:,.2f}' if item.amount is not None and item.amount > 0 else 'Amount pending',
               'status': 'Completed' if status == completed else 'Rejected' if status == 'Rejected' else 'With discrepancy',
               'reason': (transition.comment or '').strip(),
               'name': item.payee_name_snapshot if kind == 'payment' else item.client_name_snapshot,
               'concept': item.concept_name_snapshot, 'payee_notice_id':payee_notice_id, 'client_notice_id':client_notice_id,
               'en': contract(item, 'en'), 'sp': contract(item, 'sp')}
    notice = FinanceCompletionNotification(request_kind=kind, request_id=item.id, event_id=transition.id,
        request_number=item.request_number, recipient=item.requester.email,
        requester_user_id=item.requester_user_id, payload=json.dumps(payload))
    db.session.add(notice)
    db.session.flush()
    if has_request_context():
        g.setdefault('_completion_pending', []).append(notice.id)


@event.listens_for(Session, 'after_commit')
def committed(unit):
    if has_request_context() and unit is db.session():
        g.setdefault('_completion_committed', []).extend(g.pop('_completion_pending', []))
        g.setdefault('_payee_committed', []).extend(g.pop('_payee_pending', []))
        g.setdefault('_client_committed', []).extend(g.pop('_client_pending', []))


@event.listens_for(Session, 'after_rollback')
def rolled_back(unit):
    if has_request_context() and unit is db.session():
        g.pop('_completion_pending', None)
        g.pop('_payee_pending', None)
        g.pop('_client_pending', None)


@completion_bp.after_app_request
def send_committed(response):
    from app.payee_notifications import deliver_payee_notification
    for notice_id in g.pop('_payee_committed', []):
        try:
            deliver_payee_notification(notice_id)
        except Exception:
            db.session.rollback()
            current_app.logger.warning('Payee notification %s needs review.', notice_id)
    from app.payee_notifications import deliver_client_notification
    for notice_id in g.pop('_client_committed', []):
        try:
            deliver_client_notification(notice_id)
        except Exception:
            db.session.rollback()
            current_app.logger.warning('Client notification %s needs review.', notice_id)
    for notice_id in g.pop('_completion_committed', []):
        try:
            deliver_completion(notice_id)
        except Exception:
            db.session.rollback()
            current_app.logger.warning('Completion notification %s needs administrator review.', notice_id)
    return response


def deliver_completion(notice_id):
    notice = db.session.get(FinanceCompletionNotification, notice_id)
    if not notice or notice.status not in {'pending', 'failed'}:
        return False
    claimed = FinanceCompletionNotification.query.filter(
        FinanceCompletionNotification.id == notice_id,
        FinanceCompletionNotification.status.in_(['pending', 'failed']),
    ).update({'status': 'sending'}, synchronize_session=False)
    db.session.commit()
    if not claimed:
        return False
    try:
        payload = json.loads(notice.payload)
        from app.payee_notifications import deliver_payee_notification, deliver_client_notification
        from app.models import PayeePaymentNotification, ClientInvoiceNotification
        for key, model, deliver, recipient_label in (
            ('payee_notice_id', PayeePaymentNotification, deliver_payee_notification, 'Payee'),
            ('client_notice_id', ClientInvoiceNotification, deliver_client_notification, 'Client'),
        ):
            if not payload.get(key):
                continue
            recipient_notice = db.session.get(model, payload[key])
            if recipient_notice and recipient_notice.status == 'pending':
                deliver(recipient_notice.id)
            payload['payee_notice_result'] = (
                f'The {recipient_label} has been notified at {recipient_notice.recipient}.'
                if recipient_notice and recipient_notice.status == 'sent' else
                f'The {recipient_label} notification was not confirmed. Please review API integrations; do not assume the {recipient_label} was notified.')
        status_label = payload['status']
        subject = f"{'Payment' if notice.request_kind == 'payment' else 'Invoice'} request {status_label.lower()} — {notice.request_number}"
        text = f"Dear {payload['requester']},\n\nYour {'payment' if notice.request_kind == 'payment' else 'invoice'} request {notice.request_number} has changed to {status_label}.\nAmount: {payload['amount']}\n\n"
        if payload.get('payee_notice_result'):
            text += payload['payee_notice_result'] + '\n\n'
        if payload['reason']:
            text += f"Reason: {payload['reason']}\n\n"
        for language, heading, instruction in (
            ('en', 'ENGLISH MESSAGE', 'Copy the message below and paste it into WhatsApp to send it.'),
            ('sp', 'MENSAJE EN ESPAÑOL', 'Copiá el mensaje de abajo y pegalo en WhatsApp para enviarlo.'),
        ):
            contract = payload[language]
            text += f"{heading}\n{instruction}\n\n{contract['message'] or contract['error']}\n\n"
        text += 'Path International Examinations'
        html = render_template('finance_requests/completion_email.html', notice=notice, details=payload)
        notice.gmail_message_id = send_notification_email(notice.recipient, subject, text, html,
            f'<finance-completion-{notice.id}@pathexaminations.com>')
        notice.status, notice.last_error = 'sent', None
        notice.sent_at = datetime.now(timezone.utc)
    except MailNotSent as exc:
        notice.status, notice.last_error = 'failed', str(exc)
    except MailDeliveryUnknown:
        notice.status, notice.last_error = 'unknown', 'Delivery not confirmed; verify Sent in Gmail before retrying.'
    except Exception:
        notice.status, notice.last_error = 'unknown', 'Notification delivery needs administrator review.'
        current_app.logger.warning('Completion notification %s needs review.', notice_id)
    db.session.commit()
    return notice.status == 'sent'


@completion_bp.get('/finance-requests/completion/<int:notice_id>/<language>')
def copy_message(notice_id, language):
    if language not in {'en', 'sp'}:
        abort(404)
    if not g.user:
        from flask import redirect
        session['finance_email_review_next'] = url_for('finance_completion.copy_message', notice_id=notice_id, language=language)
        return redirect(url_for('login'))
    from app.routes import require_menu_view, can_view_payment_request, can_view_billing_request
    require_menu_view('finance_requests')
    notice = db.session.get(FinanceCompletionNotification, notice_id)
    if notice is None:
        abort(404)
    item = db.session.get(PaymentRequest if notice.request_kind == 'payment' else BillingRequest, notice.request_id)
    user = getattr(g, 'current_user', None)
    allowed = can_view_payment_request if notice.request_kind == 'payment' else can_view_billing_request
    if item is None or not allowed(user, item):
        abort(404)
    if not (user and user.id == notice.requester_user_id) and not (user and user.is_superadmin):
        abort(404)
    response = current_app.make_response(render_template('finance_requests/completion_copy.html', notice=notice,
        language=language, status_label=json.loads(notice.payload)["status"], contract=json.loads(notice.payload)[language]))
    response.headers['Cache-Control'] = 'private, no-store'
    response.headers['Referrer-Policy'] = 'no-referrer'
    return response
