from __future__ import annotations

from rest_framework import serializers

from bizpilot.billing.models import Plan
from bizpilot.billing.models import PlanEntitlement
from bizpilot.billing.models import PriceMapping
from bizpilot.billing.models import Subscription


class PlanEntitlementSerializer(serializers.ModelSerializer):
    class Meta:
        model = PlanEntitlement
        fields = ["id", "key", "value"]


class PriceMappingSerializer(serializers.ModelSerializer):
    class Meta:
        model = PriceMapping
        fields = [
            "id",
            "stripe_price_id",
            "interval",
            "amount",
            "currency",
            "is_active",
        ]


class PlanSerializer(serializers.ModelSerializer):
    entitlements = PlanEntitlementSerializer(many=True, read_only=True)
    prices = PriceMappingSerializer(many=True, read_only=True)

    class Meta:
        model = Plan
        fields = [
            "id",
            "code",
            "name",
            "description",
            "tier",
            "trial_days",
            "is_active",
            "entitlements",
            "prices",
        ]


class SubscriptionSerializer(serializers.ModelSerializer):
    plan = PlanSerializer(read_only=True)

    class Meta:
        model = Subscription
        fields = [
            "id",
            "organization",
            "plan",
            "status",
            "trial_start",
            "trial_end",
            "current_period_start",
            "current_period_end",
            "cancel_at_period_end",
            "created_at",
        ]
        read_only_fields = fields


class CheckoutRequestSerializer(serializers.Serializer):
    price_id = serializers.CharField(max_length=255)
    success_url = serializers.URLField()
    cancel_url = serializers.URLField()


class PortalRequestSerializer(serializers.Serializer):
    return_url = serializers.URLField()
