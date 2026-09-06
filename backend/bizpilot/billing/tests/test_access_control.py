from __future__ import annotations

import pytest
from django.core.cache import cache
from django.test import override_settings
from rest_framework import status
from rest_framework.test import APITestCase

from bizpilot.billing.engine import (
    FeatureNotAvailable,
    PlanLimitExceeded,
    allow,
    enforce,
    get_or_create_free_subscription,
    seed_default_plans,
)
from bizpilot.billing.models import Plan, Subscription
from bizpilot.erp.models import Client, Invoice, Product
from bizpilot.orgs.models import Membership
from bizpilot.orgs.services import create_organization
from bizpilot.users.models import User


class SubscriptionAccessControlTest(APITestCase):
    def setUp(self) -> None:
        cache.clear()
        seed_default_plans()

        self.user = User.objects.create_user(
            email="owner@subscription-test.com",
            password="password123",  # noqa: S106
            name="Test Owner",
        )
        self.org = create_organization(name="Subscription Corp", owner=self.user)
        self.client.force_authenticate(user=self.user)

    def tearDown(self) -> None:
        cache.clear()

    # -------------------------------------------------------------------------
    # 1. Free Tier Access Control
    # -------------------------------------------------------------------------
    def test_free_tier_features_blocked(self) -> None:
        """Free tier organizations are blocked from accessing paid features."""
        with override_settings(BILLING_ENFORCEMENT=True):
            restricted_features = [
                "recurring_invoices",
                "email_invoice_delivery",
                "client_portal",
                "data_export",
                "audit_log",
                "custom_roles",
            ]
            for feat in restricted_features:
                with pytest.raises(FeatureNotAvailable):
                    allow(self.org, feat)

    def test_free_tier_invoice_limit(self) -> None:
        """Free tier allows up to 10 invoices/month; 11th is denied."""
        with override_settings(BILLING_ENFORCEMENT=True):
            assert enforce(self.org, "max_invoices_per_month", current_count=9) is True
            with pytest.raises(PlanLimitExceeded):
                enforce(self.org, "max_invoices_per_month", current_count=10)

    def test_free_tier_client_limit(self) -> None:
        """Free tier allows up to 5 clients; 6th is denied."""
        with override_settings(BILLING_ENFORCEMENT=True):
            assert enforce(self.org, "max_clients", current_count=4) is True
            with pytest.raises(PlanLimitExceeded):
                enforce(self.org, "max_clients", current_count=5)

    def test_free_tier_product_limit(self) -> None:
        """Free tier allows up to 10 products; 11th is denied."""
        with override_settings(BILLING_ENFORCEMENT=True):
            assert enforce(self.org, "max_products", current_count=9) is True
            with pytest.raises(PlanLimitExceeded):
                enforce(self.org, "max_products", current_count=10)

    def test_free_tier_team_member_limit(self) -> None:
        """Free tier allows 1 team member; second invite is denied."""
        with override_settings(BILLING_ENFORCEMENT=True):
            with pytest.raises(PlanLimitExceeded):
                enforce(self.org, "max_team_members", current_count=1)

    # -------------------------------------------------------------------------
    # 2. Pro Tier Access Control
    # -------------------------------------------------------------------------
    def test_pro_tier_features_unlocked(self) -> None:
        """Pro tier unlocks core premium features, while enterprise features remain restricted."""
        sub = get_or_create_free_subscription(self.org)
        sub.plan = Plan.objects.get(code="pro")
        sub.status = Subscription.Status.ACTIVE
        sub.save()
        cache.clear()

        with override_settings(BILLING_ENFORCEMENT=True):
            allowed_features = [
                "recurring_invoices",
                "email_invoice_delivery",
                "client_portal",
                "data_export",
                "audit_log",
            ]
            for feat in allowed_features:
                assert allow(self.org, feat) is True

            # Custom roles is Enterprise-only
            with pytest.raises(FeatureNotAvailable):
                allow(self.org, "custom_roles")

    def test_pro_tier_expanded_limits(self) -> None:
        """Pro tier expands capacity to 500 invoices, 200 clients, 1000 products, and 10 members."""
        sub = get_or_create_free_subscription(self.org)
        sub.plan = Plan.objects.get(code="pro")
        sub.save()
        cache.clear()

        with override_settings(BILLING_ENFORCEMENT=True):
            assert enforce(self.org, "max_invoices_per_month", current_count=499) is True
            with pytest.raises(PlanLimitExceeded):
                enforce(self.org, "max_invoices_per_month", current_count=500)

            assert enforce(self.org, "max_clients", current_count=199) is True
            with pytest.raises(PlanLimitExceeded):
                enforce(self.org, "max_clients", current_count=200)

            assert enforce(self.org, "max_team_members", current_count=9) is True
            with pytest.raises(PlanLimitExceeded):
                enforce(self.org, "max_team_members", current_count=10)

    # -------------------------------------------------------------------------
    # 3. Enterprise Tier Access Control
    # -------------------------------------------------------------------------
    def test_enterprise_tier_unlimited(self) -> None:
        """Enterprise tier has no numeric limits and unlocks custom roles."""
        sub = get_or_create_free_subscription(self.org)
        sub.plan = Plan.objects.get(code="enterprise")
        sub.save()
        cache.clear()

        with override_settings(BILLING_ENFORCEMENT=True):
            assert allow(self.org, "custom_roles") is True
            assert enforce(self.org, "max_invoices_per_month", current_count=100_000) is True
            assert enforce(self.org, "max_clients", current_count=50_000) is True
            assert enforce(self.org, "max_team_members", current_count=10_000) is True

    # -------------------------------------------------------------------------
    # 4. API Endpoints Access Control
    # -------------------------------------------------------------------------
    def test_api_invoice_send_access_control(self) -> None:
        """Sending invoice email via API is denied on Free plan, allowed on Pro plan."""
        inv = Invoice.objects.create(
            organization=self.org,
            invoice_number="INV-SUB-001",
            issue_date="2026-09-01",
            due_date="2026-09-15",
            subtotal="100.00",
            client_email="client@test.com",
            status=Invoice.Status.DRAFT,
        )

        url = f"/api/v1/orgs/{self.org.id}/invoices/{inv.id}/send/"

        with override_settings(BILLING_ENFORCEMENT=True):
            # Free tier: 403 Forbidden
            res = self.client.post(url)
            assert res.status_code == status.HTTP_403_FORBIDDEN
            assert "feature_not_available" in str(res.data)

            # Upgrade to Pro
            sub = get_or_create_free_subscription(self.org)
            sub.plan = Plan.objects.get(code="pro")
            sub.save()
            cache.clear()

            # Pro tier: 200 OK
            res = self.client.post(url)
            assert res.status_code == status.HTTP_200_OK

    def test_api_invoice_create_limit_exceeded(self) -> None:
        """Creating invoice via API returns 402 when monthly limit is reached."""
        with override_settings(BILLING_ENFORCEMENT=True):
            # Fill up free allowance
            for i in range(10):
                Invoice.objects.create(
                    organization=self.org,
                    invoice_number=f"INV-TEST-{i:03d}",
                    issue_date="2026-09-01",
                    due_date="2026-09-15",
                    subtotal="50.00",
                    status=Invoice.Status.DRAFT,
                )

            url = f"/api/v1/orgs/{self.org.id}/invoices/"
            payload = {
                "invoice_number": "INV-TEST-EXCEED",
                "issue_date": "2026-09-06",
                "due_date": "2026-09-20",
                "items": [{"description": "Item", "quantity": 1, "rate": "100.00"}],
            }

            # 11th invoice fails on Free plan
            res = self.client.post(url, payload, format="json")
            assert res.status_code == status.HTTP_402_PAYMENT_REQUIRED
            assert "plan_limit_exceeded" in str(res.data)

            # Upgrade to Pro
            sub = get_or_create_free_subscription(self.org)
            sub.plan = Plan.objects.get(code="pro")
            sub.save()
            cache.clear()

            # Succeeds on Pro plan
            res = self.client.post(url, payload, format="json")
            assert res.status_code == status.HTTP_201_CREATED

    def test_api_client_create_limit_exceeded(self) -> None:
        """Creating client via API returns 402 when client limit is reached."""
        with override_settings(BILLING_ENFORCEMENT=True):
            # Fill up free allowance (5 clients)
            for i in range(5):
                Client.objects.create(
                    organization=self.org,
                    name=f"Client {i}",
                    email=f"client{i}@test.com",
                )

            url = f"/api/v1/orgs/{self.org.id}/clients/"
            payload = {"name": "6th Client", "email": "client6@test.com"}

            # 6th client fails on Free plan
            res = self.client.post(url, payload, format="json")
            assert res.status_code == status.HTTP_402_PAYMENT_REQUIRED

            # Upgrade to Pro
            sub = get_or_create_free_subscription(self.org)
            sub.plan = Plan.objects.get(code="pro")
            sub.save()
            cache.clear()

            # Succeeds on Pro plan
            res = self.client.post(url, payload, format="json")
            assert res.status_code == status.HTTP_201_CREATED

    def test_api_team_invite_limit_exceeded(self) -> None:
        """Inviting team member returns 402 when team limit is reached."""
        with override_settings(BILLING_ENFORCEMENT=True):
            url = f"/api/v1/orgs/{self.org.id}/invites/"
            payload = {"email": "colleague@test.com"}

            # Free plan already has 1 member (owner); 2nd member fails
            res = self.client.post(url, payload, format="json")
            assert res.status_code == status.HTTP_402_PAYMENT_REQUIRED

            # Upgrade to Pro
            sub = get_or_create_free_subscription(self.org)
            sub.plan = Plan.objects.get(code="pro")
            sub.save()
            cache.clear()

            # Succeeds on Pro plan
            res = self.client.post(url, payload, format="json")
            assert res.status_code == status.HTTP_201_CREATED
