from __future__ import annotations

from typing import Final

# Complete RBAC v2 Permission Catalog (40+ permissions across resources)
PERMISSION_CATALOG: Final[list[dict[str, str]]] = [
    {
        "codename": "invoices.view",
        "resource": "invoices",
        "action": "view",
        "description": "View invoices and invoice summaries",
    },
    {
        "codename": "invoices.create",
        "resource": "invoices",
        "action": "create",
        "description": "Create new invoices",
    },
    {
        "codename": "invoices.edit",
        "resource": "invoices",
        "action": "edit",
        "description": "Edit existing invoices",
    },
    {
        "codename": "invoices.delete",
        "resource": "invoices",
        "action": "delete",
        "description": "Delete invoices",
    },
    {
        "codename": "invoices.send",
        "resource": "invoices",
        "action": "send",
        "description": "Send invoices to clients via email or share links",
    },
    {
        "codename": "invoices.record_payment",
        "resource": "invoices",
        "action": "record_payment",
        "description": "Record payments against invoices",
    },
    {
        "codename": "invoices.cancel",
        "resource": "invoices",
        "action": "cancel",
        "description": "Cancel invoices and restore stock",
    },
    {
        "codename": "clients.view",
        "resource": "clients",
        "action": "view",
        "description": "View clients and client statistics",
    },
    {
        "codename": "clients.create",
        "resource": "clients",
        "action": "create",
        "description": "Create new clients",
    },
    {
        "codename": "clients.edit",
        "resource": "clients",
        "action": "edit",
        "description": "Edit existing client details",
    },
    {
        "codename": "clients.delete",
        "resource": "clients",
        "action": "delete",
        "description": "Delete clients",
    },
    {
        "codename": "products.view",
        "resource": "products",
        "action": "view",
        "description": "View products and inventory stock",
    },
    {
        "codename": "products.create",
        "resource": "products",
        "action": "create",
        "description": "Create new products",
    },
    {
        "codename": "products.edit",
        "resource": "products",
        "action": "edit",
        "description": "Edit existing product details",
    },
    {
        "codename": "products.delete",
        "resource": "products",
        "action": "delete",
        "description": "Delete products",
    },
    {
        "codename": "products.adjust_stock",
        "resource": "products",
        "action": "adjust_stock",
        "description": "Adjust product inventory stock quantities",
    },
    {
        "codename": "expenses.view",
        "resource": "expenses",
        "action": "view",
        "description": "View expenses and expense categories",
    },
    {
        "codename": "expenses.create",
        "resource": "expenses",
        "action": "create",
        "description": "Record new business expenses",
    },
    {
        "codename": "expenses.edit",
        "resource": "expenses",
        "action": "edit",
        "description": "Edit existing expense records",
    },
    {
        "codename": "expenses.delete",
        "resource": "expenses",
        "action": "delete",
        "description": "Delete expense records",
    },
    {
        "codename": "payments.view",
        "resource": "payments",
        "action": "view",
        "description": "View payment history and receipts",
    },
    {
        "codename": "payments.create",
        "resource": "payments",
        "action": "create",
        "description": "Record manual payments",
    },
    {
        "codename": "payments.delete",
        "resource": "payments",
        "action": "delete",
        "description": "Delete or reverse payment records",
    },
    {
        "codename": "reports.view",
        "resource": "reports",
        "action": "view",
        "description": "View financial dashboard and report summaries",
    },
    {
        "codename": "reports.export",
        "resource": "reports",
        "action": "export",
        "description": "Export reports and bulk data to CSV/PDF",
    },
    {
        "codename": "exports.download",
        "resource": "exports",
        "action": "download",
        "description": "Download generated reports and export archives",
    },
    {
        "codename": "team.view",
        "resource": "team",
        "action": "view",
        "description": "View team members, roles, and pending invites",
    },
    {
        "codename": "team.invite",
        "resource": "team",
        "action": "invite",
        "description": "Invite new members to the organization",
    },
    {
        "codename": "team.manage_roles",
        "resource": "team",
        "action": "manage_roles",
        "description": "Create, edit, and assign member roles and permissions",
    },
    {
        "codename": "team.remove",
        "resource": "team",
        "action": "remove",
        "description": "Remove members from the organization",
    },
    {
        "codename": "organization.view",
        "resource": "organization",
        "action": "view",
        "description": "View organization profile and settings",
    },
    {
        "codename": "organization.edit_settings",
        "resource": "organization",
        "action": "edit_settings",
        "description": "Edit organization profile, branding, and defaults",
    },
    {
        "codename": "organization.delete",
        "resource": "organization",
        "action": "delete",
        "description": "Delete organization and all associated data",
    },
    {
        "codename": "billing.view",
        "resource": "billing",
        "action": "view",
        "description": "View billing history, invoices, and active subscription",
    },
    {
        "codename": "billing.manage",
        "resource": "billing",
        "action": "manage",
        "description": "Manage subscriptions, payment methods, and portal",
    },
    {
        "codename": "ai.use_assistant",
        "resource": "ai",
        "action": "use_assistant",
        "description": "Query BizPilot AI business assistant",
    },
    {
        "codename": "ai.generate",
        "resource": "ai",
        "action": "generate",
        "description": "Generate line items, descriptions, and OCR data using AI",
    },
    {
        "codename": "audit_log.view",
        "resource": "audit_log",
        "action": "view",
        "description": "View organization audit trail and activity log",
    },
    {
        "codename": "custom_roles.manage",
        "resource": "custom_roles",
        "action": "manage",
        "description": "Create and configure custom organizational roles",
    },
]

# Set of all codenames for quick membership resolution
ALL_PERMISSION_CODENAMES: Final[set[str]] = {p["codename"] for p in PERMISSION_CATALOG}

# System role identifiers
SYSTEM_ROLE_OWNER: Final[str] = "owner"
SYSTEM_ROLE_ADMIN: Final[str] = "admin"
SYSTEM_ROLE_EDITOR: Final[str] = "editor"
SYSTEM_ROLE_VIEWER: Final[str] = "viewer"

SYSTEM_ROLES: Final[list[str]] = [
    SYSTEM_ROLE_OWNER,
    SYSTEM_ROLE_ADMIN,
    SYSTEM_ROLE_EDITOR,
    SYSTEM_ROLE_VIEWER,
]

# Default permissions assigned to each system role
SYSTEM_ROLE_PERMISSIONS: Final[dict[str, list[str]]] = {
    SYSTEM_ROLE_OWNER: list(ALL_PERMISSION_CODENAMES),
    SYSTEM_ROLE_ADMIN: [
        p for p in ALL_PERMISSION_CODENAMES if p != "organization.delete"
    ],
    SYSTEM_ROLE_EDITOR: [
        "invoices.view",
        "invoices.create",
        "invoices.edit",
        "invoices.send",
        "invoices.record_payment",
        "invoices.cancel",
        "clients.view",
        "clients.create",
        "clients.edit",
        "products.view",
        "products.create",
        "products.edit",
        "products.adjust_stock",
        "expenses.view",
        "expenses.create",
        "expenses.edit",
        "payments.view",
        "payments.create",
        "reports.view",
        "ai.use_assistant",
        "ai.generate",
        "organization.view",
        "team.view",
    ],
    SYSTEM_ROLE_VIEWER: [
        "invoices.view",
        "clients.view",
        "products.view",
        "expenses.view",
        "payments.view",
        "reports.view",
        "ai.use_assistant",
        "organization.view",
        "team.view",
    ],
}
