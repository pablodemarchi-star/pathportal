"""Administrator-managed Google authorization for notification email."""
import base64
import hashlib
import hmac
import json
import os
import secrets
import tempfile
import time
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


def google_json(url, *, fields=None, bearer=None):
    headers = {"Accept": "application/json"}
    body = None
    if fields is not None:
        body = urlencode(fields).encode()
        headers["Content-Type"] = "application/x-www-form-urlencoded"
    if bearer:
        headers["Authorization"] = "Bearer " + bearer
    with urlopen(Request(url, data=body, headers=headers), timeout=15) as response:
        return json.load(response)


@google_mail_bp.after_request
def private_response(response):
    response.headers["Cache-Control"] = "private, no-store"
    response.headers["Referrer-Policy"] = "no-referrer"
    return response


@google_mail_bp.get("/integrations/google")
@administrator
def settings():
    session.setdefault("csrf_token", secrets.token_urlsafe(32))
    try:
        saved = read_connection()
        connected = bool(saved.get("refresh_token"))
    except (OSError, ValueError):
        saved, connected = {}, False
        flash("The saved Google connection could not be read. Check the server configuration.", "error")
    values = configuration()
    return render_template("integrations/google.html", configured=configured(), connected=connected,
        account=saved.get("account") if connected else os.getenv("GMAIL_ACCOUNT_EMAIL", EXPECTED_ACCOUNT),
        sender=os.getenv("GMAIL_FROM_EMAIL", "no-reply@pathexaminations.com"),
        callback_uri=values["GOOGLE_OAUTH_REDIRECT_URI"], csrf_token=session.get("csrf_token"))


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
    state, verifier = secrets.token_urlsafe(32), secrets.token_urlsafe(64)
    session["google_mail_oauth"] = {"state": state, "verifier": verifier, "started": time.time()}
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip("=")
    return redirect("https://accounts.google.com/o/oauth2/v2/auth?" + urlencode({
        "client_id": configuration()["GOOGLE_OAUTH_CLIENT_ID"],
        "redirect_uri": configuration()["GOOGLE_OAUTH_REDIRECT_URI"],
        "response_type": "code", "scope": SCOPES, "access_type": "offline", "prompt": "consent",
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
        identity = google_json("https://openidconnect.googleapis.com/v1/userinfo", bearer=tokens["access_token"])
        expected = os.getenv("GMAIL_ACCOUNT_EMAIL", EXPECTED_ACCOUNT).lower()
        if identity.get("email", "").lower() != expected or identity.get("email_verified") is not True:
            flash("Authorize the designated Path account. The existing connection has not changed.", "error")
            return redirect(url_for("google_mail.settings"))
        if not tokens.get("refresh_token"):
            flash("Google did not provide offline authorization. Please reconnect and grant consent.", "error")
            return redirect(url_for("google_mail.settings"))
        save_connection({"account": expected, "refresh_token": tokens["refresh_token"], "connected_at": time.time(),
                         "client_id": values["GOOGLE_OAUTH_CLIENT_ID"]})
    except (HTTPError, URLError, OSError, ValueError, KeyError):
        flash("Google could not be connected. Please retry or check the server configuration.", "error")
        return redirect(url_for("google_mail.settings"))
    flash("Google account connected. No email has been sent.", "success")
    return redirect(url_for("google_mail.settings"))
