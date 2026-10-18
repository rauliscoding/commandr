from django.db import connection
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_GET


@require_GET
@ensure_csrf_cookie
def csrf(request: HttpRequest) -> HttpResponse:
    """Sets the CSRF cookie so the SPA can send X-CSRFToken on its first POST."""
    return HttpResponse(status=204)


@require_GET
def healthz(request: HttpRequest) -> JsonResponse:
    """Shallow liveness: this process answers and can reach the database.

    Deliberately says nothing else — it is public, and polled by the external
    uptime monitor.
    """
    with connection.cursor() as cursor:
        cursor.execute("SELECT 1")
    return JsonResponse({"status": "ok"})
