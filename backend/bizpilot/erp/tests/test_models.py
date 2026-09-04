from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.test import TestCase
from django.utils import timezone

from bizpilot.erp.models import Client
from bizpilot.erp.models import Expense
from bizpilot.erp.models import Invoice
from bizpilot.erp.models import InvoiceItem
from bizpilot.erp.models import InvoiceSequence
from bizpilot.erp.models import Payment
from bizpilot.erp.models import Product
from bizpilot.orgs.models import Organization
from bizpilot.users.models import User


class ERPModelsTest(TestCase):
    def setUp(self) -> None:
        self.user = User.objects.create_user(
            email="erpowner@example.com",
            password="testpassword123",  # noqa: S106
            name="ERP Owner",
        )
        self.org = Organization.objects.create(
            name="ERP Enterprise",
            owner=self.user,
        )

    def test_client_creation(self) -> None:
        client = Client.objects.create(
            organization=self.org,
            name="Acme Corp",
            email="contact@acme.com",
            phone="+123456789",
            company="Acme Global Inc",
        )
        assert client.name == "Acme Corp"
        assert str(client) == "Acme Corp"
        assert client.status == Client.Status.ACTIVE
        assert isinstance(client.id, uuid.UUID)

    def test_product_and_low_stock_property(self) -> None:
        product = Product.objects.create(
            organization=self.org,
            name="Cloud Storage 1TB",
            unit_price=Decimal("49.99"),
            track_stock=True,
            stock_quantity=4,
            low_stock_threshold=5,
        )
        assert str(product) == "Cloud Storage 1TB"
        assert product.is_low_stock is True

        product.stock_quantity = 10
        product.save()
        assert product.is_low_stock is False

    def test_invoice_and_items_lifecycle(self) -> None:
        client = Client.objects.create(
            organization=self.org,
            name="Client 1",
            email="client1@example.com",
        )
        invoice = Invoice.objects.create(
            organization=self.org,
            client=client,
            invoice_number="INV-2026-001",
            issue_date=timezone.now().date(),
            due_date=timezone.now().date() + timezone.timedelta(days=14),
            subtotal=Decimal("200.00"),
            tax_rate=Decimal("10.00"),
            tax_amount=Decimal("20.00"),
            total=Decimal("220.00"),
        )
        assert invoice.invoice_number == "INV-2026-001"
        assert invoice.status == Invoice.Status.DRAFT
        assert invoice.paid_amount == Decimal("0.00")
        assert invoice.balance_due == Decimal("220.00")

        item = InvoiceItem.objects.create(
            invoice=invoice,
            description="Consulting Hour",
            quantity=Decimal("2.00"),
            rate=Decimal("100.00"),
        )
        assert item.amount == Decimal("200.00")
        assert "Consulting Hour" in str(item)

        # Add payment
        Payment.objects.create(
            organization=self.org,
            invoice=invoice,
            amount=Decimal("100.00"),
            payment_method=Payment.PaymentMethod.BANK_TRANSFER,
        )
        assert invoice.paid_amount == Decimal("100.00")
        assert invoice.balance_due == Decimal("120.00")

    def test_duplicate_invoice_number_in_same_org_fails(self) -> None:
        Invoice.objects.create(
            organization=self.org,
            invoice_number="INV-2026-999",
            issue_date=timezone.now().date(),
            due_date=timezone.now().date(),
            total=Decimal("100.00"),
        )
        with pytest.raises((IntegrityError, ValidationError)):
            Invoice.objects.create(
                organization=self.org,
                invoice_number="INV-2026-999",
                issue_date=timezone.now().date(),
                due_date=timezone.now().date(),
                total=Decimal("100.00"),
            )

    def test_expense_creation(self) -> None:
        expense = Expense.objects.create(
            organization=self.org,
            title="AWS Hosting",
            category=Expense.Category.SOFTWARE,
            amount=Decimal("150.00"),
            vendor="Amazon Web Services",
        )
        assert expense.title == "AWS Hosting"
        assert "AWS Hosting" in str(expense)
        assert expense.category == Expense.Category.SOFTWARE

    def test_invoice_sequence_unique_together(self) -> None:
        InvoiceSequence.objects.create(
            organization=self.org,
            year=2026,
            last_number=5,
        )
        with pytest.raises(IntegrityError):
            InvoiceSequence.objects.create(
                organization=self.org,
                year=2026,
                last_number=6,
            )
