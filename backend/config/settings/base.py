"""Settings shared by every environment.

Everything that differs between environments comes from the environment
(django-environ). Every variable read here is documented in `.env.example` at
the repository root — add it there in the same change.
"""

from pathlib import Path

import environ

BASE_DIR = Path(__file__).resolve().parent.parent.parent

env = environ.Env()
# A local .env is a convenience for development only; containers get real
# environment variables and never ship a .env file.
environ.Env.read_env(BASE_DIR.parent / ".env", overwrite=False)

SECRET_KEY = env("DJANGO_SECRET_KEY")
DEBUG = False
ALLOWED_HOSTS = env.list("DJANGO_ALLOWED_HOSTS", default=[])

# The public origin the SPA is served from (scheme + host, no path). The API and
# the SPA share it — see ADR 0003.
APP_ORIGIN = env("APP_ORIGIN", default="http://localhost:5173")
CSRF_TRUSTED_ORIGINS = env.list("CSRF_TRUSTED_ORIGINS", default=[APP_ORIGIN])

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # Third party
    "rest_framework",
    "drf_spectacular",
    "django_celery_beat",
    "allauth",
    "allauth.account",
    "allauth.socialaccount",
    "allauth.socialaccount.providers.google",
    "allauth.mfa",
    "allauth.headless",
    # Commandr
    "commandr.core",
    "commandr.accounts",
    "commandr.tenancy",
    "commandr.audit",
    "commandr.integrations",
    "commandr.connectors",
    "commandr.ingest",
    "commandr.monitoring",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "commandr.core.middleware.RequestIdMiddleware",
    "commandr.tenancy.middleware.TenantResetMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "allauth.account.middleware.AccountMiddleware",
]

# The `ingest` process sets DJANGO_ROOT_URLCONF=config.urls_ingest: same image,
# but none of the app's URLs (auth, admin, sessions) are reachable through it.
ROOT_URLCONF = env("DJANGO_ROOT_URLCONF", default="config.urls")
WSGI_APPLICATION = "config.wsgi.application"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

# --- Database --------------------------------------------------------------
# The app connects as a role that does NOT own the tables and has no BYPASSRLS,
# so row-level security applies to every query (ADR 0002). Migrations run as the
# owner role via MIGRATE_DATABASE_URL — see deploy/compose.
DATABASES = {"default": env.db("DATABASE_URL")}
DATABASES["default"]["ATOMIC_REQUESTS"] = True
DATABASES["default"]["CONN_MAX_AGE"] = env.int("DB_CONN_MAX_AGE", default=60)
DATABASES["default"]["CONN_HEALTH_CHECKS"] = True

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# --- Auth ------------------------------------------------------------------
AUTH_USER_MODEL = "accounts.User"
AUTHENTICATION_BACKENDS = [
    "django.contrib.auth.backends.ModelBackend",
    "allauth.account.auth_backends.AuthenticationBackend",
]
PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.Argon2PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2PasswordHasher",
]
AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
        "OPTIONS": {"min_length": 12},
    },
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
]

# django-allauth, headless only: the SPA drives every flow (ADR 0003).
HEADLESS_ONLY = True
HEADLESS_CLIENTS = ("browser",)
HEADLESS_FRONTEND_URLS = {
    "account_confirm_email": f"{APP_ORIGIN}/verify-email/{{key}}",
    "account_reset_password": f"{APP_ORIGIN}/reset-password",
    "account_reset_password_from_key": f"{APP_ORIGIN}/reset-password/{{key}}",
    "account_signup": f"{APP_ORIGIN}/sign-up",
    "socialaccount_login_error": f"{APP_ORIGIN}/sign-in?error=social",
}
ACCOUNT_LOGIN_METHODS = {"email"}
ACCOUNT_SIGNUP_FIELDS = ["email*", "password1*"]
ACCOUNT_USER_MODEL_USERNAME_FIELD = None
ACCOUNT_UNIQUE_EMAIL = True
ACCOUNT_EMAIL_VERIFICATION = env("ACCOUNT_EMAIL_VERIFICATION", default="mandatory")
ACCOUNT_LOGIN_BY_CODE_ENABLED = False
ACCOUNT_RATE_LIMITS = {
    # Per account AND per IP — allauth's own limiter, backed by the cache.
    "login_failed": "10/m/ip,5/5m/key",
    "signup": "20/h/ip",
    "reset_password": "20/h/ip,5/h/key",
}
ACCOUNT_PREVENT_ENUMERATION = True
# How long a sign-in or password re-entry counts as "recent" for sensitive
# actions: connecting or removing an integration, creating keys (security.md).
ACCOUNT_REAUTHENTICATION_TIMEOUT = 300
MFA_SUPPORTED_TYPES = ["totp", "recovery_codes", "webauthn"]
MFA_PASSKEY_LOGIN_ENABLED = True
MFA_WEBAUTHN_ALLOW_INSECURE_ORIGIN = False
SOCIALACCOUNT_PROVIDERS = {
    "google": {
        "APPS": [
            {
                "client_id": env("GOOGLE_SIGNIN_CLIENT_ID", default=""),
                "secret": env("GOOGLE_SIGNIN_CLIENT_SECRET", default=""),
            }
        ],
        "SCOPE": ["openid", "email", "profile"],
        "OAUTH_PKCE_ENABLED": True,
    }
}

