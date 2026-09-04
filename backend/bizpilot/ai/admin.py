from __future__ import annotations

from django.contrib import admin

from bizpilot.ai.models import AILog


@admin.register(AILog)
class AILogAdmin(admin.ModelAdmin):
    list_display = [
        "organization",
        "feature",
        "model",
        "prompt_tokens",
        "completion_tokens",
        "latency_ms",
        "created_at",
    ]
    list_filter = ["feature", "model", "created_at"]
    search_fields = ["organization__name", "feature"]
