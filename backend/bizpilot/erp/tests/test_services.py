from __future__ import annotations

from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.utils import timezone

from bizpilot.erp.models import Client
from bizpilot.erp.models import Expense
from bizpilot.erp.models import Invoice
from bizpilot.erp.models import InvoiceItem
from bizpilot.erp.models import Payment
from bizpilot.erp.models import Product
from bizpilot.erp.services import PaymentDetails
from bizpilot.erp.services import adjust_product_stock
from bizpilot.erp.services import cancel_invoice
from bizpilot.erp.services import generate_next_invoice_number
from bizpilot.erp.services import get_client_stats
from bizpilot.erp.services import get_dashboard_stats
from bizpilot.erp.services import get_report_data
from bizpilot.erp.services import global_org_search
from bizpilot.erp.services import recalculate_invoice_totals
from bizpilot.erp.services import record_invoice_payment
from bizpilot.erp.services import send_invoice
from bizpilot.orgs.models import Organization
from bizpilot.users.models import User

EXPECTED_STOCK_SENT = 15
EXPECTED_STOCK_RESTORED = 20
EXPECTED_STOCK_ADDED = 15
EXPECTED_STOCK_SUBTRACTED = 12
EXPECTED_REVENUE = 1000.0
EXPECTED_EXPENSE = 300.0
EXPECTED_PROFIT = 700.0
SERIES_LEN_6 = 6
SERIES_LEN_12 = 12


