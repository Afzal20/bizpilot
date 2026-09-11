from __future__ import annotations

import json
from decimal import Decimal
from typing import TYPE_CHECKING
from typing import Any

from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _

from bizpilot.ai.gateway import extract_json_array
from bizpilot.ai.gateway import extract_json_object
from bizpilot.ai.gateway import get_cached_or_complete
from bizpilot.ai.gateway import get_llm_provider
from bizpilot.ai.models import AILog
from bizpilot.billing.engine import enforce
from bizpilot.billing.engine import meter
from bizpilot.erp.services import get_report_data

if TYPE_CHECKING:
    from collections.abc import Generator

    from bizpilot.erp.models import Invoice
    from bizpilot.orgs.models import Organization
    from bizpilot.users.models import User

MIN_PROMPT_LEN = 4
MAX_PROMPT_LEN = 600
MAX_QUESTION_LEN = 500

EXPENSE_CATEGORIES = [
    "Office Supplies",
    "Software & Subscriptions",
    "Travel & Meals",
    "Utilities",
    "Professional Services",
    "Advertising & Marketing",
    "Equipment",
    "Other",
]


def _log_ai_usage(  # noqa: PLR0913
    *,
    organization: Organization,
    user: User | None,
    feature: str,
    model: str,
    prompt_tokens: int = 0,
    completion_tokens: int = 0,
    latency_ms: int = 0,
    cost_estimate: Decimal = Decimal("0.000000"),
) -> AILog:
    return AILog.objects.create(
        organization=organization,
        user=user,
        feature=feature,
        model=model,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        latency_ms=latency_ms,
        cost_estimate=cost_estimate,
    )


def generate_invoice_items(
    *,
    organization: Organization,
    prompt: str,
    currency: str | None = None,
    user: User | None = None,
) -> list[dict[str, Any]]:
    """
    Convert natural language billing description into structured invoice line items.
    """
    enforce(organization, "ai_credits_per_month")

    trimmed = prompt.strip()
    if len(trimmed) < MIN_PROMPT_LEN:
        msg = _("Please describe what you would like to bill.")
        raise ValidationError(msg)
    if len(trimmed) > MAX_PROMPT_LEN:
        msg = _("Please keep your description under 600 characters.")
        raise ValidationError(msg)

    target_currency = currency or organization.default_currency or "USD"
    provider = get_llm_provider()

    system_msg = (
        "You convert plain-language billing descriptions into invoice line items. "
        "Return a JSON object with an 'items' key containing an array of line items. "
        f"Each line item must have 'description' (string), 'quantity' (number), and 'rate' (unit price number in {target_currency}). "
        f'Example: {{"items": [{{"description": "Web Development", "quantity": 1, "rate": 500}}]}}. '
        "Infer reasonable quantities and market rates when not explicitly stated. "
        "Output at most 8 items. Do not include markdown fences or conversational text outside the JSON."
    )
    messages = [
        {"role": "system", "content": system_msg},
        {"role": "user", "content": trimmed},
    ]

    res = get_cached_or_complete(provider, messages, json_mode=True)
    raw_items = extract_json_array(res.content)
    if not raw_items:
        msg = _("Could not parse generated line items. Please rephrase.")
        raise ValidationError(msg)

    cleaned_items: list[dict[str, Any]] = []
    for it in raw_items:
        if not isinstance(it, dict):
            continue
        desc = str(it.get("description", "")).strip()
        try:
            qty = float(it.get("quantity", 1))
            rate = float(it.get("rate", 0))
        except (ValueError, TypeError):
            continue

        if desc and qty > 0 and rate >= 0:
            cleaned_items.append({
                "description": desc[:200],
                "quantity": qty,
                "rate": rate,
            })

    if not cleaned_items:
        msg = _("No usable line items could be produced.")
        raise ValidationError(msg)

    _log_ai_usage(
        organization=organization,
        user=user,
        feature="generate-items",
        model=res.model,
        prompt_tokens=res.prompt_tokens,
        completion_tokens=res.completion_tokens,
        latency_ms=res.latency_ms,
    )
    meter(organization, "ai_credits_per_month", 1)
    return cleaned_items


def ask_bizpilot(
    *,
    organization: Organization,
    question: str,
    user: User | None = None,
) -> str:
    """Answer business questions using live organizational report context."""
    enforce(organization, "ai_credits_per_month")

    trimmed = question.strip()
    if not trimmed:
        msg = _("Please ask a question.")
        raise ValidationError(msg)
    if len(trimmed) > MAX_QUESTION_LEN:
        msg = _("Please keep your question under 500 characters.")
        raise ValidationError(msg)

    data = get_report_data(organization)
    context = {
        "organization": organization.name,
        "currency": organization.default_currency or "USD",
        "totals": data.get("totals", {}),
        "monthly_last_6_months": data.get("monthly_series", [])[-6:],
        "expense_by_category": data.get("expense_by_category", [])[:8],
        "top_clients": data.get("top_clients", []),
    }

    system_msg = (
        "You are BizPilot, a sharp small-business analyst. Answer questions about "
        "THIS business using only the JSON data provided below. "
        "Be concise (max 150 words), specific with numbers, and practical. "
        "If the data cannot answer the question, state so briefly. "
        "Do not invent figures.\n\nDATA:\n"
        f"{json.dumps(context)}"
    )
    messages = [
        {"role": "system", "content": system_msg},
        {"role": "user", "content": trimmed},
    ]

    provider = get_llm_provider()
    res = get_cached_or_complete(provider, messages)

    _log_ai_usage(
        organization=organization,
        user=user,
        feature="assistant",
        model=res.model,
        prompt_tokens=res.prompt_tokens,
        completion_tokens=res.completion_tokens,
        latency_ms=res.latency_ms,
    )
    meter(organization, "ai_credits_per_month", 1)
    return res.content


