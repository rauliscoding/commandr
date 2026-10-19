from django.http import HttpRequest, HttpResponse, JsonResponse
from django.urls import include, path, re_path


def item(request: HttpRequest, pk: int) -> JsonResponse:
    return JsonResponse({"id": pk})


def legacy(request: HttpRequest, slug: str) -> HttpResponse:
    return HttpResponse(slug)


def boom(request: HttpRequest) -> HttpResponse:
    raise KeyError("unit")


async def slow_async(request: HttpRequest) -> HttpResponse:
    return HttpResponse("ok")


urlpatterns = [
    path("api/items/<int:pk>/", item),
    re_path(r"^legacy/(?P<slug>[a-z]+)/$", legacy),
    path("boom/", boom),
    path("async/", slow_async),
    path("", include("commandr_django.urls")),
]
