from __future__ import annotations

from typing import TYPE_CHECKING
from typing import Any

import stripe
from django.conf import settings
from django.db import transaction
from django.utils import timezone

from bizpilot.billing.engine import get_or_create_free_subscription
from bizpilot.billing.models import Plan
from bizpilot.billing.models import PriceMapping
from bizpilot.billing.models import StripeEvent
from bizpilot.billing.models import Subscription

if TYPE_CHECKING:
    from bizpilot.orgs.models import Organization


def get_stripe_client() -> None:
    stripe.api_key = getattr(
        settings,
        "STRIPE_SECRET_KEY",
        "sk_test_placeholder",
    )


def create_checkout_session(
    *,
    organization: Organization,
    price_id: str,
    success_url: str,
    cancel_url: str,
    customer_email: str | None = None,
) -> dict[str, str]:
    """Create a Stripe Checkout Session for subscription upgrade."""
    get_stripe_client()
    sub = get_or_create_free_subscription(organization)

    price_mapping = PriceMapping.objects.filter(
        stripe_price_id=price_id,
        is_active=True,
    ).first()

    session_kwargs: dict[str, Any] = {
        "payment_method_types": ["card"],
        "mode": "subscription",
        "line_items": [{"price": price_id, "quantity": 1}],
        "success_url": success_url,
        "cancel_url": cancel_url,
        "client_reference_id": str(organization.id),
        "metadata": {
            "organization_id": str(organization.id),
            "plan_code": price_mapping.plan.code if price_mapping else "",
        },
    }

    if sub.stripe_customer_id:
        session_kwargs["customer"] = sub.stripe_customer_id
    elif customer_email:
        session_kwargs["customer_email"] = customer_email

    session = stripe.checkout.Session.create(**session_kwargs)
    return {"session_id": session.id, "url": session.url or ""}


def create_customer_portal_session(
    *,
    organization: Organization,
    return_url: str,
) -> dict[str, str]:
    """Create a Stripe Customer Portal session for billing management."""
    get_stripe_client()
    sub = get_or_create_free_subscription(organization)
    if not sub.stripe_customer_id:
        msg = "No Stripe customer associated with this organization."
        raise ValueError(msg)

    session = stripe.billing_portal.Session.create(
        customer=sub.stripe_customer_id,
        return_url=return_url,
    )
    return {"url": session.url}


def _process_checkout_completed(event_data: dict[str, Any]) -> None:
    session = event_data.get("object", {})
    org_id = session.get("client_reference_id") or session.get(
        "metadata",
        {},
    ).get("organization_id")
    if not org_id:
        return

    from bizpilot.orgs.models import Organization  # noqa: PLC0415

    org = Organization.objects.filter(id=org_id).first()
    if not org:
        return

    customer_id = session.get("customer")
    sub_id = session.get("subscription")
    plan_code = session.get("metadata", {}).get("plan_code")

    plan = Plan.objects.filter(code=plan_code).first()
    sub = get_or_create_free_subscription(org)

    if customer_id:
        sub.stripe_customer_id = str(customer_id)
    if sub_id:
        sub.stripe_subscription_id = str(sub_id)
    if plan:
        sub.plan = plan
    sub.status = Subscription.Status.ACTIVE
    sub.save()


def _process_subscription_updated(event_data: dict[str, Any]) -> None:
    stripe_sub = event_data.get("object", {})
    sub_id = stripe_sub.get("id")
    if not sub_id:
        return

    sub = Subscription.objects.filter(stripe_subscription_id=sub_id).first()
    if not sub:
        return

    status_str = stripe_sub.get("status")
    status_map = {
        "trialing": Subscription.Status.TRIALING,
        "active": Subscription.Status.ACTIVE,
        "past_due": Subscription.Status.PAST_DUE,
        "canceled": Subscription.Status.CANCELED,
        "incomplete": Subscription.Status.INCOMPLETE,
        "paused": Subscription.Status.PAUSED,
    }
    if status_str in status_map:
        sub.status = status_map[status_str]

    sub.cancel_at_period_end = stripe_sub.get("cancel_at_period_end", False)

    period_start = stripe_sub.get("current_period_start")
    if period_start:
        sub.current_period_start = timezone.datetime.fromtimestamp(
            period_start,
            tz=timezone.utc,
        )

    period_end = stripe_sub.get("current_period_end")
    if period_end:
        sub.current_period_end = timezone.datetime.fromtimestamp(
            period_end,
            tz=timezone.utc,
        )

    sub.save()


def _process_subscription_deleted(event_data: dict[str, Any]) -> None:
    stripe_sub = event_data.get("object", {})
    sub_id = stripe_sub.get("id")
    if not sub_id:
        return

    sub = Subscription.objects.filter(stripe_subscription_id=sub_id).first()
    if not sub:
        return

    free_plan = Plan.objects.filter(code="free").first()
    if free_plan:
        sub.plan = free_plan
    sub.status = Subscription.Status.CANCELED
    sub.stripe_subscription_id = ""
    sub.cancel_at_period_end = False
    sub.save()


def process_stripe_event(event_dict: dict[str, Any]) -> StripeEvent:
    """Process a verified Stripe event idempotently."""
    event_id = event_dict.get("id", "")
    event_type = event_dict.get("type", "")

    with transaction.atomic():
        stripe_event, created = StripeEvent.objects.get_or_create(
            stripe_event_id=event_id,
            defaults={
                "event_type": event_type,
                "payload": event_dict,
                "processed": False,
            },
        )
        if not created and stripe_event.processed:
            return stripe_event

        data = event_dict.get("data", {})
        if event_type == "checkout.session.completed":
            _process_checkout_completed(data)
        elif event_type in (
            "customer.subscription.created",
            "customer.subscription.updated",
        ):
            _process_subscription_updated(data)
        elif event_type == "customer.subscription.deleted":
            _process_subscription_deleted(data)
        elif event_type == "invoice.payment_failed":
            pass

        stripe_event.processed = True
        stripe_event.processed_at = timezone.now()
        stripe_event.save(update_fields=["processed", "processed_at"])

    return stripe_event
