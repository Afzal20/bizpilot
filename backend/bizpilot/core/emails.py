from __future__ import annotations

import logging
from typing import Any, Sequence

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string

logger = logging.getLogger(__name__)


def send_branded_email(
    *,
    subject: str,
    template_prefix: str,
    context: dict[str, Any],
    to: Sequence[str] | str,
    attachments: list[tuple[str, bytes, str]] | None = None,
) -> bool:
    """Render plain-text and HTML email templates and dispatch via configured email backend.

    Args:
        subject: Email subject line.
        template_prefix: Prefix path without extension, e.g. "emails/invoice_email".
        context: Context dictionary passed to template renderer.
        to: Recipient email address or list of addresses.
        attachments: Optional list of tuples (filename, content_bytes, mimetype).

    Returns:
        bool: True if sent successfully, False otherwise.
    """
    recipient_list = [to] if isinstance(to, str) else list(to)
    if not recipient_list:
        logger.warning("Attempted to send email with empty recipient list.")
        return False

    context.setdefault("frontend_url", getattr(settings, "FRONTEND_URL", "http://localhost:3000"))

    txt_template = f"{template_prefix}.txt"
    html_template = f"{template_prefix}.html"

    try:
        body_text = render_to_string(txt_template, context)
    except Exception as exc:
        logger.warning(f"Plain text template {txt_template} failed to render: {exc}. Using fallback.")
        body_text = subject

    try:
        body_html = render_to_string(html_template, context)
    except Exception as exc:
        logger.error(f"HTML email template {html_template} failed to render: {exc}")
        body_html = None

    from_email = getattr(settings, "DEFAULT_FROM_EMAIL", "BizPilot <notifications@bizpilot.local>")

    msg = EmailMultiAlternatives(
        subject=subject,
        body=body_text,
        from_email=from_email,
        to=recipient_list,
    )

    if body_html:
        msg.attach_alternative(body_html, "text/html")

    if attachments:
        for filename, content, mimetype in attachments:
            msg.attach(filename, content, mimetype)

    try:
        msg.send(fail_silently=False)
        logger.info(f"Email '{subject}' sent to {recipient_list}")
        return True
    except Exception as exc:
        logger.error(f"Failed to send email '{subject}' to {recipient_list}: {exc}")
        return False
