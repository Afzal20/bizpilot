from __future__ import annotations

from decimal import Decimal

from django.core.cache import cache
from rest_framework import status
from rest_framework.test import APITestCase

from bizpilot.erp.models import Client
from bizpilot.erp.models import Expense
from bizpilot.erp.models import Invoice
from bizpilot.erp.models import Payment
from bizpilot.erp.models import Product
from bizpilot.orgs.constants import SYSTEM_ROLE_VIEWER
from bizpilot.orgs.models import Membership
from bizpilot.orgs.services import create_organization
from bizpilot.users.models import User

EXPECTED_CLIENT_COUNT = 1
EXPECTED_PRODUCT_STOCK = 25
EXPECTED_STOCK_AFTER_DEDUCTION = 7
EXPECTED_SERIES_COUNT = 6
TOTAL_INVOICE_AMOUNT = 300.0


class ERPAPITest(APITestCase):
    def setUp(self) -> None:
        cache.clear()
        self.owner = User.objects.create_user(
            email="owner@erpcorp.com",
            password="password123",  # noqa: S106
            name="Owner User",
        )
        self.viewer = User.objects.create_user(
            email="viewer@erpcorp.com",
            password="password123",  # noqa: S106
            name="Viewer User",
        )
        self.org = create_organization(name="ERP Corp", owner=self.owner)

        # Add viewer to org with Viewer role
        viewer_role = self.org.roles.get(name=SYSTEM_ROLE_VIEWER)
        self.viewer_membership = Membership.objects.create(
            organization=self.org,
            user=self.viewer,
            email=self.viewer.email,
            name=self.viewer.name,
            status=Membership.Status.ACTIVE,
        )
        self.viewer_membership.roles.add(viewer_role)

        self.other_user = User.objects.create_user(
            email="other@othercorp.com",
            password="password123",  # noqa: S106
            name="Other User",
        )
        self.other_org = create_organization(
            name="Other Corp",
            owner=self.other_user,
        )

    def tearDown(self) -> None:
        cache.clear()

    def test_client_crud_and_tenant_isolation(self) -> None:
        self.client.force_authenticate(user=self.owner)

        # Create client
        create_url = f"/api/v1/orgs/{self.org.id}/clients/"
        payload = {
            "name": "Acme Inc",
            "email": "acme@example.com",
            "company": "Acme Global",
        }
        res = self.client.post(create_url, payload, format="json")
        assert res.status_code == status.HTTP_201_CREATED
        assert "id" in res.data

        # List clients in self.org
        list_res = self.client.get(create_url)
        assert list_res.status_code == status.HTTP_200_OK
        assert len(list_res.data["results"]) == EXPECTED_CLIENT_COUNT

        # Other org cannot see this client
        other_list_url = f"/api/v1/orgs/{self.other_org.id}/clients/"
        self.client.force_authenticate(user=self.other_user)
        other_res = self.client.get(other_list_url)
        assert other_res.status_code == status.HTTP_200_OK
        assert len(other_res.data["results"]) == 0

        # Viewer cannot create a client (403 forbidden)
        self.client.force_authenticate(user=self.viewer)
        forbidden_res = self.client.post(create_url, payload, format="json")
        assert forbidden_res.status_code == status.HTTP_403_FORBIDDEN

    def test_client_stats_endpoint(self) -> None:
        self.client.force_authenticate(user=self.owner)
        erp_client = Client.objects.create(
            organization=self.org,
            name="Big Corp",
            email="big@example.com",
        )
        stats_url = f"/api/v1/orgs/{self.org.id}/clients/{erp_client.id}/stats/"
        res = self.client.get(stats_url)
        assert res.status_code == status.HTTP_200_OK
        assert "outstanding" in res.data
        assert "total_invoiced" in res.data

    def test_product_crud_and_adjust_stock(self) -> None:
        self.client.force_authenticate(user=self.owner)
        create_url = f"/api/v1/orgs/{self.org.id}/products/"
        payload = {
            "name": "Laptop Stand",
            "unit_price": "49.99",
            "track_stock": True,
            "stock_quantity": 20,
        }
        res = self.client.post(create_url, payload, format="json")
        assert res.status_code == status.HTTP_201_CREATED
        product_id = res.data["id"]

        # Adjust stock
        adjust_url = (
            f"/api/v1/orgs/{self.org.id}/products/{product_id}/adjust-stock/"
        )
        adjust_res = self.client.post(
            adjust_url,
            {"quantity_delta": 5, "reason": "Restock"},
            format="json",
        )
        assert adjust_res.status_code == status.HTTP_200_OK
        assert adjust_res.data["stock_quantity"] == EXPECTED_PRODUCT_STOCK

    def test_invoice_flow_send_payment_cancel(self) -> None:
        self.client.force_authenticate(user=self.owner)
        product = Product.objects.create(
            organization=self.org,
            name="Mechanical Keyboard",
            unit_price=Decimal("100.00"),
            track_stock=True,
            stock_quantity=10,
        )
        erp_client = Client.objects.create(
            organization=self.org,
            name="Tech Buyer",
            email="buyer@tech.com",
        )

        create_inv_url = f"/api/v1/orgs/{self.org.id}/invoices/"
        payload = {
            "client": str(erp_client.id),
            "issue_date": "2026-09-04",
            "due_date": "2026-09-18",
            "items": [
                {
                    "product": str(product.id),
                    "description": "3 Keyboards",
                    "quantity": "3.00",
                    "rate": "100.00",
                },
            ],
        }
        res = self.client.post(create_inv_url, payload, format="json")
        assert res.status_code == status.HTTP_201_CREATED
        inv_id = res.data["id"]
        assert res.data["invoice_number"].startswith("INV-2026-")
        assert float(res.data["total"]) == TOTAL_INVOICE_AMOUNT

        # Send invoice -> stock deducted
        send_url = f"/api/v1/orgs/{self.org.id}/invoices/{inv_id}/send/"
        send_res = self.client.post(send_url)
        assert send_res.status_code == status.HTTP_200_OK
        assert send_res.data["status"] == Invoice.Status.PENDING
        product.refresh_from_db()
        assert product.stock_quantity == EXPECTED_STOCK_AFTER_DEDUCTION

        # Add payment
        pay_url = f"/api/v1/orgs/{self.org.id}/invoices/{inv_id}/payments/"
        pay_payload = {
            "amount": "300.00",
            "payment_method": Payment.PaymentMethod.BANK_TRANSFER,
        }
        pay_res = self.client.post(pay_url, pay_payload, format="json")
        assert pay_res.status_code == status.HTTP_201_CREATED

        # Verify invoice is now PAID
        detail_url = f"/api/v1/orgs/{self.org.id}/invoices/{inv_id}/"
        detail_res = self.client.get(detail_url)
        assert detail_res.data["status"] == Invoice.Status.PAID
        assert float(detail_res.data["balance_due"]) == 0.0

    def test_expense_crud(self) -> None:
        self.client.force_authenticate(user=self.owner)
        exp_url = f"/api/v1/orgs/{self.org.id}/expenses/"
        payload = {
            "title": "Hosting Bill",
            "category": Expense.Category.SOFTWARE,
            "amount": "45.00",
            "expense_date": "2026-09-01",
        }
        res = self.client.post(exp_url, payload, format="json")
        assert res.status_code == status.HTTP_201_CREATED
        assert res.data["title"] == "Hosting Bill"

    def test_dashboard_and_reports_and_search_endpoints(self) -> None:
        self.client.force_authenticate(user=self.owner)

        dash_url = f"/api/v1/orgs/{self.org.id}/dashboard/stats/"
        dash_res = self.client.get(dash_url)
        assert dash_res.status_code == status.HTTP_200_OK
        assert len(dash_res.data["monthly_series"]) == EXPECTED_SERIES_COUNT

        reports_url = f"/api/v1/orgs/{self.org.id}/reports/"
        rep_res = self.client.get(reports_url)
        assert rep_res.status_code == status.HTTP_200_OK
        assert "totals" in rep_res.data

        search_url = f"/api/v1/orgs/{self.org.id}/search/?q=test"
        search_res = self.client.get(search_url)
        assert search_res.status_code == status.HTTP_200_OK
        assert "clients" in search_res.data
        assert "products" in search_res.data
        assert "invoices" in search_res.data
        assert "expenses" in search_res.data
