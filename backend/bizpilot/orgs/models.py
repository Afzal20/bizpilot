from __future__ import annotations

from decimal import Decimal
import secrets
from typing import TYPE_CHECKING
from typing import Any
import uuid

from django.conf import settings
from django.db import models
from django.utils import timezone
from django.utils.text import slugify
from django.utils.translation import gettext_lazy as _

from bizpilot.core.models import TimestampedModel
from bizpilot.core.models import UUIDModel

if TYPE_CHECKING:
    from django.db.models.manager import RelatedManager
    from bizpilot.users.models import User


class Organization(UUIDModel, TimestampedModel):
    """Business organization / company entity scoping all business and operational data."""

    name = models.CharField(_("organization name"), max_length=255)
    slug = models.SlugField(_("slug"), max_length=255, unique=True, blank=True)
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="owned_organizations",
        verbose_name=_("owner"),
    )
    logo_url = models.CharField(_("logo URL"), max_length=1024, blank=True, default="")
    website = models.CharField(_("website"), max_length=500, blank=True, default="")
    company_email = models.EmailField(_("company email"), blank=True, default="")
    company_address = models.TextField(_("company address"), blank=True, default="")
    company_phone = models.CharField(
        _("company phone"),
        max_length=50,
        blank=True,
        default="",
    )
    default_currency = models.CharField(
        _("default currency"),
        max_length=3,
        default="USD",
    )
    default_tax_rate = models.DecimalField(
        _("default tax rate"),
        max_digits=5,
        decimal_places=2,
        default=Decimal("0.00"),
    )
    default_notes = models.TextField(_("default invoice notes"), blank=True, default="")
    default_terms = models.TextField(_("default invoice terms"), blank=True, default="")

    stripe_customer_id = models.CharField(
        _("Stripe customer ID"),
        max_length=255,
        blank=True,
        null=True,
        db_index=True,
    )
    stripe_subscription_id = models.CharField(
        _("Stripe subscription ID"),
        max_length=255,
        blank=True,
        null=True,
    )
    is_active = models.BooleanField(_("is active"), default=True)

    if TYPE_CHECKING:
        roles: RelatedManager[Role]
        memberships: RelatedManager[Membership]
        invites: RelatedManager[Invite]

    class Meta:
        verbose_name = _("organization")
        verbose_name_plural = _("organizations")
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return self.name

    def save(self, *args: Any, **kwargs: Any) -> None:
        if not self.slug:
            base_slug = slugify(self.name) or "org"
            candidate = base_slug
            counter = 1
            while (
                Organization.objects.filter(slug=candidate)
                .exclude(pk=self.pk)
                .exists()
            ):
                candidate = f"{base_slug}-{counter}"
                counter += 1
            self.slug = candidate
        super().save(*args, **kwargs)


class Permission(models.Model):
    """Fixed RBAC v2 permission definition representing resource.action capabilities."""

    codename = models.CharField(
        _("codename"),
        max_length=100,
        unique=True,
        db_index=True,
    )
    resource = models.CharField(_("resource"), max_length=50, db_index=True)
    action = models.CharField(_("action"), max_length=50)
    description = models.CharField(_("description"), max_length=255, blank=True, default="")
    created_at = models.DateTimeField(_("created at"), auto_now_add=True)

    if TYPE_CHECKING:
        roles: RelatedManager[Role]

    class Meta:
        verbose_name = _("permission")
        verbose_name_plural = _("permissions")
        ordering = ["resource", "action"]

    def __str__(self) -> str:
        return self.codename


class Role(UUIDModel, TimestampedModel):
    """Organizational role bundling a set of permissions for members."""

    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="roles",
        verbose_name=_("organization"),
    )
    name = models.CharField(_("role name"), max_length=100)
    description = models.TextField(_("description"), blank=True, default="")
    is_system = models.BooleanField(
        _("is system role"),
        default=False,
        help_text=_("Designates whether this is a seeded default system role"),
    )
    permissions = models.ManyToManyField(
        Permission,
        related_name="roles",
        blank=True,
        verbose_name=_("permissions"),
    )

    if TYPE_CHECKING:
        memberships: RelatedManager[Membership]
        invites: RelatedManager[Invite]

    class Meta:
        verbose_name = _("role")
        verbose_name_plural = _("roles")
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "name"],
                name="unique_org_role_name",
            ),
        ]

    def __str__(self) -> str:
        org_prefix = self.organization.name if self.organization else "System Template"
        return f"{self.name} ({org_prefix})"


class Membership(UUIDModel, TimestampedModel):
    """User membership within an organization, linked to one or more roles."""

    class Status(models.TextChoices):
        PENDING = "pending", _("Pending")
        ACTIVE = "active", _("Active")
        INACTIVE = "inactive", _("Inactive")

    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name="memberships",
        verbose_name=_("organization"),
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="memberships",
        verbose_name=_("user"),
    )
    email = models.EmailField(_("email address"), db_index=True)
    name = models.CharField(_("member name"), max_length=255, blank=True, default="")
    department = models.CharField(_("department"), max_length=100, blank=True, default="")
    roles = models.ManyToManyField(
        Role,
        related_name="memberships",
        blank=True,
        verbose_name=_("roles"),
    )
    status = models.CharField(
        _("status"),
        max_length=20,
        choices=Status.choices,
        default=Status.ACTIVE,
    )
    invited_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="sent_memberships",
        verbose_name=_("invited by"),
    )
    invited_at = models.DateTimeField(_("invited at"), default=timezone.now)
    joined_at = models.DateTimeField(_("joined at"), null=True, blank=True)

    class Meta:
        verbose_name = _("membership")
        verbose_name_plural = _("memberships")
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "email"],
                name="unique_org_member_email",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.email} - {self.organization.name} ({self.status})"

    @property
    def is_owner(self) -> bool:
        """Check if member has the owner role or is the organization owner."""
        if self.user_id and self.organization.owner_id == self.user_id:
            return True
        return self.roles.filter(name="owner").exists()


class Invite(UUIDModel, TimestampedModel):
    """Cryptographically tokenized invitation for onboarding members to an organization."""

    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name="invites",
        verbose_name=_("organization"),
    )
    email = models.EmailField(_("invited email"), db_index=True)
    roles = models.ManyToManyField(
        Role,
        related_name="invites",
        blank=True,
        verbose_name=_("roles"),
    )
    department = models.CharField(_("department"), max_length=100, blank=True, default="")
    invited_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="created_invites",
        verbose_name=_("invited by"),
    )
    token = models.CharField(_("invitation token"), max_length=64, unique=True, db_index=True)
    expires_at = models.DateTimeField(_("expires at"))
    accepted_at = models.DateTimeField(_("accepted at"), null=True, blank=True)

    class Meta:
        verbose_name = _("invite")
        verbose_name_plural = _("invites")
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"Invite for {self.email} to {self.organization.name}"

    @property
    def is_expired(self) -> bool:
        return timezone.now() > self.expires_at

    @property
    def is_valid(self) -> bool:
        return self.accepted_at is None and not self.is_expired

    @classmethod
    def generate_token(cls) -> str:
        return secrets.token_urlsafe(32)
