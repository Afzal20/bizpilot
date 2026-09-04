from __future__ import annotations

import uuid
from typing import TYPE_CHECKING
from typing import Any

from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import permissions
from rest_framework import status
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from bizpilot.core.models import AuditLog
from bizpilot.orgs.api.serializers import InviteAcceptSerializer
from bizpilot.orgs.api.serializers import InviteCreateSerializer
from bizpilot.orgs.api.serializers import InviteSerializer
from bizpilot.orgs.api.serializers import MembershipSerializer
from bizpilot.orgs.api.serializers import MembershipUpdateRolesSerializer
from bizpilot.orgs.api.serializers import OrganizationCreateSerializer
from bizpilot.orgs.api.serializers import OrganizationSerializer
from bizpilot.orgs.api.serializers import PermissionSerializer
from bizpilot.orgs.api.serializers import RoleCreateUpdateSerializer
from bizpilot.orgs.api.serializers import RoleSerializer
from bizpilot.orgs.models import Invite
from bizpilot.orgs.models import Membership
from bizpilot.orgs.models import Organization
from bizpilot.orgs.models import Permission
from bizpilot.orgs.models import Role
from bizpilot.orgs.permissions import OrgPermission
from bizpilot.orgs.services import accept_invite
from bizpilot.orgs.services import create_invite
from bizpilot.orgs.services import create_organization
from bizpilot.orgs.services import remove_member
from bizpilot.orgs.services import resolve_user_permissions
from bizpilot.orgs.services import seed_permissions
from bizpilot.orgs.services import update_member_roles
from bizpilot.orgs.viewsets import OrgScopedViewSet
from bizpilot.users.models import User as UserModel

if TYPE_CHECKING:
    from rest_framework.request import Request


