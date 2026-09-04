from __future__ import annotations

from http import HTTPStatus
from typing import TYPE_CHECKING
from typing import Any

from rest_framework.views import exception_handler

if TYPE_CHECKING:
    from rest_framework.response import Response


def _flatten_errors(detail: Any, parent_key: str = "") -> list[dict[str, Any]]:
    """Flatten nested serializer error dictionaries into field-level errors."""
    items: list[dict[str, Any]] = []
    if isinstance(detail, dict):
        for key, value in detail.items():
            full_key = f"{parent_key}.{key}" if parent_key else str(key)
            items.extend(_flatten_errors(value, full_key))
    elif isinstance(detail, (list, tuple)):
        for item in detail:
            if isinstance(item, (dict, list)):
                items.extend(_flatten_errors(item, parent_key))
            else:
                items.append({
                    "name": parent_key or "non_field_errors",
                    "reason": str(item),
                })
    else:
        items.append({
            "name": parent_key or "non_field_errors",
            "reason": str(detail),
        })
    return items


def _parse_error_details(
    raw_data: Any,
) -> tuple[str, str, list[dict[str, Any]]]:
    """Extract detail message, code, and invalid params from response data."""
    invalid_params: list[dict[str, Any]] = []
    error_code = "error"

    if isinstance(raw_data, dict):
        if "detail" in raw_data and len(raw_data) == 1:
            detail_str = str(raw_data["detail"])
            if hasattr(raw_data["detail"], "code"):
                error_code = str(raw_data["detail"].code)
        else:
            invalid_params = _flatten_errors(raw_data)
            detail_str = "One or more validation constraints failed."
            error_code = "validation_error"
    elif isinstance(raw_data, list):
        invalid_params = _flatten_errors(raw_data)
        detail_str = str(raw_data[0]) if raw_data else "An error occurred."
    else:
        detail_str = str(raw_data)

    return detail_str, error_code, invalid_params


def custom_exception_handler(
    exc: Exception,
    context: dict[str, Any],
) -> Response | None:
    """RFC 7807 compliant problem details exception handler for DRF."""
    response = exception_handler(exc, context)
    if response is None:
        return None

    status_code = response.status_code
    try:
        title = HTTPStatus(status_code).phrase
    except ValueError:
        title = "Error"

    request = context.get("request")
    instance = request.build_absolute_uri() if request else ""
    detail_str, error_code, invalid_params = _parse_error_details(response.data)

    get_codes = getattr(exc, "get_codes", None)
    if callable(get_codes):
        codes = get_codes()
        if isinstance(codes, str):
            error_code = codes

    payload: dict[str, Any] = {
        "type": f"https://api.bizpilot.com/errors/{error_code}",
        "title": title,
        "status": status_code,
        "detail": detail_str,
        "code": error_code,
    }
    if instance:
        payload["instance"] = instance
    if invalid_params:
        payload["invalid_params"] = invalid_params

    response.data = payload
    response["Content-Type"] = "application/problem+json"
    return response
