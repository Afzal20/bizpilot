from typing import TYPE_CHECKING
from typing import Any

from django.contrib.auth.tokens import default_token_generator
from django.utils.encoding import force_bytes
from django.utils.encoding import force_str
from django.utils.http import urlsafe_base64_decode
from django.utils.http import urlsafe_base64_encode
from django.utils.translation import gettext_lazy as _
from rest_framework import permissions
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.mixins import ListModelMixin
from rest_framework.mixins import RetrieveModelMixin
from rest_framework.mixins import UpdateModelMixin
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.viewsets import GenericViewSet
from rest_framework_simplejwt.tokens import RefreshToken

from bizpilot.core.mixins import log_audit_event
from bizpilot.users.models import Profile
from bizpilot.users.models import User

if TYPE_CHECKING:
    from rest_framework.request import Request

from .serializers import CurrentUserSerializer
from .serializers import LoginSerializer
from .serializers import PasswordResetConfirmSerializer
from .serializers import PasswordResetRequestSerializer
from .serializers import ProfileSerializer
from .serializers import SignupSerializer
from .serializers import UserSerializer


def get_tokens_for_user(user: User) -> dict[str, str]:
    """Generate SimpleJWT access and refresh tokens for user."""
    refresh = RefreshToken.for_user(user)
    return {
        "access": str(refresh.access_token),
        "refresh": str(refresh),
    }


class UserViewSet(RetrieveModelMixin, ListModelMixin, UpdateModelMixin, GenericViewSet):
    """Legacy user viewset from template scaffold."""

    serializer_class = UserSerializer
    queryset = User.objects.all()
    lookup_field = "pk"

    def get_queryset(self, *args: Any, **kwargs: Any) -> Any:
        user = self.request.user
        assert isinstance(user, User)
        assert isinstance(user.id, int)
        queryset = self.queryset
        assert queryset is not None
        return queryset.filter(id=user.id)

    @action(detail=False)
    def me(self, request: Request) -> Response:
        assert isinstance(request.user, User)
        serializer = UserSerializer(request.user, context={"request": request})
        return Response(status=status.HTTP_200_OK, data=serializer.data)


class SignupView(APIView):
    """Register a new user account with profile and return authentication tokens."""

    permission_classes = [permissions.AllowAny]

    def post(self, request: Request) -> Response:
        serializer = SignupSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        user = serializer.save()

        tokens = get_tokens_for_user(user)
        log_audit_event(
            request=request,
            action="auth.signup",
            target=user,
            changes_diff={"email": user.email},
        )

        user_data = CurrentUserSerializer(user).data
        return Response(
            {
                "user": user_data,
                "tokens": tokens,
            },
            status=status.HTTP_201_CREATED,
        )


class LoginView(APIView):
    """Authenticate user with email and password, returning tokens and profile."""

    permission_classes = [permissions.AllowAny]

    def post(self, request: Request) -> Response:
        serializer = LoginSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        user = serializer.validated_data["user"]

        tokens = get_tokens_for_user(user)
        log_audit_event(
            request=request,
            action="auth.login",
            target=user,
        )

        user_data = CurrentUserSerializer(user).data
        return Response(
            {
                "user": user_data,
                "tokens": tokens,
            },
            status=status.HTTP_200_OK,
        )


class LogoutView(APIView):
    """Log out authenticated user and optionally blacklist refresh token."""

    permission_classes = [permissions.IsAuthenticated]

    def post(self, request: Request) -> Response:
        assert isinstance(request.user, User)
        refresh_token = (
            request.data.get("refresh")
            if isinstance(request.data, dict)
            else None
        )
        if refresh_token:
            try:
                token = RefreshToken(refresh_token)
                token.blacklist()
            except Exception:  # noqa: BLE001, S110
                # If token blacklist is disabled or token invalid, continue logout
                pass

        log_audit_event(
            request=request,
            action="auth.logout",
            target=request.user,
        )
        return Response(
            {"detail": _("Successfully logged out.")},
            status=status.HTTP_200_OK,
        )