class OrganizationViewSet(viewsets.ModelViewSet):
    """
    CRUD viewset for business organizations.
    Listing returns all organizations where caller is an active member.
    """

    permission_classes = [permissions.IsAuthenticated, OrgPermission]
    permission_map = {
        "retrieve": "organization.view",
        "update": "organization.edit_settings",
        "partial_update": "organization.edit_settings",
        "destroy": "organization.delete",
    }

    def get_serializer_class(
        self,
    ) -> type[OrganizationSerializer | OrganizationCreateSerializer]:
        if self.action == "create":
            return OrganizationCreateSerializer
        return OrganizationSerializer

    def get_queryset(self) -> Any:
        user = self.request.user
        assert user.is_authenticated
        return (
            Organization.objects.filter(
                memberships__user=user,
                memberships__status=Membership.Status.ACTIVE,
                is_active=True,
            )
            .distinct()
            .select_related("owner")
        )

    def create(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = request.user
        assert isinstance(user, UserModel)

        org = create_organization(
            owner=user,
            **serializer.validated_data,
        )

        AuditLog.objects.create(
            organization_id=org.id,
            actor=user,
            actor_email=user.email,
            action="organization.create",
            target_model="Organization",
            target_id=str(org.id),
            changes_diff={"name": org.name},
        )

        output_serializer = OrganizationSerializer(org)
        return Response(output_serializer.data, status=status.HTTP_201_CREATED)

    def perform_destroy(self, instance: Organization) -> None:
        user = self.request.user
        # Only the actual owner or member with organization.delete permission can delete
        if instance.owner_id != getattr(user, "id", None):
            perms = resolve_user_permissions(user.id, instance.id)  # type: ignore[union-attr]
            if "organization.delete" not in perms and "*" not in perms:
                msg = "Only the organization owner can delete the organization."
                raise PermissionDenied(msg)

        instance.is_active = False
        instance.save(update_fields=["is_active"])


class MembershipViewSet(OrgScopedViewSet):
    """Viewset for managing organization members and their role assignments."""

    serializer_class = MembershipSerializer
    queryset = (
        Membership.objects.all()
        .select_related("user", "organization")
        .prefetch_related("roles__permissions")
    )
    permission_map = {
        "list": "team.view",
        "retrieve": "team.view",
        "update": "team.manage_roles",
        "partial_update": "team.manage_roles",
        "destroy": "team.remove",
        "update_roles": "team.manage_roles",
    }

    def destroy(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        instance = self.get_object()
        org_id = self.get_organization_id()
        user = request.user
        assert isinstance(user, UserModel)

        try:
            remove_member(
                organization_id=org_id,
                membership_id=instance.id,
                actor=user,
            )
        except DjangoValidationError as exc:
            msg = exc.message if hasattr(exc, "message") else str(exc)
            raise ValidationError(msg) from exc

        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=True, methods=["patch"], url_path="roles")
    def update_roles(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        instance = self.get_object()
        org_id = self.get_organization_id()
        serializer = MembershipUpdateRolesSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        user = request.user
        assert isinstance(user, UserModel)

        try:
            updated_membership = update_member_roles(
                organization_id=org_id,
                membership_id=instance.id,
                role_ids=serializer.validated_data["role_ids"],
                actor=user,
            )
        except DjangoValidationError as exc:
            msg = exc.message if hasattr(exc, "message") else str(exc)
            raise ValidationError(msg) from exc

        output_serializer = MembershipSerializer(updated_membership)
        return Response(output_serializer.data, status=status.HTTP_200_OK)


class RoleViewSet(OrgScopedViewSet):
    """Viewset for managing organizational roles and granular permission sets."""

    serializer_class = RoleSerializer
    queryset = Role.objects.all().prefetch_related("permissions")
    permission_map = {
        "list": "team.view",
        "retrieve": "team.view",
        "create": "team.manage_roles",
        "update": "team.manage_roles",
        "partial_update": "team.manage_roles",
        "destroy": "team.manage_roles",
    }

    def get_queryset(self) -> Any:
        org_id = self.get_organization_id()
        return Role.objects.filter(organization_id=org_id).prefetch_related(
            "permissions",
        )

    def create(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        org_id = self.get_organization_id()
        serializer = RoleCreateUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        data = serializer.validated_data
        role = Role.objects.create(
            organization_id=org_id,
            name=data["name"],
            description=data.get("description", ""),
            is_system=False,
        )
        if data.get("resolved_permissions"):
            role.permissions.set(data["resolved_permissions"])

        output_serializer = RoleSerializer(role)
        return Response(output_serializer.data, status=status.HTTP_201_CREATED)

    def partial_update(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        role = self.get_object()
        serializer = RoleCreateUpdateSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)

        data = serializer.validated_data
        if "name" in data:
            if role.is_system and data["name"] != role.name:
                msg = "System roles cannot be renamed."
                raise ValidationError(msg)
            role.name = data["name"]

        if "description" in data:
            role.description = data["description"]

        if "resolved_permissions" in data:
            if role.is_system and role.name == "owner":
                msg = "Permissions on the owner role cannot be modified."
                raise ValidationError(msg)
            role.permissions.set(data["resolved_permissions"])

        role.save()
        output_serializer = RoleSerializer(role)
        return Response(output_serializer.data, status=status.HTTP_200_OK)

    def destroy(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        role = self.get_object()
        if role.is_system:
            msg = "System default roles cannot be deleted."
            raise ValidationError(msg)

        if role.memberships.filter(status=Membership.Status.ACTIVE).exists():
            msg = "Cannot delete role that is currently assigned to active members."
            raise ValidationError(msg)

        role.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class PermissionListView(APIView):
    """List the fixed RBAC v2 permission catalog."""

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        seed_permissions()
        all_perms = Permission.objects.all().order_by("resource", "action")
        serializer = PermissionSerializer(all_perms, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)


class InviteViewSet(OrgScopedViewSet):
    """Viewset for inviting new members to an organization and managing invitations."""

    serializer_class = InviteSerializer
    queryset = Invite.objects.all().prefetch_related("roles")
    permission_map = {
        "list": "team.invite",
        "retrieve": "team.invite",
        "create": "team.invite",
        "destroy": "team.invite",
    }

    def create(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        org = self.get_organization()
        serializer = InviteCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        user = request.user
        assert isinstance(user, UserModel)

        data = serializer.validated_data
        try:
            invite = create_invite(
                organization=org,
                email=data["email"],
                role_ids=data.get("role_ids", []),
                invited_by=user,
                department=data.get("department", ""),
            )
        except DjangoValidationError as exc:
            msg = exc.message if hasattr(exc, "message") else str(exc)
            raise ValidationError(msg) from exc

        output_serializer = InviteSerializer(invite)
        try:
            from bizpilot.core.tasks import send_invite_email_task  # noqa: PLC0415
            send_invite_email_task.delay(str(invite.id))
        except Exception:
            pass
        return Response(output_serializer.data, status=status.HTTP_201_CREATED)


class InviteAcceptView(APIView):
    """Accept an invitation via cryptographic token and activate membership."""

    permission_classes = [permissions.IsAuthenticated]

    def post(self, request: Request) -> Response:
        serializer = InviteAcceptSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        user = request.user
        assert isinstance(user, UserModel)

        try:
            membership = accept_invite(
                token=serializer.validated_data["token"],
                user=user,
            )
        except DjangoValidationError as exc:
            msg = exc.message if hasattr(exc, "message") else str(exc)
            raise ValidationError(msg) from exc

        output_serializer = MembershipSerializer(membership)
        return Response(
            {
                "message": "Invitation accepted successfully.",
                "membership": output_serializer.data,
            },
            status=status.HTTP_200_OK,
        )


class MyPermissionsView(APIView):
    """Returns effective permissions for user in requested organization."""

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request: Request) -> Response:
        org_id = request.query_params.get("org") or request.query_params.get("org_id")
        if not org_id:
            raise ValidationError({"org": "Organization ID parameter is required."})

        try:
            uuid.UUID(str(org_id))
        except ValueError as err:
            raise ValidationError(
                {"org": "Invalid organization UUID format."},
            ) from err

        user = request.user
        assert user.is_authenticated

        perms = resolve_user_permissions(user.id, org_id)  # type: ignore[union-attr]
        membership = (
            Membership.objects.filter(
                organization_id=org_id,
                user=user,
                status=Membership.Status.ACTIVE,
            )
            .prefetch_related("roles")
            .first()
        )

        if not membership:
            return Response(
                {
                    "organization_id": str(org_id),
                    "is_member": False,
                    "is_owner": False,
                    "roles": [],
                    "permissions": [],
                },
                status=status.HTTP_200_OK,
            )

        roles = list(membership.roles.values_list("name", flat=True))
        return Response(
            {
                "organization_id": str(org_id),
                "is_member": True,
                "is_owner": membership.is_owner,
                "roles": roles,
                "permissions": sorted(perms),
            },
            status=status.HTTP_200_OK,
        )
