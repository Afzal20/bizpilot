from __future__ import annotations

from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from bizpilot.orgs.constants import SYSTEM_ROLE_VIEWER
from bizpilot.orgs.models import Membership
from bizpilot.orgs.services import create_organization
from bizpilot.users.models import User


class InvitesAPITest(APITestCase):
    def setUp(self) -> None:
        self.owner = User.objects.create_user(
            email="owner@inviteapi.com",
            password="password123",  # noqa: S106
            name="Invite Owner",
        )
        self.invitee_user = User.objects.create_user(
            email="invitee@inviteapi.com",
            password="password123",  # noqa: S106
            name="Invitee User",
        )
        self.org = create_organization(
            name="Invite Enterprise",
            owner=self.owner,
        )
        self.viewer_role = self.org.roles.get(name=SYSTEM_ROLE_VIEWER)

    def test_create_and_list_invites(self) -> None:
        self.client.force_authenticate(user=self.owner)
        url = reverse("v1-orgs:org-invites-list", kwargs={"org_id": self.org.id})
        payload = {
            "email": "candidate@inviteapi.com",
            "department": "Operations",
            "role_ids": [str(self.viewer_role.id)],
        }
        response = self.client.post(url, data=payload, format="json")
        assert response.status_code == status.HTTP_201_CREATED
        assert response.data["email"] == "candidate@inviteapi.com"
        assert response.data["token"] is not None

        # List invites
        list_response = self.client.get(url)
        assert list_response.status_code == status.HTTP_200_OK
        emails = [inv["email"] for inv in list_response.data["results"]]
        assert "candidate@inviteapi.com" in emails

    def test_accept_invite_via_api(self) -> None:
        self.client.force_authenticate(user=self.owner)
        create_url = reverse("v1-orgs:org-invites-list", kwargs={"org_id": self.org.id})
        payload = {
            "email": "invitee@inviteapi.com",
            "department": "Support",
            "role_ids": [str(self.viewer_role.id)],
        }
        create_res = self.client.post(create_url, data=payload, format="json")
        token = create_res.data["token"]

        # Authenticate as the invitee user
        self.client.force_authenticate(user=self.invitee_user)
        accept_url = reverse("v1-orgs:invite-accept")
        accept_res = self.client.post(accept_url, data={"token": token}, format="json")

        assert accept_res.status_code == status.HTTP_200_OK
        assert "membership" in accept_res.data

        # Verify active membership
        membership = Membership.objects.filter(
            organization=self.org,
            user=self.invitee_user,
            status=Membership.Status.ACTIVE,
        ).first()
        assert membership is not None

    def test_accept_invalid_invite_token_returns_400(self) -> None:
        self.client.force_authenticate(user=self.invitee_user)
        accept_url = reverse("v1-orgs:invite-accept")
        response = self.client.post(
            accept_url,
            data={"token": "completely-bogus-token-12345"},
            format="json",
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST
