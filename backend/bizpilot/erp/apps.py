from __future__ import annotations

from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class ErpConfig(AppConfig):
    name = "bizpilot.erp"
    verbose_name = _("ERP")

    def ready(self) -> None:
        pass
