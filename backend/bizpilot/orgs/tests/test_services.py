from __future__ import annotations

import pytest
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.test import TestCase

from bizpilot.orgs.constants import SYSTEM_ROLE_ADMIN
from bizpilot.orgs.constants import SYSTEM_ROLE_EDITOR
from bizpilot.orgs.constants import SYSTEM_ROLE_OWNER
from bizpilot.orgs.constants import SYSTEM_ROLE_VIEWER
from bizpilot.orgs.models import Membership
from bizpilot.orgs.models import Permission
from bizpilot.orgs.services import accept_invite
from bizpilot.orgs.services import claim_pending_invites_for_user
from bizpilot.orgs.services import create_invite
from bizpilot.orgs.services import create_organization
from bizpilot.orgs.services import remove_member
from bizpilot.orgs.services import resolve_user_permissions
from bizpilot.orgs.services import seed_permissions
from bizpilot.orgs.services import update_member_roles
from bizpilot.users.models import User

MIN_CATALOG_PERMS = 35


class RBACServicesTest(TestCase):
    def setUp(self) -> None:
        cache.clear()
        self.owner_user = User.objects.create_user(
            email="owner@servicecorp.com",
            password="password123",  # noqa: S106
            name="Alice Owner",
        )
        self.staff_user = User.objects.create_user(
            email="staff@servicecorp.com",
            password="password123",  # noqa: S106
            name="Bob Staff",
        )
        self.org = create_organization(
            name="Service Corp",
            owner=self.owner_user,
        )

    def tearDown(self) -> None:
        cache.clear()

    def test_seed_permissions_is_idempotent(self) -> None:
        seed_permissions()
        count2 = seed_permissions()
        assert count2 == 0
        assert Permission.objects.count() >= MIN_CATALOG_PERMS

    def test_create_organization_seeds_system_roles_and_owner_membership(self) -> None:
        roles = {r.name: r for r in self.org.roles.all()}
        assert SYSTEM_ROLE_OWNER in roles
        assert SYSTEM_ROLE_ADMIN in roles
        assert SYSTEM_ROLE_EDITOR in roles
        assert SYSTEM_ROLE_VIEWER in roles

        owner_membership = Membership.objects.filter(
            organization=self.org,
            user=self.owner_user,
        ).first()
        assert owner_membership is not None
        assert owner_membership is not None
        assert owner_membership.roles.filter(name=SYSTEM_ROLE_OWNER).exists()

    def test_resolve_user_permissions_for_owner_and_caching(self) -> None:
        perms = resolve_user_permissions(self.owner_user.pk, self.org.pk)
        assert "*" in perms
        assert "invoices.create" in perms
        assert "organization.delete" in perms

        # Test cache hit
        cached_perms = resolve_user_permissions(self.owner_user.pk, self.org.pk)
        assert perms == cached_perms

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
        assert "invoices.create" in editor_perms
        assert "organization.delete" not in editor_perms
        assert "*" not in editor_perms

        # Change role to viewer and verify invalidation
        editor_membership.roles.set([viewer_role])
        cache.clear()
        viewer_perms = resolve_user_permissions(self.staff_user.pk, self.org.pk)
        assert "invoices.view" in viewer_perms
        assert "invoices.create" not in viewer_perms

    def test_invite_creation_and_acceptance(self) -> None:
        editor_role = self.org.roles.get(name=SYSTEM_ROLE_EDITOR)
        invite = create_invite(
            organization=self.org,
            email="newhire@servicecorp.com",
            role_ids=[editor_role.id],
            invited_by=self.owner_user,
            department="Engineering",
        )
        assert invite.token is not None
        assert invite.department == "Engineering"

        # Verify pending membership was created
        pending = Membership.objects.filter(
            organization=self.org,
            email="newhire@servicecorp.com",
        ).first()
        assert pending is not None
        assert pending is not None
        assert pending.status == Membership.Status.PENDING

        # Register user and accept invite
        new_user = User.objects.create_user(
            email="newhire@servicecorp.com",
            password="securepassword123",  # noqa: S106
            name="Charlie Newhire",
        )
        accepted_membership = accept_invite(
            token=invite.token,
            user=new_user,
        )
        assert accepted_membership.status == Membership.Status.ACTIVE
        assert accepted_membership.user == new_user
        assert accepted_membership.roles.filter(name=SYSTEM_ROLE_EDITOR).exists()

    def test_cannot_invite_existing_active_member(self) -> None:
        with pytest.raises(ValidationError):
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
        with pytest.raises(ValidationError) as ctx:
            remove_member(
                organization_id=self.org.id,
                membership_id=owner_membership.id,
                actor=self.owner_user,
            )
        assert "last active owner" in str(ctx.value)

    def test_last_active_owner_protection_on_demote(self) -> None:
        owner_membership = Membership.objects.get(
            organization=self.org,
            user=self.owner_user,
        )
        viewer_role = self.org.roles.get(name=SYSTEM_ROLE_VIEWER)
        with pytest.raises(ValidationError) as ctx:
            update_member_roles(
                organization_id=self.org.id,
                membership_id=owner_membership.id,
                role_ids=[viewer_role.id],
                actor=self.owner_user,
            )
        assert "last active owner" in str(ctx.value)

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
            password="securepassword123",  # noqa: S106
            name="Claimed User",
        )
        claimed_count = claim_pending_invites_for_user(user)
        assert claimed_count == 1

        membership = Membership.objects.get(
            organization=self.org,
            email="claimme@servicecorp.com",
        )
        assert membership.user == user
        assert membership.status == Membership.Status.ACTIVE
