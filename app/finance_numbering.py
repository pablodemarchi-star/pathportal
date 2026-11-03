"""Persistent Finance counters survive request and event deletion."""
import json
import re

from sqlalchemy import func
from sqlalchemy.dialects.sqlite import insert
from app import db
from app.models import (FinanceSequence, FinanceAgendaNotification, FinanceAgendaCoverage,
    FinanceCompletionNotification, PaymentReviewNotification, GoogleDriveUpload,
    GoogleDriveInvoiceUpload, PaymentRequest, BillingRequest, PaymentRequestEvent, BillingRequestEvent)


def advance(scope, minimum):
    statement = insert(FinanceSequence).values(scope=scope, last_value=minimum + 1)
    statement = statement.on_conflict_do_update(index_elements=['scope'],
        set_={'last_value': func.max(FinanceSequence.last_value, minimum) + 1})
    # The atomic upsert reserves a distinct value while holding the write lock.
    return db.session.execute(statement.returning(FinanceSequence.last_value)).scalar_one()


def next_number(model, prefix, year, legacy_prefixes=()):
    scope = f'number:{prefix}:{year}'
    prefixes = (prefix, *legacy_prefixes)
    pattern = re.compile(r'^(?:' + '|'.join(re.escape(value) for value in prefixes) + rf')-{year}-(\d+)$')
    def suffix(value):
        match = pattern.fullmatch(value or '')
        return int(match.group(1)) if match else 0
    highest = max((suffix(number) for (number,) in db.session.query(model.request_number).filter(
        model.request_number.like(f'%-{year}-%')).all()), default=0)
    if db.session.get(FinanceSequence, scope) is None:
        # Recover deleted numbers that remain in historical email snapshots.
        for (number,) in db.session.query(FinanceCompletionNotification.request_number).all():
            highest = max(highest, suffix(number))
        for (payload,) in db.session.query(FinanceAgendaNotification.payload).all():
            try:
                rows = json.loads(payload)
                for row in rows if isinstance(rows, list) else []:
                    if isinstance(row, dict):
                        highest = max(highest, suffix(row.get('number')))
            except (ValueError, TypeError):
                continue
    return f'{prefix}-{year}-{advance(scope, highest):04d}'


def next_identity(model):
    """Do not reuse IDs referenced by historical notification/delivery records."""
    references = []
    if model in (PaymentRequest, BillingRequest):
        kind = 'payment' if model is PaymentRequest else 'invoice'
        references = [
            db.session.query(func.max(FinanceAgendaCoverage.request_id)).filter_by(request_kind=kind).scalar(),
            db.session.query(func.max(FinanceCompletionNotification.request_id)).filter_by(request_kind=kind).scalar(),
        ]
        if model is PaymentRequest:
            references += [db.session.query(func.max(PaymentReviewNotification.payment_request_id)).scalar(),
                db.session.query(func.max(GoogleDriveUpload.payment_request_id)).scalar()]
        else:
            references += [db.session.query(func.max(GoogleDriveInvoiceUpload.billing_request_id)).scalar()]
    elif model in (PaymentRequestEvent, BillingRequestEvent):
        kind = 'payment' if model is PaymentRequestEvent else 'invoice'
        references = [db.session.query(func.max(FinanceCompletionNotification.event_id)).filter_by(request_kind=kind).scalar()]
        if model is PaymentRequestEvent:
            references += [db.session.query(func.max(PaymentReviewNotification.review_event_id)).scalar()]
    maximum = max([db.session.query(func.max(model.id)).scalar() or 0] + [value or 0 for value in references])
    return advance('identity:' + model.__tablename__, maximum)


def remember_deleted_request(item):
    """Reserve legacy numbers too, even if the first action after deploy is deletion."""
    def retain(scope, value):
        statement = insert(FinanceSequence).values(scope=scope, last_value=value)
        db.session.execute(statement.on_conflict_do_update(index_elements=['scope'],
            set_={'last_value': func.max(FinanceSequence.last_value, value)}))
    match = re.fullmatch(r'(PAY|INVOICE|BILL)-(\d{4})-(\d+)', item.request_number or '')
    if match:
        prefix, year, number = match.groups()
        retain(f"number:{'INVOICE' if prefix == 'BILL' else prefix}:{year}", int(number))
    retain('identity:' + item.__tablename__, item.id)
    event_model = PaymentRequestEvent if isinstance(item, PaymentRequest) else BillingRequestEvent
    event_max = max((event.id for event in item.events), default=0)
    if event_max:
        retain('identity:' + event_model.__tablename__, event_max)
