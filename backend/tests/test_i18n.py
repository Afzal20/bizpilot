"""i18n: English + Bangla language behavior tests."""

from http import HTTPStatus

import pytest
from django.urls import reverse

# ATOMIC_REQUESTS=True means every request opens a DB transaction.
pytestmark = pytest.mark.django_db


def test_default_language_is_english(client):
    response = client.get("/")
    assert response.status_code == HTTPStatus.OK
    body = response.content.decode("utf-8")
    assert 'lang="en"' in body
    assert "Home" in body
    assert "হোম" not in body


def test_set_language_renders_bangla(client):
    response = client.post(reverse("set_language"), {"language": "bn", "next": "/"})
    assert response.status_code == HTTPStatus.FOUND
    response = client.get("/about/")
    assert response.status_code == HTTPStatus.OK
    body = response.content.decode("utf-8")
    assert 'lang="bn"' in body
    assert "সম্পর্কে" in body  # About
    assert "হোম" in body  # Home
    assert "সাইন ইন" in body  # Sign In


def test_accept_language_header_honoured(client):
    response = client.get("/", HTTP_ACCEPT_LANGUAGE="bn")
    assert response.status_code == HTTPStatus.OK
    assert "হোম" in response.content.decode("utf-8")


def test_unfold_admin_renders_with_bangla_cookie(client):
    client.cookies["django_language"] = "bn"
    response = client.get(reverse("admin:index"), follow=True)
    assert response.status_code == HTTPStatus.OK
    body = response.content.decode("utf-8")
    assert "BizPilot অ্যাডমিন" in body  # UNFOLD SITE_TITLE in Bangla
