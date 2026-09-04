from __future__ import annotations

from decimal import Decimal

from django.core.cache import cache
from rest_framework import status
from rest_framework.test import APITestCase

from bizpilot.erp.models import Client
from bizpilot.erp.models import Invoice
from bizpilot.orgs.services import create_organization
from bizpilot.users.models import User

EXPECTED_ITEM_COUNT = 2


class AIAPITest(APITestCase):
    def setUp(self) -> None:
        cache.clear()
        self.owner = User.objects.create_user(
            email="ai_api_owner@corp.com",
            password="password123",  # noqa: S106
            name="AI API Owner",
        )
        self.org = create_organization(name="AI API Corp", owner=self.owner)
        self.client_obj = Client.objects.create(
            organization=self.org,
            name="API Client",
        )
        self.invoice = Invoice.objects.create(
            organization=self.org,
            client=self.client_obj,
            invoice_number="INV-AI-API-01",
            issue_date="2026-09-01",
            due_date="2026-09-15",
            total=Decimal("800.00"),
        )
        self.client.force_authenticate(user=self.owner)

    def tearDown(self) -> None:
        cache.clear()

    def test_generate_items_api(self) -> None:
        url = f"/api/v1/orgs/{self.org.id}/ai/generate-items/"
        payload = {"prompt": "Design and development services [20 hours]"}
        res = self.client.post(url, payload, format="json")
        assert res.status_code == status.HTTP_200_OK
        assert "items" in res.data
        assert len(res.data["items"]) == EXPECTED_ITEM_COUNT

    def test_ask_bizpilot_api_json(self) -> None:
        url = f"/api/v1/orgs/{self.org.id}/ai/assistant/"
        payload = {"question": "How is my business doing?"}
        res = self.client.post(url, payload, format="json")
        assert res.status_code == status.HTTP_200_OK
        assert "answer" in res.data

    def test_ask_bizpilot_api_streaming(self) -> None:
        url = f"/api/v1/orgs/{self.org.id}/ai/assistant/"
        payload = {"question": "How is my business doing?", "stream": True}
        res = self.client.post(url, payload, format="json")
        assert res.status_code == status.HTTP_200_OK
        assert res["Content-Type"].startswith("text/event-stream")

    def test_categorize_expense_api(self) -> None:
        url = f"/api/v1/orgs/{self.org.id}/ai/categorize-expense/"
        payload = {"title": "AWS Cloud Hosting"}
        res = self.client.post(url, payload, format="json")
        assert res.status_code == status.HTTP_200_OK
        assert "category" in res.data
        assert "confidence" in res.data

    def test_draft_reminder_api(self) -> None:
        url = f"/api/v1/orgs/{self.org.id}/ai/draft-reminder/"
        payload = {"invoice_id": str(self.invoice.id), "tone": "firm"}
        res = self.client.post(url, payload, format="json")
        assert res.status_code == status.HTTP_200_OK
        assert "subject" in res.data
        assert "body" in res.data

    def test_list_ai_logs(self) -> None:
        # Trigger an AI action to generate a log
        url = f"/api/v1/orgs/{self.org.id}/ai/categorize-expense/"
        self.client.post(url, {"title": "Office Desk"}, format="json")

        logs_url = f"/api/v1/orgs/{self.org.id}/ai/logs/"
        res = self.client.get(logs_url)
        assert res.status_code == status.HTTP_200_OK
        assert len(res.data["results"]) >= 1
