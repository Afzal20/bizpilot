from __future__ import annotations

from rest_framework import serializers

from bizpilot.ai.models import AILog


class GenerateInvoiceItemsSerializer(serializers.Serializer):
    prompt = serializers.CharField(min_length=4, max_length=600)
    currency = serializers.CharField(
        max_length=10,
        required=False,
        allow_blank=True,
    )


class AskBizPilotSerializer(serializers.Serializer):
    question = serializers.CharField(min_length=1, max_length=500)
    stream = serializers.BooleanField(default=False, required=False)


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
