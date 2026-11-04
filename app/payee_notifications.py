"""Independent, retryable Payee notices and receipt-only private links."""
import json
import os
import re
import secrets
from datetime import datetime, timedelta, timezone
from urllib.parse import urlsplit, unquote, parse_qs
from flask import Blueprint, abort, current_app, g, has_request_context, redirect, render_template, send_from_directory, url_for
from app import db
from app.google_mail import MailNotSent, MailDeliveryUnknown, send_notification_email
from app.models import PayeePaymentNotification, ClientInvoiceNotification, GoogleDriveUpload, GoogleDriveInvoiceUpload

payee_bp = Blueprint('payee_notifications', __name__)


PAYEE_EMAIL_COPY = {
    'en': {
        'subject':'Payment completed', 'status':'Payment completed',
        'heading':'Your payment has been completed.', 'greeting':'Dear',
        'intro':'We are pleased to confirm that your payment has been made. You can access your receipt below.',
        'reference':'Payment reference', 'amount':'Amount', 'concept':'Concept', 'method':'Payment method',
        'date':'Payment date', 'receipt':'View payment receipt',
        'contact':'If you have any questions, please contact', 'footer':'Automated payment notification',
    },
    'sp': {
        'subject':'Pago realizado', 'status':'Pago realizado',
        'heading':'Tu pago ha sido realizado.', 'greeting':'Hola',
        'intro':'Te informamos que tu pago ha sido realizado. Podés consultar el comprobante a continuación.',
        'reference':'Referencia del pago', 'amount':'Importe', 'concept':'Concepto', 'method':'Medio de pago',
        'date':'Fecha de pago', 'receipt':'Ver comprobante de pago',
        'contact':'Si tenés alguna consulta, escribinos a', 'footer':'Aviso automático de pago',
    },
}
CLIENT_EMAIL_COPY = {
    'en': {**PAYEE_EMAIL_COPY['en'], 'subject':'Invoice issued', 'status':'Invoice issued',
        'heading':'Your invoice has been issued.',
        'intro':'Your invoice is now available. You can access it using the link below.',
        'reference':'Invoice request reference', 'invoice_number':'Invoice number',
        'date':'Issue date', 'receipt':'View invoice', 'footer':'Automated invoice notification'},
    'sp': {**PAYEE_EMAIL_COPY['sp'], 'subject':'Factura emitida', 'status':'Factura emitida',
        'heading':'Tu factura ha sido emitida.',
        'intro':'Tu factura ya está disponible. Podés consultarla mediante el enlace a continuación.',
        'reference':'Referencia de la solicitud', 'invoice_number':'Número de factura',
        'date':'Fecha de emisión', 'receipt':'Ver factura', 'footer':'Aviso automático de factura'},
}
SPANISH_METHODS = {
    'Bank transfer':'Transferencia bancaria', 'Deposit':'Depósito', 'Cash':'Efectivo', 'Card':'Tarjeta',
    'Electronic Payment Slip (EPS)':'Boleta de pago electrónico (EPS)', 'Direct debit':'Débito automático',
    'UK bank transfer':'Transferencia bancaria en el Reino Unido',
}


def valid_notification_email(value):
    from email.headerregistry import Address
    from app.validators import EMAIL_RE
    if not value or len(value) > 254 or not EMAIL_RE.fullmatch(value):
        return False
    try:
        address = Address(addr_spec=value)
        return bool(address.username and address.domain)
    except (ValueError, IndexError):
        return False


