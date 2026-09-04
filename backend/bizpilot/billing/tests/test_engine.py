from __future__ import annotations

import pytest
from django.core.cache import cache
from django.test import TestCase
from django.test import override_settings

from bizpilot.billing.engine import FeatureNotAvailable
from bizpilot.billing.engine import PlanLimitExceeded
from bizpilot.billing.engine import allow
from bizpilot.billing.engine import enforce
from bizpilot.billing.engine import get_or_create_free_subscription
from bizpilot.billing.engine import meter
from bizpilot.billing.engine import seed_default_plans
from bizpilot.billing.engine import usage_summary
from bizpilot.billing.models import Plan
from bizpilot.billing.models import Subscription
from bizpilot.erp.models import Client
from bizpilot.orgs.services import create_organization
from bizpilot.users.models import User

EXPECTED_DEFAULT_PLANS = 3
EXPECTED_METER_TOTAL = 5


class BillingEngineTest(TestCase):
    def setUp(self) -> None:
        cache.clear()
        self.user = User.objects.create_user(
            email="billing@test.com",
            password="password123",  # noqa: S106
            name="Billing User",
        )
        self.org = create_organization(name="Billing Corp", owner=self.user)

    def tearDown(self) -> None:
        cache.clear()

    def test_seed_default_plans(self) -> None:
        seed_default_plans()
        assert (
            Plan.objects.filter(is_active=True).count()
            == EXPECTED_DEFAULT_PLANS
        )
        free_plan = Plan.objects.get(code="free")
        assert free_plan.entitlements.count() > 0

    def test_get_or_create_free_subscription(self) -> None:
        sub = get_or_create_free_subscription(self.org)
        assert sub.plan.code == "free"
        assert sub.status == Subscription.Status.ACTIVE

    def test_allow_feature(self) -> None:
        # When BILLING_ENFORCEMENT=False, allow returns True
        assert allow(self.org, "recurring_invoices") is True

        # When BILLING_ENFORCEMENT=True, Free plan does not have recurring_invoices
        with (
            override_settings(BILLING_ENFORCEMENT=True),
            pytest.raises(FeatureNotAvailable),
        ):
            allow(self.org, "recurring_invoices")

    def test_enforce_limits(self) -> None:
        # Free plan max_clients is 5
        # When BILLING_ENFORCEMENT=False, enforce returns True even if over limit
        assert enforce(self.org, "max_clients", current_count=10) is True

        # When BILLING_ENFORCEMENT=True
        with override_settings(BILLING_ENFORCEMENT=True):
            assert enforce(self.org, "max_clients", current_count=4) is True
            with pytest.raises(PlanLimitExceeded):
                enforce(self.org, "max_clients", current_count=5)

    def test_enforce_with_live_models(self) -> None:
        with override_settings(BILLING_ENFORCEMENT=True):
            for i in range(5):
                Client.objects.create(
                    organization=self.org,
                    name=f"Client {i}",
                )
            with pytest.raises(PlanLimitExceeded):
                enforce(self.org, "max_clients")

    def test_meter_and_usage_summary(self) -> None:
        meter(self.org, "ai_credits", amount=2)
        meter(self.org, "ai_credits", amount=3)
        summary = usage_summary(self.org)
        assert "max_invoices_per_month" in summary
        assert "max_clients" in summary
        assert "max_products" in summary
        assert "max_team_members" in summary