def stream_bizpilot(
    *,
    organization: Organization,
    question: str,
    user: User | None = None,
) -> Generator[str]:
    """Stream BizPilot assistant answer via SSE."""
    enforce(organization, "ai_credits_per_month")

    trimmed = question.strip()
    if not trimmed:
        msg = _("Please ask a question.")
        raise ValidationError(msg)

    data = get_report_data(organization)
    context = {
        "organization": organization.name,
        "currency": organization.default_currency or "USD",
        "totals": data.get("totals", {}),
        "monthly_last_6_months": data.get("monthly_series", [])[-6:],
        "expense_by_category": data.get("expense_by_category", [])[:8],
        "top_clients": data.get("top_clients", []),
    }

    system_msg = (
        "You are BizPilot, a sharp small-business analyst. Answer questions about "
        "THIS business using only the JSON data provided below. "
        "Be concise (max 150 words), specific with numbers, and practical.\n\nDATA:\n"
        f"{json.dumps(context)}"
    )
    messages = [
        {"role": "system", "content": system_msg},
        {"role": "user", "content": trimmed},
    ]

    provider = get_llm_provider()
    for chunk in provider.stream(messages):
        payload = json.dumps({"delta": chunk})
        yield f"data: {payload}\n\n"

    yield "data: [DONE]\n\n"

    _log_ai_usage(
        organization=organization,
        user=user,
        feature="assistant-stream",
        model="stream/bizpilot",
    )
    meter(organization, "ai_credits_per_month", 1)


def categorize_expense(
    *,
    organization: Organization,
    title: str,
    description: str = "",
    user: User | None = None,
) -> dict[str, Any]:
    """Suggest category and vendor for an expense based on title and description."""
    enforce(organization, "ai_credits_per_month")

    system_msg = (
        "Analyze the given expense title and description. Return a JSON object with: "
        f'"category" (must be one of: {", ".join(EXPENSE_CATEGORIES)}), '
        '"vendor" (detected vendor/merchant name, or ""), '
        '"confidence" (float between 0.0 and 1.0).'
    )
    user_msg = f"Title: {title}\nDescription: {description}"
    messages = [
        {"role": "system", "content": system_msg},
        {"role": "user", "content": user_msg},
    ]

    provider = get_llm_provider()
    res = get_cached_or_complete(provider, messages, json_mode=True)
    obj = extract_json_object(res.content) or {}

    category = obj.get("category", "Other")
    if category not in EXPENSE_CATEGORIES:
        category = "Other"

    _log_ai_usage(
        organization=organization,
        user=user,
        feature="categorize-expense",
        model=res.model,
        prompt_tokens=res.prompt_tokens,
        completion_tokens=res.completion_tokens,
        latency_ms=res.latency_ms,
    )
    meter(organization, "ai_credits_per_month", 1)

    return {
        "category": category,
        "vendor": str(obj.get("vendor", "")),
        "confidence": float(obj.get("confidence", 0.8)),
    }


def draft_payment_reminder(
    *,
    organization: Organization,
    invoice: Invoice,
    tone: str = "friendly",
    user: User | None = None,
) -> dict[str, str]:
    """Draft an email reminder for an invoice with tone control."""
    enforce(organization, "ai_credits_per_month")

    system_msg = (
        f"Draft a payment reminder email with a '{tone}' tone. "
        "Return a JSON object with 'subject' and 'body'. "
        "Keep it professional and concise."
    )
    user_msg = (
        f"Organization: {organization.name}\n"
        f"Invoice Number: {invoice.invoice_number}\n"
        f"Client: {invoice.client_name}\n"
        f"Due Date: {invoice.due_date}\n"
        f"Total Amount: {invoice.total} {invoice.currency}\n"
        f"Amount Due: {invoice.balance_due} {invoice.currency}"
    )
    messages = [
        {"role": "system", "content": system_msg},
        {"role": "user", "content": user_msg},
    ]

    provider = get_llm_provider()
    res = get_cached_or_complete(provider, messages, json_mode=True)
    obj = extract_json_object(res.content) or {}

    _log_ai_usage(
        organization=organization,
        user=user,
        feature="draft-reminder",
        model=res.model,
        prompt_tokens=res.prompt_tokens,
        completion_tokens=res.completion_tokens,
        latency_ms=res.latency_ms,
    )
    meter(organization, "ai_credits_per_month", 1)

    return {
        "subject": str(
            obj.get(
                "subject",
                f"Reminder: Invoice {invoice.invoice_number} Payment Due",
            ),
        ),
        "body": str(
            obj.get(
                "body",
                (
                    f"Dear {invoice.client_name}, your payment for "
                    f"{invoice.invoice_number} is due."
                ),
            ),
        ),
    }
