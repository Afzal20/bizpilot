from __future__ import annotations

from typing import TYPE_CHECKING
from typing import Any
import uuid

from rest_framework import permissions
from rest_framework.exceptions import PermissionDenied

from bizpilot.orgs.services import resolve_user_permissions

if TYPE_CHECKING:
    from rest_framework.request import Request
    from rest_framework.views import APIView


def get_org_id_from_request_or_view(request: Request, view: APIView) -> str | None:
    """Extract organization UUID from URL parameters, query parameters, or headers."""
    kwargs = getattr(view, "kwargs", {})
    org_id = (
        kwargs.get("org_id")
        or kwargs.get("organization_id")
        or kwargs.get("org_pk")
    )
    if org_id:
        return str(org_id)

    # Detail route of Organization itself where pk is the org ID
    if getattr(view, "basename", "") in ("organization", "org", "v1-orgs") and "pk" in kwargs:
        return str(kwargs["pk"])

    query_org = request.query_params.get("org_id") or request.query_params.get("org")
    if query_org:
        return str(query_org)

    header_org = request.headers.get("X-Organization-ID")
    if header_org:
        return str(header_org)

    return None


class OrgPermission(permissions.BasePermission):
    """
    Enforces RBAC v2 organizational permissions on API views.
    Resolves permissions for (user, org) and checks required capability.
    """

    def has_permission(self, request: Request, view: APIView) -> bool:
        if not request.user or not request.user.is_authenticated:
            return False

        org_id = get_org_id_from_request_or_view(request, view)
        if not org_id:
            # If no org in context, allow view-level handler to decide or fail
            return True

        # Validate UUID format
        try:
            uuid.UUID(str(org_id))
        except ValueError:
            raise PermissionDenied("Invalid organization identifier.")

        required_perm = self._get_required_permission(request, view)
        if not required_perm:
            return True

        user_id = getattr(request.user, "id", None)
        if not user_id:
            return False

        effective_perms = resolve_user_permissions(user_id, org_id)

        if "*" in effective_perms or required_perm in effective_perms:
            return True

        # Raise explicit PermissionDenied with missing permission info for RFC 7807 handler
        raise PermissionDenied({
            "detail": f"You do not have the required permission: {required_perm}",
            "required_permission": required_perm,
            "organization_id": str(org_id),
        })

    def _get_required_permission(self, request: Request, view: APIView) -> str | None:
        """Inspect view attributes for explicit required permission or permission map."""
        # 1. Check explicit required_permission on view
        explicit_perm = getattr(view, "required_permission", None)
        if explicit_perm:
            return str(explicit_perm)

        # 2. Check permission_map based on action (for ViewSets)
        action = getattr(view, "action", None)
        perm_map: dict[str, str] = getattr(view, "permission_map", {})

        if action and action in perm_map:
            return perm_map[action]

        # 3. Check permission_map based on HTTP method
        method = request.method.upper() if request.method else "GET"
        if method in perm_map:
            return perm_map[method]

        return None


class IsOrgMember(permissions.BasePermission):
    """Allows access only to active members of the organization."""

    def has_permission(self, request: Request, view: APIView) -> bool:
        if not request.user or not request.user.is_authenticated:
            return False

        org_id = get_org_id_from_request_or_view(request, view)
        if not org_id:
            return False

        user_id = getattr(request.user, "id", None)
        if not user_id:
            return False

        effective_perms = resolve_user_permissions(user_id, org_id)
        # Any resolved permissions (or empty set if not member)
        from bizpilot.orgs.models import Membership

        return Membership.objects.filter(
            user_id=user_id,
            organization_id=org_id,
            status=Membership.Status.ACTIVE,
        ).exists()
