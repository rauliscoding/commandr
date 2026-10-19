"""A throwaway project: the smallest Django app a customer could have."""

SECRET_KEY = "test-only-not-secret"
DEBUG = False
ALLOWED_HOSTS = ["testserver", "localhost"]
USE_TZ = True
ROOT_URLCONF = "testproject.urls"
INSTALLED_APPS = [
    "django.contrib.contenttypes",
    "django.contrib.auth",
    "commandr_django",
]
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "commandr_django.middleware.TrafficMiddleware",
    "django.middleware.common.CommonMiddleware",
]
DATABASES = {"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": ":memory:"}}
CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
COMMANDR = {
    "INGEST_KEY": "cmdr_ingest_test_" + "x" * 43,
    "SIGNING_SECRET": "test-signing-secret",
    "SERVICE": "testproject",
    "VERSION": "1.2.0",
    "ENVIRONMENT": "test",
    "INGEST_URL": "http://127.0.0.1:9",  # replaced per test by the fake ingest server
    "FLUSH_INTERVAL": 3600,  # tests flush by hand
}