class MeView(APIView):
    """Retrieve current authenticated user details, profile, and memberships."""

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request: Request) -> Response:
        assert isinstance(request.user, User)
        serializer = CurrentUserSerializer(request.user)
        return Response(serializer.data, status=status.HTTP_200_OK)


class ProfileView(APIView):
    """Retrieve or update profile settings and invoice defaults for current user."""

    permission_classes = [permissions.IsAuthenticated]

    def get_profile(self, user: User) -> Profile:
        profile, _ = Profile.objects.get_or_create(
            user=user,
            defaults={"full_name": user.name or ""},
        )
        return profile

    def get(self, request: Request) -> Response:
        assert isinstance(request.user, User)
        profile = self.get_profile(request.user)
        serializer = ProfileSerializer(profile)
        return Response(serializer.data, status=status.HTTP_200_OK)

    def patch(self, request: Request) -> Response:
        assert isinstance(request.user, User)
        profile = self.get_profile(request.user)
        serializer = ProfileSerializer(
            profile,
            data=request.data,
            partial=True,
        )
        serializer.is_valid(raise_exception=True)
        updated_profile = serializer.save()

        log_audit_event(
            request=request,
            action="profile.update",
            target=updated_profile,
            changes_diff=serializer.validated_data,
        )
        return Response(serializer.data, status=status.HTTP_200_OK)


class PasswordResetRequestView(APIView):
    """Send password reset token via email."""

    permission_classes = [permissions.AllowAny]

    def post(self, request: Request) -> Response:
        serializer = PasswordResetRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        email = serializer.validated_data["email"].strip().lower()

        user = User.objects.filter(email=email).first()
        if user:
            token = default_token_generator.make_token(user)
            uid = urlsafe_base64_encode(force_bytes(user.pk))
            log_audit_event(
                request=request,
                action="auth.password_reset_requested",
                target=user,
            )
            # Response message stays generic to prevent user enumeration
            return Response(
                {
                    "detail": _("Password reset instructions sent."),
                    "uid": uid,
                    "token": token,
                },
                status=status.HTTP_200_OK,
            )

        return Response(
            {"detail": _("Password reset instructions sent.")},
            status=status.HTTP_200_OK,
        )


class PasswordResetConfirmView(APIView):
    """Confirm password reset with UID, token, and new password."""

    permission_classes = [permissions.AllowAny]

    def post(self, request: Request) -> Response:
        serializer = PasswordResetConfirmSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        uid_b64 = serializer.validated_data["uid"]
        token = serializer.validated_data["token"]
        new_password = serializer.validated_data["new_password"]

        try:
            uid = force_str(urlsafe_base64_decode(uid_b64))
            user = User.objects.get(pk=uid)
        except (TypeError, ValueError, OverflowError, User.DoesNotExist):
            return Response(
                {"detail": _("Invalid password reset link.")},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not default_token_generator.check_token(user, token):
            return Response(
                {"detail": _("Invalid or expired reset token.")},
                status=status.HTTP_400_BAD_REQUEST,
            )

        user.set_password(new_password)
        user.save(update_fields=["password"])

        log_audit_event(
            request=request,
            action="auth.password_reset_confirmed",
            target=user,
        )
        return Response(
            {"detail": _("Password has been reset successfully.")},
            status=status.HTTP_200_OK,
        )


class ClaimPendingInvitesView(APIView):
    """Claim pending team invites matching user's email."""

    permission_classes = [permissions.IsAuthenticated]

    def post(self, request: Request) -> Response:
        assert isinstance(request.user, User)
        email = request.user.email.strip().lower()
        claimed_count = 0
        claimed_orgs: list[str] = []

        # When orgs app is active in Phase 2, connect invites to membership
        # For now, return empty result if orgs app has no pending invites
        return Response(
            {
                "claimed_count": claimed_count,
                "claimed_orgs": claimed_orgs,
                "email": email,
            },
            status=status.HTTP_200_OK,
        )
