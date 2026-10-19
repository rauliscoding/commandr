from django.urls import path

from . import views

_PROJECT = "orgs/<uuid:org_id>/projects/<uuid:project_id>"

urlpatterns = [
    path(f"{_PROJECT}/catalogue/", views.CatalogueView.as_view(), name="catalogue"),
    path(f"{_PROJECT}/connections/", views.ConnectionListCreateView.as_view(), name="connections"),
    path(
        f"{_PROJECT}/connections/<uuid:connection_id>/",
        views.ConnectionDetailView.as_view(),
        name="connection-detail",
    ),
    path(
        f"{_PROJECT}/connections/<uuid:connection_id>/first-data/",
        views.FirstDataView.as_view(),
        name="connection-first-data",
    ),
    path(
        f"{_PROJECT}/connections/<uuid:connection_id>/check-now/",
        views.CheckNowView.as_view(),
        name="connection-check-now",
    ),
]
