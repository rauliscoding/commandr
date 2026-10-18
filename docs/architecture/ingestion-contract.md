# Ingestion contract v1

How any developer's app feeds Commandr. This is a **public contract**: once
released, v1 changes only by adding optional fields. Machine-readable form:
[openapi/ingest-v1.yaml](openapi/ingest-v1.yaml).

## Four ways in, in order of effort

| | Method | Developer effort | Best for |
|---|---|---|---|
| 0 | **Uptime probe** — we call a URL | None | "Is it up?" |
| 0 | **Heartbeat** — they call a unique URL after each job run | One `curl` | Cron jobs, Celery beat, backups |
| 1 | **Status endpoint (pull)** — they expose a JSON document, we poll it, signed | One endpoint | Current state: checks, gauges, KPI totals |
| 2 | **Push API** — they POST batches | A few calls | Things that happen: events, counters, errors |
| 3 | **SDK** — does 1 + 2 for them | `pip install` + 3 lines of settings | Django today; Node and FastAPI next |
| later | **OTLP/HTTP** | Point an OpenTelemetry exporter at us | Teams already instrumented |

Pull answers **"what is true now"** and doubles as liveness (no answer = down).
Push answers **"what happened"** and works from networks we cannot reach. Most
apps use both, which is what the SDK does.

## Concepts

- **Project** — one app. Each has ingest keys, a signing secret and a status URL.
- **Check** — a named pass/fail with a status: `ok | warn | fail | unknown`.
- **Gauge** — a value right now (queue depth, disk ratio).
- **Counter** — a monotonically increasing total, or a delta when pushed.
- **KPI** — a business number shown on the dashboard with a label and unit.
- **Event** — something that happened at a time (`user.signup`).
- **Error** — an exception with a fingerprint for grouping.

### Naming

`lowercase.dot.separated`, `[a-z0-9_.]`, max 120 chars. Reserved namespaces get
built-in dashboards and default alerts, following OpenTelemetry semantic
conventions where one exists:

| Namespace | Examples |
|---|---|
| `system.*` | `system.cpu.load_per_core`, `system.memory.used_ratio`, `system.disk.used_ratio` |
| `http.*` | `http.server.requests` (attrs `route`, `status_class`), `http.server.duration_ms` |
| `queue.*` | `queue.depth`, `queue.workers` |
| `job.*` | `job.last_success_at` |
| `user.*` | `user.signup`, `user.active` |
| `revenue.*` | `revenue.subscriptions.active`, `revenue.mrr` |

Anything else is custom and appears under the project's KPIs.

### Attributes

Up to 8 attributes per point, string values ≤ 128 chars. **No personal data** —
no emails, names, IPs or user ids in attributes or event properties (the SDK
hashes `user_id` if given). Attribute cardinality is capped per plan; high-
cardinality keys (`route` is fine; `user_id` is not) are rejected with an error
that says so.

## 0. Heartbeats

```
POST https://ingest.commandr.app/v1/heartbeat/<token>          # success
POST https://ingest.commandr.app/v1/heartbeat/<token>/fail     # explicit failure
POST https://ingest.commandr.app/v1/heartbeat/<token>/start    # optional: measures duration
```

`GET` also accepted for `curl`-in-cron simplicity. Configure in the UI: expected
period and grace ("every 5 min, alert after 16 min"). The token is the credential
(unguessable, revocable, scoped to one heartbeat).

## 1. Status endpoint (pull)

The customer exposes, at a path they choose (default
`/.well-known/commandr/status`):

```http
GET /.well-known/commandr/status HTTP/1.1
Host: api.pantrini.app
User-Agent: Commandr-Poller/1 (+https://commandr.app/poller)
X-Commandr-Signature: t=1760600000,v1=5f2b…
X-Commandr-Project: prj_01JA…
```

**Verification (customer side):** compute `HMAC-SHA256(secret, "<t>.GET.<path>")`,
hex-encode, compare in constant time with `v1`; reject if `|now − t| > 300`.
Respond `401` otherwise, with no body detail.

**Response** — `200`, `application/json`, ≤ 1 MB, within 10 s:

```json
{
  "schema": "commandr.status/v1",
  "service": "pantrini-api",
  "version": "1.2.0",
  "environment": "production",
  "generated_at": "2026-10-16T06:00:00Z",
  "checks": [
    {"key": "database", "name": "PostgreSQL", "status": "ok", "summary": "reachable"},
    {"key": "heartbeat", "name": "Scheduled jobs", "status": "ok", "summary": "3 min ago"},
    {"key": "disk:External", "name": "External volume", "status": "warn",
     "summary": "86.2 / 100 GB", "value": 0.862, "unit": "ratio"}
  ],
  "gauges": [
    {"name": "system.cpu.load_per_core", "value": 0.16},
    {"name": "system.memory.used_ratio", "value": 0.48},
    {"name": "queue.depth", "value": 3, "attrs": {"queue": "celery"}}
  ],
  "kpis": [
    {"name": "user.total", "label": "Users", "value": 412, "unit": "count"},
    {"name": "pantry.items.total", "label": "Pantry items", "value": 18734, "unit": "count"},
    {"name": "revenue.subscriptions.trials_ending_48h", "label": "Trials ending in 48h",
     "value": 2, "unit": "count"}
  ]
}
```

