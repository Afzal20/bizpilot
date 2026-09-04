from __future__ import annotations

from decimal import Decimal

from django.conf import settings
from django.db import models
from django.db.models import Sum
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from bizpilot.core.models import TimestampedModel
from bizpilot.core.models import UUIDModel


class Client(UUIDModel, TimestampedModel):
    class Status(models.TextChoices):
        ACTIVE = "active", _("Active")
        INACTIVE = "inactive", _("Inactive")

    organization = models.ForeignKey(
        "orgs.Organization",
        on_delete=models.CASCADE,
        related_name="clients",
        verbose_name=_("organization"),
    )
    name = models.CharField(_("name"), max_length=255)
    email = models.EmailField(_("email address"), blank=True, default="")
    phone = models.CharField(_("phone number"), max_length=50, blank=True, default="")
    address = models.TextField(_("billing address"), blank=True, default="")
    company = models.CharField(
        _("company name"),
        max_length=255,
        blank=True,
        default="",
    )
    status = models.CharField(
        _("status"),
        max_length=20,
        choices=Status.choices,
        default=Status.ACTIVE,
        db_index=True,
    )
    notes = models.TextField(_("notes"), blank=True, default="")

    class Meta:
        verbose_name = _("client")
        verbose_name_plural = _("clients")
        ordering = ["name"]
        indexes = [
            models.Index(
                fields=["organization", "status"],
                name="idx_client_org_status",
            ),
        ]

    def __str__(self) -> str:
        return self.name


class Product(UUIDModel, TimestampedModel):
    organization = models.ForeignKey(
        "orgs.Organization",
        on_delete=models.CASCADE,
        related_name="products",
        verbose_name=_("organization"),
    )
    name = models.CharField(_("product name"), max_length=255)
    description = models.TextField(_("description"), blank=True, default="")
    unit_price = models.DecimalField(
        _("unit price"),
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
    )
    currency = models.CharField(_("currency"), max_length=3, default="USD")
    category = models.CharField(
        _("category"),
        max_length=100,
        blank=True,
        default="",
        db_index=True,
    )
    unit = models.CharField(_("unit"), max_length=50, blank=True, default="item")
    sku = models.CharField(
        _("SKU"),
        max_length=100,
        blank=True,
        default="",
        db_index=True,
    )
    stock_quantity = models.IntegerField(_("stock quantity"), default=0)
    low_stock_threshold = models.IntegerField(
        _("low stock threshold"),
        default=5,
    )
    track_stock = models.BooleanField(_("track stock"), default=False)
    is_active = models.BooleanField(_("is active"), default=True, db_index=True)

    class Meta:
        verbose_name = _("product")
        verbose_name_plural = _("products")
        ordering = ["name"]
        indexes = [
            models.Index(
                fields=["organization", "is_active"],
                name="idx_product_org_active",
            ),
        ]

    def __str__(self) -> str:
        return self.name

    @property
    def is_low_stock(self) -> bool:
        return self.track_stock and self.stock_quantity <= self.low_stock_threshold


class InvoiceSequence(UUIDModel, TimestampedModel):
    organization = models.ForeignKey(
        "orgs.Organization",
        on_delete=models.CASCADE,
        related_name="invoice_sequences",
        verbose_name=_("organization"),
    )
    year = models.PositiveIntegerField(_("year"))
    last_number = models.PositiveIntegerField(_("last number"), default=0)

    class Meta:
        verbose_name = _("invoice sequence")
        verbose_name_plural = _("invoice sequences")
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "year"],
                name="unique_org_year_invoice_sequence",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.organization_id} - {self.year}: {self.last_number}"


