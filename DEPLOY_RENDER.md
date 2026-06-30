# Deploy en Render gratis

Esta guia levanta la app Flask en Render usando el plan gratuito. Es ideal para
probar que la aplicacion funciona online antes de pagar una suscripcion.

## 1. Preparar el repositorio

1. Crear una cuenta en GitHub si todavia no tenes una.
2. Crear un repositorio nuevo, por ejemplo `path-internal-app`.
3. Subir este proyecto completo al repositorio.

Archivos importantes que ya estan preparados:

- `requirements.txt`: incluye las dependencias de Python y `gunicorn`.
- `render.yaml`: define el servicio web gratuito para Render.
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
plan: free
buildCommand: pip install -r requirements.txt
startCommand: gunicorn run:app --bind 0.0.0.0:$PORT
```

## 4. Configurar variables de entorno

En Render, abrir el servicio creado e ir a `Environment`.

Configurar:

```text
ADMIN_USERNAME=admin
ADMIN_PASSWORD_HASH=<el hash generado>
DATABASE_URL=sqlite:///academic_staff.db
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

## 6. Limitaciones del plan gratuito

En el plan gratuito, este deploy sirve para probar la app online, pero no para
guardar datos reales de forma definitiva.

Motivos:

- El servicio puede dormir cuando no recibe trafico.
- La primera carga despues de dormir puede tardar mas.
- El filesystem del servicio gratuito no debe tratarse como almacenamiento
  durable para la base SQLite.

Para usar la app en serio, el siguiente paso es pasar a un plan pago con disco
persistente o migrar la base a un servicio de base de datos.

## 7. Cuando pasemos a pago

La opcion mas simple para esta app es:

1. Agregar un persistent disk en Render.
2. Montarlo en una ruta como `/var/data`.
3. Cambiar `DATABASE_URL` a:

```text
sqlite:////var/data/academic_staff.db
```

Despues de eso, los datos dejan de depender del filesystem efimero del servicio.
