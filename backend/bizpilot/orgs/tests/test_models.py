from __future__ import annotations

from datetime import timedelta
import uuid

from django.test import TestCase
from django.utils import timezone

from bizpilot.orgs.models import Invite
from bizpilot.orgs.models import Membership
from bizpilot.orgs.models import Organization
from bizpilot.orgs.models import Permission
from bizpilot.orgs.models import Role
from bizpilot.users.models import User


class OrganizationModelTest(TestCase):
    def setUp(self) -> None:
        self.user = User.objects.create_user(
            email="orgowner@example.com",
            password="testpassword123",
            name="Org Owner",
        )

    def test_organization_creation_and_slug(self) -> None:
        org = Organization.objects.create(
            name="Acme Corp",
            owner=self.user,
        )
        self.assertEqual(org.slug, "acme-corp")
        self.assertEqual(str(org), "Acme Corp")
        self.assertIsInstance(org.id, uuid.UUID)

    def test_duplicate_name_generates_unique_slug(self) -> None:
        org1 = Organization.objects.create(name="Beta Company", owner=self.user)
        org2 = Organization.objects.create(name="Beta Company", owner=self.user)
        self.assertEqual(org1.slug, "beta-company")
        self.assertEqual(org2.slug, "beta-company-1")


class RoleAndPermissionModelTest(TestCase):
    def test_permission_str(self) -> None:
        perm = Permission.objects.create(
            codename="invoices.test",
            resource="invoices",
            action="test",
            description="Test invoice permission",
        )
        self.assertEqual(str(perm), "invoices.test")

    def test_role_str(self) -> None:
        role = Role.objects.create(name="Custom Manager")
        self.assertIn("Custom Manager", str(role))


class MembershipAndInviteModelTest(TestCase):
    def setUp(self) -> None:
        self.user = User.objects.create_user(
            email="member@example.com",
            password="testpassword123",
            name="Member User",
        )
        self.org = Organization.objects.create(name="Gamma Labs", owner=self.user)

    def test_membership_str_and_owner_detection(self) -> None:
        membership = Membership.objects.create(
            organization=self.org,
            user=self.user,
            email=self.user.email,
            status=Membership.Status.ACTIVE,
        )
        self.assertTrue(membership.is_owner)
        self.assertIn(self.user.email, str(membership))

    def test_invite_validity_and_expiry(self) -> None:
        now = timezone.now()
        invite = Invite.objects.create(
            organization=self.org,
            email="invited@example.com",
            invited_by=self.user,
            token=Invite.generate_token(),
            expires_at=now + timedelta(days=7),
        )
        self.assertTrue(invite.is_valid)
        self.assertFalse(invite.is_expired)

        expired_invite = Invite.objects.create(
            organization=self.org,
            email="expired@example.com",
            invited_by=self.user,
            token=Invite.generate_token(),
            expires_at=now - timedelta(days=1),
        )
        self.assertTrue(expired_invite.is_expired)
        self.assertFalse(expired_invite.is_valid)
