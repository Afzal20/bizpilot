from __future__ import annotations

from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView
from rest_framework_simplejwt.views import TokenVerifyView

from .views import ClaimPendingInvitesView
from .views import LoginView
from .views import LogoutView
from .views import MeView
from .views import PasswordResetConfirmView
from .views import PasswordResetRequestView
from .views import ProfileView
from .views import SignupView

app_name = "auth_api"

auth_patterns = [
    path("signup/", SignupView.as_view(), name="signup"),
    path("login/", LoginView.as_view(), name="login"),
    path("logout/", LogoutView.as_view(), name="logout"),
    path("refresh/", TokenRefreshView.as_view(), name="token-refresh"),
    path("verify/", TokenVerifyView.as_view(), name="token-verify"),
    path("password/reset/", PasswordResetRequestView.as_view(), name="password-reset"),
    path(
        "password/reset/confirm/",
        PasswordResetConfirmView.as_view(),
        name="password-reset-confirm",
    ),
    path("invites/claim/", ClaimPendingInvitesView.as_view(), name="invites-claim"),
]

me_patterns = [
    path("me/", MeView.as_view(), name="me"),
    path("me/profile/", ProfileView.as_view(), name="me-profile"),
]
