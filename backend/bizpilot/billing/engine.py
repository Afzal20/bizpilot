from __future__ import annotations

from typing import TYPE_CHECKING
from typing import Any

from django.conf import settings
from django.core.cache import cache
from django.utils import timezone
from rest_framework import status
from rest_framework.exceptions import APIException
from rest_framework.exceptions import PermissionDenied

from decimal import Decimal

from bizpilot.billing.models import Plan
from bizpilot.billing.models import PlanEntitlement
from bizpilot.billing.models import PriceMapping
from bizpilot.billing.models import Subscription
from bizpilot.billing.models import UsageCounter

if TYPE_CHECKING:
    import datetime

    from bizpilot.orgs.models import Organization

UNLIMITED = -1
ENTITLEMENT_CACHE_TTL = 60

ENTITLEMENT_CATALOG: dict[str, dict[str, Any]] = {
    "free": {
        "max_invoices_per_month": 10,
        "max_clients": 5,
        "max_products": 10,
        "max_team_members": 1,
        "max_organizations": 1,
        "ai_credits_per_month": 25,
        "recurring_invoices": False,
        "email_invoice_delivery": False,
        "client_portal": False,
        "data_export": False,
        "custom_roles": False,
        "audit_log": False,
    },
    "pro": {
        "max_invoices_per_month": 500,
        "max_clients": 200,
        "max_products": 1000,
        "max_team_members": 10,
        "max_organizations": 3,
        "ai_credits_per_month": 500,
        "recurring_invoices": True,
        "email_invoice_delivery": True,
        "client_portal": True,
        "data_export": True,
        "custom_roles": False,
        "audit_log": True,
    },
    "enterprise": {
        "max_invoices_per_month": UNLIMITED,
        "max_clients": UNLIMITED,
        "max_products": UNLIMITED,
        "max_team_members": UNLIMITED,
        "max_organizations": UNLIMITED,
        "ai_credits_per_month": 5000,
        "recurring_invoices": True,
        "email_invoice_delivery": True,
        "client_portal": True,
        "data_export": True,
        "custom_roles": True,
        "audit_log": True,
    },
}


class FeatureNotAvailable(PermissionDenied):
    status_code = status.HTTP_403_FORBIDDEN
    default_detail = (
        "This feature is not available on your current plan. Please upgrade."
    )
    default_code = "feature_not_available"


class PlanLimitExceeded(APIException):
    status_code = status.HTTP_402_PAYMENT_REQUIRED
    default_detail = "You have reached your plan limit. Please upgrade."
    default_code = "plan_limit_exceeded"


def seed_default_plans() -> None:
    """Seed Free, Pro, and Enterprise plans with entitlements."""
    plans_data = [
        {"code": "free", "name": "Free", "tier": 0, "trial_days": 0},
        {"code": "pro", "name": "Pro", "tier": 1, "trial_days": 14},
        {
            "code": "enterprise",
            "name": "Enterprise",
            "tier": 2,
            "trial_days": 14,
        },
    ]

    for p_data in plans_data:
        plan, _ = Plan.objects.get_or_create(
            code=p_data["code"],
            defaults={
                "name": p_data["name"],
                "tier": p_data["tier"],
                "trial_days": p_data["trial_days"],
                "is_active": True,
            },
        )
        catalog = ENTITLEMENT_CATALOG.get(plan.code, {})
        for key, val in catalog.items():
            PlanEntitlement.objects.update_or_create(
                plan=plan,
                key=key,
                defaults={"value": {"value": val}},
            )

        if plan.code == "pro":
            pro_price_id = getattr(settings, "STRIPE_PRO_PRICE_ID", "")
            if pro_price_id:
                PriceMapping.objects.update_or_create(
                    stripe_price_id=pro_price_id,
                    defaults={
                        "plan": plan,
                        "interval": PriceMapping.Interval.MONTH,
                        "amount": Decimal("9.00"),
                        "currency": "USD",
                        "is_active": True,
                    },
                )
            pro_yearly_id = getattr(settings, "STRIPE_PRO_YEARLY_PRICE_ID", "") or "price_1UBHQeLoTyOsviCMGed4mMyp"
            if pro_yearly_id:
                PriceMapping.objects.update_or_create(
                    stripe_price_id=pro_yearly_id,
                    defaults={
                        "plan": plan,
                        "interval": PriceMapping.Interval.YEAR,
                        "amount": Decimal("90.00"),
                        "currency": "USD",
                        "is_active": True,
                    },
                )


