"""Administrator-managed Google authorization for notification email."""
import base64
import hashlib
import hmac
import json
import os
import secrets
import tempfile
import time
from email.message import EmailMessage
from functools import wraps
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit
from urllib.request import Request, urlopen

from flask import Blueprint, abort, current_app, flash, g, redirect, render_template, request, session, url_for

from app import login_required, validate_csrf

google_mail_bp = Blueprint("google_mail", __name__)
SEND_SCOPE = "https://www.googleapis.com/auth/gmail.send"
SCOPES = "openid email " + SEND_SCOPE
EXPECTED_ACCOUNT = "pablo.demarchi@pathexaminations.com"


def administrator(view):
    @wraps(view)
    @login_required
    def wrapped(*args, **kwargs):
        user = getattr(g, "current_user", None)
        if not (user and user.is_active and user.is_superadmin) and not (
            not g.user_id and g.user_department == "Admin"
        ):
            abort(403)
        return view(*args, **kwargs)
    return wrapped


def configuration():
    return {key: os.getenv(key, "").strip() for key in (
        "GOOGLE_OAUTH_CLIENT_ID", "GOOGLE_OAUTH_CLIENT_SECRET", "GOOGLE_OAUTH_REDIRECT_URI"
    )}


def configured():
    values = configuration()
    target = urlsplit(values["GOOGLE_OAUTH_REDIRECT_URI"])
    return all(values.values()) and target.path == "/integrations/google/callback" and (
        target.scheme == "https" or target.scheme == "http" and target.hostname in {"localhost", "127.0.0.1"}
    ) and not target.query and not target.fragment


def token_path():
    return Path(os.getenv("GMAIL_TOKEN_FILE") or Path(current_app.instance_path) / "google_gmail_token.json")


def read_connection():
    try:
        return json.loads(token_path().read_text())
    except FileNotFoundError:
        return {}


def save_connection(value):
    path = token_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=".gmail-", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w") as stream:
            json.dump(value, stream)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def google_json(url, *, fields=None, bearer=None, json_body=None, timeout=15):
    headers = {"Accept": "application/json"}
    body = None
    if fields is not None:
        body = urlencode(fields).encode()
        headers["Content-Type"] = "application/x-www-form-urlencoded"
    if bearer:
        headers["Authorization"] = "Bearer " + bearer
    if json_body is not None:
        body = json.dumps(json_body).encode()
        headers["Content-Type"] = "application/json"
    with urlopen(Request(url, data=body, headers=headers), timeout=timeout) as response:
        return json.load(response)


class MailNotSent(Exception):
    pass


class MailDeliveryUnknown(Exception):
    pass


def send_notification_email(recipient, subject, text, html, message_id):
    """Send once. Never retry an ambiguous delivery automatically."""
    if current_app.testing and not current_app.config.get("MAIL_DELIVERY_IN_TESTS"):
        raise MailNotSent("Delivery is disabled in tests")
    try:
        saved = read_connection()
        values = configuration()
        if not configured() or saved.get("account") != os.getenv("GMAIL_ACCOUNT_EMAIL", EXPECTED_ACCOUNT).lower() or saved.get("client_id") != values["GOOGLE_OAUTH_CLIENT_ID"] or not saved.get("refresh_token"):
            raise MailNotSent("Connect the designated Google account first")
        tokens = google_json("https://oauth2.googleapis.com/token", timeout=8, fields={
            "grant_type": "refresh_token", "client_id": values["GOOGLE_OAUTH_CLIENT_ID"],
            "client_secret": values["GOOGLE_OAUTH_CLIENT_SECRET"], "refresh_token": saved["refresh_token"],
        })
        access_token = tokens["access_token"]
        if tokens.get("refresh_token"):
            save_connection({**saved, "refresh_token": tokens["refresh_token"]})
        message = EmailMessage()
        message["From"] = os.getenv("GMAIL_FROM_EMAIL", "no-reply@pathexaminations.com")
        message["To"], message["Subject"], message["Message-ID"] = recipient, subject, message_id
        message.set_content(text)
        message.add_alternative(html, subtype="html")
    except (OSError, ValueError, KeyError) as exc:
        raise MailNotSent("Google authorization or message preparation failed") from exc
    try:
        result = google_json("https://gmail.googleapis.com/gmail/v1/users/me/messages/send", bearer=access_token,
                             json_body={"raw": base64.urlsafe_b64encode(message.as_bytes()).decode()}, timeout=10)
        if not result.get("id"):
            raise MailDeliveryUnknown("Google did not confirm delivery")
        return result["id"]
    except HTTPError as exc:
        if exc.code < 500:
            raise MailNotSent("Google rejected the message") from exc
        raise MailDeliveryUnknown("Google delivery was not confirmed") from exc
    except (OSError, ValueError) as exc:
        raise MailDeliveryUnknown("Google delivery was not confirmed") from exc


@google_mail_bp.after_request
def private_response(response):
    response.headers["Cache-Control"] = "private, no-store"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin" if request.endpoint == "google_mail.settings" else "no-referrer"
    return response


