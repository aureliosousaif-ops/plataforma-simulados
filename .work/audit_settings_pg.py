"""Settings apenas para gerar SQL do backend PostgreSQL, sem conectar."""

from config.settings import *  # noqa: F401,F403

DEBUG = True

SECRET_KEY = 'audit-only-secret-key'

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': 'audit_only',
        'USER': 'audit_only',
        'PASSWORD': 'audit_only',
        'HOST': '127.0.0.1',
        'PORT': '5432',
        'OPTIONS': {'connect_timeout': 2},
    }
}

MEDIA_ROOT = 'C:/Users/kitiz/AppData/Local/Temp/opencode/audit-media-pg'
