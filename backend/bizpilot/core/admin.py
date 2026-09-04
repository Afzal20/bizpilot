from django.contrib import admin
from unfold.admin import ModelAdmin

from bizpilot.core.models import AuditLog


@admin.register(AuditLog)
class AuditLogAdmin(ModelAdmin):
    list_display = [
        "action",
        "target_model",
        "target_id",
        "actor_email",
        "organization_id",
        "created_at",
    ]
    list_filter = ["action", "target_model", "created_at"]
    search_fields = ["target_model", "target_id", "actor_email", "action"]
    readonly_fields = [
        "id",
        "organization_id",
        "actor",
        "actor_email",
        "action",
        "target_model",
        "target_id",
        "changes_diff",
        "ip_address",
        "user_agent",
        "created_at",
    ]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
