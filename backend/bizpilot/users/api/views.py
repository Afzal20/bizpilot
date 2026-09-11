from typing import TYPE_CHECKING
from typing import Any
import urllib.parse

import requests
from allauth.socialaccount.models import SocialAccount
from django.conf import settings
from django.contrib.auth.tokens import default_token_generator
from django.http import HttpResponseRedirect
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
from bizpilot.orgs.services import create_organization
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
            try:
                from bizpilot.core.tasks import (  # noqa: PLC0415
                    send_password_reset_email_task,
                )
                send_password_reset_email_task.delay(user.pk, uid, token)
            except Exception:  # noqa: BLE001, S110
                pass
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


def _exchange_google_code(  # noqa: PLR0911
    code: str, redirect_uri: str,
) -> tuple[dict[str, Any] | None, Response | None]:
    client_id = getattr(settings, "GOOGLE_CLIENT_ID", "")
    client_secret = getattr(settings, "GOOGLE_CLIENT_SECRET", "")
    if not client_id or not client_secret:
        return None, Response(
            {"error": _("Google OAuth credentials are not configured on the server.")},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    oauth_token_url = "https://oauth2.googleapis.com/token"  # noqa: S105
    payload = {
        "code": code,
        "client_id": client_id,
        "client_secret": client_secret,
        "redirect_uri": redirect_uri,
        "grant_type": "authorization_code",
    }
    try:
        token_resp = requests.post(oauth_token_url, data=payload, timeout=10)
    except requests.RequestException as exc:
        msg = _("Failed to connect to Google token endpoint: %s") % exc
        return None, Response({"error": msg}, status=status.HTTP_502_BAD_GATEWAY)

    if token_resp.status_code != status.HTTP_200_OK:
        try:
            err_json = token_resp.json()
            err_msg = (
                err_json.get("error_description")
                or err_json.get("error")
                or "Failed to exchange authorization code."
            )
        except Exception:  # noqa: BLE001
            err_msg = "Failed to exchange authorization code with Google."
        return None, Response({"error": _(err_msg)}, status=status.HTTP_400_BAD_REQUEST)

    token_data = token_resp.json()
    access_token = token_data.get("access_token")
    if not access_token:
        return None, Response(
            {"error": _("Google did not return an access token.")},
            status=status.HTTP_400_BAD_REQUEST,
        )

    try:
        userinfo_resp = requests.get(
            "https://www.googleapis.com/oauth2/v3/userinfo",
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=10,
        )
    except requests.RequestException as exc:
        msg = _("Failed to connect to Google userinfo endpoint: %s") % exc
        return None, Response({"error": msg}, status=status.HTTP_502_BAD_GATEWAY)

    if userinfo_resp.status_code != status.HTTP_200_OK:
        return None, Response(
            {"error": _("Failed to fetch user profile from Google.")},
            status=status.HTTP_400_BAD_REQUEST,
        )

    return userinfo_resp.json(), None


def _verify_google_id_token(
    id_token: str,
) -> tuple[dict[str, Any] | None, Response | None]:
    tokeninfo_url = f"https://oauth2.googleapis.com/tokeninfo?id_token={id_token}"
    try:
        tokeninfo_resp = requests.get(tokeninfo_url, timeout=10)
    except requests.RequestException as exc:
        msg = _("Failed to verify ID token with Google: %s") % exc
        return None, Response({"error": msg}, status=status.HTTP_502_BAD_GATEWAY)

    if tokeninfo_resp.status_code != status.HTTP_200_OK:
        return None, Response(
            {"error": _("Invalid or expired Google ID token.")},
            status=status.HTTP_400_BAD_REQUEST,
        )

    user_info = tokeninfo_resp.json()
    client_id = getattr(settings, "GOOGLE_CLIENT_ID", "")
    if client_id and user_info.get("aud") != client_id:
        return None, Response(
            {"error": _("Token audience does not match this application.")},
            status=status.HTTP_400_BAD_REQUEST,
        )
    return user_info, None


def _provision_google_user(
    user_info: dict[str, Any],
    request: Request,
) -> tuple[User, bool]:
    email = user_info["email"].strip().lower()
    google_sub = str(user_info.get("sub", ""))
    name = user_info.get("name", "").strip()
    picture = user_info.get("picture", "").strip()

    user = User.objects.filter(email=email).first()
    is_new = False
    if not user:
        user = User.objects.create_user(
            email=email,
            name=name,
            password=None,
        )
        user.set_unusable_password()
        user.save()
        is_new = True
    elif name and not user.name:
        user.name = name
        user.save(update_fields=["name"])

    SocialAccount.objects.update_or_create(
        provider="google",
        uid=google_sub or email,
        defaults={
            "user": user,
            "extra_data": user_info,
        },
    )

    profile, _created = Profile.objects.get_or_create(
        user=user,
        defaults={"full_name": name, "avatar_url": picture},
    )
    updated_fields = []
    if picture and not profile.avatar_url:
        profile.avatar_url = picture
        updated_fields.append("avatar_url")
    if name and not profile.full_name:
        profile.full_name = name
        updated_fields.append("full_name")
    if updated_fields:
        profile.save(update_fields=updated_fields)

    has_active_org = (
        hasattr(user, "memberships")
        and user.memberships.filter(status="active").exists()
    )
    if not has_active_org:
        try:
            org_name = f"{name or 'My'} Organization"
            create_organization(name=org_name, owner=user)
        except Exception:  # noqa: BLE001, S110
            pass

    log_audit_event(
        request=request,
        action="auth.google_signup" if is_new else "auth.google_login",
        target=user,
        changes_diff={"provider": "google", "email": email},
    )
    return user, is_new


class GoogleAuthView(APIView):
    """Authenticate or register user via Google OAuth 2.0 or Google ID Token."""

    permission_classes = [permissions.AllowAny]

    def get(self, request: Request) -> Response:
        """Return Google OAuth public configuration and authorization URL."""
        client_id = getattr(settings, "GOOGLE_CLIENT_ID", "")
        frontend_url = getattr(settings, "FRONTEND_URL", "http://localhost:3000").rstrip("/")
        redirect_uri = request.query_params.get("redirect_uri") or f"{frontend_url}/auth/callback"
        next_url = request.query_params.get("next", "/dashboard")

        params = {
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": "openid email profile",
            "access_type": "offline",
            "prompt": "select_account",
            "state": next_url,
        }
        auth_url = (
            f"https://accounts.google.com/o/oauth2/v2/auth?{urllib.parse.urlencode(params)}"
            if client_id
            else ""
        )
        return Response(
            {"client_id": client_id, "authorization_url": auth_url},
            status=status.HTTP_200_OK,
        )

    def post(self, request: Request) -> Response:
        """Verify Google OAuth authorization code or ID token, and return JWT tokens."""
        data = request.data if isinstance(request.data, dict) else {}
        code = data.get("code")
        redirect_uri = data.get("redirect_uri", "")
        id_token = data.get("id_token")

        if not code and not id_token:
            return Response(
                {"error": _("Authorization code or ID token is required.")},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if code:
            user_info, err_resp = _exchange_google_code(code, redirect_uri)
            if err_resp:
                return err_resp
        else:
            assert id_token is not None
            user_info, err_resp = _verify_google_id_token(id_token)
            if err_resp:
                return err_resp

        if not user_info or not user_info.get("email"):
            return Response(
                {"error": _("No email address provided by Google account.")},
                status=status.HTTP_400_BAD_REQUEST,
            )

        email_verified = user_info.get("email_verified")
        if isinstance(email_verified, str):
            email_verified = email_verified.lower() in ("true", "1")
        elif email_verified is None:
            email_verified = True

        if not email_verified:
            return Response(
                {"error": _("Your Google account email is not verified.")},
                status=status.HTTP_400_BAD_REQUEST,
            )

        user, is_new = _provision_google_user(user_info, request)
        tokens = get_tokens_for_user(user)
        user_data = CurrentUserSerializer(user).data

        return Response(
            {"user": user_data, "tokens": tokens},
            status=status.HTTP_201_CREATED if is_new else status.HTTP_200_OK,
        )


class GoogleRedirectView(APIView):
    """Initiate Google OAuth 2.0 flow by redirecting to Google authorization URL."""

    permission_classes = [permissions.AllowAny]

    def get(self, request: Request) -> Response | HttpResponseRedirect:
        client_id = getattr(settings, "GOOGLE_CLIENT_ID", "").strip()
        frontend_url = getattr(settings, "FRONTEND_URL", "http://localhost:3000").rstrip("/")
        default_redirect_uri = f"{frontend_url}/auth/callback"

        redirect_uri = request.query_params.get("redirect_uri") or default_redirect_uri
        next_url = request.query_params.get("next", "/dashboard")
        is_json_request = (
            request.query_params.get("format") == "json"
            or request.query_params.get("json") == "true"
        )

        if not client_id:
            error_msg = _("Google OAuth credentials are not configured on the server.")
            if is_json_request:
                return Response(
                    {"error": error_msg},
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR,
                )
            return HttpResponseRedirect(
                f"{frontend_url}/auth/login?error={urllib.parse.quote(str(error_msg))}",
            )

        params = {
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": "openid email profile",
            "access_type": "offline",
            "prompt": "select_account",
            "state": next_url,
        }
        google_auth_url = (
            f"https://accounts.google.com/o/oauth2/v2/auth?{urllib.parse.urlencode(params)}"
        )

        if is_json_request:
            return Response(
                {"authorization_url": google_auth_url, "client_id": client_id},
                status=status.HTTP_200_OK,
            )

        return HttpResponseRedirect(google_auth_url)


class GoogleCallbackView(APIView):
    """Handle direct OAuth redirect callback from Google on backend."""

    permission_classes = [permissions.AllowAny]

    def get(self, request: Request) -> HttpResponseRedirect:
        frontend_url = getattr(settings, "FRONTEND_URL", "http://localhost:3000").rstrip("/")
        error = request.query_params.get("error")
        error_description = request.query_params.get("error_description")
        next_url = request.query_params.get("state") or "/dashboard"

        if error:
            msg = error_description or error or _("Google authentication was cancelled or failed.")
            return HttpResponseRedirect(
                f"{frontend_url}/auth/login?error={urllib.parse.quote(str(msg))}",
            )

        code = request.query_params.get("code")
        if not code:
            return HttpResponseRedirect(
                f"{frontend_url}/auth/login?error=Missing+authorization+code",
            )

        callback_uri = request.build_absolute_uri(request.path)
        user_info, err_resp = _exchange_google_code(code, callback_uri)
        if err_resp or not user_info:
            err_msg = "Failed to exchange authorization code with Google."
            if err_resp and isinstance(err_resp.data, dict) and "error" in err_resp.data:
                err_msg = str(err_resp.data["error"])
            return HttpResponseRedirect(
                f"{frontend_url}/auth/login?error={urllib.parse.quote(err_msg)}",
            )

        if not user_info.get("email"):
            return HttpResponseRedirect(
                f"{frontend_url}/auth/login?error=No+email+address+provided+by+Google",
            )

        email_verified = user_info.get("email_verified")
        if isinstance(email_verified, str):
            email_verified = email_verified.lower() in ("true", "1")
        elif email_verified is None:
            email_verified = True

        if not email_verified:
            return HttpResponseRedirect(
                f"{frontend_url}/auth/login?error=Google+account+email+is+not+verified",
            )

        user, _is_new = _provision_google_user(user_info, request)
        tokens = get_tokens_for_user(user)

        target_url = (
            f"{frontend_url}/auth/callback"
            f"?access={urllib.parse.quote(tokens['access'])}"
            f"&refresh={urllib.parse.quote(tokens['refresh'])}"
            f"&next={urllib.parse.quote(next_url)}"
        )
        return HttpResponseRedirect(target_url)



