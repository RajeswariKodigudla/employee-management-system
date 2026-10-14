import os
from pathlib import Path
from django.core.exceptions import ImproperlyConfigured

BASE_DIR=Path(__file__).resolve().parent.parent
SECRET_KEY=os.environ.get("DJANGO_SECRET_KEY")
if not SECRET_KEY:
 raise ImproperlyConfigured("Set the DJANGO_SECRET_KEY environment variable.")
DEBUG=os.environ.get("DJANGO_DEBUG","False").strip().lower() in {"true","1","yes","on"}
ALLOWED_HOSTS=[
 host.strip()
 for host in os.environ.get("DJANGO_ALLOWED_HOSTS","127.0.0.1,localhost").split(",")
 if host.strip()
]
render_host = os.environ.get("RENDER_EXTERNAL_HOSTNAME")

if render_host:
    if render_host not in ALLOWED_HOSTS:
        ALLOWED_HOSTS.append(render_host)

    CSRF_TRUSTED_ORIGINS = [f"https://{render_host}"]
else:
    CSRF_TRUSTED_ORIGINS = []
INSTALLED_APPS=["django.contrib.admin","django.contrib.auth","django.contrib.contenttypes","django.contrib.sessions","django.contrib.messages","django.contrib.staticfiles","core"]
MIDDLEWARE=["django.middleware.security.SecurityMiddleware","whitenoise.middleware.WhiteNoiseMiddleware","django.contrib.sessions.middleware.SessionMiddleware","django.middleware.common.CommonMiddleware","django.middleware.csrf.CsrfViewMiddleware","django.contrib.auth.middleware.AuthenticationMiddleware","django.contrib.messages.middleware.MessageMiddleware","django.middleware.clickjacking.XFrameOptionsMiddleware"]
ROOT_URLCONF="config.urls"
TEMPLATES=[{"BACKEND":"django.template.backends.django.DjangoTemplates","DIRS":[BASE_DIR/"templates"],"APP_DIRS":True,"OPTIONS":{"context_processors":["django.template.context_processors.debug","django.template.context_processors.request","django.contrib.auth.context_processors.auth","django.contrib.messages.context_processors.messages","core.notifications.notification_summary"]}}]
WSGI_APPLICATION="config.wsgi.application"
DATABASES={"default":{"ENGINE":"django.db.backends.sqlite3","NAME":BASE_DIR/"db.sqlite3"}}
AUTH_PASSWORD_VALIDATORS=[{"NAME":"django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},{"NAME":"django.contrib.auth.password_validation.MinimumLengthValidator"},{"NAME":"django.contrib.auth.password_validation.CommonPasswordValidator"},{"NAME":"django.contrib.auth.password_validation.NumericPasswordValidator"}]
LANGUAGE_CODE="en-us"; TIME_ZONE="Asia/Kolkata"; USE_I18N=True; USE_TZ=True
STATIC_URL="static/"; STATICFILES_DIRS=[BASE_DIR/"static"]; STATIC_ROOT=BASE_DIR/"staticfiles"
DEFAULT_AUTO_FIELD="django.db.models.BigAutoField"
LOGIN_URL="login"; LOGIN_REDIRECT_URL="dashboard"; LOGOUT_REDIRECT_URL="login"
PAYSLIP_COMPANY_NAME="Employee Management System"
