from __future__ import annotations

from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from bizpilot.orgs.constants import SYSTEM_ROLE_VIEWER
from bizpilot.orgs.models import Membership
from bizpilot.orgs.services import create_organization
from bizpilot.users.models import User


class PermissionsAPITest(APITestCase):
    def setUp(self) -> None:
        self.owner = User.objects.create_user(
            email="owner@permsapi.com",
            password="password123",  # noqa: S106
            name="Perms Owner",
        )
        self.viewer = User.objects.create_user(
            email="viewer@permsapi.com",
            password="password123",  # noqa: S106
            name="Perms Viewer",
        )
        self.outsider = User.objects.create_user(
            email="outsider@permsapi.com",
            password="password123",  # noqa: S106
            name="Perms Outsider",
        )
        self.org = create_organization(
            name="Security First Ltd",
            owner=self.owner,
        )
        self.viewer_role = self.org.roles.get(name=SYSTEM_ROLE_VIEWER)
        self.viewer_membership = Membership.objects.create(
            organization=self.org,
            user=self.viewer,
            email=self.viewer.email,
            name=self.viewer.name,
            status=Membership.Status.ACTIVE,
        )
        self.viewer_membership.roles.add(self.viewer_role)

    def test_list_catalog_permissions(self) -> None:
        self.client.force_authenticate(user=self.owner)
        url = reverse("v1-orgs:permission-list")
        response = self.client.get(url)

        assert response.status_code == status.HTTP_200_OK
        codenames = [p["codename"] for p in response.data]
        assert "invoices.view" in codenames
        assert "invoices.create" in codenames
        assert "organization.delete" in codenames

    def test_my_permissions_endpoint_for_owner(self) -> None:
        self.client.force_authenticate(user=self.owner)
        url = reverse("v1-orgs:my-permissions")
        response = self.client.get(url, {"org": str(self.org.id)})

        assert response.status_code == status.HTTP_200_OK
        assert response.data["is_member"]
        assert response.data["is_owner"]
        assert "*" in response.data["permissions"]

    def test_my_permissions_endpoint_for_viewer(self) -> None:
        self.client.force_authenticate(user=self.viewer)
        url = reverse("v1-orgs:my-permissions")
        response = self.client.get(url, {"org": str(self.org.id)})

        assert response.status_code == status.HTTP_200_OK
        assert response.data["is_member"]
        assert not response.data["is_owner"]
        assert "invoices.view" in response.data["permissions"]
        assert "invoices.create" not in response.data["permissions"]

    def test_permission_denied_returns_403_with_detail_when_unauthorized(self) -> None:
        # Viewer attempting to invite another member (requires team.invite)
        self.client.force_authenticate(user=self.viewer)
        url = reverse("v1-orgs:org-invites-list", kwargs={"org_id": self.org.id})
        payload = {"email": "someone@example.com"}
        response = self.client.post(url, data=payload, format="json")

        assert response.status_code == status.HTTP_403_FORBIDDEN
        assert response.data["code"] == "permission_denied"
        assert "team.invite" in response.data["detail"]
