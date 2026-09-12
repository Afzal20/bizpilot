from __future__ import annotations

from typing import TYPE_CHECKING
from typing import Any

from django.utils import timezone

from bizpilot.erp.services import get_report_data

if TYPE_CHECKING:
    from bizpilot.orgs.models import Organization

MAX_CLIENTS = 50
MAX_PRODUCTS = 50
MAX_INVOICES = 30
MAX_PAYMENTS = 30
MAX_EXPENSES = 20


def build_assistant_context(organization: Organization) -> dict[str, Any]:
    """Build the full data context the assistant reasons over."""
    data = get_report_data(organization)

    clients = organization.clients.all().order_by("name")[:MAX_CLIENTS]
    products = organization.products.all().order_by("name")[:MAX_PRODUCTS]
    invoices = (
        organization.invoices.select_related("client")
        .order_by("-issue_date", "-created_at")[:MAX_INVOICES]
    )
    payments = (
        organization.payments.select_related("invoice", "invoice__client")
        .order_by("-payment_date", "-created_at")[:MAX_PAYMENTS]
    )
    expenses = organization.expenses.order_by(
        "-expense_date",
        "-created_at",
    )[:MAX_EXPENSES]

    return {
        "today": str(timezone.localdate()),
        "organization": organization.name,
        "currency": organization.default_currency or "USD",
        "totals": data.get("totals", {}),
        "monthly_series": data.get("monthly_series", []),
        "expense_by_category": data.get("expense_by_category", [])[:8],
        "top_clients": data.get("top_clients", []),
        "clients": [
            {
                "name": c.name,
                "email": c.email,
                "phone": c.phone,
                "company": c.company,
                "address": c.address,
                "status": c.status,
            }
            for c in clients
        ],
        "products": [
            {
                "name": p.name,
                "category": p.category,
                "unit_price": float(p.unit_price),
                "currency": p.currency,
                "stock_quantity": p.stock_quantity,
                "low_stock_threshold": p.low_stock_threshold,
                "sku": p.sku,
                "is_active": p.is_active,
            }
            for p in products
        ],
        "invoices": [
            {
                "invoice_number": i.invoice_number,
                "client": i.client_name or (i.client.name if i.client else ""),
                "client_email": i.client_email,
                "status": i.status,
                "total": float(i.total),
                "balance_due": float(i.balance_due),
                "currency": i.currency,
                "issue_date": str(i.issue_date),
                "due_date": str(i.due_date),
            }
            for i in invoices
        ],
        "payments": [
            {
                "invoice_number": p.invoice.invoice_number,
                "client": (
                    p.invoice.client_name
                    or (p.invoice.client.name if p.invoice.client else "")
                ),
                "amount": float(p.amount),
                "currency": p.currency,
                "method": p.payment_method,
                "date": str(p.payment_date),
            }
            for p in payments
        ],
        "expenses": [
            {
                "title": e.title,
                "vendor": e.vendor,
                "category": e.category,
                "amount": float(e.amount),
                "currency": e.currency,
                "date": str(e.expense_date),
                "method": e.payment_method,
            }
            for e in expenses
        ],
    }
