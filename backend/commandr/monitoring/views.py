from typing import Any

from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import generics, serializers
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response

from commandr.audit.services import record
from commandr.tenancy.mixins import OrgScopedMixin
from commandr.tenancy.models import Project, Role
from commandr.tenancy.permissions import HasOrgRole

from . import rules
from .health import snapshot
from .models import AlertRule, Check, CheckSource, RuleKind


class HealthView(OrgScopedMixin):
    """Everything the Health page shows, in one read."""

    permission_classes = [IsAuthenticated, HasOrgRole]

    def get(self, request: Request, org_id: Any, project_id: Any) -> Response:
        project = get_object_or_404(Project.objects.all(), pk=project_id)
        return Response(snapshot(project, timezone.now()))


class AlertRuleSerializer(serializers.ModelSerializer[AlertRule]):
    metric = serializers.RegexField(r"^[a-z0-9_]+(\.[a-z0-9_]+)*$", max_length=120)

    class Meta:
        model = AlertRule
        fields = [
            "id",
            "name",
            "metric",
            "attrs",
            "kind",
            "comparator",
            "threshold",
            "window_seconds",
            "severity",
            "enabled",
            "created_at",
        ]
        read_only_fields = ["id", "created_at"]

    def validate_window_seconds(self, value: int) -> int:
        if not 60 <= value <= 7 * 86400:
            raise serializers.ValidationError("Between 1 minute and 7 days.")
        return value

    def validate_attrs(self, value: Any) -> dict[str, str]:
        if not isinstance(value, dict) or not all(
            isinstance(k, str) and isinstance(v, str) for k, v in value.items()
        ):
            raise serializers.ValidationError("Attributes are string keys and values.")
        return value

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        kind = attrs.get("kind", getattr(self.instance, "kind", None))
        if kind == RuleKind.THRESHOLD:
            comparator = attrs.get("comparator", getattr(self.instance, "comparator", ""))
            threshold = attrs.get("threshold", getattr(self.instance, "threshold", None))
            errors = {}
            if not comparator:
                errors["comparator"] = "A threshold rule needs a comparison."
            if threshold is None:
                errors["threshold"] = "A threshold rule needs a value."
            if errors:
                raise serializers.ValidationError(errors)
        return attrs


class _RuleMixin(OrgScopedMixin):
    permission_classes = [IsAuthenticated, HasOrgRole]
    write_role = Role.ADMIN

    def _project(self) -> Project:
        project: Project = get_object_or_404(Project.objects.all(), pk=self.kwargs["project_id"])
        return project

    def get_queryset(self) -> Any:
        return AlertRule.objects.filter(project=self._project())


class AlertRuleListCreateView(_RuleMixin, generics.ListCreateAPIView[AlertRule]):
    serializer_class = AlertRuleSerializer

    def perform_create(self, serializer: Any) -> None:
        project = self._project()
        rule = serializer.save(project=project, created_by=self.request.user)
        rules.apply(rule, project, timezone.now())
        record(
            "alert_rule.created",
            actor=self.request.user,  # type: ignore[arg-type]
            organization=self.request.organization,  # type: ignore[attr-defined]
            target=rule,
        )


class AlertRuleDetailView(_RuleMixin, generics.RetrieveUpdateDestroyAPIView[AlertRule]):
    serializer_class = AlertRuleSerializer
    lookup_url_kwarg = "rule_id"

    def perform_update(self, serializer: Any) -> None:
        rule = serializer.save()
        rules.apply(rule, rule.project, timezone.now())

    def perform_destroy(self, instance: AlertRule) -> None:
        Check.objects.filter(source=CheckSource.RULE, source_id=instance.id).delete()
        record(
            "alert_rule.deleted",
            actor=self.request.user,  # type: ignore[arg-type]
            organization=self.request.organization,  # type: ignore[attr-defined]
            target=instance,
        )
        instance.delete()
