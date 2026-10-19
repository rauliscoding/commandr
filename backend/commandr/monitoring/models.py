"""Metrics, checks, alert rules, notifications and the things that poll.

Raw points live in a monthly-partitioned table (ADR 0006); dashboards read the
1-minute and 1-hour rollups. Every table is tenant-owned and under RLS,
including each partition of `monitoring_metricpoint` (migration 0001).
"""

from django.conf import settings
from django.db import models

from commandr.core.ids import uuid7
from commandr.integrations.models import Connection
from commandr.tenancy.models import Project, TenantOwned


class MetricKind(models.TextChoices):
    COUNTER = "counter", "Counter"
    GAUGE = "gauge", "Gauge"
    KPI = "kpi", "KPI"


class MetricSeries(TenantOwned):
    """One metric name + attribute set in one project.

    `last_value` / `last_at` are the latest report, kept here so the Health
    page never scans points. `last_value` is NULL when the latest report said
    "not available" (or nothing was ever reported): unknown is not zero.
    """

    id = models.UUIDField(primary_key=True, default=uuid7, editable=False)
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="metric_series")
    name = models.CharField(max_length=120)
    kind = models.CharField(max_length=8, choices=MetricKind.choices)
    label = models.CharField(max_length=120, blank=True)
    unit = models.CharField(max_length=32, blank=True)
    attrs = models.JSONField(default=dict, blank=True)
    attrs_hash = models.CharField(max_length=64)
    last_value = models.FloatField(null=True, blank=True)
    last_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta(TenantOwned.Meta):
        constraints = [
            models.UniqueConstraint(
                fields=["project", "name", "attrs_hash"], name="uniq_metric_series"
            ),
        ]

    def __str__(self) -> str:
        return self.name


class MetricPoint(TenantOwned):
    """A raw point. Partitioned by month on `ts`; created by raw SQL in 0001.

    The composite primary key makes every write idempotent: the same point
    sent twice (a retried batch, a replayed stream entry) is stored once.
    """

    pk = models.CompositePrimaryKey("series_id", "ts")
    series = models.ForeignKey(MetricSeries, on_delete=models.CASCADE, related_name="+")
    ts = models.DateTimeField()
    value = models.FloatField()

    def __str__(self) -> str:
        return f"{self.series_id}@{self.ts.isoformat()}"


class MetricRollup1m(TenantOwned):
    pk = models.CompositePrimaryKey("series_id", "bucket")
    series = models.ForeignKey(MetricSeries, on_delete=models.CASCADE, related_name="+")
    bucket = models.DateTimeField()
    min = models.FloatField()
    max = models.FloatField()
    sum = models.FloatField()
    count = models.PositiveIntegerField()
    last = models.FloatField()
    last_ts = models.DateTimeField()

    def __str__(self) -> str:
        return f"{self.series_id}@{self.bucket.isoformat()}"


class MetricRollup1h(TenantOwned):
    pk = models.CompositePrimaryKey("series_id", "bucket")
    series = models.ForeignKey(MetricSeries, on_delete=models.CASCADE, related_name="+")
    bucket = models.DateTimeField()
    min = models.FloatField()
    max = models.FloatField()
    sum = models.FloatField()
    count = models.PositiveIntegerField()
    last = models.FloatField()
    last_ts = models.DateTimeField()

    def __str__(self) -> str:
        return f"{self.series_id}@{self.bucket.isoformat()}"


class Event(TenantOwned):
    """Something that happened (`user.signup`). No personal data: validated at ingest."""

    id = models.UUIDField(primary_key=True, default=uuid7, editable=False)
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="+")
    name = models.CharField(max_length=120)
    ts = models.DateTimeField()
    props = models.JSONField(default=dict, blank=True)
    client_id = models.CharField(max_length=64, blank=True)  # "" = none given
    received_at = models.DateTimeField(auto_now_add=True)

    class Meta(TenantOwned.Meta):
        constraints = [
            models.UniqueConstraint(
                fields=["project", "client_id"],
                condition=~models.Q(client_id=""),
                name="uniq_event_client_id",
            ),
        ]
        indexes = [models.Index(fields=["project", "name", "ts"])]

    def __str__(self) -> str:
        return self.name


