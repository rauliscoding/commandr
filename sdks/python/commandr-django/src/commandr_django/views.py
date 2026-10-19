# SPDX-License-Identifier: AGPL-3.0-only
"""The signed status endpoint, `/.well-known/commandr/status`."""

from __future__ import annotations

import json
import time

from django.http import HttpRequest, HttpResponse
from django.utils.cache import patch_vary_headers
from django.utils.encoding import escape_uri_path
from django.views.decorators.csrf import csrf_exempt

from . import _log, signing, status
from .conf import get_config

SIGNATURE_HEADER = "X-Commandr-Signature"
PROJECT_HEADER = "X-Commandr-Project"


def _refused() -> HttpResponse:
    # No detail: whoever is guessing learns nothing about why.
    response = HttpResponse(status=401)
    response["Cache-Control"] = "no-store"
    return response


def _signed(request: HttpRequest, secret: str) -> bool:
    header = request.headers.get(SIGNATURE_HEADER, "")
    now = int(time.time())
    # Commandr signs the path as it sent it (percent-encoded); Django hands us
    # the decoded form. They differ only when the path has unusual characters.
    paths = {request.path, escape_uri_path(request.path)}
    return any(signing.verify(secret, header, request.method or "", p, now) for p in paths)


@csrf_exempt
def status_view(request: HttpRequest) -> HttpResponse:
    config = get_config()
    if request.method not in ("GET", "HEAD"):
        response = HttpResponse(status=405)
        response["Allow"] = "GET, HEAD"
        return response
    if not config.enabled or not config.signing_secret:
        _log.warn(
            "no-secret",
            "commandr: status endpoint polled but COMMANDR['SIGNING_SECRET'] is not set; "
            "answering 401.",
        )
        return _refused()
    if not _signed(request, config.signing_secret):
        return _refused()
    project = request.headers.get(PROJECT_HEADER, "")
    if config.project and project != config.project:
        return _refused()

    document = status.build(config)
    tag = status.etag(document)
    if request.headers.get("If-None-Match") == tag:
        response = HttpResponse(status=304)
    else:
        response = HttpResponse(
            json.dumps(document, separators=(",", ":")), content_type="application/json"
        )
    response["ETag"] = tag
    response["Cache-Control"] = "no-store"
    patch_vary_headers(response, (SIGNATURE_HEADER, PROJECT_HEADER))
    return response
