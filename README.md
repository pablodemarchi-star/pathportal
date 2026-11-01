# Path Examinations Internal App

Internal web dashboard for managing academic staff members.

## Stack

- Python 3
- Flask
- Flask-SQLAlchemy
- SQLite
- HTML, CSS and vanilla JavaScript

## Folder Structure

```text
.
├── app/
│   ├── static/
│   │   ├── css/styles.css
│   │   └── js/app.js
│   ├── templates/
│   │   ├── base.html
│   │   ├── login.html
│   │   └── staff/
│   │       ├── _badges.html
│   │       ├── _form.html
│   │       └── index.html
│   ├── __init__.py
│   ├── models.py
│   ├── routes.py
│   └── validators.py
├── instance/
├── requirements.txt
├── run.py
└── .env.example
```

## Local Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Generate a real password hash before using the app beyond local testing:

```bash
python -c "from werkzeug.security import generate_password_hash; print(generate_password_hash('replace-with-a-strong-password', method='pbkdf2:sha256'))"
```

Paste the generated value into `ADMIN_PASSWORD_HASH` in `.env`, set a long random `SECRET_KEY`, then run:

```bash
flask run --host 127.0.0.1 --port 5001
```

You can also run:

```bash
python run.py
```

Open `http://127.0.0.1:5001`.

## Render Free Deploy

This repository includes `render.yaml` for deploying the Flask app as a Render
web service.

1. Push the project to a GitHub repository.
2. In Render, create a new Blueprint or Web Service from that repository.
3. Use the free instance type for the first test deploy.
4. Keep the generated build command:

```bash
pip install -r requirements.txt
```

5. Keep the generated start command:

```bash
gunicorn run:app --bind 0.0.0.0:$PORT
```

6. Configure these environment variables in Render:

```text
SECRET_KEY=<long-random-secret>
ADMIN_USERNAME=<admin-user>
ADMIN_PASSWORD_HASH=<generated-werkzeug-password-hash>
DATABASE_URL=sqlite:///academic_staff.db
```

Generate the password hash locally with:

```bash
python -c "from werkzeug.security import generate_password_hash; print(generate_password_hash('replace-with-a-strong-password', method='pbkdf2:sha256'))"
```

Important: Render's free web service filesystem is ephemeral. With the current
SQLite setup, this is appropriate for an online demo/test deployment only. For
real operational data, use a paid Render service with a persistent disk or
migrate the application to a managed database before storing production data.

For first local testing only, if no valid `ADMIN_PASSWORD_HASH` is configured, the fallback credentials are:

```text
admin / admin123
```

## Security Notes

### Google notification account connection

The administrator-only **Email connection** page is available at
`/integrations/google`. It authorizes the designated Google Workspace mailbox
with offline access and the `gmail.send`, `openid`, and `email` scopes. Connecting
does not send messages. New requests entering **Management review** notify
`pablo.demarchi@pathexaminations.com` from the configured sender alias. This
includes Submitted, Pending approval, and Resubmitted requests; already-approved
requests and completed card payments do not trigger a review notification.

Emails include Approve, Reject, and Mark discrepancy links. Links open an
authenticated confirmation page and never change payment status on GET. Review
permissions, CSRF, pending amounts and required comments are enforced. Links from
an earlier submission cannot approve a later resubmission of the same request.

Each review event has one persistent delivery record. Known failures are available
under **Email connection → Retry unsent notifications**. Ambiguous deliveries
(for example, a timeout while sending) are excluded from retries to avoid duplicate
messages; check Gmail's Sent folder before resolving them. Tests never send real
emails. Links use the origin of `GOOGLE_OAUTH_REDIRECT_URI`; optionally set
`PORTAL_BASE_URL` to the production HTTPS origin to override it.

Configure these environment variables on each server:

```text
GOOGLE_OAUTH_CLIENT_ID=<OAuth web client ID>
GOOGLE_OAUTH_CLIENT_SECRET=<OAuth web client secret>
GOOGLE_OAUTH_REDIRECT_URI=https://portal.pathinternalportal.com/integrations/google/callback
GMAIL_ACCOUNT_EMAIL=pablo.demarchi@pathexaminations.com
GMAIL_FROM_EMAIL=no-reply@pathexaminations.com
GMAIL_TOKEN_FILE=<absolute path on persistent server storage>
```

For local authorization, register
`http://127.0.0.1:5001/integrations/google/callback` as an additional authorized
redirect URI in Google Cloud, and use that value locally. Keep the production URI
registered too. Open the connection page on the same host as the configured URI.

The connection uses a private token file with mode `0600`; locally this defaults
to `instance/google_gmail_token.json` and is excluded from Git. Production needs
persistent storage and a stable `SECRET_KEY`; an ephemeral Render filesystem
will lose the connection on restart or redeploy. Reconnecting replaces the stored
authorization only after verifying the account and send permission. The alias
must already be enabled in Gmail's **Accounts → Send mail as** settings.

- The app binds to `127.0.0.1` by default for local isolation.
- Access requires login.
- Passwords are checked with Werkzeug password hashing.
- Session cookies are HTTP-only and SameSite=Lax.
- Forms include CSRF token validation.
- Security headers reduce clickjacking, MIME sniffing and unnecessary browser permissions.
- No file uploads are accepted. CV only stores validated `http` or `https` links, reducing malware exposure.
- Archived records are never deleted from the database.
- For production use, place the app behind HTTPS, use a real identity provider or stronger user management, rotate secrets, keep dependencies updated, and restrict access with firewall/VPN/IP allowlists.

## Brand Palette

The authorised Path International Examinations palette is defined in `app/static/css/styles.css` under the `:root` variables:

- `--path-blue-303up`
- `--path-black`
- `--path-cyan`
- `--path-violet-grey`
- `--path-warm-grey`
- `--path-sage`
- `--path-ochre`
- `--path-red`

The badge and interface colours use these variables and their light tints, so the final hex values can be adjusted centrally if official digital values are provided later.

## Logo

Only the exact authorised logo source should be used. Do not redraw, trace, recolour or recreate it in SVG/CSS.

The original Illustrator file is stored unchanged in:

```text
app/static/img/path-logo-original.ai
```

The browser-facing image is:

```text
app/static/img/path-logo-web.png
```

The sidebar uses the white transparent version:

```text
app/static/img/path-logo-white-transparent.png
```

Both were generated from the original `.ai` preview for web display and are referenced directly in the layout without stretching.

## Data Model

`AcademicStaff` stores status, title, full name, roles, contact details, start year, address fields, Google Maps location point, CV link, profile picture link, timestamped interview history, account fields, creation date and update date.

`PotentialEntry` stores pre-selection candidates before they become academic staff members. Potential entries can be edited, annotated with timestamped interview notes, rejected into a hidden audit view, or accepted into the main academic staff list.

Dates are stored in UTC and displayed in GMT-3 using `DD/MM/YYYY HH`.