# --- Sessions & cookies ----------------------------------------------------
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
SESSION_COOKIE_AGE = 60 * 60 * 24 * 7  # idle timeout: 7 days, refreshed on use
SESSION_SAVE_EVERY_REQUEST = True
# The SPA reads the CSRF cookie to send X-CSRFToken, so it cannot be HttpOnly.
CSRF_COOKIE_HTTPONLY = False
CSRF_COOKIE_SAMESITE = "Lax"

# --- DRF -------------------------------------------------------------------
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework.authentication.SessionAuthentication",
    ],
    # Default DENY: every view must declare its own permission classes.
    # tests/test_permissions_declared.py fails if one does not.
    "DEFAULT_PERMISSION_CLASSES": ["commandr.core.permissions.DenyAll"],
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.LimitOffsetPagination",
    "PAGE_SIZE": 50,
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "EXCEPTION_HANDLER": "commandr.core.exceptions.exception_handler",
    "DEFAULT_THROTTLE_CLASSES": [
        "commandr.core.throttling.PerUserThrottle",
    ],
    "DEFAULT_THROTTLE_RATES": {"user": "600/min"},
}
SPECTACULAR_SETTINGS = {
    "TITLE": "Commandr API",
    "VERSION": "0.1.0",
    "SERVE_INCLUDE_SCHEMA": False,
}

# --- Cache / Redis / Celery ------------------------------------------------
REDIS_URL = env("REDIS_URL", default="redis://localhost:6379/0")
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.redis.RedisCache",
        "LOCATION": REDIS_URL,
        "KEY_PREFIX": "cmdr",
    }
}
CELERY_BROKER_URL = env("CELERY_BROKER_URL", default=REDIS_URL)
CELERY_RESULT_BACKEND = None
CELERY_TASK_ACKS_LATE = True
CELERY_TASK_REJECT_ON_WORKER_LOST = True
CELERY_WORKER_PREFETCH_MULTIPLIER = 1
CELERY_TASK_TIME_LIMIT = 300
CELERY_TASK_SOFT_TIME_LIMIT = 240
CELERY_BEAT_SCHEDULER = "django_celery_beat.schedulers:DatabaseScheduler"
CELERY_TASK_DEFAULT_QUEUE = "default"
# `egress` tasks fetch customer URLs. They run in the `poller` container, which
# has a route to the broker and the internet but NOT to Postgres: they receive
# everything they need as arguments and hand results back to a default-queue
# task (docs/architecture/overview.md § Process types).
CELERY_TASK_ROUTES = {
    "commandr.monitoring.tasks.fetch_status": {"queue": "egress"},
    "commandr.monitoring.tasks.probe_uptime": {"queue": "egress"},
}
CELERY_BEAT_SCHEDULE = {
    "monitoring-schedule-polls": {
        "task": "commandr.monitoring.tasks.schedule_polls",
        "schedule": 30.0,
    },
    "monitoring-evaluate": {"task": "commandr.monitoring.tasks.evaluate", "schedule": 60.0},
    "monitoring-digests": {
        "task": "commandr.monitoring.tasks.send_due_digests",
        "schedule": 15 * 60.0,
    },
    "monitoring-partitions": {
        "task": "commandr.monitoring.tasks.maintain_partitions",
        "schedule": 6 * 3600.0,
    },
    "monitoring-prune": {"task": "commandr.monitoring.tasks.prune", "schedule": 24 * 3600.0},
}

# --- Credential vault ------------------------------------------------------
# Comma-separated Fernet keys, NEWEST FIRST. Rotation: prepend a new key, run
# `manage.py vault_rotate`, then drop the old one. Generate a key with
# `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`.
VAULT_KEYS = env.list("VAULT_KEYS")

