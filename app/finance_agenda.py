"""Daily Finance agenda and notices for same-day work scheduled after 06:30."""
import hmac
import json
import os
from datetime import datetime, time, timedelta, timezone
from urllib.parse import urlsplit

from flask import Blueprint, abort, current_app, g, has_request_context, jsonify, render_template, request, url_for
from sqlalchemy import event, inspect
from sqlalchemy.dialects.sqlite import insert
from sqlalchemy.orm import Session

from app import db
from app.google_mail import MailDeliveryUnknown, MailNotSent, send_notification_email
from app.models import BillingRequest, PaymentRequest, FinanceAgendaNotification, FinanceAgendaCoverage

agenda_bp = Blueprint('finance_agenda', __name__)
RECIPIENT = 'finance@pathexaminations.com'
LOCAL_TZ = timezone(timedelta(hours=-3))
CUTOFF = time(6, 30)
PAYMENT_STATES = {'Management approved', 'Payment scheduled', 'Payment delayed'}
INVOICE_STATES = {'Requested', 'Processing invoice', 'Invoice scheduled'}


def local_now():
    return datetime.now(LOCAL_TZ)


def due_date(item):
    if isinstance(item, PaymentRequest):
        return item.scheduled_payment_date
    return item.scheduled_invoice_issue_date or item.requested_invoice_issue_date


def actionable(item, today):
    if item.is_archived:
        return False
    if isinstance(item, PaymentRequest):
        return item.status in PAYMENT_STATES and bool(due_date(item) and due_date(item) <= today)
    return item.status in INVOICE_STATES and (due_date(item) is None or due_date(item) <= today)


def row_for(item):
    return {'kind': 'Payment' if isinstance(item, PaymentRequest) else 'Invoice', 'id': item.id,
            'number': item.request_number,
            'name': item.payee_name_snapshot if isinstance(item, PaymentRequest) else item.client_name_snapshot,
            'amount': f'{item.currency} {item.amount:,.2f}' if item.amount is not None and item.amount > 0 else 'Amount pending',
            'concept': item.concept_name_snapshot, 'status': item.status,
            'scheduled_date': due_date(item).strftime('%d/%m/%Y') if due_date(item) else 'To be arranged',
            'requester': item.requester.full_name if item.requester else item.requester_department}


def reserve_notice(key, category, today, items):
    # A write lock plus unique keys serializes cron and web requests on SQLite.
    result = db.session.execute(insert(FinanceAgendaNotification).values(
        notice_key=key, category=category, agenda_date=today, payload='[]', status='pending'
    ).on_conflict_do_nothing(index_elements=['notice_key']))
    notice = FinanceAgendaNotification.query.filter_by(notice_key=key).one()
    if result.rowcount == 0:
        return notice
    rows = []
    for item in items:
        kind = 'payment' if isinstance(item, PaymentRequest) else 'invoice'
        reserved = db.session.execute(insert(FinanceAgendaCoverage).values(
            agenda_date=today, request_kind=kind, request_id=item.id, notification_id=notice.id,
        ).on_conflict_do_nothing(index_elements=['agenda_date', 'request_kind', 'request_id']))
        if reserved.rowcount:
            rows.append(row_for(item))
    notice.payload = json.dumps(rows)
    if not rows:
        notice.status = 'empty'
    return notice


@event.listens_for(Session, 'before_flush')
def capture_agenda_changes(unit, *_):
    if not has_request_context() or unit is not db.session():
        return
    candidates = unit.info.setdefault('_finance_agenda_candidates', set())
    for item in list(unit.new) + list(unit.dirty):
        if isinstance(item, (PaymentRequest, BillingRequest)):
            attrs = ['status', 'is_archived', 'scheduled_payment_date'] if isinstance(item, PaymentRequest) else ['status', 'is_archived', 'scheduled_invoice_issue_date', 'requested_invoice_issue_date']
            if item in unit.new or any(inspect(item).attrs[name].history.has_changes() for name in attrs):
                candidates.add(item)


