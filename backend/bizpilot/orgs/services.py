from __future__ import annotations

from datetime import timedelta
from typing import TYPE_CHECKING
from typing import Any

from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from bizpilot.orgs.constants import ALL_PERMISSION_CODENAMES
from bizpilot.orgs.constants import PERMISSION_CATALOG
from bizpilot.orgs.constants import SYSTEM_ROLE_ADMIN
from bizpilot.orgs.constants import SYSTEM_ROLE_EDITOR
from bizpilot.orgs.constants import SYSTEM_ROLE_OWNER
from bizpilot.orgs.constants import SYSTEM_ROLE_PERMISSIONS
from bizpilot.orgs.constants import SYSTEM_ROLE_VIEWER
from bizpilot.orgs.constants import SYSTEM_ROLES
from bizpilot.orgs.models import Invite
from bizpilot.orgs.models import Membership
from bizpilot.orgs.models import Organization
from bizpilot.orgs.models import Permission
from bizpilot.orgs.models import Role

if TYPE_CHECKING:
    import uuid

    from bizpilot.users.models import User


def seed_permissions() -> int:
    """Seed or update the fixed RBAC v2 permission catalog in the database."""
    created_or_updated = 0
    for perm_data in PERMISSION_CATALOG:
        _perm_obj, created = Permission.objects.update_or_create(
            codename=perm_data["codename"],
            defaults={
                "resource": perm_data["resource"],
                "action": perm_data["action"],
                "description": perm_data["description"],
            },
        )
        if created:
            created_or_updated += 1
    return created_or_updated


def seed_system_roles_for_org(organization: Organization) -> dict[str, Role]:
    """Create default system roles (owner, admin, editor, viewer) for an org."""
    seed_permissions()
    all_perms = {p.codename: p for p in Permission.objects.all()}
    created_roles: dict[str, Role] = {}

    role_descriptions = {
        SYSTEM_ROLE_OWNER: "Full control over all organization resources and billing",
        SYSTEM_ROLE_ADMIN: "Operational and team management access except org deletion",
        SYSTEM_ROLE_EDITOR: "Create, edit, and manage ERP records and AI tools",
        SYSTEM_ROLE_VIEWER: "Read-only access across ERP records and business reports",
    }

    for role_name in SYSTEM_ROLES:
        role, _created = Role.objects.get_or_create(
            organization=organization,
            name=role_name,
            defaults={
                "description": role_descriptions.get(role_name, ""),
                "is_system": True,
            },
        )
        target_perm_codenames = SYSTEM_ROLE_PERMISSIONS.get(role_name, [])
        target_perms = [
            all_perms[code] for code in target_perm_codenames if code in all_perms
        ]
        role.permissions.set(target_perms)
        created_roles[role_name] = role

    return created_roles


@transaction.atomic
def create_organization(  # noqa: PLR0913
    *,
    name: str,
    owner: User,
    logo_url: str = "",
    website: str = "",
    company_email: str = "",
    company_address: str = "",
    company_phone: str = "",
    default_currency: str = "USD",
    default_tax_rate: Any = "0.00",
    default_notes: str = "",
    default_terms: str = "",
) -> Organization:
    """Create an organization, seed default system roles, and assign owner."""
    organization = Organization.objects.create(
        name=name,
        owner=owner,
        logo_url=logo_url,
        website=website,
        company_email=company_email or owner.email,
        company_address=company_address,
        company_phone=company_phone,
        default_currency=default_currency,
        default_tax_rate=default_tax_rate,
        default_notes=default_notes,
        default_terms=default_terms,
    )

    roles = seed_system_roles_for_org(organization)
    owner_role = roles[SYSTEM_ROLE_OWNER]

    membership = Membership.objects.create(
        organization=organization,
        user=owner,
        email=owner.email.strip().lower(),
        name=owner.name or owner.email,
        status=Membership.Status.ACTIVE,
        joined_at=timezone.now(),
    )
    membership.roles.add(owner_role)

    invalidate_permission_cache(owner.pk, organization.pk)
    return organization


