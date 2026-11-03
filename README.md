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


## Finance files in Google Drive

Drive storage is optional and uses the existing Google connection. Enable Google
Drive API and Google Picker API in the OAuth client's Cloud project. Configure
`GOOGLE_PICKER_API_KEY` and `GOOGLE_CLOUD_PROJECT_NUMBER` on each server. Restrict
the browser key to Google Picker API and the portal's origin plus
`https://docs.google.com/*` (add localhost origins separately for local Picker use).

A superadmin opens **Email connection**, selects **Connect Google Drive**, and
authorizes the designated account with the additional `drive.file` scope. Existing
Gmail authorization remains in place if this authorization is cancelled or refused.
Then use **Choose and authorize folder** for the two independent Finance destinations:
**Supporting documentation** and **Payment receipts**. The selected folder must allow
this Google account to add children. Folder settings persist in the portal database
and can be changed later without changing application code. Future menus can register
separate destination keys using the same connection.

Until a destination is selected, that document category keeps using portal storage.
Once configured, a Drive failure rejects the upload instead of silently saving it
locally. New Drive files are prefixed with the payment request number. They retain
the folder's Drive permissions; the application does not make documents public.
Finance users open documents through authenticated portal download links which also
check the payment request's visibility. Earlier local files are not migrated and
continue to use the existing download route. Uploads from rolled-back transactions
are moved to Drive trash; committed documents remain in Drive when a request is deleted.

### Finance completion emails

Payment completed, Invoice issued, Rejected and Needs correction (displayed as
With discrepancy) transitions queue an English status email to
the requester's account email in the same database transaction. Delivery starts
after commit using the existing Gmail connection. A unique record per transition event and
an atomic sending claim prevent duplicate notices on repeated saves. A request resubmitted and marked
with a discrepancy again receives a new notice for that transition.
Existing completed requests are not backfilled. Email failures do not roll back
the saved finance operation; pending/failed notices can be retried from Email
connection. Unknown deliveries require checking Gmail Sent before any retry.

Status emails include both the English and Spanish WhatsApp messages directly in
the HTML and plain-text versions. Each has its own copy-and-paste instruction.
The content is generated by the card's existing copy helpers and saved with the
status transition, including WhatsApp asterisks, line breaks and document URLs.
No portal visit is needed to copy the text; authenticated document URLs still
require the recipient to have access when opening a document. Older email links
continue to work through the restricted copy page. Reasons are included when
recorded on the status event.

### Daily Finance agenda

The authenticated `/internal/jobs/finance-agenda` job sends a single English agenda
to finance@pathexaminations.com at/after 06:30 Argentina (fixed GMT-3). Render cron
activation is described in DEPLOY_RENDER.md; it does not depend on portal visits.
No email is sent on days without actionable work.

The agenda includes unarchived approved/scheduled/delayed payments due today or
overdue, and unarchived Requested/Processing invoice/Invoice scheduled invoices
whose scheduled (or requested) date is today or overdue. Invoices without a date
are treated as actionable now. Completed, cancelled, rejected, held, discrepancy
and pending-management payments are excluded. The old SMTP approval-time notice
is replaced by this agenda.

After 06:30, creating or rescheduling an actionable request for today triggers an
immediate Gmail notice after commit. Approving a previously pending payment for
today also triggers it. Per-day coverage prevents duplicate mentions when the
cron is repeated, when a card is edited, or when cron and a late notice overlap.
Each day starts fresh for work still outstanding. Delivery errors and uncertain
outcomes follow the same admin retry policy as other finance notifications.

### Permanent Finance request numbering

`FinanceSequence` persists separate annual PAY and INVOICE counters; cancellation,
archiving and deletion never reset a committed counter. Atomic SQLite upserts
reserve numbers in the request transaction, so concurrent writers cannot allocate
the same number. A rolled-back creation does not count as an issued request.
Initialization uses numeric suffixes from existing requests (including legacy BILL)
and retained completion/agenda email snapshots. Numbers deleted before this change
with no surviving record cannot be reconstructed. Existing request numbers remain
unchanged.

Request and event IDs also use persistent counters, seeded from current records and
retained notification/Drive references. This prevents a deleted request's previous
notification coverage from suppressing a new request's email if SQLite would
otherwise reuse its primary key.

### Staff portal invoices

Invoicing instructions in the staff portal accept exactly one file per upload,
validated in the browser and on the server. Each upload is linked to the portal
share and exam year; the share must include a confirmed matching assignment for
that year. CSRF is required. Files use a separately authorized Staff invoices
Drive destination (proposed folder 1_VrUoXNBbVT_hSo_vAbL7prSj8hBAUNV).
Authorize it once in Email connection, using Google Picker, after deployment.
Uploads fail visibly if it is not configured; they never silently use local
storage or a Finance payment/invoice folder. Staff can access their own uploaded
file through the private portal. Only one active invoice per staff portal and year is allowed, including a database
unique constraint. Staff payments shows Invoice (View ×) and Verification. Viewing
opens a same-origin preview modal, dismissible via its × or the backdrop. Removing
an invoice requires staff_payments edit permission and CSRF, moves the file to the
Drive trash, and only then deletes the record and unlocks a new portal upload. A
failed trash operation keeps the association and upload lock intact.

The displayed deadline is two business days before the configured next staff
payment date, at the portal's existing standard time of 5:00 pm GMT-3. The same
two-business-day instruction is used in all invitation details and generated
official email copies. If no payment date is configured, it says To be confirmed.

### Staff invoice annulment notifications

After Drive confirms moving a staff invoice to the trash, its removal and an email
notification record are committed together. The English Path email tells the staff
member that errors were found, asks them to contact Administration for verification
and directs them to reload the corrected invoice in their portal within the stated
deadlines. It goes to the member's configured email, not to Finance.

There is one notification per Drive file ID, claimed atomically before sending.
Failed Drive operations retain the invoice and never queue this email. Email
failures keep the completed annulment and appear in Email connection. Confirmed
failures can be retried there; ambiguous delivery must be checked in Gmail Sent
before any retry. Missing staff email is reported as a failed notification.

Examiner guidelines are configured per certification year with separate Onsite
and Online URLs. Existing guideline URLs remain assigned to Onsite. Missing
format-specific links show a disabled Open resource and Available soon in the
staff portal, without preventing invitations. Online at exam centre permits
Supervisors and Interns, but no Examiners. Startup cleanup and session format
changes remove Examiner assignments and their portal submissions for that format.
