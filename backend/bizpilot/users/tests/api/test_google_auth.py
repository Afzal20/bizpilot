from __future__ import annotations

from http import HTTPStatus
from unittest.mock import MagicMock
from unittest.mock import patch

import pytest
from allauth.socialaccount.models import SocialAccount
from django.test import override_settings
from django.urls import reverse
from rest_framework.test import APIClient

from bizpilot.users.models import Profile
from bizpilot.users.models import User


@pytest.mark.django_db
class TestGoogleAuthEndpoints:
    def setup_method(self):
        self.client = APIClient()
        self.url = reverse("v1-auth:google-auth")

    def test_get_google_config(self):
        with override_settings(
            GOOGLE_CLIENT_ID="mock-client-id.apps.googleusercontent.com",
        ):
            response = self.client.get(self.url)
            assert response.status_code == HTTPStatus.OK
            assert (
                response.data.get("client_id")
                == "mock-client-id.apps.googleusercontent.com"
            )

    def test_google_auth_missing_params(self):
        response = self.client.post(self.url, data={}, format="json")
        assert response.status_code == HTTPStatus.BAD_REQUEST
        assert "error" in response.data

    @patch("bizpilot.users.api.views.requests.get")
    @patch("bizpilot.users.api.views.requests.post")
    def test_google_auth_code_flow_new_user(self, mock_post, mock_get):
        # Mock token response
        token_response = MagicMock()
        token_response.status_code = 200
        token_response.json.return_value = {
            "access_token": "mock-access-token",
            "id_token": "mock-id-token",
        }
        mock_post.return_value = token_response

        # Mock userinfo response
        userinfo_response = MagicMock()
        userinfo_response.status_code = 200
        userinfo_response.json.return_value = {
            "sub": "google-user-12345",
            "email": "newuser@example.com",
            "name": "New User",
            "picture": "https://example.com/avatar.jpg",
            "email_verified": True,
        }
        mock_get.return_value = userinfo_response

        with override_settings(
            GOOGLE_CLIENT_ID="test-client-id",
            GOOGLE_CLIENT_SECRET="test-client-secret",  # noqa: S106
        ):
            response = self.client.post(
                self.url,
                data={
                    "code": "test-auth-code",
                    "redirect_uri": "http://localhost:3000/auth/callback",
                },
                format="json",
            )

        assert response.status_code == HTTPStatus.CREATED
        assert "tokens" in response.data
        assert "access" in response.data["tokens"]
        assert "refresh" in response.data["tokens"]
        assert response.data["user"]["email"] == "newuser@example.com"
        assert response.data["user"]["name"] == "New User"

        # Verify DB records
        user = User.objects.get(email="newuser@example.com")
        assert user.name == "New User"
        assert not user.has_usable_password()

        # Verify SocialAccount
        social = SocialAccount.objects.get(user=user, provider="google")
        assert social.uid == "google-user-12345"

        # Verify Profile
        profile = Profile.objects.get(user=user)
        assert profile.avatar_url == "https://example.com/avatar.jpg"
        assert profile.full_name == "New User"

        # Verify default organization was created
        assert user.memberships.filter(status="active").exists()

    @patch("bizpilot.users.api.views.requests.get")
    @patch("bizpilot.users.api.views.requests.post")
    def test_google_auth_code_flow_existing_user(self, mock_post, mock_get):
        existing_user = User.objects.create_user(
            email="existing@example.com",
            name="Existing User",
            password="StrongPassword123!",  # noqa: S106
        )

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
            "sub": "google-user-99999",
            "email": "existing@example.com",
            "name": "Existing User",
            "picture": "https://example.com/existing-avatar.jpg",
            "email_verified": True,
        }
        mock_get.return_value = userinfo_response

        with override_settings(
            GOOGLE_CLIENT_ID="test-client-id",
            GOOGLE_CLIENT_SECRET="test-client-secret",  # noqa: S106
        ):
            response = self.client.post(
                self.url,
                data={
                    "code": "test-auth-code",
                    "redirect_uri": "http://localhost:3000/auth/callback",
                },
                format="json",
            )

        assert response.status_code == HTTPStatus.OK
        assert response.data["user"]["email"] == "existing@example.com"
        assert SocialAccount.objects.filter(
            user=existing_user, provider="google",
        ).exists()

    @patch("bizpilot.users.api.views.requests.get")
    def test_google_auth_id_token_flow(self, mock_get):
        tokeninfo_response = MagicMock()
        tokeninfo_response.status_code = 200
        tokeninfo_response.json.return_value = {
            "aud": "test-client-id",
            "sub": "google-user-token-flow",
            "email": "idtokenuser@example.com",
            "name": "ID Token User",
            "picture": "",
            "email_verified": "true",
        }
        mock_get.return_value = tokeninfo_response

        with override_settings(GOOGLE_CLIENT_ID="test-client-id"):
            response = self.client.post(
                self.url,
                data={"id_token": "valid-id-token"},
                format="json",
            )

        assert response.status_code == HTTPStatus.CREATED
        assert response.data["user"]["email"] == "idtokenuser@example.com"
        assert User.objects.filter(email="idtokenuser@example.com").exists()

    @patch("bizpilot.users.api.views.requests.get")
    def test_google_auth_unverified_email(self, mock_get):
        tokeninfo_response = MagicMock()
        tokeninfo_response.status_code = 200
        tokeninfo_response.json.return_value = {
            "aud": "test-client-id",
            "sub": "unverified-user",
            "email": "unverified@example.com",
            "name": "Unverified User",
            "email_verified": False,
        }
        mock_get.return_value = tokeninfo_response

        with override_settings(GOOGLE_CLIENT_ID="test-client-id"):
            response = self.client.post(
                self.url,
                data={"id_token": "unverified-id-token"},
                format="json",
            )

        assert response.status_code == HTTPStatus.BAD_REQUEST
        assert "verified" in response.data.get("error", "").lower()

    @patch("bizpilot.users.api.views.requests.post")
    def test_google_auth_token_exchange_failure(self, mock_post):
        error_response = MagicMock()
        error_response.status_code = 400
        error_response.json.return_value = {
            "error": "invalid_grant",
            "error_description": "Bad Request code expired",
        }
        mock_post.return_value = error_response

        with override_settings(
            GOOGLE_CLIENT_ID="test-client-id",
            GOOGLE_CLIENT_SECRET="test-client-secret",  # noqa: S106
        ):
            response = self.client.post(
                self.url,
                data={
                    "code": "expired-code",
                    "redirect_uri": "http://localhost:3000/auth/callback",
                },
                format="json",
            )

        assert response.status_code == HTTPStatus.BAD_REQUEST
        assert "code expired" in response.data.get("error", "")

    @patch("bizpilot.users.api.views.requests.get")
    def test_google_auth_access_token_flow(self, mock_get):
        userinfo_response = MagicMock()
        userinfo_response.status_code = 200
        userinfo_response.json.return_value = {
            "sub": "google-user-access-token-flow",
            "email": "accesstokenuser@example.com",
            "name": "Access Token User",
            "picture": "",
            "email_verified": True,
        }
        mock_get.return_value = userinfo_response

        with override_settings(GOOGLE_CLIENT_ID="test-client-id"):
            response = self.client.post(
                self.url,
                data={"id_token": "valid-oauth-access-token"},
                format="json",
            )

        assert response.status_code == HTTPStatus.CREATED
        assert response.data["user"]["email"] == "accesstokenuser@example.com"
        assert User.objects.filter(email="accesstokenuser@example.com").exists()

