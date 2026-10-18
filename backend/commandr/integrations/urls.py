from django.urls import path

from . import views

urlpatterns = [
    path(
        "orgs/<uuid:org_id>/projects/<uuid:project_id>/catalogue/",
        views.CatalogueView.as_view(),
        name="catalogue",
    ),
]
