from __future__ import annotations

import logging
from typing import Any

from celery import shared_task
from django.conf import settings
from django.contrib.auth import get_user_model

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def send_invoice_email_task(
    self: Any,
    invoice_id: str,
    recipient_email: str | None = None,
    attach_pdf: bool = True,
) -> bool:
    """Send an invoice notification email with optional PDF attachment to the client."""
    from bizpilot.core.emails import send_branded_email  # noqa: PLC0415
    from bizpilot.erp.models import Invoice  # noqa: PLC0415
    from bizpilot.erp.pdf import generate_invoice_pdf  # noqa: PLC0415

    try:
        invoice = (
            Invoice.objects.select_related("client", "organization")
            .prefetch_related("items")
            .get(id=invoice_id)
        )
    except Invoice.DoesNotExist:
        logger.error(f"Invoice {invoice_id} not found for email task.")
        return False

    to_email = recipient_email or invoice.client_email or (invoice.client.email if invoice.client else None)
    if not to_email:
        logger.warning(f"No recipient email found for invoice {invoice_id}.")
        return False

    attachments = []
    if attach_pdf:
        try:
            pdf_bytes = generate_invoice_pdf(invoice)
            attachments.append((f"{invoice.invoice_number}.pdf", pdf_bytes, "application/pdf"))
        except Exception as exc:
            logger.error(f"Error generating PDF for invoice {invoice_id}: {exc}")

    business_name = invoice.business_name or (invoice.organization.name if invoice.organization else "BizPilot Business")
    subject = f"Invoice {invoice.invoice_number} from {business_name}"

    context = {
        "invoice": invoice,
    }

    try:
        return send_branded_email(
            subject=subject,
            template_prefix="emails/invoice_email",
            context=context,
            to=to_email,
            attachments=attachments,
        )
    except Exception as exc:
        logger.error(f"Error sending invoice email for {invoice_id}: {exc}")
        raise self.retry(exc=exc) from exc


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def send_payment_receipt_email_task(
    self: Any,
    payment_id: str,
    recipient_email: str | None = None,
) -> bool:
    """Send a payment receipt confirmation email to the client."""
    from bizpilot.core.emails import send_branded_email  # noqa: PLC0415
    from bizpilot.erp.models import Payment  # noqa: PLC0415

    try:
        payment = Payment.objects.select_related("invoice", "invoice__client", "organization").get(id=payment_id)
    except Payment.DoesNotExist:
        logger.error(f"Payment {payment_id} not found for email task.")
        return False

    invoice = payment.invoice
    to_email = recipient_email or invoice.client_email or (invoice.client.email if invoice.client else None)
    if not to_email:
        logger.warning(f"No recipient email found for payment {payment_id}.")
        return False

    subject = f"Payment Receipt for Invoice {invoice.invoice_number}"
    context = {
        "payment": payment,
    }

    try:
        return send_branded_email(
            subject=subject,
            template_prefix="emails/payment_receipt_email",
            context=context,
            to=to_email,
        )
    except Exception as exc:
        logger.error(f"Error sending payment receipt email for {payment_id}: {exc}")
        raise self.retry(exc=exc) from exc


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def send_invite_email_task(
    self: Any,
    invite_id: str,
    base_url: str | None = None,
) -> bool:
    """Send organization invitation email to the invited user."""
    from bizpilot.core.emails import send_branded_email  # noqa: PLC0415
    from bizpilot.orgs.models import Invite  # noqa: PLC0415

    try:
        invite = Invite.objects.select_related("organization", "invited_by").prefetch_related("roles").get(id=invite_id)
    except Invite.DoesNotExist:
        logger.error(f"Invite {invite_id} not found for email task.")
        return False

    root_url = base_url or getattr(settings, "FRONTEND_URL", "http://localhost:3000")
    invite_url = f"{root_url}/auth/sign-up?token={invite.token}"

    subject = f"You've been invited to join {invite.organization.name} on BizPilot"
    context = {
        "invite": invite,
        "invite_url": invite_url,
    }

    try:
        return send_branded_email(
            subject=subject,
            template_prefix="emails/team_invite_email",
            context=context,
            to=invite.email,
        )
    except Exception as exc:
        logger.error(f"Error sending invite email for {invite_id}: {exc}")
        raise self.retry(exc=exc) from exc


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def send_password_reset_email_task(
    self: Any,
    user_id: int | str,
    uid: str,
    token: str,
    base_url: str | None = None,
) -> bool:
    """Send password reset instructions with secure one-time link."""
    from bizpilot.core.emails import send_branded_email  # noqa: PLC0415

    User = get_user_model()
    try:
        user = User.objects.get(pk=user_id)
    except User.DoesNotExist:
        logger.error(f"User {user_id} not found for password reset email task.")
        return False

    root_url = base_url or getattr(settings, "FRONTEND_URL", "http://localhost:3000")
    reset_url = f"{root_url}/auth/update-password?uid={uid}&token={token}"

    subject = "Reset your BizPilot password"
    context = {
        "user": user,
        "reset_url": reset_url,
    }

    try:
        return send_branded_email(
            subject=subject,
            template_prefix="emails/password_reset_email",
            context=context,
            to=user.email,
        )
    except Exception as exc:
        logger.error(f"Error sending password reset email for user {user_id}: {exc}")
        raise self.retry(exc=exc) from exc
