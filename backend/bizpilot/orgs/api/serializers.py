from __future__ import annotations

from typing import Any

from rest_framework import serializers

from bizpilot.orgs.models import Invite
from bizpilot.orgs.models import Membership
from bizpilot.orgs.models import Organization
from bizpilot.orgs.models import Permission
from bizpilot.orgs.models import Role


class PermissionSerializer(serializers.ModelSerializer[Permission]):
    """Serializer for RBAC v2 catalog permissions."""

    class Meta:  # pyright: ignore[reportIncompatibleVariableOverride]
        model = Permission
        fields = [
            "id",
            "codename",
            "resource",
            "action",
            "description",
        ]


class RoleSerializer(serializers.ModelSerializer[Role]):
    """Detailed role serializer with resolved permissions."""

    permissions = PermissionSerializer(many=True, read_only=True)
    permission_codenames = serializers.SerializerMethodField()

    class Meta:  # pyright: ignore[reportIncompatibleVariableOverride]
        model = Role
        fields = [
            "id",
            "organization",
            "name",
            "description",
            "is_system",
            "permissions",
            "permission_codenames",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "organization",
            "is_system",
            "created_at",
            "updated_at",
        ]

    def get_permission_codenames(self, obj: Role) -> list[str]:
        return list(obj.permissions.values_list("codename", flat=True))


class RoleCreateUpdateSerializer(serializers.Serializer):
    """Serializer for creating and updating organizational custom roles."""

    name = serializers.CharField(max_length=100)
    description = serializers.CharField(required=False, allow_blank=True, default="")
    permission_ids = serializers.ListField(
        child=serializers.IntegerField(),
        required=False,
        default=list,
    )
    permission_codenames = serializers.ListField(
        child=serializers.CharField(),
        required=False,
        default=list,
    )

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        p_ids = attrs.get("permission_ids", [])
        p_codes = attrs.get("permission_codenames", [])

        query = Permission.objects.none()
        if p_ids:
            query = query | Permission.objects.filter(id__in=p_ids)
        if p_codes:
            query = query | Permission.objects.filter(codename__in=p_codes)

        resolved_permissions = list(query)
        attrs["resolved_permissions"] = resolved_permissions
        return attrs


class MembershipSerializer(serializers.ModelSerializer[Membership]):
    """Serializer for organization team members and their roles."""

    roles = RoleSerializer(many=True, read_only=True)
    role_names = serializers.SerializerMethodField()

    class Meta:  # pyright: ignore[reportIncompatibleVariableOverride]
        model = Membership
        fields = [
            "id",
            "organization",
            "user",
            "email",
            "name",
            "department",
            "roles",
            "role_names",
            "status",
            "invited_at",
            "joined_at",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "organization",
            "user",
            "email",
            "status",
            "invited_at",
            "joined_at",
            "created_at",
            "updated_at",
        ]

    def get_role_names(self, obj: Membership) -> list[str]:
        return list(obj.roles.values_list("name", flat=True))


class MembershipUpdateRolesSerializer(serializers.Serializer):
    """Serializer for assigning/updating roles on a team member."""

    role_ids = serializers.ListField(
        child=serializers.UUIDField(),
        min_length=1,
    )


class InviteSerializer(serializers.ModelSerializer[Invite]):
    """Serializer for pending or accepted invitations."""

    roles = RoleSerializer(many=True, read_only=True)
    is_expired = serializers.BooleanField(read_only=True)
    is_valid = serializers.BooleanField(read_only=True)

    class Meta:  # pyright: ignore[reportIncompatibleVariableOverride]
        model = Invite
        fields = [
            "id",
            "organization",
            "email",
            "department",
            "roles",
            "token",
            "expires_at",
            "accepted_at",
            "is_expired",
            "is_valid",
            "created_at",
        ]
        read_only_fields = [
            "id",
            "organization",
            "token",
            "expires_at",
            "accepted_at",
            "created_at",
        ]


class InviteCreateSerializer(serializers.Serializer):
    """Serializer for sending new team member invitations."""

    email = serializers.EmailField()
    department = serializers.CharField(required=False, allow_blank=True, default="")
    role_ids = serializers.ListField(
        child=serializers.UUIDField(),
        required=False,
        default=list,
    )


class InviteAcceptSerializer(serializers.Serializer):
    """Serializer for accepting an invitation with token."""

    token = serializers.CharField(max_length=64)


class OrganizationSerializer(serializers.ModelSerializer[Organization]):
    """Serializer for organization profiles and invoice settings."""

    owner_email = serializers.EmailField(source="owner.email", read_only=True)
    member_count = serializers.SerializerMethodField()

    class Meta:  # pyright: ignore[reportIncompatibleVariableOverride]
        model = Organization
        fields = [
            "id",
            "name",
            "slug",
            "owner",
            "owner_email",
            "logo_url",
            "website",
            "company_email",
            "company_address",
            "company_phone",
            "default_currency",
            "default_tax_rate",
            "default_notes",
            "default_terms",
            "stripe_customer_id",
            "stripe_subscription_id",
            "member_count",
            "is_active",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "slug",
            "owner",
            "owner_email",
            "stripe_customer_id",
            "stripe_subscription_id",
            "created_at",
            "updated_at",
        ]

    def get_member_count(self, obj: Organization) -> int:
        return obj.memberships.filter(status=Membership.Status.ACTIVE).count()


class OrganizationCreateSerializer(serializers.ModelSerializer[Organization]):
    """Serializer for provisioning a new organization."""

    class Meta:  # pyright: ignore[reportIncompatibleVariableOverride]
        model = Organization
        fields = [
            "id",
            "name",
            "logo_url",
            "website",
            "company_email",
            "company_address",
            "company_phone",
            "default_currency",
            "default_tax_rate",
            "default_notes",
            "default_terms",
        ]
        read_only_fields = ["id"]
