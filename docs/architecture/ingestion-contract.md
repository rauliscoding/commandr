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

`GET` also accepted for `curl`-in-cron simplicity (on all three; only `POST
/fail` carries a message). Configure in the UI: expected period and grace
("every day, alert when an hour late"). The token is the credential
(unguessable, revocable, scoped to one heartbeat): Commandr stores only its
SHA-256 and shows the URL **once**, at setup. Lost it? Remove the heartbeat
and add it again.

Responses: `204` recorded · `404` unknown or revoked token · `429` more than 60
pings a minute for this heartbeat (`Retry-After`). The `/fail` body (plain
text) is truncated to 1,000 characters and scrubbed of token-shaped strings.

A heartbeat that has never pinged is **waiting** (unknown), never "ok". It
fails when its last run reported a failure, or when no success arrived within
period + grace of the previous one.

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
Respond `401` otherwise, with no body detail. `<path>` is the request path
exactly as sent, **without the query string** (`/.well-known/commandr/status`).
`X-Commandr-Project` is `prj_` + the project id as 32 hex digits.

The secret is per project (every status endpoint and SDK in a project shares
it), shown once when the first status endpoint is set up, and stored
vault-encrypted because Commandr needs it to sign. Rotation with an overlap
window is planned; until then, rotating means removing and re-adding.

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
  per-route check that only exists while failing works naturally. Commandr
  sends the recovery message (if it had alerted) and removes the check.
- A KPI with `"value": null` is shown as "—" (not available), never as 0.
- Unreachable, non-200, invalid signature response, or invalid JSON → the project's
  synthetic `commandr.reachability` check fails. Timeouts count as failures.
  Redirects are not followed (a 3xx is a failure). A document that does not
  match the schema fails too, with the first problem in the check's summary.
- Polled every 5 min or every minute (chosen at setup). `ETag` / `304`
  honoured: Commandr sends `If-None-Match` with the last ETag.
- Requests come from the `poller`, through Commandr's SSRF guard: https only,
  public addresses only, 10 s, 1 MB.

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
−24 h / +5 min of now (with a time zone; a metric without `ts` gets the receipt
time). Each section optional. Rate limit: 600 requests a minute **per ingest
key** by default.

Cardinality caps (per plan; defaults): 2,000 metric series per project and 500
distinct values per attribute key per metric. An item over a cap is rejected
with `cardinality_limit` and a message naming the attribute; series that
already exist keep being accepted.

**Response** — `202 Accepted`:

```json
{"accepted": 3, "rejected": [
  {"section": "metrics", "index": 0, "code": "cardinality_limit",
   "message": "Attribute 'route' has more than 500 distinct values for this metric."}
]}
```

Partial acceptance is normal; a whole-request failure uses `400` (malformed,
including an unknown top-level field), `401` (missing, bad or revoked key),
`413` (body over 1 MB, or more than 1,000 items), `429` (rate limited,
`Retry-After`), `503` (temporarily not accepting — the queue is unavailable —
`Retry-After`). Error bodies are RFC 9457 problem documents with a `code`.
Clients retry `429`/`503`/network errors with exponential backoff and the same
`Idempotency-Key`. Idempotency keys are scoped to the ingest key; a repeat
within 24 h returns the first answer and is not queued again. Points are also
de-duplicated by `(series, ts)` and events and errors by `id`, so a retry that
slips past the idempotency window still stores nothing twice.

**Several processes, one series:** because of that de-duplication, two
processes that push the same counter series with the same `ts` keep only one
value. A client that runs in several processes (gunicorn or Celery workers)
must give each process distinct timestamps, for example by adding a random
sub-second offset per process to its window timestamps. The SDK does this.

Personal data: an attribute or property whose key names personal data
(`email`, `user_id`, `ip`, `name`, `phone`…) or whose value looks like an email
address or IP address is rejected with `personal_data`.

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

Source: [`sdks/python/commandr-django/`](../../sdks/python/commandr-django/), whose
README lists every setting. Supports Django 5.2, 6.0 and 6.1 on Python 3.10+;
it depends on nothing but Django. Set up from **Integrations → Django SDK**,
which creates one connection with an ingest key and a polled status endpoint
(help: [connectors/django-sdk.md](../connectors/django-sdk.md)).

Gives, with no further code:

- **Signed status endpoint** at `/.well-known/commandr/status`, verified exactly
  as in § 1 (401 with no body otherwise; with `PROJECT` set, a poll for another
  project is refused too). Built-in checks: `database` (one per database
  alias), `cache` (one per cache alias), `celery` (workers that answer a
  ping, when a Celery app is configured) and `disk`; gauges
  `system.cpu.load_per_core` and `system.memory.used_ratio` where the OS
  reports them. Each check runs in its own thread with a 5 s budget: one that
  raises or overruns is `fail` (only the exception type is reported), and one
  still stuck from the previous poll is not started again. The answer carries
  an `ETag` and honours `If-None-Match`.
- **Traffic** by **route template** (`api/items/{pk}/`, never the concrete
  path), aggregated in process and flushed every 60 s:
  `http.server.requests` counters (attrs `route`, `status_class`, with
  `interval_s`) and `http.server.duration_ms` gauges (attrs `route`,
  `quantile` = `p50` | `p95`). Over 200 routes in a window fold into `other`.
- **Errors** through a logging handler added to the root logger (records at
  ERROR and above). The fingerprint is `sha1:` of the type, the culprit (the
  innermost frame in the app's own code) and the frames without line numbers;
  a log record without an exception is grouped by logger, function and
  message template. At most 10 per fingerprint a minute.
- **Heartbeats**: `@commandr.heartbeat("nightly-prune")` pings `start`, then
  success or `fail` with the exception, which it re-raises. The token comes from
  `COMMANDR["HEARTBEATS"]`. Celery beat has no built-in check: a heartbeat on
  a frequent beat task covers it.

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

commandr.event("user.signup", plan="trial", user_id=user.pk)   # push, buffered, non-blocking
```

A check returns a `Check`, `True` or `False`; `None` is `unknown`. A KPI that
raises, overruns or returns `None` is sent as `null`, never 0. `user_id` is
sent only as `user_ref`, an HMAC keyed with the project's secret; event
properties that look like personal data (§ Push API) are left out with a
warning rather than getting the whole event rejected.

The SDK never blocks or raises into the host app: buffers are bounded (2,000
items; newer items are dropped when full), sending is on one background thread
per process (restarted after a fork), a failed batch is retried with backoff
and the same `Idempotency-Key` up to 5 times, redirects are not followed, and
failures are logged at WARNING at most once a minute. Its tests validate the
status document and every pushed batch against
[openapi/ingest-v1.yaml](openapi/ingest-v1.yaml), and sign requests with the
server's own `monitoring/signing.py`.

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