@event.listens_for(Session, 'before_commit')
def queue_same_day_changes(unit):
    if not has_request_context() or unit is not db.session():
        return
    unit.flush()
    candidates = unit.info.pop('_finance_agenda_candidates', set())
    now = local_now()
    if now.time() < CUTOFF:
        return
    for item in candidates:
        if item in unit.deleted or inspect(item).deleted or not actionable(item, now.date()):
            continue
        kind = 'payment' if isinstance(item, PaymentRequest) else 'invoice'
        notice = reserve_notice(f'late:{now.date()}:{kind}:{item.id}', 'late', now.date(), [item])
        if notice.status in {'pending', 'failed'}:
            g.setdefault('_agenda_pending', set()).add(notice.id)


@event.listens_for(Session, 'after_commit')
def agenda_committed(unit):
    if has_request_context() and unit is db.session():
        g.setdefault('_agenda_committed', set()).update(g.pop('_agenda_pending', set()))


@event.listens_for(Session, 'after_rollback')
def agenda_rolled_back(unit):
    unit.info.pop('_finance_agenda_candidates', None)
    if has_request_context() and unit is db.session():
        g.pop('_agenda_pending', None)


@agenda_bp.after_app_request
def send_immediate_notices(response):
    for notice_id in g.pop('_agenda_committed', set()):
        try:
            deliver_agenda(notice_id)
        except Exception:
            db.session.rollback()
            current_app.logger.warning('Finance agenda notification %s needs review.', notice_id)
    return response


def queue_daily(now=None):
    now = now or local_now()
    if now.time() < CUTOFF:
        return None
    today = now.date()
    payments = PaymentRequest.query.filter(PaymentRequest.is_archived.is_(False), PaymentRequest.status.in_(PAYMENT_STATES), PaymentRequest.scheduled_payment_date <= today).order_by(PaymentRequest.scheduled_payment_date, PaymentRequest.id).all()
    invoices = BillingRequest.query.filter(BillingRequest.is_archived.is_(False), BillingRequest.status.in_(INVOICE_STATES)).order_by(BillingRequest.id).all()
    items = payments + [item for item in invoices if actionable(item, today)]
    notice = reserve_notice(f'daily:{today}', 'daily', today, items)
    db.session.commit()
    return notice.id


def deliver_agenda(notice_id):
    notice = db.session.get(FinanceAgendaNotification, notice_id)
    if not notice or notice.status not in {'pending', 'failed'}:
        return bool(notice and notice.status in {'sent', 'empty'})
    claimed = FinanceAgendaNotification.query.filter(FinanceAgendaNotification.id == notice_id,
        FinanceAgendaNotification.status.in_(['pending', 'failed'])).update({'status': 'sending'}, synchronize_session=False)
    db.session.commit()
    if not claimed:
        return False
    try:
        callback = urlsplit(os.getenv('GOOGLE_OAUTH_REDIRECT_URI', 'https://portal.pathinternalportal.com/integrations/google/callback'))
        base = os.getenv('PORTAL_BASE_URL', f'{callback.scheme}://{callback.netloc}').rstrip('/')
        origin = urlsplit(base)
        if (origin.scheme != 'https' and not (origin.scheme == 'http' and origin.hostname in {'localhost','127.0.0.1'})) or not origin.netloc or origin.path or origin.query or origin.fragment:
            raise MailNotSent('Set PORTAL_BASE_URL to the production HTTPS origin')
        link = base + '/finance-requests?tab=finance_payments&finance_filter=today'
        rows = json.loads(notice.payload)
        title = 'Today’s Finance agenda' if notice.category == 'daily' else 'New work for today’s Finance agenda'
        text = f"{title} — {notice.agenda_date:%d/%m/%Y}\n\n"
        for row in rows:
            text += f"{row['kind']} {row['number']} | {row['name'] or '-'} | {row['amount']} | {row['status']} | Scheduled: {row['scheduled_date']} | Requested by: {row['requester'] or '-'}\n"
        text += f'\nOpen Finance actions: {link}\n\nPath International Examinations'
        html = render_template('finance_requests/agenda_email.html', title=title, notice=notice, rows=rows, link=link)
        notice.gmail_message_id = send_notification_email(RECIPIENT, f'{title} — {notice.agenda_date:%d/%m/%Y}', text, html,
            f'<finance-agenda-{notice.id}@pathexaminations.com>')
        notice.status, notice.last_error = 'sent', None
        notice.sent_at = datetime.now(timezone.utc)
    except MailNotSent as exc:
        notice.status, notice.last_error = 'failed', str(exc)
    except MailDeliveryUnknown:
        notice.status, notice.last_error = 'unknown', 'Delivery not confirmed; verify Sent in Gmail before retrying.'
    except Exception:
        notice.status, notice.last_error = 'unknown', 'Notification delivery needs administrator review.'
        current_app.logger.warning('Finance agenda notification %s needs review.', notice_id)
    db.session.commit()
    return notice.status == 'sent'