def get_permission_cache_key(
    user_id: int | uuid.UUID,
    organization_id: uuid.UUID | str,
) -> str:
    """Generate cache key for resolved user permissions within an organization."""
    return f"org_perms:{organization_id}:{user_id}"


def resolve_user_permissions(
    user_id: int,
    organization_id: uuid.UUID | str,
) -> set[str]:
    """
    Resolve effective permissions for a user within an organization.
    Uses Redis/local cache with 5-minute TTL and invalidation on role/membership change.
    """
    cache_key = get_permission_cache_key(user_id, organization_id)
    cached_perms = cache.get(cache_key)
    if cached_perms is not None:
        return set(cached_perms)

    membership = (
        Membership.objects.filter(
            user_id=user_id,
            organization_id=organization_id,
            status=Membership.Status.ACTIVE,
        )
        .prefetch_related("roles__permissions", "organization")
        .first()
    )

    if not membership:
        perms: set[str] = set()
        cache.set(cache_key, list(perms), timeout=300)
        return perms

    # Organization owners or members with the 'owner' role possess all permissions
    if membership.is_owner or membership.roles.filter(name=SYSTEM_ROLE_OWNER).exists():
        perms = set(ALL_PERMISSION_CODENAMES)
        perms.add("*")
        cache.set(cache_key, list(perms), timeout=300)
        return perms

    # Aggregate permissions across all assigned roles
    resolved = set(
        membership.roles.values_list("permissions__codename", flat=True),
    )
    cache.set(cache_key, list(resolved), timeout=300)
    return resolved


def invalidate_permission_cache(
    user_id: int | uuid.UUID | None,
    organization_id: uuid.UUID | str,
) -> None:
    """Invalidate cached permissions for a user or all members of an org."""
    if user_id is not None:
        cache.delete(get_permission_cache_key(user_id, organization_id))
    else:
        invalidate_org_permission_caches(organization_id)


def invalidate_org_permission_caches(organization_id: uuid.UUID | str) -> None:
    """Invalidate cached permissions for every member of an organization."""
    member_user_ids = Membership.objects.filter(
        organization_id=organization_id,
        user__isnull=False,
    ).values_list("user_id", flat=True)

    for uid in member_user_ids:
        cache.delete(get_permission_cache_key(uid, organization_id))


def create_invite(
    *,
    organization: Organization,
    email: str,
    role_ids: list[uuid.UUID | str],
    invited_by: User,
    department: str = "",
) -> Invite:
    """Create a tokenized invitation and register a pending membership."""
    normalized_email = email.strip().lower()

    if Membership.objects.filter(
        organization=organization,
        email=normalized_email,
        status=Membership.Status.ACTIVE,
    ).exists():
        msg = _(
            "User with this email is already an active member of this organization.",
        )
        raise ValidationError(msg)

    roles = list(Role.objects.filter(organization=organization, id__in=role_ids))
    if not roles:
        # Fallback to viewer role if not specified
        viewer_role = Role.objects.filter(
            organization=organization,
            name=SYSTEM_ROLE_VIEWER,
        ).first()
        if viewer_role:
            roles = [viewer_role]

    token = Invite.generate_token()
    expires_at = timezone.now() + timedelta(days=7)

    with transaction.atomic():
        invite = Invite.objects.create(
            organization=organization,
            email=normalized_email,
            department=department,
            invited_by=invited_by,
            token=token,
            expires_at=expires_at,
        )
        invite.roles.set(roles)

        membership, _created = Membership.objects.get_or_create(
            organization=organization,
            email=normalized_email,
            defaults={
                "name": "",
                "department": department,
                "status": Membership.Status.PENDING,
                "invited_by": invited_by,
            },
        )
        membership.status = Membership.Status.PENDING
        membership.department = department
        membership.invited_by = invited_by
        membership.save(update_fields=["status", "department", "invited_by"])
        membership.roles.set(roles)

    return invite


