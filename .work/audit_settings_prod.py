"""Settings de auditoria com DEBUG=False para simular deploy."""

from pathlib import Path

from config.settings import *  # noqa: F401,F403

BASE_AUDITORIA = Path(__file__).resolve().parent

DEBUG = False

SECRET_KEY = 'audit-only-secret-key'

ALLOWED_HOSTS = ['127.0.0.1', 'localhost', 'testserver']

# Evita redirecionamento HTTPS no cliente de teste.
SECURE_SSL_REDIRECT = False
SECURE_HSTS_SECONDS = 0
SECURE_HSTS_INCLUDE_SUBDOMAINS = False
SESSION_COOKIE_SECURE = False
CSRF_COOKIE_SECURE = False
SECURE_PROXY_SSL_HEADER = None

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_AUDITORIA / 'audit_prod.sqlite3',
    }
}

MEDIA_ROOT = BASE_AUDITORIA / 'audit_media_prod'
