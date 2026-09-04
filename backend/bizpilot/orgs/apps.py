from __future__ import annotations

from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class OrgsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "bizpilot.orgs"
    verbose_name = _("Organizations & RBAC")
