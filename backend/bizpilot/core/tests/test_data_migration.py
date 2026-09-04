from __future__ import annotations

import datetime
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.hashers import check_password
from django.core.management import call_command
from django.test import TestCase

from bizpilot.core.management.commands.migrate_supabase_data import clean_cell_value
from bizpilot.core.management.commands.migrate_supabase_data import parse_date_expression
from bizpilot.core.management.commands.migrate_supabase_data import parse_values_block
from bizpilot.erp.models import Client
from bizpilot.erp.models import Expense
from bizpilot.erp.models import Invoice
from bizpilot.erp.models import InvoiceItem
from bizpilot.erp.models import Payment
from bizpilot.erp.models import Product
from bizpilot.orgs.models import Invite
from bizpilot.orgs.models import Membership
from bizpilot.orgs.models import Organization
from scripts.verify_migration import verify_database_state

User = get_user_model()


class SupabaseDataMigrationTests(TestCase):
    def test_parse_date_expression(self) -> None:
        base = datetime.date(2026, 9, 4)
        self.assertEqual(parse_date_expression("now()::date", base_date=base), base)
        self.assertEqual(
            parse_date_expression("(now() - interval '1 month')::date", base_date=base),
            datetime.date(2026, 8, 4),
        )
        self.assertEqual(
            parse_date_expression("(now() + interval '5 days')::date", base_date=base),
            datetime.date(2026, 9, 9),
        )
        self.assertEqual(
            parse_date_expression("'2026-01-15'", base_date=base),
            datetime.date(2026, 1, 15),
        )

    def test_clean_cell_value(self) -> None:
        self.assertIsNone(clean_cell_value("null"))
        self.assertIsNone(clean_cell_value("NULL"))
        self.assertTrue(clean_cell_value("true"))
        self.assertFalse(clean_cell_value("false"))
        self.assertEqual(clean_cell_value("'Acme''s Studio'"), "Acme's Studio")
        self.assertEqual(clean_cell_value("125.50"), Decimal("125.50"))
        self.assertEqual(clean_cell_value("42"), 42)

    def test_parse_values_block(self) -> None:
        block = "('val1', 10, true), ('val2', 20, false)"
        rows = parse_values_block(block)
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0], ["'val1'", "10", "true"])
        self.assertEqual(rows[1], ["'val2'", "20", "false"])

    def test_full_migration_from_seed(self) -> None:
        call_command("migrate_supabase_data", "--reset")

        # Verify User & password compatibility
        user = User.objects.filter(email="demo@bizpilot.app").first()
        self.assertIsNotNone(user)
        self.assertTrue(check_password("demo1234", user.password))

        # Verify Organization
        org = Organization.objects.filter(name="Acme Solutions Demo").first()
        self.assertIsNotNone(org)
        self.assertEqual(org.owner, user)

        # Verify System Roles
        roles = set(org.roles.values_list("name", flat=True))
        self.assertTrue({"owner", "admin", "editor", "viewer"}.issubset(roles))

        # Verify Memberships & Invites
        membership = Membership.objects.filter(organization=org, user=user).first()
        self.assertIsNotNone(membership)
        self.assertTrue(membership.roles.filter(name="owner").exists())

        invites = Invite.objects.filter(organization=org)
        self.assertEqual(invites.count(), 3)

        # Verify Clients & Products
        self.assertEqual(Client.objects.filter(organization=org).count(), 3)
        self.assertEqual(Product.objects.filter(organization=org).count(), 8)

        # Verify Invoices, Items, Payments, Expenses
        self.assertEqual(Invoice.objects.filter(organization=org).count(), 12)
        self.assertEqual(InvoiceItem.objects.filter(invoice__organization=org).count(), 26)
        self.assertEqual(Payment.objects.filter(organization=org).count(), 7)
        self.assertEqual(Expense.objects.filter(organization=org).count(), 13)

        # Run verification script
        result = verify_database_state(str(org.id))
        self.assertTrue(result)
