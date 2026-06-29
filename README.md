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

For first local testing only, if no valid `ADMIN_PASSWORD_HASH` is configured, the fallback credentials are:

```text
admin / admin123
```

## Security Notes

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
