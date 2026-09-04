from __future__ import annotations

from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from bizpilot.orgs.constants import SYSTEM_ROLE_OWNER
from bizpilot.orgs.constants import SYSTEM_ROLE_VIEWER
from bizpilot.orgs.services import create_organization
from bizpilot.users.models import User


class RoleAPITest(APITestCase):
    def setUp(self) -> None:
        self.owner = User.objects.create_user(
            email="owner@roleapi.com",
            password="password123",  # noqa: S106
            name="Role Owner",
        )
        self.org = create_organization(
            name="Role Corp",
            owner=self.owner,
        )

    def test_list_roles_includes_system_roles(self) -> None:
        self.client.force_authenticate(user=self.owner)
        url = reverse("v1-orgs:org-roles-list", kwargs={"org_id": self.org.id})
        response = self.client.get(url)

        assert response.status_code == status.HTTP_200_OK
        role_names = [r["name"] for r in response.data["results"]]
        assert SYSTEM_ROLE_OWNER in role_names
        assert SYSTEM_ROLE_VIEWER in role_names

    def test_create_custom_role(self) -> None:
        self.client.force_authenticate(user=self.owner)
        url = reverse("v1-orgs:org-roles-list", kwargs={"org_id": self.org.id})
        payload = {
            "name": "Billing Specialist",
            "description": "Handles invoices and billing exclusively",
            "permission_codenames": [
                "invoices.view",
                "invoices.create",
                "billing.view",
            ],
        }
        response = self.client.post(url, data=payload, format="json")

        assert response.status_code == status.HTTP_201_CREATED
        assert response.data["name"] == "Billing Specialist"
        assert not response.data["is_system"]
        assert "invoices.create" in response.data["permission_codenames"]

    def test_cannot_delete_system_role(self) -> None:
        self.client.force_authenticate(user=self.owner)
        viewer_role = self.org.roles.get(name=SYSTEM_ROLE_VIEWER)
        url = reverse(
            "v1-orgs:org-roles-detail",
            kwargs={"org_id": self.org.id, "pk": viewer_role.id},
        )
        response = self.client.delete(url)
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_cannot_rename_system_role(self) -> None:
        self.client.force_authenticate(user=self.owner)
        viewer_role = self.org.roles.get(name=SYSTEM_ROLE_VIEWER)
        url = reverse(
            "v1-orgs:org-roles-detail",
            kwargs={"org_id": self.org.id, "pk": viewer_role.id},
        )
        response = self.client.patch(url, data={"name": "Renamed Viewer"})
        assert response.status_code == status.HTTP_400_BAD_REQUEST
