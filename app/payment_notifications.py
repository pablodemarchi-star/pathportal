"""One management email for each submission/re-submission review event."""
import os
from datetime import datetime, timezone
from urllib.parse import urlsplit

from flask import current_app, render_template, url_for

from app import db
from app.google_mail import MailDeliveryUnknown, MailNotSent, send_notification_email
from app.models import PaymentRequestEvent, PaymentReviewNotification

REVIEW_STATUSES = {"Submitted", "Pending approval", "Resubmitted"}
RECIPIENT = "pablo.demarchi@pathexaminations.com"


def latest_review_event(payment):
    return PaymentRequestEvent.query.filter(
        PaymentRequestEvent.payment_request_id == payment.id,
        PaymentRequestEvent.event_type.in_(REVIEW_STATUSES),
        PaymentRequestEvent.new_status.in_(REVIEW_STATUSES),
    ).order_by(PaymentRequestEvent.id.desc()).first()


def queue_management_notification(payment):
    if payment.is_archived or payment.status not in REVIEW_STATUSES:
        return None
    db.session.flush()
    event = latest_review_event(payment)
    if not event:
        return None
    notification = PaymentReviewNotification.query.filter_by(review_event_id=event.id).first()
    if notification is None:
        notification = PaymentReviewNotification(payment=payment, review_event_id=event.id, recipient=RECIPIENT)
        db.session.add(notification)
        db.session.flush()
    return notification.id


def email_review_is_current(payment, event_id):
    event = latest_review_event(payment)
    return bool(not payment.is_archived and payment.status in REVIEW_STATUSES and event and event.id == event_id)


def deliver_management_notification(notification_id):
    if not notification_id:
        return False
    notification = db.session.get(PaymentReviewNotification, notification_id)
    if not notification or notification.status not in {"pending", "failed"}:
        return False
    if not email_review_is_current(notification.payment, notification.review_event_id):
        notification.status = "cancelled"
        db.session.commit()
        return False
    # Atomic claim prevents two workers from sending the same review notification.
    claimed = PaymentReviewNotification.query.filter(
        PaymentReviewNotification.id == notification_id,
        PaymentReviewNotification.status.in_(["pending", "failed"]),
    ).update({"status": "sending"}, synchronize_session=False)
    db.session.commit()
    if not claimed:
        return False
    try:
        callback = urlsplit(os.getenv("GOOGLE_OAUTH_REDIRECT_URI", "https://portal.pathinternalportal.com/integrations/google/callback"))
        base = os.getenv("PORTAL_BASE_URL", f"{callback.scheme}://{callback.netloc}").rstrip("/")
        parsed = urlsplit(base)
        local_http = parsed.scheme == "http" and parsed.hostname in {"127.0.0.1", "localhost"}
        if (parsed.scheme != "https" and not local_http) or not parsed.netloc or parsed.query or parsed.fragment or parsed.path:
            raise MailNotSent("Set PORTAL_BASE_URL to the production HTTPS origin")
        payment = notification.payment
        from app.routes import payment_amount_is_pending
        amount_pending = payment_amount_is_pending(payment)
        primary_action = ("set_amount", "Set amount & review", "#00506b") if amount_pending else ("approve", "Approve", "#00506b")
        actions = [{"action": action, "label": label, "color": color, "url": base + url_for(
            "staff.payment_request_email_review", payment_id=notification.payment.id, action=action,
            review_event_id=notification.review_event_id)} for action, label, color in [
                primary_action, ("reject", "Reject", "#b42318"),
                ("needs_correction", "Mark discrepancy", "#8a6328")]]
        amount_display = "Amount pending" if amount_pending else f"{payment.currency} {payment.amount:,.2f}"
        # Current forms store both specific dates and the next payment run here.
        # Retain the legacy requested date only for older requests without it.
        payment_date = payment.scheduled_payment_date or payment.requested_payment_date
        requested_date = payment_date.strftime("%d/%m/%Y") if payment_date else "As soon as possible"
        requester = payment.requester.full_name if payment.requester else payment.requester_department or "Not specified"
        introduction = "A payment request needs an amount before it can be approved. Set the amount in Management review, then review your decision." if amount_pending else "A payment request is awaiting your approval in Management review."
        text = (f"Dear Pablo,\n\n{introduction}\n\n"
                f"Request: {payment.request_number}\nRequested by: {requester}\n"
                f"Concept: {payment.concept_name_snapshot}\nPayee: {payment.payee_name_snapshot or 'Not specified'}\n"
                f"Amount: {amount_display}\nRequested payment date: {requested_date}\n\n"
                f"Description: {payment.description}\n\n" +
                "\n".join(f"{item['label']}: {item['url']}" for item in actions) +
                "\n\nEach button opens the portal to confirm your decision. Sign-in with review permissions is required. "
                "A reason is required when rejecting a request or marking a discrepancy.\n\nPath International Examinations")
        html = render_template("finance_requests/management_notification_email.html", payment=payment, actions=actions,
                               amount_display=amount_display, requested_date=requested_date, requester=requester, amount_pending=amount_pending)
        notification.gmail_message_id = send_notification_email(notification.recipient,
            f"New payment request awaiting approval — {payment.request_number}", text, html,
            f"<payment-review-{notification.review_event_id}@pathexaminations.com>")
        notification.status, notification.last_error = "sent", None
        notification.sent_at = datetime.now(timezone.utc)
    except MailNotSent as exc:
        notification.status, notification.last_error = "failed", str(exc)
    except MailDeliveryUnknown:
        notification.status, notification.last_error = "unknown", "Delivery not confirmed; verify Sent in Gmail before retrying."
    except Exception:
        # A claimed message must never be sent again blindly after an unexpected error.
        notification.status, notification.last_error = "unknown", "Notification delivery needs administrator review."
        current_app.logger.warning("Management notification %s needs review", notification_id)
    db.session.commit()
    return notification.status == "sent"
