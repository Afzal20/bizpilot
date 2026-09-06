from __future__ import annotations

from decimal import Decimal
from typing import Any

from django.db import transaction
from rest_framework import serializers

from bizpilot.erp.models import Client
from bizpilot.erp.models import Expense
from bizpilot.erp.models import Invoice
from bizpilot.erp.models import InvoiceItem
from bizpilot.erp.models import Payment
from bizpilot.erp.models import Product
from bizpilot.erp.services import generate_next_invoice_number
from bizpilot.erp.services import get_client_stats
from bizpilot.erp.services import recalculate_invoice_totals


class ClientSerializer(serializers.ModelSerializer):
    class Meta:
        model = Client
        fields = [
            "id",
            "name",
            "email",
            "phone",
            "address",
            "company",
            "status",
            "notes",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]


class ClientWithStatsSerializer(ClientSerializer):
    invoice_count = serializers.IntegerField(read_only=True)
    total_invoiced = serializers.DecimalField(
        max_digits=12,
        decimal_places=2,
        read_only=True,
    )
    total_paid = serializers.DecimalField(
        max_digits=12,
        decimal_places=2,
        read_only=True,
    )
    outstanding = serializers.DecimalField(
        max_digits=12,
        decimal_places=2,
        read_only=True,
    )

    class Meta(ClientSerializer.Meta):
        fields = [
            *ClientSerializer.Meta.fields,
            "invoice_count",
            "total_invoiced",
            "total_paid",
            "outstanding",
        ]

    def to_representation(self, instance: Client) -> dict[str, Any]:
        data = super().to_representation(instance)
        stats = get_client_stats(instance)
        data["invoice_count"] = stats["invoice_count"]
        data["total_invoiced"] = stats["total_invoiced"]
        data["total_paid"] = stats["total_paid"]
        data["outstanding"] = stats["outstanding"]
        return data


class ProductSerializer(serializers.ModelSerializer):
    is_low_stock = serializers.BooleanField(read_only=True)

    class Meta:
        model = Product
        fields = [
            "id",
            "name",
            "description",
            "unit_price",
            "currency",
            "category",
            "unit",
            "sku",
            "stock_quantity",
            "low_stock_threshold",
            "track_stock",
            "is_active",
            "is_low_stock",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "is_low_stock", "created_at", "updated_at"]


class AdjustStockSerializer(serializers.Serializer):
    quantity_delta = serializers.IntegerField()
    reason = serializers.CharField(required=False, allow_blank=True, default="")


class InvoiceItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = InvoiceItem
        fields = [
            "id",
            "product",
            "description",
            "quantity",
            "rate",
            "amount",
            "created_at",
        ]
        read_only_fields = ["id", "amount", "created_at"]


class InvoicePaymentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Payment
        fields = [
            "id",
            "amount",
            "currency",
            "payment_method",
            "payment_date",
            "reference",
            "notes",
            "created_at",
        ]
        read_only_fields = ["id", "created_at"]


class InvoiceSerializer(serializers.ModelSerializer):
    organization_id = serializers.UUIDField(read_only=True)
    items = InvoiceItemSerializer(many=True, required=False)
    payments = InvoicePaymentSerializer(many=True, read_only=True)
    paid_amount = serializers.DecimalField(
        max_digits=12,
        decimal_places=2,
        read_only=True,
    )
    balance_due = serializers.DecimalField(
        max_digits=12,
        decimal_places=2,
        read_only=True,
    )

    class Meta:
        model = Invoice
        fields = [
            "id",
            "organization_id",
            "client",
            "invoice_number",
            "status",
            "issue_date",
            "due_date",
            "currency",
            "subtotal",
            "tax_rate",
            "tax_amount",
            "discount_amount",
            "total",
            "paid_amount",
            "balance_due",
            "notes",
            "terms",
            "business_name",
            "business_email",
            "business_address",
            "business_phone",
            "client_name",
            "client_email",
            "client_address",
            "stock_deducted",
            "items",
            "payments",
            "created_by",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "organization_id",
            "paid_amount",
            "balance_due",
            "stock_deducted",
            "created_by",
            "created_at",
            "updated_at",
        ]
        extra_kwargs = {
            "invoice_number": {"required": False, "allow_blank": True},
        }

    def _set_business_snapshots(
        self,
        data: dict[str, Any],
        org: Any,
    ) -> None:
        data.setdefault("business_name", org.name)
        data.setdefault("business_email", org.company_email)
        data.setdefault("business_address", org.company_address)
        data.setdefault("business_phone", org.company_phone)

    def _set_client_snapshots(self, data: dict[str, Any]) -> None:
        client = data.get("client")
        if client:
            data.setdefault("client_name", client.name)
            data.setdefault("client_email", client.email)
            data.setdefault("client_address", client.address)

    def create(self, validated_data: dict[str, Any]) -> Invoice:
        items_data = validated_data.pop("items", [])
        org = (
            validated_data.get("organization")
            or self.context["view"].get_organization()
        )
        validated_data["organization"] = org

        if not validated_data.get("invoice_number"):
            validated_data["invoice_number"] = generate_next_invoice_number(
                org,
                validated_data.get("issue_date"),
            )

        self._set_business_snapshots(validated_data, org)
        self._set_client_snapshots(validated_data)

        request = self.context.get("request")
        if request and request.user and request.user.is_authenticated:
            validated_data["created_by"] = request.user

        with transaction.atomic():
            invoice = Invoice.objects.create(**validated_data)
            for item_data in items_data:
                InvoiceItem.objects.create(invoice=invoice, **item_data)
            recalculate_invoice_totals(invoice)

        return invoice

    def update(self, instance: Invoice, validated_data: dict[str, Any]) -> Invoice:
        items_data = validated_data.pop("items", None)

        with transaction.atomic():
            for attr, value in validated_data.items():
                setattr(instance, attr, value)
            instance.save()

            if items_data is not None:
                instance.items.all().delete()
                for item_data in items_data:
                    InvoiceItem.objects.create(invoice=instance, **item_data)
                recalculate_invoice_totals(instance)

        return instance


class PaymentCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Payment
        fields = [
            "id",
            "invoice",
            "amount",
            "currency",
            "payment_method",
            "payment_date",
            "reference",
            "notes",
            "recorded_by",
            "created_at",
        ]
        read_only_fields = ["id", "recorded_by", "created_at"]

    def validate_amount(self, value: Decimal) -> Decimal:
        if value <= Decimal("0.00"):
            msg = "Payment amount must be greater than zero."
            raise serializers.ValidationError(msg)
        return value


class ExpenseSerializer(serializers.ModelSerializer):
    class Meta:
        model = Expense
        fields = [
            "id",
            "title",
            "category",
            "vendor",
            "amount",
            "currency",
            "expense_date",
            "payment_method",
            "receipt_url",
            "notes",
            "created_by",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "created_by",
            "created_at",
            "updated_at",
        ]

    def create(self, validated_data: dict[str, Any]) -> Expense:
        request = self.context.get("request")
        if request and request.user and request.user.is_authenticated:
            validated_data["created_by"] = request.user
        return super().create(validated_data)
