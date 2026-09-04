from __future__ import annotations

from typing import Any

from django.contrib.auth import authenticate
from django.contrib.auth.password_validation import validate_password
from django.utils.translation import gettext_lazy as _
from rest_framework import serializers

from bizpilot.users.models import Profile
from bizpilot.users.models import User


class ProfileSerializer(serializers.ModelSerializer[Profile]):
    """Serializer for user profile preferences and defaults."""

    class Meta:  # pyright: ignore[reportIncompatibleVariableOverride]
        model = Profile
        fields = [
            "full_name",
            "avatar_url",
            "company_name",
            "company_email",
            "company_address",
            "company_phone",
            "default_currency",
            "default_tax_rate",
            "default_notes",
            "default_terms",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["created_at", "updated_at"]


class UserSerializer(serializers.ModelSerializer[User]):
    """Default user serializer for the cookiecutter viewset."""

    class Meta:  # pyright: ignore[reportIncompatibleVariableOverride]
        model = User
        fields = ["name", "url"]
        extra_kwargs = {
            "url": {"view_name": "api:user-detail", "lookup_field": "pk"},
        }


class CurrentUserSerializer(serializers.ModelSerializer[User]):
    """Detailed user serializer including profile and organization memberships."""

    profile = ProfileSerializer(read_only=True)
    memberships = serializers.SerializerMethodField()

    class Meta:  # pyright: ignore[reportIncompatibleVariableOverride]
        model = User
        fields = [
            "id",
            "email",
            "name",
            "profile",
            "memberships",
            "is_active",
            "date_joined",
        ]
        read_only_fields = ["id", "email", "is_active", "date_joined"]

    def get_memberships(self, obj: User) -> list[dict[str, Any]]:
        """Return list of active memberships if orgs app is active."""
        if not hasattr(obj, "memberships"):
            return []
        memberships_data: list[dict[str, Any]] = []
        for membership in obj.memberships.select_related("organization").all():
            roles = (
                [r.name for r in membership.roles.all()]
                if hasattr(membership, "roles")
                else []
            )
            memberships_data.append({
                "id": str(membership.id),
                "org_id": str(membership.organization_id),
                "org_name": getattr(membership.organization, "name", ""),
                "roles": roles,
                "status": getattr(membership, "status", "active"),
            })
        return memberships_data


class SignupSerializer(serializers.Serializer):
    """Serializer for user registration."""

    email = serializers.EmailField()
    password = serializers.CharField(write_only=True, min_length=8)
    name = serializers.CharField(required=False, allow_blank=True, default="")
    company_name = serializers.CharField(required=False, allow_blank=True, default="")

    def validate_email(self, value: str) -> str:
        normalized = value.strip().lower()
        if User.objects.filter(email=normalized).exists():
            msg = _("A user with this email address already exists.")
            raise serializers.ValidationError(msg)
        return normalized

    def validate_password(self, value: str) -> str:
        validate_password(value)
        return value

    def create(self, validated_data: dict[str, Any]) -> User:
        email = validated_data["email"]
        password = validated_data["password"]
        name = validated_data.get("name", "")
        company_name = validated_data.get("company_name", "")

        user = User.objects.create_user(
            email=email,
            password=password,
            name=name,
        )

        if company_name and hasattr(user, "profile"):
            user.profile.company_name = company_name
            user.profile.save(update_fields=["company_name"])

        return user


class LoginSerializer(serializers.Serializer):
    """Serializer for user authentication via email and password."""

    email = serializers.EmailField()
    password = serializers.CharField(write_only=True)

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        email = attrs.get("email", "").strip().lower()
        password = attrs.get("password", "")

        user = authenticate(
            request=self.context.get("request"),
            email=email,
            password=password,
        )
        if not user:
            msg = _("Unable to log in with provided credentials.")
            raise serializers.ValidationError(msg, code="authorization")

        if not user.is_active:
            msg = _("User account is deactivated.")
            raise serializers.ValidationError(msg, code="authorization")

        attrs["user"] = user
        return attrs


class PasswordResetRequestSerializer(serializers.Serializer):
    """Serializer to initiate a password reset via email."""

    email = serializers.EmailField()


class PasswordResetConfirmSerializer(serializers.Serializer):
    """Serializer to confirm password reset with token."""

    uid = serializers.CharField()
    token = serializers.CharField()
    new_password = serializers.CharField(write_only=True, min_length=8)

    def validate_new_password(self, value: str) -> str:
        validate_password(value)
        return value