Rules:

- `status` is the app's own judgement; Commandr can add rules on top (`value`).
- A check absent from one poll to the next is **recovered**, not unknown — so a
  per-route check that only exists while failing works naturally.
- Unreachable, non-200, invalid signature response, or invalid JSON → the project's
  synthetic `commandr.reachability` check fails. Timeouts count as failures.
- Polled every 5 min (free) / 1 min (paid). `ETag` / `304` honoured.

## 2. Push API

```http
POST https://ingest.commandr.app/v1/ingest
Authorization: Bearer cmdr_ingest_live_…
Content-Type: application/json
Idempotency-Key: 01JA9Z…            # optional, recommended; 24h window
```

```json
{
  "schema": "commandr.ingest/v1",
  "sent_at": "2026-10-16T06:00:01Z",
  "resource": {"service": "pantrini-api", "version": "1.2.0", "environment": "production"},
  "metrics": [
    {"name": "http.server.requests", "type": "counter", "value": 1203,
     "ts": "2026-10-16T06:00:00Z", "interval_s": 60,
     "attrs": {"route": "api/pantries/", "status_class": "2xx"}},
    {"name": "queue.depth", "type": "gauge", "value": 3, "ts": "2026-10-16T06:00:00Z"}
  ],
  "events": [
    {"id": "evt_01JA…", "name": "user.signup", "ts": "2026-10-16T05:59:12Z",
     "props": {"plan": "trial", "source": "web"}}
  ],
  "errors": [
    {"id": "err_01JA…", "ts": "2026-10-16T05:58:40Z", "level": "error",
     "fingerprint": "sha1:9c1e…", "type": "KeyError", "message": "'unit'",
     "culprit": "apps.pantries.views.PantryItemViewSet.create",
     "stack": "Traceback (most recent call last): …",
     "attrs": {"route": "api/pantries/{id}/items/"}}
  ]
}
```

Limits per request: ≤ 1 MB body, ≤ 1,000 items total, timestamps within
−24 h / +5 min of now. Each section optional.

**Response** — `202 Accepted`:

```json
{"accepted": 3, "rejected": [
  {"section": "metrics", "index": 0, "code": "cardinality_limit",
   "message": "Attribute 'route' has more than 500 distinct values for this metric."}
]}
```

Partial acceptance is normal; a whole-request failure uses `400` (malformed),
`401` (bad key), `413` (too large), `429` (rate limited, `Retry-After`),
`503` (temporarily not accepting, `Retry-After`). Clients retry `429`/`503`/network
errors with exponential backoff and the same `Idempotency-Key`.

Errors are grouped by `fingerprint` (SDK computes it from type + culprit + normalised
frames); the stack is truncated to 64 KB and scrubbed of obvious secrets
server-side as a second line of defence.

## 3. SDK — `commandr-django`

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
    "SERVICE": "pantrini-api",
}
# urls.py
urlpatterns += [path("", include("commandr_django.urls"))]   # mounts the status endpoint
```

Gives, with no further code: signed status endpoint; database, cache, Celery
worker/beat and disk checks; per-route traffic by **route template** (in-process
aggregation, flushed every 60 s); error capture via a logging handler; a
`@commandr.heartbeat("nightly-prune")` decorator for tasks.

Custom checks and KPIs:

```python
import commandr_django as commandr

@commandr.check("disk:External", name="External volume")
def external_volume():
    usage = shutil.disk_usage("/mnt/external")
    ratio = usage.used / usage.total
    return commandr.Check.from_ratio(ratio, warn=0.85, fail=0.95, unit="ratio")

@commandr.kpi("user.total", label="Users", unit="count")
def users_total():
    return User.objects.count()

commandr.event("user.signup", plan="trial")     # push, buffered, non-blocking
```

The SDK never blocks or raises into the host app: buffers are bounded, sending is
on a background thread, failures are logged at WARNING once per minute.

**Pantrini migration path:** `apps/ops/checks.py` checks become `@commandr.check`
functions, `metrics.growth()` rows become `@commandr.kpi`s, `traffic.py` is
replaced by the SDK middleware, `log_handler.py` by the SDK handler — and the
watchdog's emails move to Commandr's alerts and digest.

## Versioning

- URL-versioned (`/v1/`) and schema-tagged (`commandr.ingest/v1`).
- Within v1: only optional fields are added; unknown fields in **responses** must
  be ignored by clients; unknown top-level fields in **requests** are rejected
  (catches typos).
- A v2 runs alongside v1 for at least 12 months.