def request_delivery_diagnostic(number):
    """Read-only view of the actual stored schedule, eligibility and delivery."""
    from app.models import FinanceAgendaCoverage
    number = (number or '').strip().upper()
    if not number:
        return None
    if len(number) > 80:
        return {'error': 'Enter a payment or invoice request number.'}
    model = PaymentRequest if number.startswith('PAY-') else BillingRequest if number.startswith('INVOICE-') else None
    item = model.query.filter_by(request_number=number).first() if model else None
    if item is None:
        return {'error': 'Request not found.'}
    now = local_now()
    kind = 'payment' if isinstance(item, PaymentRequest) else 'invoice'
    coverage = FinanceAgendaCoverage.query.filter_by(agenda_date=now.date(), request_kind=kind, request_id=item.id).first()
    notice = db.session.get(FinanceAgendaNotification, coverage.notification_id) if coverage else None
    created = item.created_on
    if created and created.tzinfo is None:
        created = created.replace(tzinfo=timezone.utc)
    if notice:
        explanation = {
            'sent': 'Google confirmed sending this notification. The Gmail message ID is recorded below.',
            'pending': 'A notification was queued but has not been sent.',
            'failed': 'The send attempt failed before delivery was confirmed. It can be retried from this page.',
            'sending': 'Delivery was claimed but has not been confirmed. Check Gmail Sent before retrying.',
            'unknown': 'Delivery could not be confirmed. Check Gmail Sent before retrying.',
            'empty': 'The notification was stored without any requests to include.',
        }.get(notice.status, 'Review the recorded notification status.')
    elif item.is_archived:
        explanation = 'This request is archived and is excluded from the agenda.'
    elif not actionable(item, now.date()):
        explanation = 'The current status or scheduled date does not qualify for today’s agenda.'
    elif now.time() < CUTOFF:
        explanation = 'The request qualifies for today, but the 06:30 GMT-3 cutoff has not been reached.'
    else:
        explanation = 'This request qualifies for today, but no notification coverage was recorded for today. The production send needs investigation.'
    return {'number': item.request_number, 'status': item.status, 'scheduled': due_date(item),
            'created': created.astimezone(LOCAL_TZ).strftime('%d/%m/%Y %H:%M:%S') if created else 'Not recorded',
            'now': now.strftime('%d/%m/%Y %H:%M:%S'), 'eligible': actionable(item, now.date()),
            'notice': notice, 'explanation': explanation}


@agenda_bp.post('/internal/jobs/finance-agenda')
def daily_job():
    expected = os.getenv('FINANCE_AGENDA_JOB_TOKEN', '')
    supplied = request.headers.get('Authorization', '')
    if len(expected) < 32 or not hmac.compare_digest(supplied, 'Bearer ' + expected):
        abort(403)
    try:
        from app.process_timing import reconcile_due
        reconcile_due()
    except Exception:
        db.session.rollback()
        current_app.logger.exception('Process timing calendar reconciliation failed')
    notice_id = queue_daily()
    if notice_id is None:
        return jsonify(status='before_cutoff')
    ok = deliver_agenda(notice_id)
    response = jsonify(status='ok' if ok else 'delivery_needs_review')
    response.headers['Cache-Control'] = 'no-store'
    return response, 200 if ok else 503
