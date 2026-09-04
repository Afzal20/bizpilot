from __future__ import annotations

from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from bizpilot.orgs.constants import SYSTEM_ROLE_ADMIN
from bizpilot.orgs.constants import SYSTEM_ROLE_VIEWER
from bizpilot.orgs.models import Membership
from bizpilot.orgs.services import create_organization
from bizpilot.users.models import User


class MembersAPITest(APITestCase):
    def setUp(self) -> None:
        self.owner = User.objects.create_user(
            email="owner@memberapi.com",
            password="password123",  # noqa: S106
            name="Member Owner",
        )
        self.staff = User.objects.create_user(
            email="staff@memberapi.com",
            password="password123",  # noqa: S106
            name="Member Staff",
        )
        self.org = create_organization(
            name="Team Dynamics",
            owner=self.owner,
        )
        self.viewer_role = self.org.roles.get(name=SYSTEM_ROLE_VIEWER)
        self.admin_role = self.org.roles.get(name=SYSTEM_ROLE_ADMIN)

        self.staff_membership = Membership.objects.create(
            organization=self.org,
            user=self.staff,
            email=self.staff.email,
            name=self.staff.name,
            status=Membership.Status.ACTIVE,
        )
        self.staff_membership.roles.add(self.viewer_role)

    def test_list_members(self) -> None:
        self.client.force_authenticate(user=self.owner)
        url = reverse("v1-orgs:org-members-list", kwargs={"org_id": self.org.id})
        response = self.client.get(url)

        assert response.status_code == status.HTTP_200_OK
        emails = [m["email"] for m in response.data["results"]]
        assert self.owner.email in emails
        assert self.staff.email in emails

    def test_update_member_roles(self) -> None:
        self.client.force_authenticate(user=self.owner)
        url = reverse(
            "v1-orgs:org-members-update-roles",
            kwargs={"org_id": self.org.id, "pk": self.staff_membership.id},
        )
        payload = {"role_ids": [str(self.admin_role.id)]}
        response = self.client.patch(url, data=payload, format="json")

        assert response.status_code == status.HTTP_200_OK
        self.staff_membership.refresh_from_db()
        assert self.staff_membership.roles.filter(name=SYSTEM_ROLE_ADMIN).exists()

    def test_remove_member(self) -> None:
        self.client.force_authenticate(user=self.owner)
        url = reverse(
            "v1-orgs:org-members-detail",
            kwargs={"org_id": self.org.id, "pk": self.staff_membership.id},
        )
        response = self.client.delete(url)
        assert response.status_code == status.HTTP_204_NO_CONTENT
        assert not Membership.objects.filter(id=self.staff_membership.id).exists()

    def test_cannot_remove_last_active_owner(self) -> None:
        self.client.force_authenticate(user=self.owner)
        owner_membership = Membership.objects.get(
            organization=self.org,
            user=self.owner,
        )
        url = reverse(
            "v1-orgs:org-members-detail",
            kwargs={"org_id": self.org.id, "pk": owner_membership.id},
        )
        response = self.client.delete(url)
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "last active owner" in str(response.data)
