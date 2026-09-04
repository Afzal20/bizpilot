from __future__ import annotations

from django.contrib import admin
from unfold.admin import ModelAdmin
from unfold.admin import TabularInline

from bizpilot.erp.models import Client
from bizpilot.erp.models import Expense
from bizpilot.erp.models import Invoice
from bizpilot.erp.models import InvoiceItem
from bizpilot.erp.models import Payment
from bizpilot.erp.models import Product


class InvoiceItemInline(TabularInline):
    model = InvoiceItem
    extra = 0
    fields = ["description", "quantity", "rate", "amount"]
    readonly_fields = ["amount"]


@admin.register(Client)
class ClientAdmin(ModelAdmin):
    list_display = ["name", "company", "email", "phone", "status", "organization"]
    search_fields = ["name", "company", "email", "phone"]
    list_filter = ["status", "organization"]


@admin.register(Product)
class ProductAdmin(ModelAdmin):
    list_display = [
        "name",
        "sku",
        "category",
        "unit_price",
        "stock_quantity",
        "track_stock",
        "is_active",
        "organization",
    ]
    search_fields = ["name", "sku", "category", "description"]
    list_filter = ["is_active", "track_stock", "category", "organization"]


@admin.register(Invoice)
class InvoiceAdmin(ModelAdmin):
    list_display = [
        "invoice_number",
        "organization",
        "client",
        "status",
        "issue_date",
        "due_date",
        "total",
        "currency",
    ]
    search_fields = [
        "invoice_number",
        "client_name",
        "client_email",
        "business_name",
    ]
    list_filter = ["status", "currency", "issue_date", "organization"]
    inlines = [InvoiceItemInline]


@admin.register(Payment)
class PaymentAdmin(ModelAdmin):
    list_display = [
        "invoice",
        "amount",
        "currency",
        "payment_method",
        "payment_date",
        "reference",
        "organization",
    ]
    search_fields = ["reference", "invoice__invoice_number", "notes"]
    list_filter = ["payment_method", "payment_date", "organization"]


@admin.register(Expense)
class ExpenseAdmin(ModelAdmin):
    list_display = [
        "title",
        "category",
        "vendor",
        "amount",
        "currency",
        "expense_date",
        "payment_method",
        "organization",
    ]
    search_fields = ["title", "vendor", "notes"]
    list_filter = ["category", "payment_method", "expense_date", "organization"]
