"""Default deny, enforced: every DRF view must declare its own permission classes,
and no serializer may expose a secret field."""

import re
from collections.abc import Iterator

from django.urls import URLPattern, URLResolver, get_resolver
from rest_framework import serializers
from rest_framework.settings import api_settings
from rest_framework.views import APIView

SECRET_FIELD = re.compile(r"(_encrypted|_secret|^secret|token|key_hash|password)$")


def _walk(patterns: list[object]) -> Iterator[URLPattern]:
    for p in patterns:
        if isinstance(p, URLResolver):
            yield from _walk(p.url_patterns)
        elif isinstance(p, URLPattern):
            yield p


def _drf_views() -> list[type[APIView]]:
    views = []
    for pattern in _walk(get_resolver().url_patterns):
        cls = getattr(pattern.callback, "cls", None)
        if isinstance(cls, type) and issubclass(cls, APIView):
            module = cls.__module__
            if module.startswith("commandr."):
                views.append(cls)
    return views


def test_every_commandr_view_declares_permissions() -> None:
    views = _drf_views()
    assert views, "no DRF views found"
    default = api_settings.DEFAULT_PERMISSION_CLASSES
    offenders = [v.__qualname__ for v in views if list(v.permission_classes) == list(default)]
    assert offenders == [], f"Views relying on the deny-all default: {offenders}"


def _all_serializers() -> Iterator[type[serializers.BaseSerializer]]:  # type: ignore[type-arg]
    seen: set[type] = set()
    stack = list(serializers.BaseSerializer.__subclasses__())
    while stack:
        cls = stack.pop()
        if cls in seen:
            continue
        seen.add(cls)
        stack.extend(cls.__subclasses__())
        if cls.__module__.startswith("commandr."):
            yield cls


def test_no_serializer_exposes_secret_fields() -> None:
    get_resolver().url_patterns  # noqa: B018 — import every view, and so every serializer
    offenders = []
    for cls in _all_serializers():
        if not issubclass(cls, serializers.Serializer):
            continue
        for name, field in cls().fields.items():
            if SECRET_FIELD.search(name) and not field.write_only:
                offenders.append(f"{cls.__qualname__}.{name}")
    assert offenders == []