class Invoice(UUIDModel, TimestampedModel):
    class Status(models.TextChoices):
        DRAFT = "draft", _("Draft")
        PENDING = "pending", _("Pending")
        PAID = "paid", _("Paid")
        OVERDUE = "overdue", _("Overdue")
        CANCELLED = "cancelled", _("Cancelled")

    organization = models.ForeignKey(
        "orgs.Organization",
        on_delete=models.CASCADE,
        related_name="invoices",
        verbose_name=_("organization"),
    )
    client = models.ForeignKey(
        Client,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="invoices",
        verbose_name=_("client"),
    )
    invoice_number = models.CharField(
        _("invoice number"),
        max_length=50,
        db_index=True,
    )
    status = models.CharField(
        _("status"),
        max_length=20,
        choices=Status.choices,
        default=Status.DRAFT,
        db_index=True,
    )
    issue_date = models.DateField(_("issue date"), default=timezone.localdate)
    due_date = models.DateField(_("due date"))
    currency = models.CharField(_("currency"), max_length=3, default="USD")

    subtotal = models.DecimalField(
        _("subtotal"),
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
    )
    tax_rate = models.DecimalField(
        _("tax rate (%)"),
        max_digits=5,
        decimal_places=2,
        default=Decimal("0.00"),
    )
    tax_amount = models.DecimalField(
        _("tax amount"),
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
    )
    discount_amount = models.DecimalField(
        _("discount amount"),
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
    )
    total = models.DecimalField(
        _("total"),
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
    )

    notes = models.TextField(_("notes"), blank=True, default="")
    terms = models.TextField(_("terms"), blank=True, default="")

    business_name = models.CharField(
        _("business name snapshot"),
        max_length=255,
        blank=True,
        default="",
    )
    business_email = models.CharField(
        _("business email snapshot"),
        max_length=255,
        blank=True,
        default="",
    )
    business_address = models.TextField(
        _("business address snapshot"),
        blank=True,
        default="",
    )
    business_phone = models.CharField(
        _("business phone snapshot"),
        max_length=50,
        blank=True,
        default="",
    )

    client_name = models.CharField(
        _("client name snapshot"),
        max_length=255,
        blank=True,
        default="",
    )
    client_email = models.CharField(
        _("client email snapshot"),
        max_length=255,
        blank=True,
        default="",
    )
    client_address = models.TextField(
        _("client address snapshot"),
        blank=True,
        default="",
    )

    stock_deducted = models.BooleanField(
        _("stock deducted"),
        default=False,
    )

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="invoices_created",
        verbose_name=_("created by"),
    )

    class Meta:
        verbose_name = _("invoice")
        verbose_name_plural = _("invoices")
        ordering = ["-issue_date", "-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "invoice_number"],
                name="unique_org_invoice_number",
            ),
        ]
        indexes = [
            models.Index(
                fields=["organization", "status"],
                name="idx_invoice_org_status",
            ),
            models.Index(
                fields=["organization", "issue_date"],
                name="idx_invoice_org_issue_date",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.invoice_number} ({self.status})"

    @property
    def paid_amount(self) -> Decimal:
        result = self.payments.aggregate(total_paid=Sum("amount"))["total_paid"]
        return result or Decimal("0.00")

    @property
    def balance_due(self) -> Decimal:
        due = self.total - self.paid_amount
        return max(Decimal("0.00"), due)


class InvoiceItem(UUIDModel, TimestampedModel):
    invoice = models.ForeignKey(
        Invoice,
        on_delete=models.CASCADE,
        related_name="items",
        verbose_name=_("invoice"),
    )
    product = models.ForeignKey(
        Product,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="invoice_items",
        verbose_name=_("product"),
    )
    description = models.CharField(_("description"), max_length=500)
    quantity = models.DecimalField(
        _("quantity"),
        max_digits=10,
        decimal_places=2,
        default=Decimal("1.00"),
    )
    rate = models.DecimalField(
        _("unit rate"),
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
    )
    amount = models.DecimalField(
        _("line total"),
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
    )

    class Meta:
        verbose_name = _("invoice item")
        verbose_name_plural = _("invoice items")
        ordering = ["created_at"]

    def __str__(self) -> str:
        return f"{self.description} ({self.quantity} x {self.rate})"

    def save(self, *args: object, **kwargs: object) -> None:
        self.amount = Decimal(str(self.quantity)) * Decimal(str(self.rate))
        super().save(*args, **kwargs)


class Payment(UUIDModel, TimestampedModel):
    class PaymentMethod(models.TextChoices):
        CASH = "cash", _("Cash")
        CARD = "card", _("Card")
        BANK_TRANSFER = "bank_transfer", _("Bank Transfer")
        MOBILE_MONEY = "mobile_money", _("Mobile Money")
        OTHER = "other", _("Other")

    organization = models.ForeignKey(
        "orgs.Organization",
        on_delete=models.CASCADE,
        related_name="payments",
        verbose_name=_("organization"),
    )
    invoice = models.ForeignKey(
        Invoice,
        on_delete=models.CASCADE,
        related_name="payments",
        verbose_name=_("invoice"),
    )
    amount = models.DecimalField(
        _("payment amount"),
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
    )
    currency = models.CharField(_("currency"), max_length=3, default="USD")
    payment_method = models.CharField(
        _("payment method"),
        max_length=50,
        choices=PaymentMethod.choices,
        default=PaymentMethod.BANK_TRANSFER,
    )
    payment_date = models.DateField(_("payment date"), default=timezone.localdate)
    reference = models.CharField(
        _("reference number"),
        max_length=255,
        blank=True,
        default="",
    )
    notes = models.TextField(_("notes"), blank=True, default="")
    recorded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="payments_recorded",
        verbose_name=_("recorded by"),
    )

    class Meta:
        verbose_name = _("payment")
        verbose_name_plural = _("payments")
        ordering = ["-payment_date", "-created_at"]
        indexes = [
            models.Index(
                fields=["organization", "payment_date"],
                name="idx_payment_org_date",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.amount} {self.currency} for {self.invoice.invoice_number}"


class Expense(UUIDModel, TimestampedModel):
    class Category(models.TextChoices):
        RENT = "rent", _("Rent")
        UTILITIES = "utilities", _("Utilities")
        SALARIES = "salaries", _("Salaries")
        MARKETING = "marketing", _("Marketing")
        SUPPLIES = "supplies", _("Supplies")
        SOFTWARE = "software", _("Software")
        TRAVEL = "travel", _("Travel")
        TAXES = "taxes", _("Taxes")
        OTHER = "other", _("Other")

    organization = models.ForeignKey(
        "orgs.Organization",
        on_delete=models.CASCADE,
        related_name="expenses",
        verbose_name=_("organization"),
    )
    title = models.CharField(_("expense title"), max_length=255)
    category = models.CharField(
        _("expense category"),
        max_length=50,
        choices=Category.choices,
        default=Category.OTHER,
        db_index=True,
    )
    vendor = models.CharField(
        _("vendor / merchant"),
        max_length=255,
        blank=True,
        default="",
    )
    amount = models.DecimalField(
        _("amount"),
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
    )
    currency = models.CharField(_("currency"), max_length=3, default="USD")
    expense_date = models.DateField(_("expense date"), default=timezone.localdate)
    payment_method = models.CharField(
        _("payment method"),
        max_length=50,
        choices=Payment.PaymentMethod.choices,
        default=Payment.PaymentMethod.CARD,
    )
    receipt_url = models.URLField(
        _("receipt URL"),
        max_length=1024,
        blank=True,
        default="",
    )
    notes = models.TextField(_("notes"), blank=True, default="")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="expenses_created",
        verbose_name=_("created by"),
    )

    class Meta:
        verbose_name = _("expense")
        verbose_name_plural = _("expenses")
        ordering = ["-expense_date", "-created_at"]
        indexes = [
            models.Index(
                fields=["organization", "category"],
                name="idx_expense_org_category",
            ),
            models.Index(
                fields=["organization", "expense_date"],
                name="idx_expense_org_date",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.title} - {self.amount} {self.currency}"
