from __future__ import annotations

from unittest.mock import MagicMock
from unittest.mock import patch

from django.core.cache import cache
from rest_framework import status
from rest_framework.test import APITestCase

from bizpilot.billing.models import Plan
from bizpilot.billing.models import Subscription
from bizpilot.orgs.services import create_organization
from bizpilot.users.models import User

EXPECTED_PLANS_COUNT = 3


class BillingAPITest(APITestCase):
    def setUp(self) -> None:
        cache.clear()
        self.owner = User.objects.create_user(
            email="owner@billingcorp.com",
            password="password123",  # noqa: S106
            name="Billing Owner",
        )
        self.org = create_organization(name="Billing Corp", owner=self.owner)

    def tearDown(self) -> None:
        cache.clear()

    def test_list_plans(self) -> None:
        url = "/api/v1/billing/plans/"
        res = self.client.get(url)
        assert res.status_code == status.HTTP_200_OK
        assert len(res.data["results"]) == EXPECTED_PLANS_COUNT

    def test_get_subscription(self) -> None:
        self.client.force_authenticate(user=self.owner)
        url = f"/api/v1/orgs/{self.org.id}/subscription/"
        res = self.client.get(url)
        assert res.status_code == status.HTTP_200_OK
        assert res.data["plan"]["code"] == "free"
        assert "usage" in res.data

    @patch("stripe.checkout.Session.create")
    def test_create_checkout_session(
        self,
        mock_checkout: MagicMock,
    ) -> None:
        mock_checkout.return_value = MagicMock(
            id="cs_test_123",
            url="https://checkout.stripe.com/pay/cs_test_123",
        )
        self.client.force_authenticate(user=self.owner)
        url = f"/api/v1/orgs/{self.org.id}/billing/checkout/"
        payload = {
            "price_id": "price_pro_monthly",
            "success_url": "https://example.com/success",
            "cancel_url": "https://example.com/cancel",
        }
        res = self.client.post(url, payload, format="json")
        assert res.status_code == status.HTTP_200_OK
        assert res.data["session_id"] == "cs_test_123"

    @patch("stripe.billing_portal.Session.create")
    def test_create_customer_portal(self, mock_portal: MagicMock) -> None:
        mock_portal.return_value = MagicMock(
            url="https://billing.stripe.com/p/session/test",
        )
        # Give org a customer id first
        sub = self.org.subscription
        sub.stripe_customer_id = "cus_test_123"
        sub.save()

        self.client.force_authenticate(user=self.owner)
        url = f"/api/v1/orgs/{self.org.id}/billing/portal/"
        payload = {"return_url": "https://example.com/settings"}
        res = self.client.post(url, payload, format="json")
        assert res.status_code == status.HTTP_200_OK
        assert "stripe.com" in res.data["url"]

    def test_stripe_webhook_checkout_completed(self) -> None:
        url = "/api/v1/billing/webhooks/stripe/"
        event_payload = {
            "id": "evt_test_checkout_1",
            "type": "checkout.session.completed",
            "data": {
                "object": {
                    "id": "cs_test_123",
                    "client_reference_id": str(self.org.id),
                    "customer": "cus_test_abc",
                    "subscription": "sub_test_xyz",
                    "metadata": {
                        "organization_id": str(self.org.id),
                        "plan_code": "pro",
                    },
                },
            },
        }
        res = self.client.post(url, event_payload, format="json")
        assert res.status_code == status.HTTP_200_OK
        assert res.data["status"] == "received"

        sub = Subscription.objects.get(organization=self.org)
        assert sub.plan.code == "pro"
        assert sub.stripe_customer_id == "cus_test_abc"
        assert sub.stripe_subscription_id == "sub_test_xyz"
        assert sub.status == Subscription.Status.ACTIVE

    def test_stripe_webhook_subscription_deleted(self) -> None:
        sub = self.org.subscription
        pro_plan = Plan.objects.get(code="pro")
        sub.plan = pro_plan
        sub.stripe_subscription_id = "sub_to_delete"
        sub.status = Subscription.Status.ACTIVE
        sub.save()

        url = "/api/v1/billing/webhooks/stripe/"
        event_payload = {
            "id": "evt_test_deleted_1",
            "type": "customer.subscription.deleted",
            "data": {
                "object": {
                    "id": "sub_to_delete",
                },
            },
        }
        res = self.client.post(url, event_payload, format="json")
        assert res.status_code == status.HTTP_200_OK

        sub.refresh_from_db()
        assert sub.plan.code == "free"
        assert sub.status == Subscription.Status.CANCELED