def receipt_manifest(payment, kind='payment'):
    invoice = kind == 'invoice'
    document_model = GoogleDriveInvoiceUpload if invoice else GoogleDriveUpload
    owner_key = 'billing_request_id' if invoice else 'payment_request_id'
    destination_key = 'finance_invoice_proofs' if invoice else 'finance_payment_receipts'
    local_category = 'invoice_proofs' if invoice else 'payment_proofs'
    receipts = []
    for address in ((payment.invoice_link if invoice else payment.payment_proof_url) or '').splitlines():
        parsed = urlsplit(address.strip())
        path = unquote(parsed.path)
        match = re.fullmatch(r'/finance-requests/drive-documents/([A-Za-z0-9_-]+)', path)
        drive_match = re.fullmatch(r'/file/d/([A-Za-z0-9_-]+)/?(?:view|preview)?', path) if parsed.hostname in {'drive.google.com', 'docs.google.com'} else None
        if not drive_match and parsed.hostname in {'drive.google.com', 'docs.google.com'}:
            drive_id = parse_qs(parsed.query).get('id', [''])[0]
            if re.fullmatch(r'[A-Za-z0-9_-]{10,160}', drive_id):
                drive_match = re.fullmatch(r'([A-Za-z0-9_-]+)', drive_id)
            else:
                raise MailNotSent('Use an uploaded receipt file instead of a Google Drive folder link.')
        if match or drive_match:
            file_id = (match or drive_match).group(1)
            document = document_model.query.filter_by(file_id=file_id, destination_key=destination_key,
                **{owner_key:payment.id}).first()
            if not document:
                raise MailNotSent('The payment receipt is unavailable or does not belong to this payment.')
            receipts.append({'kind':'drive', 'file_id':file_id, 'name':document.filename})
        elif path.startswith('/finance-requests/uploads/'):
            from werkzeug.utils import secure_filename
            relative = path[len('/finance-requests/uploads/'):]
            parts = relative.split('/')
            if len(parts) != 3 or parts[0] != local_category or parts[1] != secure_filename(payment.request_number) or parts[2] != secure_filename(parts[2]):
                raise MailNotSent('The receipt does not belong to this payment.')
            from app.routes import finance_upload_root
            from werkzeug.security import safe_join
            local_path = safe_join(finance_upload_root(), relative)
            if not local_path or not os.path.isfile(local_path):
                raise MailNotSent('The payment receipt file is unavailable.')
            receipts.append({'kind':'local', 'path':relative, 'name':parts[-1]})
        elif parsed.scheme in {'https', 'http'} and parsed.hostname:
            from app.google_mail import configuration
            portal_hosts = {urlsplit(os.getenv('PORTAL_BASE_URL', '')).hostname,
                            urlsplit(configuration()['GOOGLE_OAUTH_REDIRECT_URI']).hostname,
                            'portal.pathinternalportal.com', '127.0.0.1', 'localhost'}
            if parsed.hostname in portal_hosts:
                raise MailNotSent('The receipt link cannot be shared externally.')
            receipts.append({'kind':'external', 'url':address.strip(), 'name':'Payment receipt'})
        else:
            raise MailNotSent('A valid payment receipt is required before notifying the Payee.')
    if not receipts:
        raise MailNotSent('A payment receipt is required before notifying the Payee.')
    return receipts


def queue_payee_notification(payment, previous, status, transition, kind='payment'):
    invoice = kind == 'invoice'
    completed = 'Invoice issued' if invoice else 'Payment completed'
    model = ClientInvoiceNotification if invoice else PayeePaymentNotification
    if previous == status or status != completed or not payment.automatic_payment_notification:
        return None
    db.session.flush()
    notice = model.query.filter_by(event_id=transition.id).first()
    if notice:
        return notice.id
    completed_at = (getattr(transition, 'created_at', None) if invoice else payment.payment_completed_at) or datetime.now(timezone.utc)
    if completed_at.tzinfo is None:
        completed_at = completed_at.replace(tzinfo=timezone.utc)
    payload = {'name':(payment.client_name_snapshot if invoice else payment.payee_name_snapshot) or ('Client' if invoice else 'Payee'), 'request_number':payment.request_number,
               'amount':f'{payment.currency} {payment.amount:,.2f}', 'concept':payment.concept_name_snapshot,
               'method':None if invoice else payment.payment_method, 'invoice_number':payment.invoice_number if invoice else None, 'language':payment.payment_notification_language or 'en',
               'amount_sp':f'{payment.currency} {payment.amount:,.2f}'.replace(',', '_').replace('.', ',').replace('_', '.'),
               'date':completed_at.astimezone(timezone(timedelta(hours=-3))).strftime('%d/%m/%Y')}
    notice = model(**{'billing' if invoice else 'payment':payment}, event_id=transition.id,
        recipient=payment.payment_notification_email or '', receipt_token=secrets.token_urlsafe(32), payload=json.dumps(payload))
    db.session.add(notice); db.session.flush()
    if has_request_context():
        g.setdefault('_client_pending' if invoice else '_payee_pending', []).append(notice.id)
    return notice.id


def portal_origin():
    from app.google_mail import configuration
    callback = urlsplit(configuration()['GOOGLE_OAUTH_REDIRECT_URI'])
    origin = os.getenv('PORTAL_BASE_URL', f'{callback.scheme}://{callback.netloc}').rstrip('/')
    parsed = urlsplit(origin)
    if (parsed.scheme != 'https' and not (parsed.scheme == 'http' and parsed.hostname in {'localhost','127.0.0.1'})) or not parsed.netloc or parsed.path or parsed.query or parsed.fragment:
        raise MailNotSent('Set PORTAL_BASE_URL to the production HTTPS origin.')
    return origin


