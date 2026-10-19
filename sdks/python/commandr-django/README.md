# commandr-django

Sends a Django app's health checks, KPIs, per-route traffic, errors and job
heartbeats to [Commandr](https://github.com/rauliscoding/commandr).

- A **signed status endpoint** at `/.well-known/commandr/status`, which Commandr
  polls: database, cache, Celery workers and disk checks are built in, and you
  add your own checks, KPIs and gauges.
- **Traffic** per route template (`api/items/{pk}/`), aggregated in the process
  and sent every 60 seconds.
- **Errors** from logging, grouped by fingerprint.
- **Heartbeats** for scheduled jobs: `@commandr.heartbeat("nightly-prune")`.

It never blocks or raises into your app. Buffers are bounded, sending happens
on a background thread, and problems are logged at WARNING at most once a
minute. It depends only on Django (5.2, 6.0 and 6.1, on Python 3.10 or later).

## Install

```bash
pip install commandr-django
```

```python
# settings.py
INSTALLED_APPS += ["commandr_django"]
MIDDLEWARE.insert(1, "commandr_django.middleware.TrafficMiddleware")
COMMANDR = {
    "INGEST_KEY": env("COMMANDR_INGEST_KEY"),
    "SIGNING_SECRET": env("COMMANDR_SIGNING_SECRET"),
    "SERVICE": "my-api",
}

# urls.py
urlpatterns += [path("", include("commandr_django.urls"))]
```

Get the key and the secret from **Integrations → Django SDK → Connect** in
Commandr. Each is shown once. `python manage.py check` warns if one is missing.

## Your own checks and KPIs

```python
import shutil

import commandr_django as commandr


@commandr.check("disk:External", name="External volume")
def external_volume():
    usage = shutil.disk_usage("/mnt/external")
    return commandr.Check.from_ratio(usage.used / usage.total, warn=0.85, fail=0.95)


@commandr.kpi("user.total", label="Users", unit="count")
def users_total():
    return User.objects.count()


@commandr.gauge("queue.depth", attrs={"queue": "emails"})
def email_queue():
    return EmailJob.objects.filter(sent_at=None).count()


commandr.event("user.signup", plan="trial", user_id=user.pk)  # user_id is sent hashed
```

A check returns a `Check`, `True` (ok) or `False` (fail). If it returns `None`,
the status is `unknown`. If it raises, or takes longer than `CHECK_TIMEOUT`, the
status is `fail`. Only the exception type is reported, never its message. A KPI
that raises or returns `None` is reported as "not available", never as 0.

Put the decorated functions in a module Django imports at start-up, such as
your app's `checks.py` imported from `AppConfig.ready()`.

## Heartbeats

```python
COMMANDR["HEARTBEATS"] = {"nightly-prune": env("COMMANDR_HB_NIGHTLY_PRUNE")}


@app.task
@commandr.heartbeat("nightly-prune")  # under @app.task, so it wraps the job itself
def nightly_prune(): ...
```

The decorator pings `start` before the job runs. It then pings success, or
`fail` with the exception, and re-raises the exception unchanged. The value in
`HEARTBEATS` is the token, or the whole URL that Commandr showed at setup.

## Settings

| Key | Default | |
|---|---|---|
| `INGEST_KEY` | — | Write-only key for the push API. Without it, nothing is pushed. |
| `SIGNING_SECRET` | — | Verifies Commandr's polls. Without it, the status endpoint answers 401. |
| `SERVICE` | `"django"` | This app's name in Commandr. |
| `VERSION`, `ENVIRONMENT` | — | Shown with the data. |
| `INGEST_URL` | `https://ingest.commandr.app` | Your own Commandr's ingest address, if you self-host. |
| `PROJECT` | — | `prj_…`: refuse polls signed for another project. |
| `HEARTBEATS` | `{}` | Name → token or URL. |
| `BUILTINS` | all | Any of `database`, `cache`, `celery`, `disk`, `system`. |
| `DISK_PATHS` | `{"Disk": "/"}` | Label → path. The first one is `disk`, the others `disk:<label>`. |
| `DISK_WARN`, `DISK_FAIL` | `0.85`, `0.95` | Used-space ratios. |
| `CELERY_APP` | Celery's current app | Dotted path to your Celery app. |
| `CAPTURE_ERRORS` | `True` | Add the error handler to the root logger. |
| `TRAFFIC_EXCLUDE` | `("/.well-known/commandr/",)` | Path prefixes that are not counted. |
| `FLUSH_INTERVAL` | `60` | Seconds between pushes. |
| `CHECK_TIMEOUT` | `5` | Seconds the checks get, together. |
| `SEND_TIMEOUT` | `10` | Seconds for one request to Commandr. |
| `MAX_BUFFER` | `2000` | Items waiting to be sent. New items beyond this are dropped. |
| `ENABLED` | `True` | `False` turns everything off, for example in tests. |

If your `LOGGING` sets `propagate: False` on a logger whose errors you want,
add the handler there yourself: `"class": "commandr_django.CommandrHandler"`.

## Development

```bash
pip install -e ".[dev]"
ruff check . && ruff format --check . && mypy src tests && pytest
tox -p auto   # every supported Django on every supported Python
```

The tests check the status document and every pushed batch against the
contract in `docs/architecture/openapi/ingest-v1.yaml`. They also sign
requests with the server's own `backend/commandr/monitoring/signing.py`, so
they need the whole repository.

Licence: AGPL-3.0-only, like the rest of Commandr.