@google_mail_bp.get("/integrations/google")
@administrator
def settings():
    session.setdefault("csrf_token", secrets.token_urlsafe(32))
    from app.models import PaymentReviewNotification, FinanceCompletionNotification, FinanceAgendaNotification, StaffInvoiceCancellationNotification, PayeePaymentNotification, ClientInvoiceNotification
    retry_count = PaymentReviewNotification.query.filter(PaymentReviewNotification.status.in_(["pending", "failed"])).count()
    uncertain_count = PaymentReviewNotification.query.filter(PaymentReviewNotification.status.in_(["sending", "unknown"])).count()
    retry_count += FinanceCompletionNotification.query.filter(FinanceCompletionNotification.status.in_(["pending", "failed"])).count()
    uncertain_count += FinanceCompletionNotification.query.filter(FinanceCompletionNotification.status.in_(["sending", "unknown"])).count()
    retry_count += PayeePaymentNotification.query.filter(PayeePaymentNotification.status.in_(['pending', 'failed'])).count()
    uncertain_count += PayeePaymentNotification.query.filter(PayeePaymentNotification.status.in_(['sending', 'unknown'])).count()
    retry_count += ClientInvoiceNotification.query.filter(ClientInvoiceNotification.status.in_(['pending', 'failed'])).count()
    uncertain_count += ClientInvoiceNotification.query.filter(ClientInvoiceNotification.status.in_(['sending', 'unknown'])).count()
    retry_count += FinanceAgendaNotification.query.filter(FinanceAgendaNotification.status.in_(["pending", "failed"])).count()
    uncertain_count += FinanceAgendaNotification.query.filter(FinanceAgendaNotification.status.in_(["sending", "unknown"])).count()
    retry_count += StaffInvoiceCancellationNotification.query.filter(StaffInvoiceCancellationNotification.status.in_(["pending", "failed"])).count()
    uncertain_count += StaffInvoiceCancellationNotification.query.filter(StaffInvoiceCancellationNotification.status.in_(["sending", "unknown"])).count()
    try:
        saved = read_connection()
        connected = bool(saved.get("refresh_token"))
    except (OSError, ValueError):
        saved, connected = {}, False
        flash("The saved Google connection could not be read. Check the server configuration.", "error")
    values = configuration()
    from app.google_drive import settings_context
    from app.finance_agenda import request_delivery_diagnostic
    return render_template("integrations/google.html", configured=configured(), connected=connected,
        account=saved.get("account") if connected else os.getenv("GMAIL_ACCOUNT_EMAIL", EXPECTED_ACCOUNT),
        sender=os.getenv("GMAIL_FROM_EMAIL", "no-reply@pathexaminations.com"),
        callback_uri=values["GOOGLE_OAUTH_REDIRECT_URI"], csrf_token=session.get("csrf_token"),
        retry_count=retry_count, uncertain_count=uncertain_count,
        finance_diagnostic=request_delivery_diagnostic(request.args.get("finance_request")), **settings_context(saved))


@google_mail_bp.post("/integrations/google/retry-payment-notifications")
@administrator
def retry_payment_notifications():
    from app.models import PaymentReviewNotification, FinanceCompletionNotification, FinanceAgendaNotification, StaffInvoiceCancellationNotification, PayeePaymentNotification, ClientInvoiceNotification
    from app.payment_notifications import deliver_management_notification
    if not validate_csrf():
        abort(400)
    ids = [row.id for row in PaymentReviewNotification.query.filter(
        PaymentReviewNotification.status.in_(["pending", "failed"])
    ).order_by(PaymentReviewNotification.id).limit(50).all()]
    sent = sum(deliver_management_notification(notification_id) for notification_id in ids)
    from app.payee_notifications import deliver_payee_notification
    payee_ids = [row.id for row in PayeePaymentNotification.query.filter(
        PayeePaymentNotification.status.in_(['pending', 'failed'])).order_by(PayeePaymentNotification.id).limit(50).all()]
    sent += sum(deliver_payee_notification(notice_id) for notice_id in payee_ids)
    from app.payee_notifications import deliver_client_notification
    client_ids = [row.id for row in ClientInvoiceNotification.query.filter(
        ClientInvoiceNotification.status.in_(['pending', 'failed'])).order_by(ClientInvoiceNotification.id).limit(50).all()]
    sent += sum(deliver_client_notification(notice_id) for notice_id in client_ids)
    from app.finance_completion import deliver_completion
    completion_ids = [row.id for row in FinanceCompletionNotification.query.filter(
        FinanceCompletionNotification.status.in_(["pending", "failed"])
    ).order_by(FinanceCompletionNotification.id).limit(50).all()]
    sent += sum(deliver_completion(notice_id) for notice_id in completion_ids)
    from app.finance_agenda import deliver_agenda
    agenda_ids = [row.id for row in FinanceAgendaNotification.query.filter(
        FinanceAgendaNotification.status.in_(["pending", "failed"])
    ).order_by(FinanceAgendaNotification.id).limit(50).all()]
    sent += sum(deliver_agenda(notice_id) for notice_id in agenda_ids)
    from app.staff_invoice_notifications import deliver_invoice_cancellation
    cancellation_ids = [row.id for row in StaffInvoiceCancellationNotification.query.filter(
        StaffInvoiceCancellationNotification.status.in_(["pending", "failed"])
    ).order_by(StaffInvoiceCancellationNotification.id).limit(50).all()]
    sent += sum(deliver_invoice_cancellation(notice_id) for notice_id in cancellation_ids)
    flash(f"{sent} finance notifications sent. Unconfirmed deliveries were not retried.", "success")
    return redirect(url_for("google_mail.settings"))


