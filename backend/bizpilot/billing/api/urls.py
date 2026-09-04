from __future__ import annotations

from django.urls import path

from bizpilot.billing.api.views import CreateCheckoutSessionView
from bizpilot.billing.api.views import CreateCustomerPortalView
from bizpilot.billing.api.views import PlanListView
from bizpilot.billing.api.views import StripeWebhookView
from bizpilot.billing.api.views import SubscriptionDetailView

app_name = "billing"

urlpatterns = [
    # Global plans & webhook
    path("billing/plans/", PlanListView.as_view(), name="plan-list"),
    path(
        "billing/webhooks/stripe/",
        StripeWebhookView.as_view(),
        name="stripe-webhook",
    ),
    # Org-scoped billing endpoints
    path(
        "orgs/<uuid:org_id>/subscription/",
        SubscriptionDetailView.as_view(),
        name="subscription-detail",
    ),
    path(
        "orgs/<uuid:org_id>/billing/checkout/",
        CreateCheckoutSessionView.as_view(),
        name="billing-checkout",
    ),
    path(
        "orgs/<uuid:org_id>/billing/portal/",
        CreateCustomerPortalView.as_view(),
        name="billing-portal",
    ),
]
