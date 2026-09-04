from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import TYPE_CHECKING
from typing import Any

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Count
from django.db.models import Q
from django.db.models import Sum
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from bizpilot.erp.models import Client
from bizpilot.erp.models import Expense
from bizpilot.erp.models import Invoice
from bizpilot.erp.models import InvoiceSequence
from bizpilot.erp.models import Payment
from bizpilot.erp.models import Product

if TYPE_CHECKING:
    from datetime import date

    from bizpilot.orgs.models import Organization
    from bizpilot.users.models import User


def generate_next_invoice_number(
    organization: Organization,
    issue_date: date | None = None,
) -> str:
    target_date = issue_date or timezone.now().date()
    year = target_date.year

    with transaction.atomic():
        seq, _ = InvoiceSequence.objects.select_for_update().get_or_create(
            organization=organization,
            year=year,
            defaults={"last_number": 0},
        )
        seq.last_number += 1
        seq.save(update_fields=["last_number", "updated_at"])
        return f"INV-{year}-{seq.last_number:03d}"


def recalculate_invoice_totals(
    invoice: Invoice,
    *,
    save: bool = True,
) -> Invoice:
    subtotal = Decimal("0.00")
    for item in invoice.items.all():
        subtotal += item.amount

    tax_rate = invoice.tax_rate or Decimal("0.00")
    tax_amount = (subtotal * tax_rate) / Decimal("100.00")
    discount_amount = invoice.discount_amount or Decimal("0.00")
    total = max(Decimal("0.00"), subtotal + tax_amount - discount_amount)

    invoice.subtotal = subtotal
    invoice.tax_amount = tax_amount
    invoice.total = total

    if save:
        invoice.save(
            update_fields=[
                "subtotal",
                "tax_amount",
                "total",
                "updated_at",
            ],
        )

    return invoice


def send_invoice(
    invoice: Invoice,
    actor: User | None = None,
) -> Invoice:
    del actor
    with transaction.atomic():
        invoice = Invoice.objects.select_for_update().get(id=invoice.id)
        if not invoice.stock_deducted:
            for item in invoice.items.select_related("product"):
                if item.product and item.product.track_stock:
                    item.product.stock_quantity -= int(item.quantity)
                    item.product.save(
                        update_fields=["stock_quantity", "updated_at"],
                    )
            invoice.stock_deducted = True

        today = timezone.now().date()
        if invoice.due_date < today:
            invoice.status = Invoice.Status.OVERDUE
        else:
            invoice.status = Invoice.Status.PENDING

        invoice.save(
            update_fields=[
                "status",
                "stock_deducted",
                "updated_at",
            ],
        )

    return invoice


def cancel_invoice(
    invoice: Invoice,
    actor: User | None = None,
) -> Invoice:
    del actor
    with transaction.atomic():
        invoice = Invoice.objects.select_for_update().get(id=invoice.id)
        if invoice.status == Invoice.Status.CANCELLED:
            return invoice

        if invoice.stock_deducted:
            for item in invoice.items.select_related("product"):
                if item.product and item.product.track_stock:
                    item.product.stock_quantity += int(item.quantity)
                    item.product.save(
                        update_fields=["stock_quantity", "updated_at"],
                    )
            invoice.stock_deducted = False

        invoice.status = Invoice.Status.CANCELLED
        invoice.save(
            update_fields=[
                "status",
                "stock_deducted",
                "updated_at",
            ],
        )

    return invoice


@dataclass
class PaymentDetails:
    payment_method: str = Payment.PaymentMethod.BANK_TRANSFER
    payment_date: date | None = None
    reference: str = ""
    notes: str = ""
    recorded_by: User | None = None


def record_invoice_payment(
    invoice: Invoice,
    amount: Decimal,
    details: PaymentDetails | None = None,
) -> Payment:
    if amount <= Decimal("0.00"):
        raise ValidationError(_("Payment amount must be greater than zero."))

    pay_details = details or PaymentDetails()

    with transaction.atomic():
        invoice = Invoice.objects.select_for_update().get(id=invoice.id)

        payment = Payment.objects.create(
            organization=invoice.organization,
            invoice=invoice,
            amount=amount,
            currency=invoice.currency,
            payment_method=pay_details.payment_method,
            payment_date=pay_details.payment_date or timezone.now().date(),
            reference=pay_details.reference,
            notes=pay_details.notes,
            recorded_by=pay_details.recorded_by,
        )

        total_paid = (
            invoice.payments.aggregate(Sum("amount"))["amount__sum"] or Decimal("0.00")
        )

        if total_paid >= invoice.total:
            invoice.status = Invoice.Status.PAID
        elif invoice.status == Invoice.Status.DRAFT:
            if not invoice.stock_deducted:
                for item in invoice.items.select_related("product"):
                    if item.product and item.product.track_stock:
                        item.product.stock_quantity -= int(item.quantity)
                        item.product.save(
                            update_fields=["stock_quantity", "updated_at"],
                        )
                invoice.stock_deducted = True

            today = timezone.now().date()
            if invoice.due_date < today:
                invoice.status = Invoice.Status.OVERDUE
            else:
                invoice.status = Invoice.Status.PENDING

        invoice.save(
            update_fields=[
                "status",
                "stock_deducted",
                "updated_at",
            ],
        )

    return payment


