from __future__ import annotations

from django.urls import include
from django.urls import path
from rest_framework.routers import DefaultRouter
from rest_framework.routers import SimpleRouter

from bizpilot.orgs.api.views import InviteAcceptView
from bizpilot.orgs.api.views import InviteViewSet
from bizpilot.orgs.api.views import MembershipViewSet
from bizpilot.orgs.api.views import MyPermissionsView
from bizpilot.orgs.api.views import OrganizationViewSet
from bizpilot.orgs.api.views import PermissionListView
from bizpilot.orgs.api.views import RoleViewSet

app_name = "orgs"

router = SimpleRouter()
router.register("orgs", OrganizationViewSet, basename="org")

# Org-scoped routers
members_router = SimpleRouter()
members_router.register("members", MembershipViewSet, basename="org-members")

roles_router = SimpleRouter()
roles_router.register("roles", RoleViewSet, basename="org-roles")

invites_router = SimpleRouter()
invites_router.register("invites", InviteViewSet, basename="org-invites")

urlpatterns = [
    # General org CRUD
    path("", include(router.urls)),
    # Accept invitation
    path("orgs/invites/accept/", InviteAcceptView.as_view(), name="invite-accept"),
    # Global permission catalog
    path("permissions/", PermissionListView.as_view(), name="permission-list"),
    # User's effective permissions for an organization
    path("me/permissions/", MyPermissionsView.as_view(), name="my-permissions"),
    # Org-scoped sub-resources
    path("orgs/<uuid:org_id>/", include(members_router.urls)),
    path("orgs/<uuid:org_id>/", include(roles_router.urls)),
    path("orgs/<uuid:org_id>/", include(invites_router.urls)),
    path(
        "orgs/<uuid:org_id>/permissions/",
        PermissionListView.as_view(),
        name="org-permissions",
    ),
]
