from __future__ import annotations

from typing import Any

from rest_framework import serializers

from bizpilot.ai.models import AILog


def _clean_history(value: list[Any]) -> list[dict[str, str]]:
    """Keep only valid user/assistant turns."""
    cleaned: list[dict[str, str]] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        role = str(item.get("role", ""))
        content = str(item.get("content", ""))
        if role in ("user", "assistant") and content:
            cleaned.append({"role": role, "content": content})
    return cleaned


class GenerateInvoiceItemsSerializer(serializers.Serializer):
    prompt = serializers.CharField(min_length=4, max_length=600)
    currency = serializers.CharField(
        max_length=10,
        required=False,
        allow_blank=True,
    )


class AskBizPilotSerializer(serializers.Serializer):
    question = serializers.CharField(min_length=1, max_length=2000)
    stream = serializers.BooleanField(default=False, required=False)
    history = serializers.ListField(
        child=serializers.DictField(),
        required=False,
        default=list,
    )

    def validate_history(self, value: list[Any]) -> list[dict[str, str]]:
        return _clean_history(value)


class AgentSerializer(serializers.Serializer):
    instruction = serializers.CharField(min_length=1, max_length=2000)
    confirm = serializers.BooleanField(default=False, required=False)
    history = serializers.ListField(
        child=serializers.DictField(),
        required=False,
        default=list,
    )

    def validate_history(self, value: list[Any]) -> list[dict[str, str]]:
        return _clean_history(value)


class CategorizeExpenseSerializer(serializers.Serializer):
    title = serializers.CharField(max_length=255)
    description = serializers.CharField(
        required=False,
        allow_blank=True,
        default="",
    )


class DraftPaymentReminderSerializer(serializers.Serializer):
    invoice_id = serializers.UUIDField()
    tone = serializers.ChoiceField(
        choices=["friendly", "firm", "urgent"],
        default="friendly",
    )


class AILogSerializer(serializers.ModelSerializer):
    class Meta:
        model = AILog
        fields = [
            "id",
            "organization",
            "user",
            "feature",
            "model",
            "prompt_tokens",
            "completion_tokens",
            "latency_ms",
            "cost_estimate",
            "created_at",
        ]
        read_only_fields = fields
