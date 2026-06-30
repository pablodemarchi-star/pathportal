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
```

`SECRET_KEY` se genera automaticamente desde `render.yaml`. Si Render te pide
completar alguna variable manualmente, usa un texto largo y aleatorio para
`SECRET_KEY`.

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
