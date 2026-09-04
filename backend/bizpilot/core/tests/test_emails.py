from __future__ import annotations

from decimal import Decimal
from django.core import mail
from django.test import TestCase
from django.utils import timezone

from bizpilot.core.emails import send_branded_email
from bizpilot.core.tasks import (
    send_invoice_email_task,
    send_invite_email_task,
    send_password_reset_email_task,
    send_payment_receipt_email_task,
)
from bizpilot.erp.models import Client, Invoice, InvoiceItem, Payment
from bizpilot.erp.pdf import generate_invoice_pdf
from bizpilot.orgs.models import Invite, Organization
from bizpilot.users.models import User


class EmailSystemTests(TestCase):
    def setUp(self):
        mail.outbox.clear()
        self.user = User.objects.create_user(
            email="testowner@bizpilot.local",
            password="StrongPassword123!",
            name="Test Owner",
        )
        self.org = Organization.objects.create(
            name="Apex Technologies",
            owner=self.user,
        )
        self.client_entity = Client.objects.create(
            organization=self.org,
            name="Stark Industries",
            email="tony@stark.com",
            address="10880 Malibu Point, Malibu, CA",
        )
        self.invoice = Invoice.objects.create(
            organization=self.org,
            client=self.client_entity,
            client_name="Stark Industries",
            client_email="tony@stark.com",
            business_name="Apex Technologies",
            invoice_number="INV-2026-TEST-001",
            due_date=timezone.localdate() + timezone.timedelta(days=14),
            subtotal=Decimal("1500.00"),
            total=Decimal("1500.00"),
            created_by=self.user,
        )
        self.item = InvoiceItem.objects.create(
            invoice=self.invoice,
            description="Quantum Reactor Blueprint",
            quantity=Decimal("1.00"),
            rate=Decimal("1500.00"),
            amount=Decimal("1500.00"),
        )

    def test_send_branded_email_basic(self):
        success = send_branded_email(
            subject="Welcome to BizPilot",
            template_prefix="emails/base_email",
            context={},
            to="user@example.com",
        )
        self.assertTrue(success)
        self.assertEqual(len(mail.outbox), 1)
        sent = mail.outbox[0]
        self.assertEqual(sent.subject, "Welcome to BizPilot")
        self.assertIn("user@example.com", sent.to)
        self.assertIn("BizPilot", sent.body)

    def test_generate_invoice_pdf(self):
        pdf_bytes = generate_invoice_pdf(self.invoice)
        self.assertTrue(isinstance(pdf_bytes, bytes))
        self.assertTrue(pdf_bytes.startswith(b"%PDF-"))
        self.assertGreater(len(pdf_bytes), 1000)

    def test_send_invoice_email_task(self):
        result = send_invoice_email_task(str(self.invoice.id), attach_pdf=True)
        self.assertTrue(result)
        self.assertEqual(len(mail.outbox), 1)
        sent = mail.outbox[0]
        self.assertIn(self.invoice.invoice_number, sent.subject)
        self.assertEqual(sent.to, ["tony@stark.com"])
        self.assertEqual(len(sent.attachments), 1)
        filename, content, mimetype = sent.attachments[0]
        self.assertTrue(filename.endswith(".pdf"))
        self.assertEqual(mimetype, "application/pdf")
        self.assertTrue(content.startswith(b"%PDF-"))

    def test_send_payment_receipt_email_task(self):
        payment = Payment.objects.create(
            organization=self.org,
            invoice=self.invoice,
            amount=Decimal("1500.00"),
            payment_method=Payment.PaymentMethod.BANK_TRANSFER,
            reference="TXN-WIRE-883",
            recorded_by=self.user,
        )
        result = send_payment_receipt_email_task(str(payment.id))
        self.assertTrue(result)
        self.assertEqual(len(mail.outbox), 1)
        sent = mail.outbox[0]
        self.assertIn("Payment Receipt", sent.subject)
        self.assertEqual(sent.to, ["tony@stark.com"])
        self.assertIn("TXN-WIRE-883", sent.body)

    def test_send_invite_email_task(self):
        invite = Invite.objects.create(
            organization=self.org,
            email="candidate@example.com",
            invited_by=self.user,
            department="Engineering",
            expires_at=timezone.now() + timezone.timedelta(days=7),
        )
        result = send_invite_email_task(str(invite.id))
        self.assertTrue(result)
        self.assertEqual(len(mail.outbox), 1)
        sent = mail.outbox[0]
        self.assertIn("invited to join", sent.subject)
        self.assertEqual(sent.to, ["candidate@example.com"])
        self.assertIn(invite.token, sent.body)

    def test_send_password_reset_email_task(self):
        result = send_password_reset_email_task(
            user_id=self.user.id,
            uid="MQ",
            token="test-token-12345",
        )
        self.assertTrue(result)
        self.assertEqual(len(mail.outbox), 1)
        sent = mail.outbox[0]
        self.assertIn("Reset your BizPilot password", sent.subject)
        self.assertEqual(sent.to, [self.user.email])
        self.assertIn("test-token-12345", sent.body)