def adjust_product_stock(
    product: Product,
    quantity_delta: int,
    *,
    reason: str = "",
    actor: User | None = None,
) -> Product:
    del reason, actor
    with transaction.atomic():
        product = Product.objects.select_for_update().get(id=product.id)
        product.stock_quantity += quantity_delta
        product.save(update_fields=["stock_quantity", "updated_at"])
    return product


def get_client_stats(client: Client) -> dict[str, Any]:
    invoices = client.invoices.all()
    count = invoices.count()
    total_invoiced = (
        invoices.aggregate(total=Sum("total"))["total"] or Decimal("0.00")
    )
    total_paid = (
        Payment.objects.filter(invoice__client=client).aggregate(
            paid=Sum("amount"),
        )["paid"]
        or Decimal("0.00")
    )
    outstanding = max(Decimal("0.00"), total_invoiced - total_paid)

    return {
        "client_id": client.id,
        "invoice_count": count,
        "total_invoiced": total_invoiced,
        "total_paid": total_paid,
        "outstanding": outstanding,
    }


def _last_n_months(count: int) -> list[str]:
    now = timezone.now().date()
    months = []
    for i in range(count - 1, -1, -1):
        year = now.year
        month = now.month - i
        while month <= 0:
            month += 12
            year -= 1
        months.append(f"{year:04d}-{month:02d}")
    return months


def get_dashboard_stats(organization: Organization) -> dict[str, Any]:
    today = timezone.now().date()
    current_month_str = f"{today.year:04d}-{today.month:02d}"

    invoices = list(organization.invoices.all())
    expenses = list(organization.expenses.all())
    client_count = organization.clients.count()
    products = list(organization.products.all())

    total_revenue = Decimal("0.00")
    outstanding = Decimal("0.00")
    overdue_count = 0
    revenue_this_month = Decimal("0.00")

    for inv in invoices:
        inv_month = f"{inv.issue_date.year:04d}-{inv.issue_date.month:02d}"
        if inv.status == Invoice.Status.PAID:
            total_revenue += inv.total
            if inv_month == current_month_str:
                revenue_this_month += inv.total
        elif inv.status in (Invoice.Status.PENDING, Invoice.Status.OVERDUE):
            outstanding += inv.balance_due
            if inv.due_date < today:
                overdue_count += 1

    expenses_this_month = Decimal("0.00")
    for exp in expenses:
        exp_month = f"{exp.expense_date.year:04d}-{exp.expense_date.month:02d}"
        if exp_month == current_month_str:
            expenses_this_month += exp.amount

    months_6 = _last_n_months(6)
    monthly_series = []
    for m in months_6:
        rev_m = sum(
            (
                inv.total
                for inv in invoices
                if inv.status == Invoice.Status.PAID
                and f"{inv.issue_date.year:04d}-{inv.issue_date.month:02d}" == m
            ),
            Decimal("0.00"),
        )
        exp_m = sum(
            (
                exp.amount
                for exp in expenses
                if f"{exp.expense_date.year:04d}-{exp.expense_date.month:02d}" == m
            ),
            Decimal("0.00"),
        )
        monthly_series.append(
            {
                "month": m,
                "revenue": float(rev_m),
                "expenses": float(exp_m),
            },
        )

    low_stock_products = [p for p in products if p.is_low_stock]

    return {
        "total_revenue": float(total_revenue),
        "outstanding": float(outstanding),
        "overdue_count": overdue_count,
        "expenses_this_month": float(expenses_this_month),
        "revenue_this_month": float(revenue_this_month),
        "net_profit_this_month": float(revenue_this_month - expenses_this_month),
        "invoice_count": len(invoices),
        "client_count": client_count,
        "product_count": len(products),
        "low_stock_count": len(low_stock_products),
        "monthly_series": monthly_series,
        "recent_invoices": [
            {
                "id": str(i.id),
                "invoice_number": i.invoice_number,
                "client_name": i.client_name or (i.client.name if i.client else ""),
                "status": i.status,
                "total": float(i.total),
                "due_date": str(i.due_date),
            }
            for i in sorted(invoices, key=lambda x: x.created_at, reverse=True)[:8]
        ],
        "recent_expenses": [
            {
                "id": str(e.id),
                "title": e.title,
                "category": e.category,
                "amount": float(e.amount),
                "expense_date": str(e.expense_date),
            }
            for e in sorted(expenses, key=lambda x: x.expense_date, reverse=True)[:5]
        ],
        "low_stock_products": [
            {
                "id": str(p.id),
                "name": p.name,
                "stock_quantity": p.stock_quantity,
                "low_stock_threshold": p.low_stock_threshold,
            }
            for p in low_stock_products[:5]
        ],
    }