@transaction.atomic
def accept_invite(*, token: str, user: User) -> Membership:
    """Accept an invitation, linking user account to membership and activating it."""
    invite = (
        Invite.objects.select_related("organization")
        .prefetch_related("roles")
        .filter(token=token)
        .first()
    )
    if not invite or not invite.is_valid:
        msg = _("Invitation token is invalid or has expired.")
        raise ValidationError(msg)

    membership = Membership.objects.filter(
        organization=invite.organization,
        email=invite.email,
    ).first()

    if not membership:
        membership = Membership.objects.create(
            organization=invite.organization,
            email=invite.email,
            user=user,
            name=user.name or user.email,
            department=invite.department,
            status=Membership.Status.ACTIVE,
            joined_at=timezone.now(),
        )
        membership.roles.set(invite.roles.all())
    else:
        membership.user = user
        membership.name = user.name or membership.name
        membership.status = Membership.Status.ACTIVE
        membership.joined_at = timezone.now()
        membership.save(update_fields=["user", "name", "status", "joined_at"])
        if invite.roles.exists():
            membership.roles.set(invite.roles.all())

    invite.accepted_at = timezone.now()
    invite.save(update_fields=["accepted_at"])

    invalidate_permission_cache(user.pk, invite.organization_id)
    return membership


@transaction.atomic
def remove_member(
    *,
    organization_id: uuid.UUID | str,
    membership_id: uuid.UUID | str,
    actor: User,
) -> None:
    """
    Remove member from organization.
    Guards against removing the last active owner.
    """
    membership = (
        Membership.objects.select_related("organization")
        .prefetch_related("roles")
        .filter(organization_id=organization_id, id=membership_id)
        .first()
    )
    if not membership:
        msg = _("Membership not found.")
        raise ValidationError(msg)

    # Check last active owner guard
    if membership.is_owner:
        active_owners_count = (
            Membership.objects.filter(
                organization_id=organization_id,
                status=Membership.Status.ACTIVE,
                roles__name=SYSTEM_ROLE_OWNER,
            )
            .distinct()
            .count()
        )
        if active_owners_count <= 1:
            msg = _("Cannot remove the last active owner of the organization.")
            raise ValidationError(msg)

    user_id = membership.user_id
    membership.delete()

    if user_id:
        invalidate_permission_cache(user_id, organization_id)


@transaction.atomic
def update_member_roles(
    *,
    organization_id: uuid.UUID | str,
    membership_id: uuid.UUID | str,
    role_ids: list[uuid.UUID | str],
    actor: User,
) -> Membership:
    """
    Update assigned roles for an organization member.
    Guards against demoting the last active owner.
    """
    membership = (
        Membership.objects.select_related("organization")
        .prefetch_related("roles")
        .filter(organization_id=organization_id, id=membership_id)
        .first()
    )
    if not membership:
        msg = _("Membership not found.")
        raise ValidationError(msg)

    roles = list(
        Role.objects.filter(
            organization_id=organization_id,
            id__in=role_ids,
        ),
    )

    new_has_owner = any(r.name == SYSTEM_ROLE_OWNER for r in roles)
    if membership.is_owner and not new_has_owner:
        active_owners_count = (
            Membership.objects.filter(
                organization_id=organization_id,
                status=Membership.Status.ACTIVE,
                roles__name=SYSTEM_ROLE_OWNER,
            )
            .exclude(id=membership.id)
            .distinct()
            .count()
        )
        if active_owners_count < 1:
            msg = _("Cannot demote the last active owner of the organization.")
            raise ValidationError(msg)

    membership.roles.set(roles)
    if membership.user_id:
        invalidate_permission_cache(membership.user_id, organization_id)

    return membership


def claim_pending_invites_for_user(user: User) -> int:
    """Associate pending memberships with newly registered or logged in user."""
    normalized_email = user.email.strip().lower()
    pending_memberships = Membership.objects.filter(
        email=normalized_email,
        status=Membership.Status.PENDING,
        user__isnull=True,
    )
    claimed_count = 0
    for membership in pending_memberships:
        membership.user = user
        membership.name = user.name or membership.name
        membership.status = Membership.Status.ACTIVE
        membership.joined_at = timezone.now()
        membership.save(update_fields=["user", "name", "status", "joined_at"])
        invalidate_permission_cache(user.pk, membership.organization_id)
        claimed_count += 1
    return claimed_count
