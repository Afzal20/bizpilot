from __future__ import annotations

from http import HTTPStatus

import pytest
from django.urls import reverse
from rest_framework.test import APIClient

from bizpilot.users.models import User


@pytest.mark.django_db
class TestAuthEndpoints:
    def setup_method(self):
        self.client = APIClient()

    def test_signup_success(self):
        url = reverse("v1-auth:signup")
        payload = {
            "email": "jane@example.com",
            "password": "StrongPassword123!",
            "name": "Jane Doe",
            "company_name": "Acme Global",
        }
        response = self.client.post(url, data=payload, format="json")

        assert response.status_code == HTTPStatus.CREATED
        assert "tokens" in response.data
        assert "access" in response.data["tokens"]
        assert "refresh" in response.data["tokens"]
        assert response.data["user"]["email"] == "jane@example.com"
        assert response.data["user"]["profile"]["company_name"] == "Acme Global"

        user = User.objects.get(email="jane@example.com")
        assert user.check_password("StrongPassword123!")
        assert user.profile.company_name == "Acme Global"

    def test_signup_duplicate_email(self):
        User.objects.create_user(
            email="existing@example.com",
            password="StrongPassword123!",  # noqa: S106
        )
        url = reverse("v1-auth:signup")
        payload = {
            "email": "existing@example.com",
            "password": "StrongPassword123!",
        }
        response = self.client.post(url, data=payload, format="json")
        assert response.status_code == HTTPStatus.BAD_REQUEST

    def test_login_success(self):
        user = User.objects.create_user(
            email="login_user@example.com",
            password="StrongPassword123!",  # noqa: S106
            name="Login User",
        )
        url = reverse("v1-auth:login")
        payload = {
            "email": user.email,
            "password": "StrongPassword123!",
        }
        response = self.client.post(url, data=payload, format="json")

        assert response.status_code == HTTPStatus.OK
        assert "tokens" in response.data
        assert response.data["user"]["email"] == user.email

    def test_login_invalid_password(self):
        user = User.objects.create_user(
            email="wrong_pass@example.com",
            password="StrongPassword123!",  # noqa: S106
        )
        url = reverse("v1-auth:login")
        payload = {
            "email": user.email,
            "password": "IncorrectPassword999!",
        }
        response = self.client.post(url, data=payload, format="json")
        assert response.status_code == HTTPStatus.BAD_REQUEST

    def test_token_refresh(self):
        user = User.objects.create_user(
            email="refresh_user@example.com",
            password="StrongPassword123!",  # noqa: S106
        )
        login_url = reverse("v1-auth:login")
        login_res = self.client.post(
            login_url,
            {"email": user.email, "password": "StrongPassword123!"},
            format="json",
        )
        refresh_token = login_res.data["tokens"]["refresh"]

        refresh_url = reverse("v1-auth:token-refresh")
        refresh_res = self.client.post(
            refresh_url,
            {"refresh": refresh_token},
            format="json",
        )
        assert refresh_res.status_code == HTTPStatus.OK
        assert "access" in refresh_res.data

    def test_token_verify(self):
        user = User.objects.create_user(
            email="verify_user@example.com",
            password="StrongPassword123!",  # noqa: S106
        )
        login_url = reverse("v1-auth:login")
        login_res = self.client.post(
            login_url,
            {"email": user.email, "password": "StrongPassword123!"},
            format="json",
        )
        access_token = login_res.data["tokens"]["access"]

        verify_url = reverse("v1-auth:token-verify")
        verify_res = self.client.post(
            verify_url,
            {"token": access_token},
            format="json",
        )
        assert verify_res.status_code == HTTPStatus.OK

    def test_logout(self):
        user = User.objects.create_user(
            email="logout_user@example.com",
            password="StrongPassword123!",  # noqa: S106
        )
        self.client.force_authenticate(user=user)
        logout_url = reverse("v1-auth:logout")
        response = self.client.post(logout_url, data={}, format="json")
        assert response.status_code == HTTPStatus.OK

    def test_password_reset_flow(self):
        user = User.objects.create_user(
            email="reset_user@example.com",
            password="InitialPassword123!",  # noqa: S106
        )
        req_url = reverse("v1-auth:password-reset")
        req_res = self.client.post(
            req_url,
            {"email": user.email},
            format="json",
        )
        assert req_res.status_code == HTTPStatus.OK
        uid = req_res.data["uid"]
        token = req_res.data["token"]

        confirm_url = reverse("v1-auth:password-reset-confirm")
        confirm_res = self.client.post(
            confirm_url,
            {
                "uid": uid,
                "token": token,
                "new_password": "NewSecretPassword456!",
            },
            format="json",
        )
        assert confirm_res.status_code == HTTPStatus.OK

        # Verify login works with the new password
        login_url = reverse("v1-auth:login")
        login_res = self.client.post(
            login_url,
            {
                "email": user.email,
                "password": "NewSecretPassword456!",
            },
            format="json",
        )
        assert login_res.status_code == HTTPStatus.OK
