# Django SDK

One `pip install` gives a Django app everything on the Health page: a signed
status endpoint (database, cache, Celery, disk, plus your own checks and KPIs),
per-route traffic, errors from logging, and heartbeats for scheduled jobs. It
does what the [status endpoint](status-endpoint.md) and the
[push API](push-api.md) do, without you writing either. The formats are the
[ingestion contract § SDK](../architecture/ingestion-contract.md#3-sdk--commandr-django).

Supports Django 5.2, 6.0 and 6.1 on Python 3.10 or later. The package is in
`sdks/python/commandr-django/` and its README lists every setting.

## Set it up

1. **Integrations → Django SDK → Connect.**
2. Enter the address where your app will serve its status, usually
   `https://api.example.com/.well-known/commandr/status`, and choose how often
   it is checked.
3. Copy what Commandr shows. **Each value is shown only once.**
   - The **ingest key** (`COMMANDR_INGEST_KEY`) lets the SDK push traffic,
     errors and events. It is write-only.
   - The **signing secret** (`COMMANDR_SIGNING_SECRET`) appears only the
     first time in a project. Every status endpoint and SDK in the project
     shares it.
4. Install the package and add the settings the wizard shows:

   ```python
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

5. Deploy. Commandr polls the address straight away. The wizard switches to
   "first data" when either the first valid status document or the first
   batch of traffic arrives. Until then it shows what went wrong, for example
   "your app refused our signature", and a **Check again** button.

## What you get

- **Checks**: `database`, `cache`, `celery` (workers that answer a ping)
  and `disk`, plus anything you register with `@commandr.check`. Each check
  reports `ok`, `warn`, `fail` or `unknown`.
  - A check that raises, or runs longer than 5 seconds, is `fail`. Only the
    exception type is reported, never its message.
  - If a check is still stuck from the previous poll, it is not started again.
- *"api.example.com answers"*: fails when Commandr cannot reach your app or
  gets an invalid answer, as for any status endpoint.
- **KPIs** from `@commandr.kpi` and **gauges** from `@commandr.gauge`, plus CPU
  load and memory use on Linux. A KPI that fails shows as "—", never 0.
- **Traffic**: `http.server.requests` per route template and status class,
  and `http.server.duration_ms` (p50, p95) per route, sent every minute.
  Templates look like `api/items/{pk}/`, so no ids or other personal data are
  sent.
- **Errors**: everything logged at ERROR or above, grouped by fingerprint.
  The fingerprint is built from the exception type, the innermost frame in
  your own code, and the stack without line numbers, so a deploy keeps the
  group. At most 10 occurrences of one group are sent per minute.
- **Heartbeats**: add a [heartbeat](heartbeat.md) in Commandr, put its token
  in `COMMANDR["HEARTBEATS"]`, and decorate the job with
  `@commandr.heartbeat("name")`.
  - The SDK has no separate check for Celery beat. Put a heartbeat on a task
    that beat runs often: it proves that beat schedules and a worker runs.

## Privacy

`commandr.event(..., user_id=…)` sends only `user_ref`, a hash keyed with
your project's secret. Event properties that look like personal data are
left out, and you get a warning. These are email addresses, IP addresses,
and keys such as `email`, `name` or `user_id`. Error messages and stacks are
sent as they are. The server removes token-shaped strings from them, but
avoid logging personal data at ERROR.

## It never gets in your app's way

Sending happens on a background thread, and the buffers are bounded: 2,000
items by default, and newer items are dropped when the buffer is full. A
failed send is retried with backoff, then dropped. The SDK logs a WARNING at
most once a minute and never raises into a request or a job. If
`SIGNING_SECRET` is missing, the status endpoint answers 401 and
`manage.py check` warns.

## Removing it

Remove the source on the Health page. The ingest key stops working from the
next request on, and the status checks are removed. The signing secret stays,
because it belongs to the project.
