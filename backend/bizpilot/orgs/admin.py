from __future__ import annotations

from django.contrib import admin
from unfold.admin import ModelAdmin
from unfold.admin import TabularInline

from bizpilot.orgs.models import Invite
from bizpilot.orgs.models import Membership
from bizpilot.orgs.models import Organization
from bizpilot.orgs.models import Permission
from bizpilot.orgs.models import Role


class MembershipInline(TabularInline):
    model = Membership
    extra = 0
    fields = ["user", "email", "name", "department", "status"]
    readonly_fields = ["created_at"]


class RoleInline(TabularInline):
    model = Role
    extra = 0
    fields = ["name", "is_system", "description"]


@admin.register(Organization)
class OrganizationAdmin(ModelAdmin):
    list_display = [
        "name",
        "slug",
        "owner",
        "default_currency",
        "is_active",
        "created_at",
    ]
    search_fields = ["name", "slug", "owner__email", "company_email"]
    list_filter = ["is_active", "default_currency", "created_at"]
    inlines = [MembershipInline, RoleInline]


@admin.register(Permission)
class PermissionAdmin(ModelAdmin):
    list_display = ["codename", "resource", "action", "description"]
    search_fields = ["codename", "resource", "action", "description"]
    list_filter = ["resource"]


@admin.register(Role)
class RoleAdmin(ModelAdmin):
    list_display = ["name", "organization", "is_system", "created_at"]
    search_fields = ["name", "organization__name"]
    list_filter = ["is_system", "created_at"]
    filter_horizontal = ["permissions"]


@admin.register(Membership)
class MembershipAdmin(ModelAdmin):
    list_display = ["email", "name", "organization", "status", "created_at"]
    search_fields = ["email", "name", "organization__name"]
    list_filter = ["status", "created_at"]
    filter_horizontal = ["roles"]


@admin.register(Invite)
class InviteAdmin(ModelAdmin):
    list_display = ["email", "organization", "invited_by", "expires_at", "accepted_at"]
    search_fields = ["email", "organization__name", "token"]
    list_filter = ["expires_at", "accepted_at"]
    filter_horizontal = ["roles"]
