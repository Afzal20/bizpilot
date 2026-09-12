from __future__ import annotations

from decimal import Decimal

import pytest
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.test import TestCase

from bizpilot.ai.agent import _execute_action
from bizpilot.ai.agent import run_agent
from bizpilot.ai.context import build_assistant_context
from bizpilot.ai.models import AILog
from bizpilot.billing.models import UsageCounter
from bizpilot.erp.models import Client
from bizpilot.erp.models import Invoice
from bizpilot.erp.models import Payment
from bizpilot.erp.models import Product
from bizpilot.orgs.services import create_organization
from bizpilot.users.models import User


class AgentTest(TestCase):
    def setUp(self) -> None:
        cache.clear()
        self.user = User.objects.create_user(
            email="agent_user@example.com",
            password="password123",  # noqa: S106
            name="Agent Tester",
        )
        self.org = create_organization(name="Agent Corp", owner=self.user)
        self.invoice = Invoice.objects.create(
            organization=self.org,
            invoice_number="INV-2026-AI-1",
            issue_date="2026-09-01",
            due_date="2026-09-15",
            total=Decimal("1500.00"),
        )

    def tearDown(self) -> None:
        cache.clear()

    def test_build_assistant_context_includes_details(self) -> None:
        Client.objects.create(
            organization=self.org,
            name="Acme Corp",
            email="acme@example.com",
        )
        context = build_assistant_context(self.org)
        assert context["clients"][0]["email"] == "acme@example.com"
        assert context["today"]
        assert "invoices" in context
        assert context["invoices"][0]["invoice_number"] == "INV-2026-AI-1"

    def test_propose_does_not_write(self) -> None:
        res = run_agent(
            organization=self.org,
            instruction="Add client Rahim Traders",
            user=self.user,
        )
        assert res["executed"] is False
        assert res["planned_actions"][0]["tool"] == "add_client"
        assert not Client.objects.filter(name="Mock Client").exists()

    def test_confirm_adds_client(self) -> None:
        res = run_agent(
            organization=self.org,
            instruction="Add client Rahim Traders",
            user=self.user,
            confirm=True,
        )
        assert res["executed"] is True
        assert res["errors"] == []
        client = Client.objects.filter(name="Mock Client").first()
        assert client is not None
        assert client.organization_id == self.org.id

        log = AILog.objects.filter(organization=self.org, feature="agent").first()
        assert log is not None
        counter = UsageCounter.objects.filter(
            organization=self.org,
            key="ai_credits_per_month",
        ).first()
        assert counter is not None
        assert counter.count >= 1

    def test_confirm_adds_product(self) -> None:
        res = run_agent(
            organization=self.org,
            instruction="Add product Web Design Package",
            user=self.user,
            confirm=True,
        )
        assert res["executed"] is True
        assert Product.objects.filter(name="Mock Product").exists()

    def test_confirm_records_payment(self) -> None:
        res = run_agent(
            organization=self.org,
            instruction="Record a payment of 500 against invoice INV-2026-AI-1",
            user=self.user,
            confirm=True,
        )
        assert res["executed"] is True
        assert res["errors"] == []
        assert Payment.objects.filter(invoice=self.invoice).exists()
        self.invoice.refresh_from_db()
        assert self.invoice.status == Invoice.Status.PENDING

    def test_unknown_tool_raises(self) -> None:
        with pytest.raises(ValidationError):
            _execute_action(
                self.org,
                self.user,
                {"tool": "delete_everything", "args": {}},
            )

    def test_missing_required_field_raises(self) -> None:
        with pytest.raises(ValidationError):
            _execute_action(self.org, self.user, {"tool": "add_client", "args": {}})
