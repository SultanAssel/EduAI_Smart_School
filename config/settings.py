import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = os.getenv('SECRET_KEY', '')
if not SECRET_KEY:
    # In development generate a key; in production crash loudly
    _is_debug_env = os.getenv('DEBUG', 'False').lower() in ('true', '1', 'yes')
    if _is_debug_env:
        import secrets
        SECRET_KEY = secrets.token_urlsafe(50)
        import warnings
        warnings.warn('SECRET_KEY not set — using random key (sessions reset on restart)', stacklevel=1)
    else:
        raise RuntimeError(
            'SECRET_KEY environment variable is required in production. '
            'Generate one with: python -c "import secrets; print(secrets.token_urlsafe(50))"'
        )
DEBUG = os.getenv('DEBUG', 'False').lower() in ('true', '1', 'yes')
ALLOWED_HOSTS = os.getenv('ALLOWED_HOSTS', '').split(',')
ALLOWED_HOSTS = [h.strip() for h in ALLOWED_HOSTS if h.strip()] or (
    ['*'] if DEBUG else ['localhost', '127.0.0.1']
)

# CSRF — доверенные origin для proxy/tunnel (zrok, ngrok и т.д.)
_csrf_origins = os.getenv('CSRF_TRUSTED_ORIGINS', '')
CSRF_TRUSTED_ORIGINS = [o.strip() for o in _csrf_origins.split(',') if o.strip()] if _csrf_origins else []

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'core',  # после стандартных, чтобы не перекрывать admin-шаблоны
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.middleware.gzip.GZipMiddleware',       # сжатие ответов
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'core.middleware.UserTimezoneMiddleware',
]

ROOT_URLCONF = 'config.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'core.context_processors.eduai_context',
            ],
        },
    },
]

WSGI_APPLICATION = 'config.wsgi.application'

# --- БД ---
# По умолчанию SQLite. Для PostgreSQL/MySQL задайте DATABASE_URL.
_db_url = os.getenv('DATABASE_URL', '').strip()

if _db_url and not _db_url.startswith('sqlite'):
    try:
        import dj_database_url
        DATABASES = {'default': dj_database_url.parse(_db_url)}
    except ImportError:
        raise ImportError('Install dj-database-url: pip install dj-database-url')
else:
    # SQLite — extract path from URL or use default
    _db_name = BASE_DIR / 'db.sqlite3'
    if _db_url.startswith('sqlite:///'):
        _path = _db_url.replace('sqlite:///', '', 1)
        _db_name = _path if os.path.isabs(_path) else BASE_DIR / _path
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': _db_name,
        }
    }

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

LANGUAGE_CODE = 'ru'
TIME_ZONE = 'Asia/Almaty'
USE_I18N = True
USE_TZ = True

STATIC_URL = 'static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'

# WhiteNoise: сжатие и вечный кеш для статики с хешами
STORAGES = {
    'default': {
        'BACKEND': 'django.core.files.storage.FileSystemStorage',
    },
    'staticfiles': {
        'BACKEND': 'whitenoise.storage.CompressedManifestStaticFilesStorage',
    },
}

# ── Кеширование ──
# Файловый кеш (работает без Redis/Memcached).
# Для продакшна рекомендуется Redis: CACHES → django_redis.
CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.filebased.FileBasedCache',
        'LOCATION': str(BASE_DIR / '.cache'),
        'TIMEOUT': 300,  # 5 минут по умолчанию
        'OPTIONS': {
            'MAX_ENTRIES': 1000,
        },
    }
}

MEDIA_URL = os.getenv('MEDIA_URL', '/media/')
MEDIA_ROOT = BASE_DIR / os.getenv('MEDIA_ROOT', 'media')

# Allow uploads up to 20 MB (must match MAX_UPLOAD_SIZE in views.py)
DATA_UPLOAD_MAX_MEMORY_SIZE = 20 * 1024 * 1024
FILE_UPLOAD_MAX_MEMORY_SIZE = 20 * 1024 * 1024

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# --- ИИ / LLM ---
# Поддержка: OpenAI, Gemini (через OpenAI-совместимость), Ollama, LM Studio
# Настройка через .env: AI_API_KEY, AI_BASE_URL, AI_MODEL
AI_API_KEY = os.getenv('AI_API_KEY', '')
AI_BASE_URL = os.getenv('AI_BASE_URL', 'https://generativelanguage.googleapis.com/v1beta/openai/')
AI_MODEL = os.getenv('AI_MODEL', 'gemini-2.5-flash')
AI_TIMEOUT = int(os.getenv('AI_TIMEOUT', '25'))  # секунды

# --- Email ---
# По умолчанию console backend (письма в терминал)
# Для продакшна: EMAIL_BACKEND='django.core.mail.backends.smtp.SmtpEmailBackend'
EMAIL_BACKEND = os.getenv('EMAIL_BACKEND', 'django.core.mail.backends.console.EmailBackend')
EMAIL_HOST = os.getenv('EMAIL_HOST', 'smtp.gmail.com')
EMAIL_PORT = int(os.getenv('EMAIL_PORT', '587'))
EMAIL_USE_TLS = os.getenv('EMAIL_USE_TLS', 'True').lower() in ('true', '1')
EMAIL_HOST_USER = os.getenv('EMAIL_HOST_USER', '')
EMAIL_HOST_PASSWORD = os.getenv('EMAIL_HOST_PASSWORD', '')
DEFAULT_FROM_EMAIL = os.getenv('DEFAULT_FROM_EMAIL', 'EduAI <noreply@eduai.kz>')

# --- Защита (продакшн) ---
if not DEBUG:
    SECURE_BROWSER_XSS_FILTER = True
    SECURE_CONTENT_TYPE_NOSNIFF = True
    X_FRAME_OPTIONS = 'DENY'
    SECURE_HSTS_SECONDS = 31536000
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_SSL_REDIRECT = os.getenv('SECURE_SSL_REDIRECT', 'True').lower() in ('true', '1')
    SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
else:
    X_FRAME_OPTIONS = 'SAMEORIGIN'

# --- Язык по умолчанию ---
DEFAULT_LANGUAGE = os.getenv('DEFAULT_LANGUAGE', 'ru')

# Логирование
_LOG_DIR = BASE_DIR / 'logs'
_LOG_DIR.mkdir(exist_ok=True)

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {'format': '{asctime} {levelname} {name} {message}', 'style': '{'},
    },
    'handlers': {
        'console': {'class': 'logging.StreamHandler', 'formatter': 'verbose'},
        'file': {
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': _LOG_DIR / 'django.log',
            'maxBytes': 5 * 1024 * 1024,
            'backupCount': 3,
            'formatter': 'verbose',
        },
    },
    'root': {'handlers': ['console'] if DEBUG else ['console', 'file'], 'level': 'INFO'},
    'loggers': {
        'core': {
            'handlers': ['console'] if DEBUG else ['console', 'file'],
            'level': 'DEBUG' if DEBUG else 'INFO',
            'propagate': False,
        },
    },
}