class ERPServicesTest(TestCase):
    def setUp(self) -> None:
        self.user = User.objects.create_user(
            email="service_tester@example.com",
            password="testpassword123",  # noqa: S106
            name="Service Tester",
        )
        self.org = Organization.objects.create(
            name="ERP Services Org",
            owner=self.user,
        )

    def test_invoice_number_generation_sequence(self) -> None:
        num1 = generate_next_invoice_number(self.org)
        num2 = generate_next_invoice_number(self.org)
        current_year = timezone.now().date().year

        assert num1 == f"INV-{current_year}-001"
        assert num2 == f"INV-{current_year}-002"

    def test_recalculate_invoice_totals(self) -> None:
        invoice = Invoice.objects.create(
            organization=self.org,
            invoice_number="INV-2026-TEST",
            issue_date=timezone.now().date(),
            due_date=timezone.now().date(),
            tax_rate=Decimal("10.00"),
            discount_amount=Decimal("15.00"),
        )
        InvoiceItem.objects.create(
            invoice=invoice,
            description="Item 1",
            quantity=Decimal("2.00"),
            rate=Decimal("50.00"),
        )  # 100.00
        InvoiceItem.objects.create(
            invoice=invoice,
            description="Item 2",
            quantity=Decimal("1.00"),
            rate=Decimal("100.00"),
        )  # 100.00

        recalculated = recalculate_invoice_totals(invoice)
        assert recalculated.subtotal == Decimal("200.00")
        assert recalculated.tax_amount == Decimal("20.00")
        assert recalculated.total == Decimal("205.00")

    def test_send_and_cancel_invoice_stock_deduction(self) -> None:
        product = Product.objects.create(
            organization=self.org,
            name="Widget",
            unit_price=Decimal("10.00"),
            track_stock=True,
            stock_quantity=20,
        )
        invoice = Invoice.objects.create(
            organization=self.org,
            invoice_number="INV-2026-STOCK",
            issue_date=timezone.now().date(),
            due_date=timezone.now().date() + timezone.timedelta(days=7),
            total=Decimal("50.00"),
        )
        InvoiceItem.objects.create(
            invoice=invoice,
            product=product,
            description="5 Widgets",
            quantity=Decimal("5.00"),
            rate=Decimal("10.00"),
        )

        sent_invoice = send_invoice(invoice)
        assert sent_invoice.status == Invoice.Status.PENDING
        assert sent_invoice.stock_deducted is True
        product.refresh_from_db()
        assert product.stock_quantity == EXPECTED_STOCK_SENT

        # Cancelling restores stock
        cancelled_invoice = cancel_invoice(sent_invoice)
        assert cancelled_invoice.status == Invoice.Status.CANCELLED
        assert cancelled_invoice.stock_deducted is False
        product.refresh_from_db()
        assert product.stock_quantity == EXPECTED_STOCK_RESTORED

    def test_payment_transitions_and_validation(self) -> None:
        invoice = Invoice.objects.create(
            organization=self.org,
            invoice_number="INV-2026-PAY",
            issue_date=timezone.now().date(),
            due_date=timezone.now().date() + timezone.timedelta(days=5),
            total=Decimal("100.00"),
        )

        with pytest.raises(ValidationError):
            record_invoice_payment(invoice, Decimal("0.00"))

        # Partial payment
        record_invoice_payment(
            invoice,
            Decimal("40.00"),
            PaymentDetails(payment_method=Payment.PaymentMethod.CARD),
        )
        invoice.refresh_from_db()
        assert invoice.status == Invoice.Status.PENDING
        assert invoice.paid_amount == Decimal("40.00")
        assert invoice.balance_due == Decimal("60.00")

        # Full payment settles to PAID
        record_invoice_payment(
            invoice,
            Decimal("60.00"),
            PaymentDetails(payment_method=Payment.PaymentMethod.BANK_TRANSFER),
        )
        invoice.refresh_from_db()
        assert invoice.status == Invoice.Status.PAID
        assert invoice.paid_amount == Decimal("100.00")
        assert invoice.balance_due == Decimal("0.00")

    def test_adjust_product_stock(self) -> None:
        product = Product.objects.create(
            organization=self.org,
            name="Keyboard",
            stock_quantity=10,
        )
        adjust_product_stock(product, 5)
        product.refresh_from_db()
        assert product.stock_quantity == EXPECTED_STOCK_ADDED

        adjust_product_stock(product, -3)
        product.refresh_from_db()
        assert product.stock_quantity == EXPECTED_STOCK_SUBTRACTED

    def test_client_stats(self) -> None:
        client = Client.objects.create(
            organization=self.org,
            name="Client With Stats",
        )
        inv = Invoice.objects.create(
            organization=self.org,
            client=client,
            invoice_number="INV-2026-CLI",
            issue_date=timezone.now().date(),
            due_date=timezone.now().date(),
            total=Decimal("500.00"),
        )
        record_invoice_payment(inv, Decimal("200.00"))

        stats = get_client_stats(client)
        assert stats["invoice_count"] == 1
        assert stats["total_invoiced"] == Decimal("500.00")
        assert stats["total_paid"] == Decimal("200.00")
        assert stats["outstanding"] == Decimal("300.00")

    def test_dashboard_and_reports_data(self) -> None:
        Invoice.objects.create(
            organization=self.org,
            invoice_number="INV-2026-DASH",
            issue_date=timezone.now().date(),
            due_date=timezone.now().date(),
            status=Invoice.Status.PAID,
            total=Decimal("1000.00"),
        )
        Expense.objects.create(
            organization=self.org,
            title="Office Rent",
            category=Expense.Category.RENT,
            amount=Decimal("300.00"),
        )

        dash = get_dashboard_stats(self.org)
        assert dash["total_revenue"] == EXPECTED_REVENUE
        assert dash["expenses_this_month"] == EXPECTED_EXPENSE
        assert len(dash["monthly_series"]) == SERIES_LEN_6

        report = get_report_data(self.org)
        assert report["totals"]["revenue"] == EXPECTED_REVENUE
        assert report["totals"]["expenses"] == EXPECTED_EXPENSE
        assert report["totals"]["profit"] == EXPECTED_PROFIT
        assert len(report["monthly_series"]) == SERIES_LEN_12

    def test_global_org_search(self) -> None:
        Client.objects.create(
            organization=self.org,
            name="Unique Alpha Client",
        )
        Product.objects.create(
            organization=self.org,
            name="Unique Alpha Product",
        )
        Invoice.objects.create(
            organization=self.org,
            invoice_number="INV-ALPHA-01",
            client_name="Alpha Buyer",
            issue_date=timezone.now().date(),
            due_date=timezone.now().date(),
            total=Decimal("50.00"),
        )
        Expense.objects.create(
            organization=self.org,
            title="Alpha Office Supplies",
            amount=Decimal("25.00"),
        )

        results = global_org_search(self.org, "Alpha")
        assert len(results["clients"]) == 1
        assert len(results["products"]) == 1
        assert len(results["invoices"]) == 1
        assert len(results["expenses"]) == 1

        empty = global_org_search(self.org, "NonExistentTerm")
        assert len(empty["clients"]) == 0
