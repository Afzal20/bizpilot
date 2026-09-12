from __future__ import annotations

import json
from datetime import date
from datetime import timedelta
from decimal import Decimal
from decimal import InvalidOperation
from typing import TYPE_CHECKING
from typing import Any

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from bizpilot.ai.context import build_assistant_context
from bizpilot.ai.gateway import extract_json_object
from bizpilot.ai.gateway import get_cached_or_complete
from bizpilot.ai.gateway import get_llm_provider
from bizpilot.ai.services import _log_ai_usage
from bizpilot.billing.engine import enforce
from bizpilot.billing.engine import meter
from bizpilot.erp.models import Client
from bizpilot.erp.models import Expense
from bizpilot.erp.models import Invoice
from bizpilot.erp.models import InvoiceItem
from bizpilot.erp.models import Payment
from bizpilot.erp.models import Product
from bizpilot.erp.services import PaymentDetails
from bizpilot.erp.services import generate_next_invoice_number
from bizpilot.erp.services import recalculate_invoice_totals
from bizpilot.erp.services import record_invoice_payment

if TYPE_CHECKING:
    from bizpilot.orgs.models import Organization
    from bizpilot.users.models import User

MAX_INSTRUCTION_LEN = 2000
MAX_HISTORY_MESSAGES = 8
DEFAULT_DUE_DAYS = 30

KNOWN_TOOLS = (
    "add_client",
    "add_product",
    "create_invoice",
    "record_payment",
    "add_expense",
)


def _required_str(
    args: dict[str, Any],
    key: str,
    label: str,
    max_len: int = 255,
) -> str:
    value = str(args.get(key, "")).strip()
    if not value:
        msg = f"{label} is required."
        raise ValidationError(msg)
    return value[:max_len]


def _optional_str(args: dict[str, Any], key: str, max_len: int = 255) -> str:
    return str(args.get(key, "")).strip()[:max_len]


def _to_decimal(value: Any, label: str) -> Decimal:
    try:
        result = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        msg = f"{label} must be a number."
        raise ValidationError(msg) from None
    if result < 0:
        msg = f"{label} cannot be negative."
        raise ValidationError(msg)
    return result


def _to_int(value: Any, label: str) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        msg = f"{label} must be an integer."
        raise ValidationError(msg) from None


def _to_date(value: Any) -> date | None:
    if not value:
        return None
    try:
        return timezone.localdate().fromisoformat(str(value))
    except (TypeError, ValueError):
        return None


def _payment_method(value: Any) -> str:
    raw = str(value or "").strip().lower()
    return (
        raw
        if raw in Payment.PaymentMethod.values
        else Payment.PaymentMethod.BANK_TRANSFER
    )


def _expense_category(value: Any) -> str:
    raw = str(value or "").strip().lower()
    return raw if raw in Expense.Category.values else Expense.Category.OTHER


def _resolve_client(
    organization: Organization,
    args: dict[str, Any],
) -> Client | None:
    client_id = args.get("client_id")
    if client_id:
        client = Client.objects.filter(organization=organization, id=client_id).first()
        if not client:
            msg = "Client not found."
            raise ValidationError(msg)
        return client

    name = str(args.get("client_name", "")).strip()
    if name:
        return (
            Client.objects.filter(organization=organization, name__iexact=name).first()
            or Client.objects.filter(
                organization=organization,
                name__icontains=name,
            ).first()
        )
    return None


def _resolve_invoice(
    organization: Organization,
    args: dict[str, Any],
) -> Invoice:
    invoice_id = args.get("invoice_id")
    invoice_number = str(args.get("invoice_number", "")).strip()
    invoice = None
    if invoice_id:
        invoice = Invoice.objects.filter(
            organization=organization,
            id=invoice_id,
        ).first()
    elif invoice_number:
        invoice = Invoice.objects.filter(
            organization=organization,
            invoice_number=invoice_number,
        ).first()
    if not invoice:
        msg = "Invoice not found."
        raise ValidationError(msg)
    return invoice


