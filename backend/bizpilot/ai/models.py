from __future__ import annotations

import uuid
from decimal import Decimal

from django.db import models
from django.utils.translation import gettext_lazy as _


class AILog(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        "orgs.Organization",
        on_delete=models.CASCADE,
        related_name="ai_logs",
        verbose_name=_("organization"),
    )
    user = models.ForeignKey(
        "users.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="ai_logs",
        verbose_name=_("user"),
    )
    feature = models.CharField(_("feature"), max_length=100)
    model = models.CharField(_("model"), max_length=255)
    prompt_tokens = models.PositiveIntegerField(
        _("prompt tokens"),
        default=0,
    )
    completion_tokens = models.PositiveIntegerField(
        _("completion tokens"),
        default=0,
    )
    latency_ms = models.PositiveIntegerField(_("latency (ms)"), default=0)
    cost_estimate = models.DecimalField(
        _("cost estimate"),
        max_digits=8,
        decimal_places=6,
        default=Decimal("0.000000"),
    )
    created_at = models.DateTimeField(_("created at"), auto_now_add=True)

    class Meta:
        verbose_name = _("AI Log")
        verbose_name_plural = _("AI Logs")
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.organization.name} - {self.feature} ({self.created_at})"