@google_mail_bp.post("/integrations/google/connect")
@administrator
def connect():
    if not validate_csrf():
        abort(400)
    if not configured():
        flash("Configure the Google credentials on this server first.", "error")
        return redirect(url_for("google_mail.settings"))
    # The callback must return to this browser's portal session, on the same origin.
    target = urlsplit(configuration()["GOOGLE_OAUTH_REDIRECT_URI"])
    if target.netloc != request.host:
        flash("Open the portal at the configured callback domain before connecting Google.", "error")
        return redirect(url_for("google_mail.settings"))
    from app.google_drive import DRIVE_SCOPE, drive_connected
    try:
        was_drive_connected = drive_connected()
    except (OSError, ValueError):
        was_drive_connected = False
    want_drive = request.form.get("enable_drive") == "1" or was_drive_connected
    scopes = SCOPES + (" " + DRIVE_SCOPE if want_drive else "")
    state, verifier = secrets.token_urlsafe(32), secrets.token_urlsafe(64)
    session["google_mail_oauth"] = {"state": state, "verifier": verifier, "started": time.time(), "drive": want_drive}
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip("=")
    return redirect("https://accounts.google.com/o/oauth2/v2/auth?" + urlencode({
        "client_id": configuration()["GOOGLE_OAUTH_CLIENT_ID"],
        "redirect_uri": configuration()["GOOGLE_OAUTH_REDIRECT_URI"],
        "response_type": "code", "scope": scopes, "access_type": "offline", "prompt": "consent",
        "include_granted_scopes": "true",
        "state": state, "code_challenge": challenge, "code_challenge_method": "S256",
        "login_hint": os.getenv("GMAIL_ACCOUNT_EMAIL", EXPECTED_ACCOUNT), "hd": "pathexaminations.com",
    }))


@google_mail_bp.get("/integrations/google/callback")
@administrator
def callback():
    pending = session.pop("google_mail_oauth", {})
    received = request.args.get("state", "")
    if not pending or not received or not hmac.compare_digest(received, pending.get("state", "")) or time.time() - pending.get("started", 0) > 600:
        flash("Google authorization expired or did not match this session. Please connect again.", "error")
        return redirect(url_for("google_mail.settings"))
    if request.args.get("error") or not request.args.get("code"):
        flash("Google authorization was not completed. The existing connection has not changed.", "error")
        return redirect(url_for("google_mail.settings"))
    if not configured():
        abort(503)
    try:
        values = configuration()
        tokens = google_json("https://oauth2.googleapis.com/token", fields={
            "code": request.args["code"], "client_id": values["GOOGLE_OAUTH_CLIENT_ID"],
            "client_secret": values["GOOGLE_OAUTH_CLIENT_SECRET"], "redirect_uri": values["GOOGLE_OAUTH_REDIRECT_URI"],
            "grant_type": "authorization_code", "code_verifier": pending["verifier"],
        })
        granted = set(tokens.get("scope", "").split())
        if SEND_SCOPE not in granted:
            flash("Permission to send email was not granted. Please connect again and allow it.", "error")
            return redirect(url_for("google_mail.settings"))
        from app.google_drive import DRIVE_SCOPE
        if pending.get("drive") and DRIVE_SCOPE not in granted:
            flash("Drive permission was not granted. The existing connection has not changed.", "error")
            return redirect(url_for("google_mail.settings"))
        identity = google_json("https://openidconnect.googleapis.com/v1/userinfo", bearer=tokens["access_token"])
        expected = os.getenv("GMAIL_ACCOUNT_EMAIL", EXPECTED_ACCOUNT).lower()
        if identity.get("email", "").lower() != expected or identity.get("email_verified") is not True:
            flash("Authorize the designated Path account. The existing connection has not changed.", "error")
            return redirect(url_for("google_mail.settings"))
        if not tokens.get("refresh_token"):
            flash("Google did not provide offline authorization. Please reconnect and grant consent.", "error")
            return redirect(url_for("google_mail.settings"))
        save_connection({"account": expected, "refresh_token": tokens["refresh_token"], "connected_at": time.time(),
                         "client_id": values["GOOGLE_OAUTH_CLIENT_ID"], "scopes": sorted(granted)})
    except (HTTPError, URLError, OSError, ValueError, KeyError):
        flash("Google could not be connected. Please retry or check the server configuration.", "error")
        return redirect(url_for("google_mail.settings"))
    flash("Google account connected. No email has been sent.", "success")
    return redirect(url_for("google_mail.settings"))
