from __future__ import annotations

import uuid

from django.conf import settings
from django.core.serializers.json import DjangoJSONEncoder
from django.db import models
from django.utils.translation import gettext_lazy as _


class TimestampedModel(models.Model):
    """Abstract model providing automatic timestamp tracking."""

    created_at = models.DateTimeField(
        _("created at"),
        auto_now_add=True,
        db_index=True,
    )
    updated_at = models.DateTimeField(
        _("updated at"),
        auto_now=True,
    )

    class Meta:
        abstract = True


class UUIDModel(models.Model):
    """Abstract model providing a UUID primary key."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    class Meta:
        abstract = True


class AuditLog(models.Model):
    """Audit trail for recording user and system actions across organizations."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization_id = models.UUIDField(
        _("organization id"),
        null=True,
        blank=True,
        db_index=True,
    )
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="audit_logs",
        verbose_name=_("actor"),
    )
    actor_email = models.EmailField(_("actor email"), blank=True)
    action = models.CharField(_("action"), max_length=64, db_index=True)
    target_model = models.CharField(_("target model"), max_length=128, db_index=True)
    target_id = models.CharField(_("target id"), max_length=128, db_index=True)
    changes_diff = models.JSONField(
        _("changes diff"),
        default=dict,
        blank=True,
        encoder=DjangoJSONEncoder,
    )
    ip_address = models.GenericIPAddressField(_("ip address"), null=True, blank=True)
    user_agent = models.CharField(_("user agent"), max_length=512, blank=True)
    created_at = models.DateTimeField(_("created at"), auto_now_add=True, db_index=True)

    class Meta:
        verbose_name = _("audit log")
        verbose_name_plural = _("audit logs")
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["organization_id", "-created_at"]),
            models.Index(fields=["target_model", "target_id"]),
        ]

    def __str__(self) -> str:
        actor_repr = self.actor_email or (self.actor.email if self.actor else "system")
        return f"[{self.action}] {self.target_model}:{self.target_id} by {actor_repr}"
