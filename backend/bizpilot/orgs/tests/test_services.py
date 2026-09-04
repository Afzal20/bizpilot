from __future__ import annotations

from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.test import TestCase

from bizpilot.orgs.constants import ALL_PERMISSION_CODENAMES
from bizpilot.orgs.constants import SYSTEM_ROLE_ADMIN
from bizpilot.orgs.constants import SYSTEM_ROLE_EDITOR
from bizpilot.orgs.constants import SYSTEM_ROLE_OWNER
from bizpilot.orgs.constants import SYSTEM_ROLE_VIEWER
from bizpilot.orgs.models import Membership
from bizpilot.orgs.models import Organization
from bizpilot.orgs.models import Permission
from bizpilot.orgs.models import Role
from bizpilot.orgs.services import accept_invite
from bizpilot.orgs.services import claim_pending_invites_for_user
from bizpilot.orgs.services import create_invite
from bizpilot.orgs.services import create_organization
from bizpilot.orgs.services import remove_member
from bizpilot.orgs.services import resolve_user_permissions
from bizpilot.orgs.services import seed_permissions
from bizpilot.orgs.services import seed_system_roles_for_org
from bizpilot.orgs.services import update_member_roles
from bizpilot.users.models import User


class RBACServicesTest(TestCase):
    def setUp(self) -> None:
        cache.clear()
        self.owner_user = User.objects.create_user(
            email="owner@servicecorp.com",
            password="password123",
            name="Alice Owner",
        )
        self.staff_user = User.objects.create_user(
            email="staff@servicecorp.com",
            password="password123",
            name="Bob Staff",
        )
        self.org = create_organization(
            name="Service Corp",
            owner=self.owner_user,
        )

    def tearDown(self) -> None:
        cache.clear()

    def test_seed_permissions_is_idempotent(self) -> None:
        count1 = seed_permissions()
        count2 = seed_permissions()
        self.assertEqual(count2, 0)
        self.assertGreaterEqual(Permission.objects.count(), 35)

    def test_create_organization_seeds_system_roles_and_owner_membership(self) -> None:
        roles = {r.name: r for r in self.org.roles.all()}
        self.assertIn(SYSTEM_ROLE_OWNER, roles)
        self.assertIn(SYSTEM_ROLE_ADMIN, roles)
        self.assertIn(SYSTEM_ROLE_EDITOR, roles)
        self.assertIn(SYSTEM_ROLE_VIEWER, roles)

        owner_membership = Membership.objects.filter(
            organization=self.org,
            user=self.owner_user,
        ).first()
        self.assertIsNotNone(owner_membership)
        assert owner_membership is not None
        self.assertTrue(owner_membership.roles.filter(name=SYSTEM_ROLE_OWNER).exists())

    def test_resolve_user_permissions_for_owner_and_caching(self) -> None:
        perms = resolve_user_permissions(self.owner_user.pk, self.org.pk)
        self.assertIn("*", perms)
        self.assertIn("invoices.create", perms)
        self.assertIn("organization.delete", perms)

        # Test cache hit
        cached_perms = resolve_user_permissions(self.owner_user.pk, self.org.pk)
        self.assertEqual(perms, cached_perms)

    def test_resolve_user_permissions_for_editor_and_viewer(self) -> None:
        editor_role = self.org.roles.get(name=SYSTEM_ROLE_EDITOR)
        viewer_role = self.org.roles.get(name=SYSTEM_ROLE_VIEWER)

        editor_membership = Membership.objects.create(
            organization=self.org,
            user=self.staff_user,
            email=self.staff_user.email,
            status=Membership.Status.ACTIVE,
        )
        editor_membership.roles.add(editor_role)

        editor_perms = resolve_user_permissions(self.staff_user.pk, self.org.pk)
        self.assertIn("invoices.create", editor_perms)
        self.assertNotIn("organization.delete", editor_perms)
        self.assertNotIn("*", editor_perms)

        # Change role to viewer and verify invalidation
        editor_membership.roles.set([viewer_role])
        cache.clear()
        viewer_perms = resolve_user_permissions(self.staff_user.pk, self.org.pk)
        self.assertIn("invoices.view", viewer_perms)
        self.assertNotIn("invoices.create", viewer_perms)

    def test_invite_creation_and_acceptance(self) -> None:
        editor_role = self.org.roles.get(name=SYSTEM_ROLE_EDITOR)
        invite = create_invite(
            organization=self.org,
            email="newhire@servicecorp.com",
            role_ids=[editor_role.id],
            invited_by=self.owner_user,
            department="Engineering",
        )
        self.assertIsNotNone(invite.token)
        self.assertEqual(invite.department, "Engineering")

        # Verify pending membership was created
        pending = Membership.objects.filter(
            organization=self.org,
            email="newhire@servicecorp.com",
        ).first()
        self.assertIsNotNone(pending)
        assert pending is not None
        self.assertEqual(pending.status, Membership.Status.PENDING)

        # Register user and accept invite
        new_user = User.objects.create_user(
            email="newhire@servicecorp.com",
            password="securepassword123",
            name="Charlie Newhire",
        )
        accepted_membership = accept_invite(
            token=invite.token,
            user=new_user,
        )
        self.assertEqual(accepted_membership.status, Membership.Status.ACTIVE)
        self.assertEqual(accepted_membership.user, new_user)
        self.assertTrue(accepted_membership.roles.filter(name=SYSTEM_ROLE_EDITOR).exists())

    def test_cannot_invite_existing_active_member(self) -> None:
        with self.assertRaises(ValidationError):
            create_invite(
                organization=self.org,
                email=self.owner_user.email,
                role_ids=[],
                invited_by=self.owner_user,
            )

    def test_last_active_owner_protection_on_remove(self) -> None:
        owner_membership = Membership.objects.get(
            organization=self.org,
            user=self.owner_user,
        )
        with self.assertRaises(ValidationError) as ctx:
            remove_member(
                organization_id=self.org.id,
                membership_id=owner_membership.id,
                actor=self.owner_user,
            )
        self.assertIn("last active owner", str(ctx.exception))

    def test_last_active_owner_protection_on_demote(self) -> None:
        owner_membership = Membership.objects.get(
            organization=self.org,
            user=self.owner_user,
        )
        viewer_role = self.org.roles.get(name=SYSTEM_ROLE_VIEWER)
        with self.assertRaises(ValidationError) as ctx:
            update_member_roles(
                organization_id=self.org.id,
                membership_id=owner_membership.id,
                role_ids=[viewer_role.id],
                actor=self.owner_user,
            )
        self.assertIn("last active owner", str(ctx.exception))

    def test_claim_pending_invites_for_user(self) -> None:
        viewer_role = self.org.roles.get(name=SYSTEM_ROLE_VIEWER)
        create_invite(
            organization=self.org,
            email="claimme@servicecorp.com",
            role_ids=[viewer_role.id],
            invited_by=self.owner_user,
        )

        user = User.objects.create_user(
            email="claimme@servicecorp.com",
            password="securepassword123",
            name="Claimed User",
        )
        claimed_count = claim_pending_invites_for_user(user)
        self.assertEqual(claimed_count, 1)

        membership = Membership.objects.get(
            organization=self.org,
            email="claimme@servicecorp.com",
        )
        self.assertEqual(membership.user, user)
        self.assertEqual(membership.status, Membership.Status.ACTIVE)
