from __future__ import annotations

from django.contrib import admin

from bizpilot.billing.models import Plan
from bizpilot.billing.models import PlanEntitlement
from bizpilot.billing.models import PriceMapping
from bizpilot.billing.models import StripeEvent
from bizpilot.billing.models import Subscription
from bizpilot.billing.models import UsageCounter


class PlanEntitlementInline(admin.TabularInline):
    model = PlanEntitlement
    extra = 0


@admin.register(Plan)
class PlanAdmin(admin.ModelAdmin):
    list_display = ["name", "code", "tier", "trial_days", "is_active"]
    list_filter = ["is_active", "tier"]
    search_fields = ["name", "code"]
    inlines = [PlanEntitlementInline]


@admin.register(Subscription)
class SubscriptionAdmin(admin.ModelAdmin):
    list_display = [
        "organization",
        "plan",
        "status",
        "current_period_end",
        "cancel_at_period_end",
    ]
    list_filter = ["status", "plan", "cancel_at_period_end"]
    search_fields = ["organization__name", "stripe_customer_id"]


@admin.register(PriceMapping)
class PriceMappingAdmin(admin.ModelAdmin):
    list_display = [
        "plan",
        "stripe_price_id",
        "interval",
        "amount",
        "currency",
        "is_active",
    ]
    list_filter = ["interval", "currency", "is_active"]


@admin.register(UsageCounter)
class UsageCounterAdmin(admin.ModelAdmin):
    list_display = ["organization", "key", "count", "period_start"]
    list_filter = ["key", "period_start"]
    search_fields = ["organization__name"]


@admin.register(StripeEvent)
class StripeEventAdmin(admin.ModelAdmin):
    list_display = ["stripe_event_id", "event_type", "processed", "created_at"]
    list_filter = ["processed", "event_type"]
    search_fields = ["stripe_event_id"]
