from __future__ import annotations

import uuid
from decimal import Decimal

from django.db import models
from django.utils.translation import gettext_lazy as _


class Plan(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    code = models.CharField(_("code"), max_length=50, unique=True)
    name = models.CharField(_("name"), max_length=100)
    description = models.TextField(_("description"), blank=True, default="")
    stripe_product_id = models.CharField(
        _("Stripe Product ID"),
        max_length=255,
        blank=True,
        default="",
    )
    tier = models.PositiveSmallIntegerField(_("tier"), default=0)
    trial_days = models.PositiveIntegerField(_("trial days"), default=14)
    is_active = models.BooleanField(_("active"), default=True)
    created_at = models.DateTimeField(_("created at"), auto_now_add=True)
    updated_at = models.DateTimeField(_("updated at"), auto_now=True)

    class Meta:
        verbose_name = _("plan")
        verbose_name_plural = _("plans")
        ordering = ["tier"]

    def __str__(self) -> str:
        return f"{self.name} ({self.code})"


class PlanEntitlement(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    plan = models.ForeignKey(
        Plan,
        on_delete=models.CASCADE,
        related_name="entitlements",
        verbose_name=_("plan"),
    )
    key = models.CharField(_("key"), max_length=100)
    value = models.JSONField(_("value"), default=dict)
    created_at = models.DateTimeField(_("created at"), auto_now_add=True)
    updated_at = models.DateTimeField(_("updated at"), auto_now=True)

    class Meta:
        verbose_name = _("plan entitlement")
        verbose_name_plural = _("plan entitlements")
        constraints = [
            models.UniqueConstraint(
                fields=["plan", "key"],
                name="unique_plan_entitlement",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.plan.code} - {self.key}: {self.value}"


class Subscription(models.Model):
    class Status(models.TextChoices):
        TRIALING = "trialing", _("Trialing")
        ACTIVE = "active", _("Active")
        PAST_DUE = "past_due", _("Past Due")
        CANCELED = "canceled", _("Canceled")
        INCOMPLETE = "incomplete", _("Incomplete")
        PAUSED = "paused", _("Paused")

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.OneToOneField(
        "orgs.Organization",
        on_delete=models.CASCADE,
        related_name="subscription",
        verbose_name=_("organization"),
    )
    plan = models.ForeignKey(
        Plan,
        on_delete=models.PROTECT,
        related_name="subscriptions",
        verbose_name=_("plan"),
    )
    stripe_customer_id = models.CharField(
        _("Stripe Customer ID"),
        max_length=255,
        blank=True,
        default="",
    )
    stripe_subscription_id = models.CharField(
        _("Stripe Subscription ID"),
        max_length=255,
        blank=True,
        default="",
    )
    status = models.CharField(
        _("status"),
        max_length=30,
        choices=Status.choices,
        default=Status.TRIALING,
    )
    trial_start = models.DateTimeField(
        _("trial start"),
        null=True,
        blank=True,
    )
    trial_end = models.DateTimeField(
        _("trial end"),
        null=True,
        blank=True,
    )
    current_period_start = models.DateTimeField(
        _("current period start"),
        null=True,
        blank=True,
    )
    current_period_end = models.DateTimeField(
        _("current period end"),
        null=True,
        blank=True,
    )
    cancel_at_period_end = models.BooleanField(
        _("cancel at period end"),
        default=False,
    )
    pending_plan = models.ForeignKey(
        Plan,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="pending_subscriptions",
        verbose_name=_("pending plan"),
    )
    created_at = models.DateTimeField(_("created at"), auto_now_add=True)
    updated_at = models.DateTimeField(_("updated at"), auto_now=True)

    class Meta:
        verbose_name = _("subscription")
        verbose_name_plural = _("subscriptions")

    def __str__(self) -> str:
        return f"{self.organization.name} - {self.plan.name} ({self.status})"

    @property
    def is_usable(self) -> bool:
        """True if org subscription allows write actions."""
        return self.status in (self.Status.TRIALING, self.Status.ACTIVE)


class PriceMapping(models.Model):
    class Interval(models.TextChoices):
        MONTH = "month", _("Month")
        YEAR = "year", _("Year")

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    plan = models.ForeignKey(
        Plan,
        on_delete=models.CASCADE,
        related_name="prices",
        verbose_name=_("plan"),
    )
    stripe_price_id = models.CharField(
        _("Stripe Price ID"),
        max_length=255,
        unique=True,
    )
    interval = models.CharField(
        _("interval"),
        max_length=20,
        choices=Interval.choices,
        default=Interval.MONTH,
    )
    amount = models.DecimalField(
        _("amount"),
        max_digits=10,
        decimal_places=2,
        default=Decimal("0.00"),
    )
    currency = models.CharField(_("currency"), max_length=10, default="USD")
    is_active = models.BooleanField(_("active"), default=True)
    created_at = models.DateTimeField(_("created at"), auto_now_add=True)
    updated_at = models.DateTimeField(_("updated at"), auto_now=True)

    class Meta:
        verbose_name = _("price mapping")
        verbose_name_plural = _("price mappings")

    def __str__(self) -> str:
        return (
            f"{self.plan.name} - {self.amount} {self.currency}/{self.interval}"
        )


class UsageCounter(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        "orgs.Organization",
        on_delete=models.CASCADE,
        related_name="usage_counters",
        verbose_name=_("organization"),
    )
    key = models.CharField(_("key"), max_length=100)
    period_start = models.DateField(_("period start"))
    count = models.PositiveIntegerField(_("count"), default=0)
    created_at = models.DateTimeField(_("created at"), auto_now_add=True)
    updated_at = models.DateTimeField(_("updated at"), auto_now=True)

    class Meta:
        verbose_name = _("usage counter")
        verbose_name_plural = _("usage counters")
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "key", "period_start"],
                name="unique_org_usage_counter_period",
            ),
        ]

    def __str__(self) -> str:
        name = self.organization.name
        return f"{name} - {self.key}: {self.count} ({self.period_start})"


class StripeEvent(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    stripe_event_id = models.CharField(
        _("Stripe Event ID"),
        max_length=255,
        unique=True,
        db_index=True,
    )
    event_type = models.CharField(_("event type"), max_length=100)
    payload = models.JSONField(_("payload"), default=dict)
    processed = models.BooleanField(_("processed"), default=False)
    processed_at = models.DateTimeField(
        _("processed at"),
        null=True,
        blank=True,
    )
    error_message = models.TextField(_("error message"), blank=True, default="")
    created_at = models.DateTimeField(_("created at"), auto_now_add=True)

    class Meta:
        verbose_name = _("Stripe event")
        verbose_name_plural = _("Stripe events")
        ordering = ["-created_at"]

    def __str__(self) -> str:
        status_str = f"processed={self.processed}"
        return f"{self.event_type} - {self.stripe_event_id} ({status_str})"