def get_report_data(organization: Organization) -> dict[str, Any]:
    invoices = list(organization.invoices.all())
    expenses = list(organization.expenses.all())

    months_12 = _last_n_months(12)
    monthly_series = []
    for m in months_12:
        rev_m = sum(
            (
                inv.total
                for inv in invoices
                if inv.status == Invoice.Status.PAID
                and f"{inv.issue_date.year:04d}-{inv.issue_date.month:02d}" == m
            ),
            Decimal("0.00"),
        )
        exp_m = sum(
            (
                exp.amount
                for exp in expenses
                if f"{exp.expense_date.year:04d}-{exp.expense_date.month:02d}" == m
            ),
            Decimal("0.00"),
        )
        monthly_series.append(
            {
                "month": m,
                "revenue": float(rev_m),
                "expenses": float(exp_m),
                "profit": float(rev_m - exp_m),
            },
        )

    cat_map: dict[str, Decimal] = {}
    for exp in expenses:
        cat_map[exp.category] = cat_map.get(exp.category, Decimal("0.00")) + exp.amount

    expense_by_category = sorted(
        [
            {"category": cat, "amount": float(amt)}
            for cat, amt in cat_map.items()
        ],
        key=lambda x: x["amount"],
        reverse=True,
    )

    client_totals = (
        Client.objects.filter(organization=organization)
        .annotate(
            total_sum=Sum("invoices__total"),
            inv_count=Count("invoices"),
        )
        .order_by("-total_sum")[:5]
    )

    top_clients = [
        {
            "name": c.name,
            "total": float(c.total_sum or 0),
            "invoice_count": c.inv_count,
        }
        for c in client_totals
    ]

    total_rev = sum(
        (inv.total for inv in invoices if inv.status == Invoice.Status.PAID),
        Decimal("0.00"),
    )
    total_exp = sum((e.amount for e in expenses), Decimal("0.00"))
    outstanding = sum(
        (
            inv.balance_due
            for inv in invoices
            if inv.status in (Invoice.Status.PENDING, Invoice.Status.OVERDUE)
        ),
        Decimal("0.00"),
    )
    paid_count = sum(1 for inv in invoices if inv.status == Invoice.Status.PAID)

    return {
        "monthly_series": monthly_series,
        "expense_by_category": expense_by_category,
        "top_clients": top_clients,
        "totals": {
            "revenue": float(total_rev),
            "expenses": float(total_exp),
            "profit": float(total_rev - total_exp),
            "outstanding": float(outstanding),
            "invoice_count": len(invoices),
            "paid_count": paid_count,
        },
    }


def global_org_search(
    organization: Organization,
    query: str,
) -> dict[str, list[dict[str, Any]]]:
    q = query.strip()
    if not q:
        return {
            "clients": [],
            "products": [],
            "invoices": [],
            "expenses": [],
        }

    clients = Client.objects.filter(
        organization=organization,
    ).filter(
        Q(name__icontains=q)
        | Q(email__icontains=q)
        | Q(company__icontains=q)
        | Q(phone__icontains=q),
    )[:5]

    products = Product.objects.filter(
        organization=organization,
    ).filter(
        Q(name__icontains=q)
        | Q(sku__icontains=q)
        | Q(category__icontains=q)
        | Q(description__icontains=q),
    )[:5]

    invoices = Invoice.objects.filter(
        organization=organization,
    ).filter(
        Q(invoice_number__icontains=q)
        | Q(client_name__icontains=q)
        | Q(client_email__icontains=q),
    )[:5]

    expenses = Expense.objects.filter(
        organization=organization,
    ).filter(
        Q(title__icontains=q)
        | Q(vendor__icontains=q)
        | Q(category__icontains=q),
    )[:5]

    return {
        "clients": [
            {
                "id": str(c.id),
                "name": c.name,
                "email": c.email,
                "company": c.company,
            }
            for c in clients
        ],
        "products": [
            {
                "id": str(p.id),
                "name": p.name,
                "sku": p.sku,
                "unit_price": float(p.unit_price),
            }
            for p in products
        ],
        "invoices": [
            {
                "id": str(i.id),
                "invoice_number": i.invoice_number,
                "client_name": i.client_name,
                "status": i.status,
                "total": float(i.total),
            }
            for i in invoices
        ],
        "expenses": [
            {
                "id": str(e.id),
                "title": e.title,
                "category": e.category,
                "amount": float(e.amount),
            }
            for e in expenses
        ],
    }
