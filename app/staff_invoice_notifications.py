"""One English notification for each successfully annulled staff invoice."""
import os
from datetime import datetime, timezone
from urllib.parse import urlsplit
from flask import current_app, render_template, url_for
from app import db
from app.google_mail import MailNotSent, MailDeliveryUnknown, send_notification_email
from app.models import AcademicStaff, StaffExamSessionsShare, StaffInvoiceCancellationNotification


def queue_invoice_cancellation(document, member_id):
    notice = StaffInvoiceCancellationNotification.query.filter_by(file_id=document.file_id).first()
    if notice:
        return notice.id
    member = db.session.get(AcademicStaff, member_id)
    notice = StaffInvoiceCancellationNotification(file_id=document.file_id, share_id=document.share_id,
        member_id=member_id, year=document.year, filename=document.filename,
        recipient=(member.email or '').strip() if member else '',
        recipient_name=member.full_name if member else 'Staff member')
    db.session.add(notice)
    db.session.flush()
    return notice.id


def deliver_invoice_cancellation(notice_id):
    notice = db.session.get(StaffInvoiceCancellationNotification, notice_id)
    if not notice or notice.status not in {'pending', 'failed'}:
        return bool(notice and notice.status == 'sent')
    claimed = StaffInvoiceCancellationNotification.query.filter(
        StaffInvoiceCancellationNotification.id == notice_id,
        StaffInvoiceCancellationNotification.status.in_(['pending', 'failed']),
    ).update({'status': 'sending'}, synchronize_session=False)
    db.session.commit()
    if not claimed:
        return False
    try:
        if not notice.recipient:
            member = db.session.get(AcademicStaff, notice.member_id)
            notice.recipient = (member.email or '').strip() if member else ''
        if not notice.recipient:
            raise MailNotSent('The staff member has no email address configured.')
        share = db.session.get(StaffExamSessionsShare, notice.share_id)
        if share is None:
            raise MailNotSent('The staff portal is no longer available.')
        callback = urlsplit(os.getenv('GOOGLE_OAUTH_REDIRECT_URI', 'https://portal.pathinternalportal.com/integrations/google/callback'))
        base = os.getenv('PORTAL_BASE_URL', f'{callback.scheme}://{callback.netloc}').rstrip('/')
        origin = urlsplit(base)
        local = origin.scheme == 'http' and origin.hostname in {'localhost','127.0.0.1'}
        if (origin.scheme != 'https' and not local) or not origin.netloc or origin.path or origin.query or origin.fragment:
            raise MailNotSent('Set PORTAL_BASE_URL to the production HTTPS origin')
        portal_url = base + url_for('staff.staff_exam_sessions', token=share.token, session_year=notice.year) + '#invoice-information-title'
        subject = f'Action required: your invoice has been cancelled — {notice.year}'
        text = (f'Dear {notice.recipient_name},\n\n'
            f'Your invoice "{notice.filename}" for your {notice.year} exam sessions has been cancelled because errors were identified in it.\n\n'
            'Please contact Administration to review the errors and confirm the corrections required. '
            'Once this review has been completed, please upload your corrected invoice through the Invoicing instructions section of your staff portal within the established deadlines.\n\n'
            'Important: Upload your corrected invoice once all your assigned exam sessions have been completed, '
            'and at least 2 business days before the scheduled payment date and time. Otherwise, your payment will be rescheduled.\n\n'
            f'Open your staff portal: {portal_url}\n\nPath International Examinations')
        html = render_template('staff_payments/invoice_cancellation_email.html', notice=notice, portal_url=portal_url)
        notice.gmail_message_id = send_notification_email(notice.recipient, subject, text, html,
            f'<staff-invoice-cancelled-{notice.id}@pathexaminations.com>')
        notice.status, notice.last_error = 'sent', None
        notice.sent_at = datetime.now(timezone.utc)
    except MailNotSent as exc:
        notice.status, notice.last_error = 'failed', str(exc)
    except MailDeliveryUnknown:
        notice.status, notice.last_error = 'unknown', 'Delivery not confirmed; verify Sent in Gmail before retrying.'
    except Exception:
        notice.status, notice.last_error = 'unknown', 'Notification delivery needs administrator review.'
        current_app.logger.warning('Staff invoice cancellation notification %s needs review.', notice_id)
    db.session.commit()
    return notice.status == 'sent'
