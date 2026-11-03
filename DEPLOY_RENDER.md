# Deploy en Render

Esta guia levanta la app Flask en Render usando un servicio pago con disco
persistente. Esta es la configuracion recomendada para no perder la base SQLite
en redeploys o restarts.

## 1. Preparar el repositorio

1. Crear una cuenta en GitHub si todavia no tenes una.
2. Crear un repositorio nuevo, por ejemplo `path-internal-app`.
3. Subir este proyecto completo al repositorio.

Archivos importantes que ya estan preparados:

- `requirements.txt`: incluye las dependencias de Python y `gunicorn`.
- `render.yaml`: define el servicio web de Render, el plan y el disco persistente.
- `run.py`: expone la app como `run:app`, que es lo que usa Gunicorn.

No subas archivos locales sensibles como `.env` ni bases SQLite dentro de
`instance/`. Ya estan ignorados por `.gitignore`.

## 2. Crear usuario y password para Render

Render necesita recibir el password como hash, no como texto plano.

Desde tu computadora, dentro del proyecto, ejecuta:

```bash
source .venv/bin/activate
python -c "from werkzeug.security import generate_password_hash; print(generate_password_hash('tu-password-seguro', method='pbkdf2:sha256'))"
```

Guarda el resultado completo. Se parece a:

```text
pbkdf2:sha256:1000000$...
```

Ese valor va en `ADMIN_PASSWORD_HASH`.

## 3. Crear el servicio en Render

1. Entrar a https://dashboard.render.com
2. Ir a `New`.
3. Elegir `Blueprint`.
4. Conectar GitHub si Render todavia no tiene acceso.
5. Elegir el repositorio del proyecto.
6. Render va a detectar `render.yaml`.
7. Confirmar la creacion del servicio.

El `render.yaml` ya define:

```text
plan: starter
buildCommand: pip install -r requirements.txt
startCommand: gunicorn run:app --bind 0.0.0.0:$PORT
disk: app-data mounted at /var/data
```

## 4. Configurar variables de entorno

En Render, abrir el servicio creado e ir a `Environment`.

Configurar:

```text
ADMIN_USERNAME=admin
ADMIN_PASSWORD_HASH=<el hash generado>
DATABASE_URL=sqlite:////var/data/academic_staff.db
SMTP_HOST=<host smtp>
SMTP_PORT=587
SMTP_USERNAME=<usuario smtp>
SMTP_PASSWORD=<password smtp>
SMTP_FROM_EMAIL=no-reply@pathexaminations.com
SMTP_USE_TLS=1
```

`SECRET_KEY` se genera automaticamente desde `render.yaml`. Si Render te pide
completar alguna variable manualmente, usa un texto largo y aleatorio para
`SECRET_KEY`.

Las variables `SMTP_*` se usan para enviar avisos automaticos, por ejemplo el
email a Finance cuando Management aprueba una solicitud de pago y queda
programada. Si no se configuran, la aprobacion funciona igual pero el email no
se envia.

## 5. Deploy

1. En Render, abrir el servicio.
2. Ir a `Manual Deploy`.
3. Elegir `Deploy latest commit`.
4. Esperar que termine el build.
5. Abrir la URL publica que Render muestra, por ejemplo:

```text
https://path-internal-app.onrender.com
```

La app deberia redirigir a `/login`.

## 6. Persistencia de datos

La base SQLite debe estar en el disco persistente de Render:

```text
sqlite:////var/data/academic_staff.db
```

El disco persistente se monta en:

```text
/var/data
```

Con esta configuracion, los datos sobreviven redeploys y restarts.

Si ya cargaste datos en la app antes de activar el disco persistente, no cambies
la ruta sin antes migrar o exportar esa base. Al cambiar a `/var/data`, SQLite
crea una base nueva si no existe una en el disco.

## 7. Configuracion esperada del disco

En Render, el servicio debe tener un Persistent Disk con:

```text
Name: app-data
Mount Path: /var/data
Size: 1 GB
```

Si Render no permite 1 GB, usar el minimo disponible.

## Finance agenda: 06:30 Argentina (GMT-3)

Create a Render Cron Job connected to this repository after deploying the Finance
agenda implementation. This job calls the web app: it must not open its own SQLite
database or copy Gmail credentials, because Render cron jobs cannot share the web
service's persistent disk.

1. Generate a random secret of at least 32 characters and set
   `FINANCE_AGENDA_JOB_TOKEN` in **both** the existing portal web service and the
   new cron job. Never put the secret in Git or in a URL.
2. Cron schedule: `30 9 * * *` (09:30 UTC = 06:30 Argentina, every day).
3. Build command: `pip install -r requirements.txt`.
4. Command: `python scripts/send_finance_agenda.py`.
5. Cron environment: `PORTAL_BASE_URL=https://portal.pathinternalportal.com`
   and the same `FINANCE_AGENDA_JOB_TOKEN`. The cron needs no database/Google secret.
6. The web service needs the existing authorized Gmail connection. Keep the current
   Gmail credentials and persistent disk configuration.

The endpoint refuses missing/incorrect secrets and never accepts a date or recipient
from the caller. It runs against the current Argentina date, refuses to send before
06:30, and reserves a unique daily notice. Repeated runs don't resend a sent or
uncertain notice. An empty agenda does not send an email. Failed deliveries can be
retried from Email connection; uncertain deliveries require checking Gmail Sent.
New actionable same-day requests after 06:30 trigger immediate emails independently
of the cron. Daily and immediate notices share per-day coverage records to avoid
notifying Finance twice about the same request on the same day.
