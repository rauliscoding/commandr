# syntax=docker/dockerfile:1.7
# One image, several process types (web, ingest, worker, beat, migrate) — the
# command decides which. See docs/architecture/overview.md.

FROM python:3.13-slim AS base
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /app
RUN groupadd --system --gid 10001 commandr \
 && useradd --system --uid 10001 --gid commandr --home-dir /app --shell /usr/sbin/nologin commandr

# Dependencies in their own layer, so a code change does not reinstall them.
FROM base AS deps
COPY pyproject.toml ./
RUN python -c "import tomllib; d = tomllib.load(open('pyproject.toml','rb'))['project']; \
print('\n'.join(d['dependencies']))" > /tmp/requirements.txt \
 && pip install -r /tmp/requirements.txt

# Development: code is bind-mounted; adds test and lint tools.
FROM deps AS dev
RUN python -c "import tomllib; d = tomllib.load(open('pyproject.toml','rb'))['project']; \
print('\n'.join(d['optional-dependencies']['dev']))" > /tmp/requirements-dev.txt \
 && pip install -r /tmp/requirements-dev.txt
USER commandr
EXPOSE 8000

# Production.
FROM deps AS prod
COPY --chown=commandr:commandr . .
# collectstatic needs settings to import, not real secrets.
RUN DJANGO_SETTINGS_MODULE=config.settings.prod \
    DJANGO_SECRET_KEY=build-only \
    VAULT_KEYS=M0pDTXhQdFNqVnBHcG1TNXRGc2tYc1pxbW1YbWlRbE4= \
    DATABASE_URL=postgres://build@localhost/build \
    python manage.py collectstatic --noinput \
 && chown -R commandr:commandr /app/staticfiles
USER commandr
ENV DJANGO_SETTINGS_MODULE=config.settings.prod
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/healthz/', timeout=4).status == 200 else 1)"
CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "3", "--access-logfile", "-", "--forwarded-allow-ips", "*"]
