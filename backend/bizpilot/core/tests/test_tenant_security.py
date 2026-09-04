from __future__ import annotations

from decimal import Decimal

from django.core.cache import cache
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from bizpilot.erp.models import Client
from bizpilot.erp.models import Invoice
from bizpilot.erp.models import InvoiceItem
from bizpilot.erp.models import Payment
from bizpilot.erp.models import Product
from bizpilot.erp.services import cancel_invoice
from bizpilot.erp.services import generate_next_invoice_number
from bizpilot.erp.services import send_invoice
from bizpilot.orgs.constants import SYSTEM_ROLE_ADMIN
from bizpilot.orgs.constants import SYSTEM_ROLE_EDITOR
from bizpilot.orgs.constants import SYSTEM_ROLE_VIEWER
from bizpilot.orgs.models import Membership
from bizpilot.orgs.services import create_organization
from bizpilot.users.models import User


class CrossTenantAndRBACSecurityTests(APITestCase):
    def setUp(self) -> None:
        cache.clear()

        # Org 1 with Owner, Admin, Editor, Viewer
        self.owner1 = User.objects.create_user(
            email="owner1@tenant1.com",
            password="password123",
            name="Owner One",
        )
        self.admin1 = User.objects.create_user(
            email="admin1@tenant1.com",
            password="password123",
            name="Admin One",
        )
        self.editor1 = User.objects.create_user(
            email="editor1@tenant1.com",
            password="password123",
            name="Editor One",
        )
        self.viewer1 = User.objects.create_user(
            email="viewer1@tenant1.com",
            password="password123",
            name="Viewer One",
        )

        self.org1 = create_organization(name="Tenant One Corp", owner=self.owner1)

        # Assign Admin
        admin_role = self.org1.roles.get(name=SYSTEM_ROLE_ADMIN)
        m_admin = Membership.objects.create(
            organization=self.org1,
            user=self.admin1,
            email=self.admin1.email,
            status=Membership.Status.ACTIVE,
        )
        m_admin.roles.add(admin_role)

        # Assign Editor
        editor_role = self.org1.roles.get(name=SYSTEM_ROLE_EDITOR)
        m_editor = Membership.objects.create(
            organization=self.org1,
            user=self.editor1,
            email=self.editor1.email,
            status=Membership.Status.ACTIVE,
        )
        m_editor.roles.add(editor_role)

        # Assign Viewer
        viewer_role = self.org1.roles.get(name=SYSTEM_ROLE_VIEWER)
        m_viewer = Membership.objects.create(
            organization=self.org1,
            user=self.viewer1,
            email=self.viewer1.email,
            status=Membership.Status.ACTIVE,
        )
        m_viewer.roles.add(viewer_role)

        # Org 2 with Owner
        self.owner2 = User.objects.create_user(
            email="owner2@tenant2.com",
            password="password123",
            name="Owner Two",
        )
        self.org2 = create_organization(name="Tenant Two Corp", owner=self.owner2)

        # Seed data in Org 1
        self.client1 = Client.objects.create(
            organization=self.org1,
            name="Client Alpha",
            email="alpha@test.com",
        )
        self.product1 = Product.objects.create(
            organization=self.org1,
            name="Product Alpha",
            unit_price=Decimal("100.00"),
            stock_quantity=20,
            track_stock=True,
        )
        self.invoice1 = Invoice.objects.create(
            organization=self.org1,
            client=self.client1,
            invoice_number="INV-2026-001",
            status=Invoice.Status.PENDING,
            due_date=timezone.localdate(),
            subtotal=Decimal("200.00"),
            total=Decimal("200.00"),
        )
        InvoiceItem.objects.create(
            invoice=self.invoice1,
            product=self.product1,
            description="Item Alpha",
            quantity=Decimal("2.00"),
            rate=Decimal("100.00"),
            amount=Decimal("200.00"),
        )

        # Seed data in Org 2
        self.client2 = Client.objects.create(
            organization=self.org2,
            name="Client Beta",
            email="beta@test.com",
        )

    def tearDown(self) -> None:
        cache.clear()

    def test_non_member_cannot_access_tenant_endpoints(self) -> None:
        """AC-SEC-01: An authenticated user with no membership in Org 1 is rejected with 403."""
        self.client.force_authenticate(user=self.owner2)

        endpoints = [
            f"/api/v1/orgs/{self.org1.id}/clients/",
            f"/api/v1/orgs/{self.org1.id}/products/",
            f"/api/v1/orgs/{self.org1.id}/invoices/",
            f"/api/v1/orgs/{self.org1.id}/expenses/",
            f"/api/v1/orgs/{self.org1.id}/members/",
            f"/api/v1/orgs/{self.org1.id}/roles/",
            f"/api/v1/orgs/{self.org1.id}/dashboard/stats/",
            f"/api/v1/orgs/{self.org1.id}/reports/",
            f"/api/v1/orgs/{self.org1.id}/search/?q=Alpha",
        ]

        for ep in endpoints:
            resp = self.client.get(ep)
            self.assertEqual(
                resp.status_code,
                status.HTTP_403_FORBIDDEN,
                f"Endpoint {ep} did not reject non-member (status {resp.status_code})",
            )

    def test_viewer_is_read_only(self) -> None:
        """AC-TEAM-01: Viewer role can read data but mutations are rejected."""
        self.client.force_authenticate(user=self.viewer1)

        # Can read clients
        resp = self.client.get(f"/api/v1/orgs/{self.org1.id}/clients/")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

        # Cannot create client
        resp = self.client.post(
            f"/api/v1/orgs/{self.org1.id}/clients/",
            {"name": "Unauthorized Client", "email": "fail@test.com"},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

        # Cannot edit client
        resp = self.client.patch(
            f"/api/v1/orgs/{self.org1.id}/clients/{self.client1.id}/",
            {"name": "Hacked Name"},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

        # Cannot delete client
        resp = self.client.delete(f"/api/v1/orgs/{self.org1.id}/clients/{self.client1.id}/")
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_editor_cannot_access_team_management(self) -> None:
        """Editor role can perform operational CRUD but not team/roles/org settings."""
        self.client.force_authenticate(user=self.editor1)

        # Can create a client
        resp = self.client.post(
            f"/api/v1/orgs/{self.org1.id}/clients/",
            {"name": "Editor Client", "email": "ed@test.com"},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)

        # Cannot invite or view members
        resp = self.client.post(
            f"/api/v1/orgs/{self.org1.id}/invites/",
            {"email": "newbie@test.com", "role": "viewer"},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

        # Cannot manage roles
        resp = self.client.post(
            f"/api/v1/orgs/{self.org1.id}/roles/",
            {"name": "Custom Role"},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_admin_cannot_delete_organization(self) -> None:
        """Admin has broad powers but cannot delete the organization."""
        self.client.force_authenticate(user=self.admin1)
        resp = self.client.delete(f"/api/v1/orgs/{self.org1.id}/")
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_stock_deduction_and_restoration_lifecycle(self) -> None:
        """Stock deduction occurs on invoice send, and restores on invoice cancellation."""
        product = Product.objects.create(
            organization=self.org1,
            name="Stocked Item",
            unit_price=Decimal("50.00"),
            stock_quantity=10,
            track_stock=True,
        )
        inv = Invoice.objects.create(
            organization=self.org1,
            invoice_number="INV-2026-002",
            status=Invoice.Status.DRAFT,
            due_date=timezone.localdate(),
            subtotal=Decimal("150.00"),
            total=Decimal("150.00"),
        )
        InvoiceItem.objects.create(
            invoice=inv,
            product=product,
            description="Item",
            quantity=Decimal("3.00"),
            rate=Decimal("50.00"),
            amount=Decimal("150.00"),
        )

        self.assertEqual(product.stock_quantity, 10)

        # Send invoice -> stock deducted
        send_invoice(inv)
        inv.refresh_from_db()
        product.refresh_from_db()
        self.assertEqual(product.stock_quantity, 7)
        self.assertTrue(inv.stock_deducted)

        # Cancel invoice -> stock restored
        cancel_invoice(inv)
        inv.refresh_from_db()
        product.refresh_from_db()
        self.assertEqual(product.stock_quantity, 10)
        self.assertFalse(inv.stock_deducted)

    def test_payment_auto_settle(self) -> None:
        """AC-PAY-01: When recorded payments meet invoice total, invoice marks paid."""
        self.client.force_authenticate(user=self.owner1)

        pay_url = f"/api/v1/orgs/{self.org1.id}/invoices/{self.invoice1.id}/payments/"

        # First partial payment (100 out of 200)
        resp1 = self.client.post(
            pay_url,
            {"amount": "100.00", "payment_method": "card"},
            format="json",
        )
        self.assertEqual(resp1.status_code, status.HTTP_201_CREATED)
        self.invoice1.refresh_from_db()
        self.assertEqual(self.invoice1.status, Invoice.Status.PENDING)
        self.assertEqual(self.invoice1.balance_due, Decimal("100.00"))

        # Second payment (100 to settle)
        resp2 = self.client.post(
            pay_url,
            {"amount": "100.00", "payment_method": "bank_transfer"},
            format="json",
        )
        self.assertEqual(resp2.status_code, status.HTTP_201_CREATED)
        self.invoice1.refresh_from_db()
        self.assertEqual(self.invoice1.status, Invoice.Status.PAID)
        self.assertEqual(self.invoice1.balance_due, Decimal("0.00"))

    def test_invoice_numbering_continuity(self) -> None:
        """AC-INV-01: Numbering generates unique gapless sequence per org."""
        year = timezone.localdate().year
        num1 = generate_next_invoice_number(self.org1)
        self.assertTrue(num1.startswith(f"INV-{year}-"))

        # Ensure next number increments
        num2 = generate_next_invoice_number(self.org1)
        val1 = int(num1.split("-")[-1])
        val2 = int(num2.split("-")[-1])
        self.assertEqual(val2, val1 + 1)

    def test_global_search_is_org_scoped(self) -> None:
        """D-05: Global search returns only records belonging to the requested organization."""
        # Create identical client name in org 2
        Client.objects.create(
            organization=self.org2,
            name="Client Alpha",
            email="other_alpha@test.com",
        )

        self.client.force_authenticate(user=self.owner1)
        resp = self.client.get(f"/api/v1/orgs/{self.org1.id}/search/?q=Alpha")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

        data = resp.json()
        clients = data.get("clients", [])
        self.assertEqual(len(clients), 1)
        self.assertEqual(clients[0]["email"], "alpha@test.com")
