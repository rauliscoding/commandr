# SPDX-License-Identifier: AGPL-3.0-only
"""Mount with `path("", include("commandr_django.urls"))`."""

from django.urls import path

from .conf import STATUS_PATH
from .views import status_view

app_name = "commandr"
urlpatterns = [path(STATUS_PATH, status_view, name="status")]