def _execute_action(
    organization: Organization,
    user: User | None,
    action: dict[str, Any],
) -> dict[str, Any]:
    tool = str(action.get("tool", ""))
    raw_args = action.get("args")
    args: dict[str, Any] = raw_args if isinstance(raw_args, dict) else {}

    if tool == "add_client":
        enforce(organization, "max_clients")
        client = Client.objects.create(
            organization=organization,
            name=_required_str(args, "name", "Client name"),
            email=_optional_str(args, "email", 254),
            phone=_optional_str(args, "phone", 50),
            company=_optional_str(args, "company"),
            address=_optional_str(args, "address", 2000),
        )
        return {"tool": tool, "client_id": str(client.id), "name": client.name}

    if tool == "add_product":
        enforce(organization, "max_products")
        product = Product.objects.create(
            organization=organization,
            name=_required_str(args, "name", "Product name"),
            description=_optional_str(args, "description", 5000),
            unit_price=_to_decimal(args.get("unit_price", 0), "Unit price"),
            currency=_optional_str(args, "currency", 3) or "USD",
            category=_optional_str(args, "category", 100),
            sku=_optional_str(args, "sku", 100),
            stock_quantity=_to_int(args.get("stock_quantity", 0), "Stock quantity"),
            track_stock=bool(args.get("track_stock", False)),
        )
        return {"tool": tool, "product_id": str(product.id), "name": product.name}

    if tool == "create_invoice":
        enforce(organization, "max_invoices_per_month")
        invoice_client = _resolve_client(organization, args)
        raw_items = args.get("items")
        if not isinstance(raw_items, list) or not raw_items:
            msg = "Invoice items are required."
            raise ValidationError(msg)

        issue_date = _to_date(args.get("issue_date")) or timezone.localdate()
        due_date = _to_date(args.get("due_date")) or issue_date + timedelta(
            days=DEFAULT_DUE_DAYS,
        )
        currency = (
            _optional_str(args, "currency", 3) or organization.default_currency or "USD"
        )

        with transaction.atomic():
            invoice = Invoice.objects.create(
                organization=organization,
                client=invoice_client,
                invoice_number=generate_next_invoice_number(organization, issue_date),
                issue_date=issue_date,
                due_date=due_date,
                currency=currency,
                tax_rate=_to_decimal(args.get("tax_rate", 0), "Tax rate"),
                client_name=(
                    invoice_client.name
                    if invoice_client
                    else _optional_str(args, "client_name")
                ),
                client_email=invoice_client.email if invoice_client else "",
                created_by=user,
            )
            for raw in raw_items:
                if not isinstance(raw, dict):
                    continue
                quantity = _to_decimal(raw.get("quantity", 1), "Quantity")
                rate = _to_decimal(raw.get("rate", 0), "Rate")
                if quantity <= 0:
                    msg = "Quantity must be greater than zero."
                    raise ValidationError(msg)
                InvoiceItem.objects.create(
                    invoice=invoice,
                    description=_required_str(
                        raw,
                        "description",
                        "Item description",
                        500,
                    ),
                    quantity=quantity,
                    rate=rate,
                )
            recalculate_invoice_totals(invoice)

        return {
            "tool": tool,
            "invoice_id": str(invoice.id),
            "invoice_number": invoice.invoice_number,
            "total": float(invoice.total),
        }

    if tool == "record_payment":
        invoice = _resolve_invoice(organization, args)
        amount = _to_decimal(args.get("amount", 0), "Payment amount")
        payment = record_invoice_payment(
            invoice,
            amount,
            PaymentDetails(payment_method=_payment_method(args.get("payment_method"))),
        )
        return {
            "tool": tool,
            "payment_id": str(payment.id),
            "invoice_number": invoice.invoice_number,
            "amount": float(payment.amount),
            "invoice_status": invoice.status,
        }

    if tool == "add_expense":
        expense = Expense.objects.create(
            organization=organization,
            title=_required_str(args, "title", "Expense title"),
            category=_expense_category(args.get("category")),
            vendor=_optional_str(args, "vendor"),
            amount=_to_decimal(args.get("amount", 0), "Expense amount"),
            currency=_optional_str(args, "currency", 3) or "USD",
            expense_date=_to_date(args.get("expense_date")) or timezone.localdate(),
            payment_method=_payment_method(args.get("payment_method")),
            created_by=user,
        )
        return {"tool": tool, "expense_id": str(expense.id), "title": expense.title}

    msg = f"Unknown tool: {tool}"
    raise ValidationError(msg)


