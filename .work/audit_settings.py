"""Settings temporário de auditoria: SQLite local em .work, sem produção."""

from pathlib import Path

from config.settings import *  # noqa: F401,F403

BASE_AUDITORIA = Path(__file__).resolve().parent

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_AUDITORIA / 'audit_migrate.sqlite3',
    }
}

MEDIA_ROOT = BASE_AUDITORIA / 'audit_media'

DEBUG = True

ALLOWED_HOSTS = ['127.0.0.1', 'localhost', 'testserver']

# config.settings aplica segurança de produção durante o import quando
# DEBUG=False. Como o settings de auditoria liga o DEBUG depois do import,
# é preciso desfazer explicitamente os redirecionamentos HTTPS.
SECURE_SSL_REDIRECT = False
SECURE_HSTS_SECONDS = 0
SECURE_HSTS_INCLUDE_SUBDOMAINS = False
SESSION_COOKIE_SECURE = False
CSRF_COOKIE_SECURE = False
SECURE_PROXY_SSL_HEADER = None
