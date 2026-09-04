from __future__ import annotations

from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from bizpilot.orgs.models import Membership
from bizpilot.orgs.models import Organization
from bizpilot.orgs.services import create_organization
from bizpilot.users.models import User


class OrganizationAPITest(APITestCase):
    def setUp(self) -> None:
        self.owner = User.objects.create_user(
            email="owner@orgapi.com",
            password="password123",  # noqa: S106
            name="Org Owner",
        )
        self.other_user = User.objects.create_user(
            email="other@orgapi.com",
            password="password123",  # noqa: S106
            name="Other User",
        )
        self.org = create_organization(
            name="Primary Org",
            owner=self.owner,
        )
        self.other_org = create_organization(
            name="Unrelated Org",
            owner=self.other_user,
        )

    def test_list_organizations_scoped_to_user_memberships(self) -> None:
        self.client.force_authenticate(user=self.owner)
        url = reverse("v1-orgs:org-list")
        response = self.client.get(url)

        assert response.status_code == status.HTTP_200_OK
        org_ids = [o["id"] for o in response.data["results"]]
        assert str(self.org.id) in org_ids
        assert str(self.other_org.id) not in org_ids

    def test_create_organization_via_api(self) -> None:
        self.client.force_authenticate(user=self.owner)
        url = reverse("v1-orgs:org-list")
        payload = {
            "name": "New Venture LLC",
            "default_currency": "EUR",
            "company_email": "hello@newventure.com",
        }
        response = self.client.post(url, data=payload)
        assert response.status_code == status.HTTP_201_CREATED
        assert response.data["name"] == "New Venture LLC"

        # Verify owner membership was established
        new_org = Organization.objects.get(id=response.data["id"])
        membership = Membership.objects.filter(
            organization=new_org,
            user=self.owner,
            status=Membership.Status.ACTIVE,
        ).first()
        assert membership is not None
        assert membership is not None
        assert membership.is_owner

    def test_update_organization_settings(self) -> None:
        self.client.force_authenticate(user=self.owner)
        url = reverse("v1-orgs:org-detail", kwargs={"pk": self.org.id})
        payload = {"company_phone": "+1 555-0199"}
        response = self.client.patch(url, data=payload)

        assert response.status_code == status.HTTP_200_OK
        self.org.refresh_from_db()
        assert self.org.company_phone == "+1 555-0199"

    def test_delete_organization_deactivates(self) -> None:
        self.client.force_authenticate(user=self.owner)
        url = reverse("v1-orgs:org-detail", kwargs={"pk": self.org.id})
        response = self.client.delete(url)

        assert response.status_code == status.HTTP_204_NO_CONTENT
        self.org.refresh_from_db()
        assert not self.org.is_active
