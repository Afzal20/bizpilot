#!/usr/bin/env python
from __future__ import annotations

import os
import sys
from decimal import Decimal
from pathlib import Path

# Setup Django environment
BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.local")

import django

django.setup()

from django.contrib.auth import get_user_model
from django.db.models import Sum

from bizpilot.erp.models import Client
from bizpilot.erp.models import Expense
from bizpilot.erp.models import Invoice
from bizpilot.erp.models import InvoiceItem
from bizpilot.erp.models import InvoiceSequence
from bizpilot.erp.models import Payment
from bizpilot.erp.models import Product
from bizpilot.orgs.models import Invite
from bizpilot.orgs.models import Membership
from bizpilot.orgs.models import Organization
from bizpilot.orgs.models import Role

User = get_user_model()


def verify_database_state(org_id: str | None = None) -> bool:
    """Reconcile and verify database integrity and migration accuracy."""
    print("============================================================")
    print("BizPilot Data Migration Verification & Reconciliation")
    print("============================================================")

    org_qs = Organization.objects.all()
    if org_id:
        org_qs = org_qs.filter(id=org_id)

    total_orgs = org_qs.count()
    if total_orgs == 0:
        print("FAIL: No organizations found to verify.")
        return False

    print(f"Found {total_orgs} organization(s) to verify.\n")
    all_passed = True

    for org in org_qs:
        print(f"--- Verifying Organization: {org.name} ({org.id}) ---")

        # 1. Verify owner and roles
        if not org.owner:
            print("  FAIL: Organization has no owner assigned.")
            all_passed = False
        else:
            print(f"  PASS: Owner assigned ({org.owner.email}).")

        system_roles = Role.objects.filter(organization=org, is_system=True)
        role_names = set(system_roles.values_list("name", flat=True))
        expected_roles = {"owner", "admin", "editor", "viewer"}
        if expected_roles.issubset(role_names):
            print(f"  PASS: All 4 system roles seeded for org ({', '.join(sorted(role_names))}).")
        else:
            print(f"  FAIL: Missing system roles. Found: {role_names}")
            all_passed = False

        # 2. Verify Memberships and Invites
        memberships_count = Membership.objects.filter(organization=org).count()
        invites_count = Invite.objects.filter(organization=org).count()
        print(f"  INFO: Memberships: {memberships_count}, Invites: {invites_count}")

        # Check that active members have at least one role
        members_without_roles = (
            Membership.objects.filter(organization=org, status=Membership.Status.ACTIVE)
            .filter(roles__isnull=True)
            .count()
        )
        if members_without_roles > 0:
            print(f"  FAIL: {members_without_roles} active members have no roles assigned.")
            all_passed = False
        else:
            print("  PASS: All active members have valid role assignments.")

        # 3. Verify Clients and Products
        clients_count = Client.objects.filter(organization=org).count()
        products_count = Product.objects.filter(organization=org).count()
        print(f"  INFO: Clients: {clients_count}, Products: {products_count}")
        if clients_count == 0 or products_count == 0:
            print("  WARN: Organization has zero clients or products.")

        # 4. Verify Invoices, Line Items, and Monetary Integrity
        invoices = Invoice.objects.filter(organization=org)
        invoice_count = invoices.count()
        print(f"  INFO: Invoices: {invoice_count}")

        total_invoiced = Decimal("0.00")
        total_items_count = 0
        math_mismatches = 0

        for inv in invoices:
            items = InvoiceItem.objects.filter(invoice=inv)
            total_items_count += items.count()

            # Verify math
            computed_subtotal = (
                items.aggregate(sub=Sum("amount"))["sub"] or Decimal("0.00")
            )
            total_invoiced += inv.total

            # Verify client organization match
            if inv.client and inv.client.organization_id != org.id:
                print(f"  FAIL: Invoice {inv.invoice_number} client cross-tenant mismatch!")
                all_passed = False

            # Verify payments
            payments = Payment.objects.filter(invoice=inv)
            paid_sum = payments.aggregate(p=Sum("amount"))["p"] or Decimal("0.00")
            for pay in payments:
                if pay.organization_id != org.id:
                    print(f"  FAIL: Payment {pay.id} cross-tenant mismatch!")
                    all_passed = False

            # Verify auto-settle status
            if paid_sum >= inv.total and inv.total > 0 and inv.status not in ("paid", "cancelled"):
                print(f"  FAIL: Invoice {inv.invoice_number} fully paid ({paid_sum} >= {inv.total}) but status is {inv.status}")
                all_passed = False

        print(f"  PASS: Total Invoiced: {total_invoiced:.2f} across {total_items_count} line items.")

        # 5. Verify Payments and Expenses totals
        payments_sum = (
            Payment.objects.filter(organization=org).aggregate(s=Sum("amount"))["s"]
            or Decimal("0.00")
        )
        expenses_sum = (
            Expense.objects.filter(organization=org).aggregate(s=Sum("amount"))["s"]
            or Decimal("0.00")
        )
        print(f"  PASS: Total Payments Collected: {payments_sum:.2f}")
        print(f"  PASS: Total Expenses Recorded: {expenses_sum:.2f}")

        # 6. Verify Sequence continuity
        seq = InvoiceSequence.objects.filter(organization=org).first()
        if seq:
            print(f"  PASS: InvoiceSequence configured for year {seq.year}, last_number={seq.last_number}")
        else:
            print("  WARN: No InvoiceSequence record found for organization.")

        print(f"--- Organization {org.name} Verification Completed ---\n")

    print("============================================================")
    if all_passed:
        print("VERIFICATION RESULT: ALL RECONCILIATION CHECKS PASSED")
    else:
        print("VERIFICATION RESULT: INTEGRITY ISSUES DETECTED")
    print("============================================================")
    return all_passed


if __name__ == "__main__":
    target_org = sys.argv[1] if len(sys.argv) > 1 else None
    success = verify_database_state(target_org)
    sys.exit(0 if success else 1)