class ErrorLevel(models.TextChoices):
    WARNING = "warning", "Warning"
    ERROR = "error", "Error"
    CRITICAL = "critical", "Critical"


class ErrorGroup(TenantOwned):
    id = models.UUIDField(primary_key=True, default=uuid7, editable=False)
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="+")
    fingerprint = models.CharField(max_length=128)
    type = models.CharField(max_length=200, blank=True)
    message = models.CharField(max_length=2000)
    culprit = models.CharField(max_length=500, blank=True)
    level = models.CharField(max_length=8, choices=ErrorLevel.choices)
    first_seen = models.DateTimeField()
    last_seen = models.DateTimeField()
    count = models.PositiveBigIntegerField(default=0)

    class Meta(TenantOwned.Meta):
        constraints = [
            models.UniqueConstraint(fields=["project", "fingerprint"], name="uniq_error_group"),
        ]

    def __str__(self) -> str:
        return self.fingerprint


class ErrorOccurrence(TenantOwned):
    id = models.UUIDField(primary_key=True, default=uuid7, editable=False)
    group = models.ForeignKey(ErrorGroup, on_delete=models.CASCADE, related_name="occurrences")
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="+")
    ts = models.DateTimeField()
    level = models.CharField(max_length=8, choices=ErrorLevel.choices)
    message = models.CharField(max_length=2000)
    stack = models.TextField(blank=True)  # truncated to 64 KB and scrubbed of secrets
    attrs = models.JSONField(default=dict, blank=True)
    client_id = models.CharField(max_length=64, blank=True)  # "" = none given

    class Meta(TenantOwned.Meta):
        constraints = [
            models.UniqueConstraint(
                fields=["project", "client_id"],
                condition=~models.Q(client_id=""),
                name="uniq_error_client_id",
            ),
        ]
        indexes = [models.Index(fields=["group", "-ts"])]

    def __str__(self) -> str:
        return f"{self.group_id}@{self.ts.isoformat()}"


class CheckStatus(models.TextChoices):
    OK = "ok", "OK"
    WARN = "warn", "Warning"
    FAIL = "fail", "Failing"
    UNKNOWN = "unknown", "Unknown"


class CheckSource(models.TextChoices):
    UPTIME = "uptime", "Uptime probe"
    HEARTBEAT = "heartbeat", "Heartbeat"
    STATUS_ENDPOINT = "status_endpoint", "Status endpoint"
    RULE = "rule", "Alert rule"


class AlertState(models.TextChoices):
    OK = "ok", "Not alerting"
    ALERTING = "alerting", "Alerting"


class Check(TenantOwned):
    """A named pass/fail, from wherever it came. Carries its own alert state.

    `last_run_at` is when the check was last *evaluated*; a check whose source
    has gone quiet turns unknown after three `expected_every_seconds`, so
    "nothing was checked" never looks healthy (invariant 5).
    """

    id = models.UUIDField(primary_key=True, default=uuid7, editable=False)
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="checks")
    source = models.CharField(max_length=16, choices=CheckSource.choices)
    source_id = models.UUIDField()  # the monitor, heartbeat, endpoint or rule
    key = models.CharField(max_length=200)
    name = models.CharField(max_length=200)
    status = models.CharField(
        max_length=8, choices=CheckStatus.choices, default=CheckStatus.UNKNOWN
    )
    summary = models.CharField(max_length=500, blank=True)
    value = models.FloatField(null=True, blank=True)
    unit = models.CharField(max_length=32, blank=True)
    expected_every_seconds = models.PositiveIntegerField(null=True, blank=True)
    last_run_at = models.DateTimeField(null=True, blank=True)
    changed_at = models.DateTimeField(null=True, blank=True)
    alert_state = models.CharField(max_length=8, choices=AlertState.choices, default=AlertState.OK)
    alerted_at = models.DateTimeField(null=True, blank=True)
    last_notified_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta(TenantOwned.Meta):
        constraints = [
            models.UniqueConstraint(
                fields=["project", "source", "source_id", "key"], name="uniq_check_key"
            ),
        ]
        ordering = ["name"]

    def __str__(self) -> str:
        return f"{self.name}: {self.status}"