# --- Outbound HTTP ---------------------------------------------------------
SAFE_HTTP_USER_AGENT = "Commandr/0.1 (+https://github.com/rauliscoding/commandr)"
STATUS_POLLER_USER_AGENT = "Commandr-Poller/1 (+https://github.com/rauliscoding/commandr)"

# --- Proxies ---------------------------------------------------------------
# Peers allowed to tell us the client's address in X-Forwarded-For. Must match
# what Caddy is (it is the only thing that can reach web/ingest in compose).
# Empty = trust nobody: REMOTE_ADDR is the client.
TRUSTED_PROXY_CIDRS = env.list("TRUSTED_PROXY_CIDRS", default=[])

# --- Ingestion (docs/architecture/ingestion-contract.md) ---------------------
# Public origin of the ingest API, used to build the URLs and snippets the
# setup wizard shows (heartbeat URLs, curl examples).
INGEST_ORIGIN = env("INGEST_ORIGIN", default="http://localhost:8001")
# Redis holding the ingest stream; the broker's Redis is fine.
INGEST_STREAM_URL = env("INGEST_STREAM_URL", default=REDIS_URL)
INGEST_STREAM_KEY = "cmdr:ingest"
INGEST_STREAM_MAXLEN = env.int("INGEST_STREAM_MAXLEN", default=100_000)
INGEST_MAX_BODY_BYTES = 1_000_000
INGEST_MAX_ITEMS = 1_000
# Every limit is per ingest key / per heartbeat, never global (invariant 4).
INGEST_RATE_LIMIT_PER_MINUTE = env.int("INGEST_RATE_LIMIT_PER_MINUTE", default=600)
HEARTBEAT_RATE_LIMIT_PER_MINUTE = env.int("HEARTBEAT_RATE_LIMIT_PER_MINUTE", default=60)
INGEST_MAX_SERIES_PER_PROJECT = env.int("INGEST_MAX_SERIES_PER_PROJECT", default=2_000)
INGEST_MAX_ATTR_VALUES = env.int("INGEST_MAX_ATTR_VALUES", default=500)

# --- Monitoring ----------------------------------------------------------------
MONITORING_ALERT_COOLDOWN_MINUTES = env.int("MONITORING_ALERT_COOLDOWN_MINUTES", default=60)
# Local hour (in the organization's timezone) the daily digest goes out.
MONITORING_DIGEST_HOUR = env.int("MONITORING_DIGEST_HOUR", default=7)
# Raw points are dropped a whole month partition at a time once older than this.
METRICS_RAW_RETENTION_DAYS = env.int("METRICS_RAW_RETENTION_DAYS", default=90)
METRICS_ROLLUP_1M_RETENTION_DAYS = 14
METRICS_ROLLUP_1H_RETENTION_DAYS = 400
EVENTS_RETENTION_DAYS = 90

# --- Email -----------------------------------------------------------------
# Resend works through plain SMTP: host smtp.resend.com, port 465, SSL,
# user "resend", password = API key. No SDK needed for transactional mail.
EMAIL_BACKEND = env("EMAIL_BACKEND", default="django.core.mail.backends.console.EmailBackend")
EMAIL_HOST = env("EMAIL_HOST", default="smtp.resend.com")
EMAIL_PORT = env.int("EMAIL_PORT", default=465)
EMAIL_USE_SSL = env.bool("EMAIL_USE_SSL", default=True)
EMAIL_HOST_USER = env("EMAIL_HOST_USER", default="resend")
EMAIL_HOST_PASSWORD = env("EMAIL_HOST_PASSWORD", default="")
DEFAULT_FROM_EMAIL = env("DEFAULT_FROM_EMAIL", default="Commandr <no-reply@localhost>")

# --- i18n / time -----------------------------------------------------------
LANGUAGE_CODE = "en"
LANGUAGES = [("en", "English"), ("pt", "Português")]
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

# --- Static ----------------------------------------------------------------
# Only the Django admin's assets; the SPA is served by Caddy.
STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

# --- Logging ---------------------------------------------------------------
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "filters": {
        "redact": {"()": "commandr.core.logging.RedactSecretsFilter"},
        "request_id": {"()": "commandr.core.logging.RequestIdFilter"},
    },
    "formatters": {
        "json": {"()": "commandr.core.logging.JsonFormatter"},
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "json",
            "filters": ["redact", "request_id"],
        },
    },
    "root": {"handlers": ["console"], "level": env("LOG_LEVEL", default="INFO")},
}
