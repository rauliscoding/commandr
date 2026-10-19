from django.urls import path

from . import views

_PROJECT = "orgs/<uuid:org_id>/projects/<uuid:project_id>"

urlpatterns = [
    path(f"{_PROJECT}/health/", views.HealthView.as_view(), name="health"),
    path(f"{_PROJECT}/alert-rules/", views.AlertRuleListCreateView.as_view(), name="alert-rules"),
    path(
        f"{_PROJECT}/alert-rules/<uuid:rule_id>/",
        views.AlertRuleDetailView.as_view(),
        name="alert-rule-detail",
    ),
]