def deliver_payee_notification(notice_id, kind='payment'):
    invoice = kind == 'invoice'
    model = ClientInvoiceNotification if invoice else PayeePaymentNotification
    notice = db.session.get(model, notice_id)
    if not notice or notice.status not in {'pending', 'failed'}:
        return bool(notice and notice.status == 'sent')
    payment = notice.billing if invoice else notice.payment
    if not payment or payment.is_archived or payment.status != ('Invoice issued' if invoice else 'Payment completed'):
        notice.status = 'cancelled'; db.session.commit(); return False
    claimed = model.query.filter(model.id == notice_id,
        model.status.in_(['pending','failed'])).update({'status':'sending'}, synchronize_session=False)
    db.session.commit()
    if not claimed:
        return False
    try:
        if not valid_notification_email(notice.recipient):
            raise MailNotSent('The Payee notification email is invalid.')
        details = json.loads(notice.payload)
        # Freeze only the receipts for this completed payment, never expose a portal session.
        if 'receipts' not in details:
            details['receipts'] = receipt_manifest(payment, kind)
            notice.payload = json.dumps(details)
            db.session.commit()
        origin = portal_origin()
        links = [origin + url_for('payee_notifications.invoice' if invoice else 'payee_notifications.receipt', token=notice.receipt_token, index=index)
                 for index, _ in enumerate(details['receipts'])]
        language = details.get('language', 'en')
        email_copy = CLIENT_EMAIL_COPY if invoice else PAYEE_EMAIL_COPY
        if language not in email_copy:
            raise MailNotSent('Select a valid language (EN or SP) for the Payee notification.')
        copy = email_copy[language]
        display = dict(details)
        if language == 'sp':
            display['amount'] = details.get('amount_sp', details['amount'])
            if not invoice:
                display['method'] = SPANISH_METHODS.get(details.get('method'), details.get('method', 'No especificado'))
        text = (f"{copy['greeting']} {display['name']},\n\n{copy['heading']}\n"
                f"{copy['reference']}: {display['request_number']}\n{copy['amount']}: {display['amount']}\n"
                f"{copy['concept']}: {display['concept']}\n" +
                (f"{copy['method']}: {display.get('method', 'Not specified')}\n" if not invoice else '') +
                (f"{copy['invoice_number']}: {display['invoice_number']}\n" if invoice and display.get('invoice_number') else '') +
                f"{copy['date']}: {display['date']}\n\n" +
                '\n'.join(f"{copy['receipt']}: {link}" for link in links) +
                f"\n\n{copy['contact']} admin@pathexaminations.com.\n\nPath International Examinations")
        html = render_template('finance_requests/payee_payment_email.html', details=display, receipt_links=links,
                               copy=copy, language=language)
        notice.gmail_message_id = send_notification_email(notice.recipient, f"{copy['subject']} — {details['request_number']}",
            text, html, f'<{"client-invoice" if invoice else "payee-payment"}-{notice.id}@pathexaminations.com>')
        notice.status, notice.last_error = 'sent', None
        notice.sent_at = datetime.now(timezone.utc)
    except MailNotSent as exc:
        notice.status, notice.last_error = 'failed', str(exc)
    except MailDeliveryUnknown:
        notice.status, notice.last_error = 'unknown', 'Delivery not confirmed; verify Sent in Gmail before retrying.'
    except Exception:
        notice.status, notice.last_error = 'unknown', 'Payee notification needs administrator review.'
        current_app.logger.warning('Payee notification %s needs review.', notice_id)
    db.session.commit()
    return notice.status == 'sent'



def queue_client_notification(billing, previous, status, transition):
    return queue_payee_notification(billing, previous, status, transition, kind='invoice')


def deliver_client_notification(notice_id):
    return deliver_payee_notification(notice_id, kind='invoice')


@payee_bp.get('/payment-receipts/<token>/<int:index>')
def receipt(token, index):
    return external_document_response(token, index, 'payment')


@payee_bp.get('/invoice-documents/<token>/<int:index>')
def invoice(token, index):
    return external_document_response(token, index, 'invoice')


def external_document_response(token, index, kind):
    is_invoice = kind == 'invoice'
    model = ClientInvoiceNotification if is_invoice else PayeePaymentNotification
    notice = model.query.filter_by(receipt_token=token).first_or_404()
    record = notice.billing if is_invoice else notice.payment
    if not record or record.is_archived or record.status != ('Invoice issued' if is_invoice else 'Payment completed'):
        abort(404)
    receipts = json.loads(notice.payload).get('receipts', [])
    if index >= len(receipts):
        abort(404)
    item = receipts[index]
    if item['kind'] == 'drive':
        from app.google_drive import stream_document
        document_model = GoogleDriveInvoiceUpload if is_invoice else GoogleDriveUpload
        owner = {'billing_request_id' if is_invoice else 'payment_request_id':record.id}
        document = document_model.query.filter_by(file_id=item['file_id'],
            destination_key='finance_invoice_proofs' if is_invoice else 'finance_payment_receipts', **owner).first_or_404()
        response = stream_document(document)
    elif item['kind'] == 'local':
        from app.routes import finance_upload_root
        response = send_from_directory(finance_upload_root(), item['path'], as_attachment=True)
    else:
        response = redirect(item['url'])
    response.headers['Cache-Control'] = 'private, no-store'
    response.headers['Referrer-Policy'] = 'no-referrer'
    response.headers['X-Robots-Tag'] = 'noindex, nofollow'
    return response