class RuleKind(models.TextChoices):
    THRESHOLD = "threshold", "Threshold"
    ABSENCE = "absence", "Missing data"


class Comparator(models.TextChoices):
    GT = "gt", ">"
    GTE = "gte", "≥"
    LT = "lt", "<"
    LTE = "lte", "≤"


class Severity(models.TextChoices):
    WARN = "warn", "Warning"
    FAIL = "fail", "Failing"


class AlertRule(TenantOwned):
    """Turns a metric into a check: a threshold on its latest value, or its absence."""

    id = models.UUIDField(primary_key=True, default=uuid7, editable=False)
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="alert_rules")
    name = models.CharField(max_length=120)
    metric = models.CharField(max_length=120)
    attrs = models.JSONField(default=dict, blank=True)  # exact match; {} = any series
    kind = models.CharField(max_length=16, choices=RuleKind.choices)
    comparator = models.CharField(max_length=4, choices=Comparator.choices, blank=True)
    threshold = models.FloatField(null=True, blank=True)
    window_seconds = models.PositiveIntegerField(default=600)
    severity = models.CharField(max_length=8, choices=Severity.choices, default=Severity.FAIL)
    enabled = models.BooleanField(default=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta(TenantOwned.Meta):
        ordering = ["created_at"]

    def __str__(self) -> str:
        return self.name


class NotificationKind(models.TextChoices):
    ALERT = "alert", "Alert"
    REMINDER = "reminder", "Still failing"
    RECOVERY = "recovery", "Passing again"
    DIGEST = "digest", "Daily digest"


class Notification(TenantOwned):
    """Outbox row: written in the same transaction as the state change that
    caused it, sent by a task. `dedupe_key` makes creating it idempotent and
    `sent_at` makes sending it idempotent."""

    id = models.UUIDField(primary_key=True, default=uuid7, editable=False)
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="+")
    kind = models.CharField(max_length=16, choices=NotificationKind.choices)
    dedupe_key = models.CharField(max_length=200)
    subject = models.CharField(max_length=200)
    body_text = models.TextField()
    body_html = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    sent_at = models.DateTimeField(null=True, blank=True)
    attempts = models.PositiveSmallIntegerField(default=0)
    last_error = models.CharField(max_length=500, blank=True)

    class Meta(TenantOwned.Meta):
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "dedupe_key"], name="uniq_notification_dedupe"
            ),
        ]
        indexes = [models.Index(fields=["project", "-created_at"])]

    def __str__(self) -> str:
        return self.subject


class UptimeMonitor(TenantOwned):
    """An address we request from Commandr's network every minute or five."""

    id = models.UUIDField(primary_key=True, default=uuid7, editable=False)
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="+")
    connection = models.OneToOneField(
        Connection, on_delete=models.CASCADE, related_name="uptime_monitor"
    )
    url = models.CharField(max_length=2000)
    interval_seconds = models.PositiveIntegerField(default=300)
    next_run_at = models.DateTimeField()
    last_run_at = models.DateTimeField(null=True, blank=True)
    last_status_code = models.PositiveSmallIntegerField(null=True, blank=True)
    last_response_ms = models.PositiveIntegerField(null=True, blank=True)
    tls_expires_at = models.DateTimeField(null=True, blank=True)
    last_error = models.CharField(max_length=500, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta(TenantOwned.Meta):
        indexes = [models.Index(fields=["next_run_at"])]

    def __str__(self) -> str:
        return self.url


class StatusEndpoint(TenantOwned):
    """A customer's status document, polled with a signed request."""

    id = models.UUIDField(primary_key=True, default=uuid7, editable=False)
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="+")
    connection = models.OneToOneField(
        Connection, on_delete=models.CASCADE, related_name="status_endpoint"
    )
    url = models.CharField(max_length=2000)
    interval_seconds = models.PositiveIntegerField(default=300)
    etag = models.CharField(max_length=200, blank=True)
    next_run_at = models.DateTimeField()
    last_run_at = models.DateTimeField(null=True, blank=True)
    last_ok_at = models.DateTimeField(null=True, blank=True)
    last_error = models.CharField(max_length=500, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta(TenantOwned.Meta):
        indexes = [models.Index(fields=["next_run_at"])]

    def __str__(self) -> str:
        return self.url