def get_or_create_free_subscription(organization: Organization) -> Subscription:
    """Ensure an organization has a subscription, defaulting to Free."""
    sub = (
        Subscription.objects.select_related("plan")
        .filter(organization=organization)
        .first()
    )
    if sub:
        return sub

    free_plan = Plan.objects.filter(code="free").first()
    if not free_plan:
        seed_default_plans()
        free_plan = Plan.objects.get(code="free")

    return Subscription.objects.create(
        organization=organization,
        plan=free_plan,
        status=Subscription.Status.ACTIVE,
    )


def get_org_entitlement(organization: Organization, key: str) -> Any:
    """Retrieve an entitlement value for an organization with Redis/memory cache."""
    cache_key = f"org_entitlement:{organization.id}:{key}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    sub = get_or_create_free_subscription(organization)
    entitlement = PlanEntitlement.objects.filter(
        plan=sub.plan,
        key=key,
    ).first()

    if entitlement and "value" in entitlement.value:
        val = entitlement.value["value"]
    else:
        # Fallback to catalog
        catalog = ENTITLEMENT_CATALOG.get(sub.plan.code, {})
        val = catalog.get(key)

    cache.set(cache_key, val, timeout=ENTITLEMENT_CACHE_TTL)
    return val


def allow(organization: Organization, key: str) -> bool:
    """Verify boolean feature entitlement. Raises FeatureNotAvailable if denied."""
    if not getattr(settings, "BILLING_ENFORCEMENT", False):
        return True

    val = get_org_entitlement(organization, key)
    if bool(val):
        return True

    msg = f"Feature '{key}' is not available on your plan. Please upgrade."
    raise FeatureNotAvailable(msg)


def _get_current_usage_count(
    organization: Organization,
    key: str,
    now: datetime.datetime,
) -> int:
    """Calculate current metric usage for an organization."""
    if key == "max_invoices_per_month":
        from bizpilot.erp.models import Invoice  # noqa: PLC0415

        start_of_month = now.replace(
            day=1,
            hour=0,
            minute=0,
            second=0,
            microsecond=0,
        )
        return Invoice.objects.filter(
            organization=organization,
            created_at__gte=start_of_month,
        ).count()

    if key == "max_clients":
        from bizpilot.erp.models import Client  # noqa: PLC0415

        return Client.objects.filter(organization=organization).count()

    if key == "max_products":
        from bizpilot.erp.models import Product  # noqa: PLC0415

        return Product.objects.filter(organization=organization).count()

    if key == "max_team_members":
        return organization.memberships.count()

    # Fallback to UsageCounter
    period_date = now.date().replace(day=1)
    counter = UsageCounter.objects.filter(
        organization=organization,
        key=key,
        period_start=period_date,
    ).first()
    return counter.count if counter else 0


def enforce(
    organization: Organization,
    key: str,
    current_count: int | None = None,
) -> bool:
    """
    Check if organization is within metric cap.
    Raises PlanLimitExceeded if limit is exceeded.
    """
    if not getattr(settings, "BILLING_ENFORCEMENT", False):
        return True

    limit = get_org_entitlement(organization, key)
    if limit is None or limit == UNLIMITED:
        return True

    now = timezone.now()
    count = (
        current_count
        if current_count is not None
        else _get_current_usage_count(organization, key, now)
    )

    if count >= limit:
        msg = f"Limit of {limit} for '{key}' reached ({count} used). Please upgrade."
        raise PlanLimitExceeded(msg)

    return True


def meter(
    organization: Organization,
    key: str,
    amount: int = 1,
) -> UsageCounter:
    """Increment organization usage counter for key in current month."""
    period_start = timezone.now().date().replace(day=1)
    counter, created = UsageCounter.objects.get_or_create(
        organization=organization,
        key=key,
        period_start=period_start,
        defaults={"count": amount},
    )
    if not created:
        counter.count += amount
        counter.save(update_fields=["count", "updated_at"])
    return counter


def usage_summary(organization: Organization) -> dict[str, dict[str, Any]]:
    """Return dictionary of all tracked metrics with current usage and caps."""
    now = timezone.now()
    keys = [
        "max_invoices_per_month",
        "max_clients",
        "max_products",
        "max_team_members",
        "ai_credits_per_month",
    ]
    summary = {}
    for key in keys:
        limit = get_org_entitlement(organization, key)
        used = _get_current_usage_count(organization, key, now)
        summary[key] = {
            "used": used,
            "limit": limit,
            "unlimited": limit == UNLIMITED,
        }
    return summary
