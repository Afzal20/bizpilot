from __future__ import annotations

from typing import TYPE_CHECKING
from typing import Any
from typing import ClassVar

from django.contrib.auth.models import AbstractUser
from django.db import models
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.urls import reverse
from django.utils.translation import gettext_lazy as _

from .managers import UserManager


class User(AbstractUser):
    """
    Default custom user model for BizPilot.
    If adding fields that need to be filled at user signup,
    check forms.SignupForm and forms.SocialSignupForms accordingly.
    """

    if TYPE_CHECKING:
        id: int
        pk: int
        profile: Profile
        memberships: Any

    # First and last name do not cover name patterns around the globe
    name = models.CharField(_("Name of User"), blank=True, max_length=255)
    first_name = None  # type: ignore[assignment]
    last_name = None  # type: ignore[assignment]
    email = models.EmailField(_("email address"), unique=True)
    username = None  # type: ignore[assignment]

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = []

    objects: ClassVar[UserManager] = UserManager()

    def get_absolute_url(self) -> str:
        """Get URL for user's detail view.

        Returns:
            str: URL for user detail.

        """
        return reverse("users:detail", kwargs={"pk": self.id})


class Profile(models.Model):
    """User profile extending User with company defaults and preferences."""

    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name="profile",
        verbose_name=_("user"),
    )
    full_name = models.CharField(
        _("Full Name"),
        max_length=255,
        blank=True,
        default="",
    )
    avatar_url = models.URLField(
        _("Avatar URL"),
        max_length=1024,
        blank=True,
        default="",
    )
    company_name = models.CharField(
        _("Company Name"),
        max_length=255,
        blank=True,
        default="",
    )
    company_email = models.EmailField(
        _("Company Email"),
        blank=True,
        default="",
    )
    company_address = models.TextField(
        _("Company Address"),
        blank=True,
        default="",
    )
    company_phone = models.CharField(
        _("Company Phone"),
        max_length=50,
        blank=True,
        default="",
    )
    default_currency = models.CharField(
        _("Default Currency"),
        max_length=10,
        default="USD",
    )
    default_tax_rate = models.DecimalField(
        _("Default Tax Rate"),
        max_digits=5,
        decimal_places=2,
        default=0.00,
    )
    default_notes = models.TextField(
        _("Default Notes"),
        blank=True,
        default="",
    )
    default_terms = models.TextField(
        _("Default Terms"),
        blank=True,
        default="",
    )
    created_at = models.DateTimeField(
        _("created at"),
        auto_now_add=True,
    )
    updated_at = models.DateTimeField(
        _("updated at"),
        auto_now=True,
    )

    class Meta:
        verbose_name = _("profile")
        verbose_name_plural = _("profiles")

    def __str__(self) -> str:
        return f"Profile for {self.user.email}"


@receiver(post_save, sender=User)
def create_or_update_user_profile(sender, instance, created, **kwargs):
    """Ensure every user has an associated profile upon creation."""
    if created:
        Profile.objects.get_or_create(
            user=instance,
            defaults={"full_name": instance.name or ""},
        )
