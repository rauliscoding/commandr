from django.urls import path

from . import views

urlpatterns = [
    path("me/", views.MeView.as_view(), name="me"),
    path("organizations/", views.OrganizationCreateView.as_view(), name="organization-create"),
    path("orgs/<uuid:org_id>/projects/", views.ProjectListCreateView.as_view(), name="projects"),
    path(
        "orgs/<uuid:org_id>/projects/<uuid:project_id>/",
        views.ProjectDetailView.as_view(),
        name="project-detail",
    ),
]
