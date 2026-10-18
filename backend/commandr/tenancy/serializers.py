from rest_framework import serializers

from .models import Organization, Project, ProjectKind


class ProjectSerializer(serializers.ModelSerializer[Project]):
    class Meta:
        model = Project
        fields = ["id", "name", "url", "kind", "created_at"]
        read_only_fields = ["id", "created_at"]

    def validate_name(self, value: str) -> str:
        value = value.strip()
        if not value:
            raise serializers.ValidationError("Give the project a name.")
        qs = Project.objects.filter(name__iexact=value)
        if self.instance is not None:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError("A project with this name already exists.")
        return value


class OrganizationSerializer(serializers.ModelSerializer[Organization]):
    class Meta:
        model = Organization
        fields = ["id", "name", "country", "currency", "timezone", "created_at"]
        read_only_fields = ["id", "created_at"]


class OrganizationCreateSerializer(serializers.Serializer[dict[str, object]]):
    """Onboarding: an organization and its first project together."""

    name = serializers.CharField(max_length=120)
    country = serializers.RegexField(r"^[A-Z]{2}$", required=False, allow_blank=True)
    currency = serializers.RegexField(r"^[A-Z]{3}$", default="EUR")
    timezone = serializers.CharField(max_length=64, default="UTC")
    project_name = serializers.CharField(max_length=120)
    project_url = serializers.URLField(required=False, allow_blank=True)
    project_kind = serializers.ChoiceField(choices=ProjectKind.choices, default=ProjectKind.WEB_APP)
