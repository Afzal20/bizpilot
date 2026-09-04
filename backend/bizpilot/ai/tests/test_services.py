from __future__ import annotations

from decimal import Decimal

from django.core.cache import cache
from django.test import TestCase

from bizpilot.ai.models import AILog
from bizpilot.ai.services import ask_bizpilot
from bizpilot.ai.services import categorize_expense
from bizpilot.ai.services import draft_payment_reminder
from bizpilot.ai.services import generate_invoice_items
from bizpilot.billing.models import UsageCounter
from bizpilot.erp.models import Client
from bizpilot.erp.models import Invoice
from bizpilot.orgs.services import create_organization
from bizpilot.users.models import User

EXPECTED_ITEMS_COUNT = 2
MIN_ANSWER_LEN = 10


class AIServicesTest(TestCase):
    def setUp(self) -> None:
        cache.clear()
        self.user = User.objects.create_user(
            email="ai_user@example.com",
            password="password123",  # noqa: S106
            name="AI Tester",
        )
        self.org = create_organization(name="AI Corp", owner=self.user)
        self.client_obj = Client.objects.create(
            organization=self.org,
            name="Acme Corp",
            email="acme@example.com",
        )
        self.invoice = Invoice.objects.create(
            organization=self.org,
            client=self.client_obj,
            invoice_number="INV-2026-AI-1",
            issue_date="2026-09-01",
            due_date="2026-09-15",
            total=Decimal("1500.00"),
        )

    def tearDown(self) -> None:
        cache.clear()

    def test_generate_invoice_items(self) -> None:
        prompt = "Web development services [hourly]: website design and frontend"
        items = generate_invoice_items(
            organization=self.org,
            prompt=prompt,
            user=self.user,
        )
        assert len(items) == EXPECTED_ITEMS_COUNT
        assert items[0]["quantity"] > 0

        # Check AILog created
        log = AILog.objects.filter(
            organization=self.org,
            feature="generate-items",
        ).first()
        assert log is not None

        # Check usage counter metered
        counter = UsageCounter.objects.filter(
            organization=self.org,
            key="ai_credits_per_month",
        ).first()
        assert counter is not None
        assert counter.count >= 1

    def test_ask_bizpilot(self) -> None:
        answer = ask_bizpilot(
            organization=self.org,
            question="What was my revenue last month?",
            user=self.user,
        )
        assert len(answer) > MIN_ANSWER_LEN

        log = AILog.objects.filter(
            organization=self.org,
            feature="assistant",
        ).first()
        assert log is not None

    def test_categorize_expense(self) -> None:
        res = categorize_expense(
            organization=self.org,
            title="GitHub Team Subscription",
            user=self.user,
        )
        assert "category" in res
        assert "vendor" in res
        assert res["confidence"] > 0

    def test_draft_payment_reminder(self) -> None:
        res = draft_payment_reminder(
            organization=self.org,
            invoice=self.invoice,
            tone="friendly",
            user=self.user,
        )
        assert "subject" in res
        assert "body" in res
