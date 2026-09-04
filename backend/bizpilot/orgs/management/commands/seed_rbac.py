from __future__ import annotations

from typing import Any

from django.core.management.base import BaseCommand

from bizpilot.orgs.models import Organization
from bizpilot.orgs.models import Permission
from bizpilot.orgs.services import seed_permissions
from bizpilot.orgs.services import seed_system_roles_for_org


class Command(BaseCommand):
    help = (
        "Seed RBAC v2 permissions catalog and default roles for existing organizations."
    )

    def handle(self, *args: Any, **options: Any) -> None:
        self.stdout.write("Seeding RBAC v2 permission catalog...")
        seed_permissions()
        total_perms = Permission.objects.count()
        self.stdout.write(
            self.style.SUCCESS(
                f"Seeded permissions. Total catalog permissions: {total_perms}",
            ),
        )

        orgs = Organization.objects.all()
        self.stdout.write(
            f"Seeding default system roles for {orgs.count()} organizations...",
        )
        for org in orgs:
            seed_system_roles_for_org(org)

        self.stdout.write(self.style.SUCCESS("RBAC seeding complete."))