def _normalize_actions(raw: Any) -> list[dict[str, Any]]:
    planned: list[dict[str, Any]] = []
    if not isinstance(raw, list):
        return planned
    for item in raw:
        if not isinstance(item, dict):
            continue
        tool = str(item.get("tool", "")).strip()
        if tool not in KNOWN_TOOLS:
            continue
        args = item.get("args")
        planned.append({"tool": tool, "args": args if isinstance(args, dict) else {}})
    return planned

def run_agent(
    *,
    organization: Organization,
    instruction: str,
    user: User | None = None,
    confirm: bool = False,
    history: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    """Propose (and optionally execute) data changes from natural language."""
    enforce(organization, "ai_credits_per_month")

    trimmed = instruction.strip()
    if not trimmed:
        msg = _("Please provide an instruction.")
        raise ValidationError(msg)
    if len(trimmed) > MAX_INSTRUCTION_LEN:
        msg = _("Please keep your instruction under 2000 characters.")
        raise ValidationError(msg)

    history = history[-MAX_HISTORY_MESSAGES:] if history else []

    context = build_assistant_context(organization)
    today = context["today"]
    system_msg = (
        "You are BizPilot, an assistant that can propose data changes for this "
        f"business. Today's date is {today}. "
        "Available tools: "
        "add_client {name, email, phone, company, address} | "
        "add_product {name, description, unit_price, currency, category, sku, "
        "stock_quantity, track_stock} | "
        "create_invoice {client_id or client_name, items: [{description, "
        "quantity, rate}], tax_rate, issue_date, due_date, currency} | "
        "record_payment {invoice_id or invoice_number, amount, payment_method} | "
        "add_expense {title, amount, category, vendor, expense_date, "
        "payment_method, currency} "
        "Return ONLY a JSON object with keys reply (string) and actions "
        "(array of {tool, args}). "
        "reply explains the proposal or answer; actions is empty when nothing "
        "needs to change. Resolve client names and invoice numbers using the "
        "data below. Do not invent figures. Answer in the language of the "
        f"question.{chr(10)}{chr(10)}DATA:{chr(10)}{json.dumps(context)}"
    )
    messages = [
        {"role": "system", "content": system_msg},
        *history,
        {"role": "user", "content": trimmed},
    ]

    provider = get_llm_provider()
    res = get_cached_or_complete(provider, messages, json_mode=True)
    obj = extract_json_object(res.content) or {}
    planned = _normalize_actions(obj.get("actions", []))

    result: dict[str, Any] = {
        "reply": str(obj.get("reply", "")),
        "planned_actions": planned,
        "executed": False,
    }

    if confirm and planned:
        executed: list[dict[str, Any]] = []
        errors: list[dict[str, Any]] = []
        for action in planned:
            try:
                with transaction.atomic():
                    executed.append(_execute_action(organization, user, action))
            except ValidationError as err:
                message = err.message if hasattr(err, "message") else str(err)
                errors.append({"tool": action.get("tool"), "error": message})
        result["executed"] = True
        result["results"] = executed
        result["errors"] = errors

    _log_ai_usage(
        organization=organization,
        user=user,
        feature="agent",
        model=res.model,
        prompt_tokens=res.prompt_tokens,
        completion_tokens=res.completion_tokens,
        latency_ms=res.latency_ms,
    )
    meter(organization, "ai_credits_per_month", 1)
    return result

