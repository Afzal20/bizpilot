from __future__ import annotations

from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class AiConfig(AppConfig):
    name = "bizpilot.ai"
    verbose_name = _("AI Platform")

    def ready(self) -> None:
        pass
