from __future__ import annotations

from http import HTTPStatus

import pytest
from django.urls import reverse
from rest_framework.test import APIClient

from bizpilot.users.models import User


@pytest.mark.django_db
class TestProfileEndpoints:
    def setup_method(self):
        self.client = APIClient()

    def test_me_unauthenticated(self):
        url = reverse("v1-me:me")
        response = self.client.get(url)
        assert response.status_code == HTTPStatus.UNAUTHORIZED

    def test_me_authenticated(self):
        user = User.objects.create_user(
            email="me_test@example.com",
            password="StrongPassword123!",  # noqa: S106
            name="Me Tester",
        )
        self.client.force_authenticate(user=user)
        url = reverse("v1-me:me")
        response = self.client.get(url)

        assert response.status_code == HTTPStatus.OK
        assert response.data["email"] == "me_test@example.com"
        assert response.data["name"] == "Me Tester"
        assert "profile" in response.data
        assert "memberships" in response.data

    def test_profile_retrieve_and_patch(self):
        user = User.objects.create_user(
            email="profile_tester@example.com",
            password="StrongPassword123!",  # noqa: S106
            name="Profile Tester",
        )
        self.client.force_authenticate(user=user)
        profile_url = reverse("v1-me:me-profile")

        # Get default profile
        get_res = self.client.get(profile_url)
        assert get_res.status_code == HTTPStatus.OK
        assert get_res.data["default_currency"] == "USD"

        # Update profile
        patch_payload = {
            "company_name": "Apex Innovations",
            "company_phone": "+1-555-0199",
            "default_currency": "EUR",
            "default_tax_rate": "15.50",
            "default_terms": "Payment due within 30 days of issuance.",
        }
        patch_res = self.client.patch(profile_url, data=patch_payload, format="json")
        assert patch_res.status_code == HTTPStatus.OK
        assert patch_res.data["company_name"] == "Apex Innovations"
        assert patch_res.data["default_currency"] == "EUR"
        assert str(patch_res.data["default_tax_rate"]) == "15.50"

        # Verify persisted in database
        user.profile.refresh_from_db()
        assert user.profile.company_name == "Apex Innovations"
        assert user.profile.default_currency == "EUR"

    def test_claim_invites_endpoint(self):
        user = User.objects.create_user(
            email="invitee@example.com",
            password="StrongPassword123!",  # noqa: S106
        )
        self.client.force_authenticate(user=user)
        url = reverse("v1-auth:invites-claim")
        response = self.client.post(url, data={}, format="json")

        assert response.status_code == HTTPStatus.OK
        assert "claimed_count" in response.data
        assert response.data["email"] == "invitee@example.com"
