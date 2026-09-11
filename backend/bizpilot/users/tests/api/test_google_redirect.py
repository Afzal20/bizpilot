from __future__ import annotations

from http import HTTPStatus
from unittest.mock import MagicMock
from unittest.mock import patch
import urllib.parse

import pytest
from allauth.socialaccount.models import SocialAccount
from django.test import override_settings
from django.urls import reverse
from rest_framework.test import APIClient

from bizpilot.users.models import User


@pytest.mark.django_db
class TestGoogleRedirectAndCallback:
    def setup_method(self):
        self.client = APIClient()
        self.redirect_url = reverse("v1-auth:google-redirect")
        self.callback_url = reverse("v1-auth:google-callback")

    def test_redirect_to_google_default(self):
        with override_settings(
            GOOGLE_CLIENT_ID="test-google-client-id",
            FRONTEND_URL="http://localhost:3000",
        ):
            response = self.client.get(self.redirect_url)
            assert response.status_code == HTTPStatus.FOUND
            location = response.headers["Location"]
            assert location.startswith("https://accounts.google.com/o/oauth2/v2/auth?")
            parsed = urllib.parse.urlparse(location)
            qs = urllib.parse.parse_qs(parsed.query)
            assert qs["client_id"] == ["test-google-client-id"]
            assert qs["redirect_uri"] == ["http://localhost:3000/auth/callback"]
            assert qs["response_type"] == ["code"]

    def test_redirect_json_format(self):
        with override_settings(
            GOOGLE_CLIENT_ID="test-google-client-id",
            FRONTEND_URL="http://localhost:3000",
        ):
            response = self.client.get(f"{self.redirect_url}?format=json")
            assert response.status_code == HTTPStatus.OK
            assert "authorization_url" in response.data
            assert "accounts.google.com" in response.data["authorization_url"]
            assert response.data["client_id"] == "test-google-client-id"

    def test_redirect_missing_client_id(self):
        with override_settings(GOOGLE_CLIENT_ID=""):
            response = self.client.get(f"{self.redirect_url}?format=json")
            assert response.status_code == HTTPStatus.INTERNAL_SERVER_ERROR
            assert "error" in response.data

    def test_callback_error_redirects_to_login(self):
        with override_settings(FRONTEND_URL="http://localhost:3000"):
            response = self.client.get(
                f"{self.callback_url}?error=access_denied&error_description=User+cancelled",
            )
            assert response.status_code == HTTPStatus.FOUND
            assert response.headers["Location"].startswith(
                "http://localhost:3000/auth/login?error=",
            )
            assert "cancelled" in response.headers["Location"]

    def test_callback_missing_code_redirects_to_login(self):
        with override_settings(FRONTEND_URL="http://localhost:3000"):
            response = self.client.get(self.callback_url)
            assert response.status_code == HTTPStatus.FOUND
            assert "error=Missing+authorization+code" in response.headers["Location"]

    @patch("bizpilot.users.api.views.requests.get")
    @patch("bizpilot.users.api.views.requests.post")
    def test_callback_successful_exchange_redirects_with_tokens(
        self, mock_post, mock_get,
    ):
        token_response = MagicMock()
        token_response.status_code = 200
        token_response.json.return_value = {
            "access_token": "mock-access-token",
            "id_token": "mock-id-token",
        }
        mock_post.return_value = token_response

        userinfo_response = MagicMock()
        userinfo_response.status_code = 200
        userinfo_response.json.return_value = {
            "sub": "google-user-redirect-flow",
            "email": "redirectuser@example.com",
            "name": "Redirect Flow User",
            "picture": "https://example.com/redirect-avatar.jpg",
            "email_verified": True,
        }
        mock_get.return_value = userinfo_response

        with override_settings(
            GOOGLE_CLIENT_ID="test-google-client-id",
            GOOGLE_CLIENT_SECRET="test-google-secret",  # noqa: S106
            FRONTEND_URL="http://localhost:3000",
        ):
            response = self.client.get(f"{self.callback_url}?code=valid-code&state=/dashboard")

            assert response.status_code == HTTPStatus.FOUND
            location = response.headers["Location"]
            assert location.startswith("http://localhost:3000/auth/callback?")
            parsed = urllib.parse.urlparse(location)
            qs = urllib.parse.parse_qs(parsed.query)
            assert "access" in qs
            assert "refresh" in qs
            assert qs.get("next") == ["/dashboard"]

            user = User.objects.get(email="redirectuser@example.com")
            assert user.name == "Redirect Flow User"
            assert SocialAccount.objects.filter(user=user, provider="google").exists()
