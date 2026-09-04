from __future__ import annotations

import uuid
from typing import TYPE_CHECKING
from typing import Any

from bizpilot.core.models import AuditLog

if TYPE_CHECKING:
    from rest_framework import serializers


def get_client_ip(request: Any) -> str | None:
    """Extract client IP address from HTTP headers."""
    if not request:
        return None
    x_forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
    if x_forwarded_for:
        return x_forwarded_for.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR")


def log_audit_event(
    request: Any,
    action: str,
    target: Any,
    changes_diff: dict[str, Any] | None = None,
    organization_id: uuid.UUID | str | None = None,
) -> AuditLog:
    """Record an entry in the audit log."""
    user = getattr(request, "user", None)
    actor = user if (user and user.is_authenticated) else None
    actor_email = actor.email if actor else ""

    # Determine organization_id if not explicitly provided
    resolved_org_id = organization_id
    if resolved_org_id is None and hasattr(target, "organization_id"):
        resolved_org_id = target.organization_id
    elif resolved_org_id is None and hasattr(target, "organization"):
        org_obj = target.organization
        resolved_org_id = getattr(org_obj, "id", None)
    elif resolved_org_id is None and request and hasattr(request, "parser_context"):
        kwargs = request.parser_context.get("kwargs", {})
        resolved_org_id = kwargs.get("org_id")

    # Coerce to UUID string or UUID object if applicable
    if isinstance(resolved_org_id, str):
        try:
            resolved_org_id = uuid.UUID(resolved_org_id)
        except ValueError:
            resolved_org_id = None

    if hasattr(target, "_meta"):
        target_model = target._meta.label  # noqa: SLF001
    else:
        target_model = target.__class__.__name__
    target_id = str(getattr(target, "pk", getattr(target, "id", "")))

    user_agent = ""
    ip_addr = None
    if request:
        user_agent = str(request.META.get("HTTP_USER_AGENT", ""))[:500]
        ip_addr = get_client_ip(request)

    return AuditLog.objects.create(
        organization_id=resolved_org_id,
        actor=actor,
        actor_email=actor_email,
        action=action,
        target_model=target_model,
        target_id=target_id,
        changes_diff=changes_diff or {},
        ip_address=ip_addr,
        user_agent=user_agent,
    )


class AuditLogMixin:
    """ViewSet mixin that logs create, update, and delete actions automatically."""

    def perform_create(self, serializer: serializers.BaseSerializer) -> None:
        instance = serializer.save()
        log_audit_event(
            request=self.request,  # type: ignore[attr-defined]
            action="create",
            target=instance,
            changes_diff=getattr(serializer, "validated_data", {}),
        )

    def perform_update(self, serializer: serializers.BaseSerializer) -> None:
        instance = serializer.save()
        log_audit_event(
            request=self.request,  # type: ignore[attr-defined]
            action="update",
            target=instance,
            changes_diff=getattr(serializer, "validated_data", {}),
        )

    def perform_destroy(self, instance: Any) -> None:
        log_audit_event(
            request=self.request,  # type: ignore[attr-defined]
            action="delete",
            target=instance,
        )
        instance.delete()
