"""Sign-up and sign-in through allauth headless (session cookies, ADR 0003)."""

import json

import pytest
from django.test import Client
from django.urls import reverse

from tests.factories import TEST_PASSWORD

pytestmark = pytest.mark.django_db

AUTH = "/api/auth/browser/v1/auth"


def post_json(client: Client, url: str, body: dict[str, str]):  # type: ignore[no-untyped-def]
    return client.post(url, data=json.dumps(body), content_type="application/json")


def test_signup_signs_in_with_a_session() -> None:
    client = Client()
    response = post_json(
        client, f"{AUTH}/signup", {"email": "New@Example.test", "password": TEST_PASSWORD}
    )
    assert response.status_code == 200, response.content
    me = client.get(reverse("me"))
    assert me.status_code == 200
    assert me.json()["user"]["email"] == "new@example.test"


def test_short_passwords_are_refused() -> None:
    response = post_json(
        Client(), f"{AUTH}/signup", {"email": "a@example.test", "password": "short1"}
    )
    assert response.status_code == 400


def test_login_and_wrong_password(user) -> None:  # type: ignore[no-untyped-def]
    client = Client()
    bad = post_json(client, f"{AUTH}/login", {"email": user.email, "password": "wrong password!!"})
    assert bad.status_code == 400
    good = post_json(client, f"{AUTH}/login", {"email": user.email, "password": TEST_PASSWORD})
    assert good.status_code == 200
    assert client.get(reverse("me")).status_code == 200


def test_csrf_is_enforced_for_session_requests(user) -> None:  # type: ignore[no-untyped-def]
    client = Client(enforce_csrf_checks=True)
    client.force_login(user)
    response = client.post(
        reverse("organization-create"),
        data=json.dumps({"name": "x", "project_name": "y"}),
        content_type="application/json",
    )
    assert response.status_code == 403
