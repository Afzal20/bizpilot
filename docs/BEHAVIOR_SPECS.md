# BizPilot Domain Behavior Specifications (D-06)

This specification defines the formal business logic and lifecycle rules for BizPilot ERP domains, resolving the edge cases and ambiguities identified in `QA_REQUIREMENTS_ANALYSIS.md`.

---

## 1. Invoice Numbering & Annual Rollover

### 1.1 Format & Structure
- Format: `INV-<YYYY>-<NNN>` (e.g. `INV-2026-001`).
- Numbers are formatted with zero-padding (minimum 3 digits, expanding dynamically for high volumes: `001` through `9999+`).

### 1.2 Sequence Scope & Concurrency
- **Per-Organization Isolation**: Every organization maintains its own isolated invoice sequence. Invoice numbers in Organization A never conflict with or affect Organization B.
- **Atomic Allocation**: Sequences are generated within a database transaction using row-level locking (`select_for_update()`) on `InvoiceSequence`. This guarantees strictly gapless, unique numbering even under concurrent invoice creations.

### 1.3 Annual Rollover Rule
- Sequence counters reset to `1` on **January 1** of each calendar year.
- The `InvoiceSequence` model maintains `(organization, year)` as a composite unique constraint. When the calendar year changes, a new sequence record is instantiated starting with `last_number = 0`.

---

## 2. Invoice Lifecycle & Status Transitions

### 2.1 State Machine
The invoice lifecycle transitions through the following statuses:
1. `draft`: Editable working invoice. No stock deducted, no balance due notifications sent.
2. `pending`: Issued and sent to the client. Stock is deducted for tracked products. Balance due is active.
3. `overdue`: Due date has passed (`due_date < current_date`) while the balance remains unpaid (`balance_due > 0.00`).
4. `paid`: Cumulative recorded payments equal or exceed the invoice total (`paid_amount >= total`).
5. `cancelled`: Voided invoice. Restores previously deducted inventory stock.

### 2.2 Overdue Transition Mechanism
- **Dynamic Calculation**: An invoice with status `pending` where `due_date < timezone.localdate()` and `balance_due > 0` is treated as overdue in business logic and reports.
- **Scheduled Batch Job**: A Celery beat task runs daily at midnight to update `status = "overdue"` on all eligible invoices, triggering automated dunning emails.
- **Clearing Overdue Status**:
  - Recording payments that satisfy the remaining balance transitions the invoice immediately to `paid`.
  - Voiding the invoice transitions it to `cancelled`.

---

## 3. Payments, Balances, and Overpayment Policy

### 3.1 Balance Calculation
- `paid_amount = sum(payments.amount)`
- `balance_due = max(0.00, total - paid_amount)`

### 3.2 Auto-Settlement
- When a payment is recorded and `new_paid_amount >= invoice.total`, the invoice status transitions automatically to `paid`.
- The payment receipt email task (`send_payment_receipt_email_task`) is automatically dispatched asynchronously to the client.

### 3.3 Overpayment Rules
- Standard ERP validation restricts payment amounts exceeding `invoice.balance_due` to prevent unintended duplicate charges.
- If an overpayment is recorded (e.g., customer tip or deposit credit), `balance_due` caps at `0.00`. An overpayment balance is tagged on the payment record for reconciliation.

---

## 4. Client Deletion & Historical Durability

### 4.1 Financial Integrity Safeguard
- Clients cannot be cascade-deleted if they have associated invoices or payments. Financial audit records must never be lost.

### 4.2 Snapshot Durability
- Each `Invoice` stores permanent snapshots of the client's information at the time of invoice creation:
  - `client_name`
  - `client_email`
  - `client_address`
- If a client record is deleted, `Invoice.client` is set to `NULL` (`on_delete=models.SET_NULL`), while the historical PDF, reporting aggregates, and snapshots remain fully intact.

### 4.3 Soft Archive
- In the user interface, client deletion defaults to archiving (`is_active = False` / `status = "inactive"`). Inactive clients do not appear in active invoice creation dropdowns but remain visible in historical reports.

---

## 5. Inventory & Stock Management

### 5.1 Stock Deduction on Send
- For products with `track_stock = True`, stock quantities are decremented upon transitioning an invoice from `draft` to `pending` via `send_invoice()`.
- The `Invoice.stock_deducted` flag tracks deduction state to prevent duplicate decrements.

### 5.2 Stock Restoration on Cancel
- If an invoice in `pending` or `paid` status is cancelled via `cancel_invoice()`, the previously deducted line item quantities are automatically restored to `Product.stock_quantity`.
- `Invoice.stock_deducted` is reset to `False`.

### 5.3 Low Stock & Over-Stock Alerts
- Line items with quantities exceeding available stock trigger user warnings during invoice drafting.
- Stock levels dropping below `Product.low_stock_threshold` generate low-stock indicators on the product catalog and dashboard.

---

## 6. Access Control & Cross-Tenant Security (RBAC v2)

### 6.1 Multi-Tenant Boundaries
- All operational resources (`Client`, `Product`, `Invoice`, `Payment`, `Expense`, `Report`, `Role`, `Membership`, `Invite`) are strictly scoped to an `Organization`.
- The DRF `OrgScopedViewSet` layer extracts `org_id` from the URL, validates active membership in the requested organization, and filters all querysets by `organization_id`.
- Access attempts by non-members or cross-tenant guesses return `403 Forbidden` or `404 Not Found` without disclosing record metadata.

### 6.2 System Role Permissions
| Action | Owner | Admin | Editor | Viewer |
|---|---|---|---|---|
| View ERP Data & Reports | Yes | Yes | Yes | Yes |
| Create/Edit Invoices, Clients, Products, Expenses | Yes | Yes | Yes | No (403) |
| Record Payments & Stock Adjustments | Yes | Yes | Yes | No (403) |
| Manage Team & Invites | Yes | Yes | No (403) | No (403) |
| Manage Custom Roles | Yes | Yes | No (403) | No (403) |
| Manage Billing & Subscriptions | Yes | Yes | No (403) | No (403) |
| Delete Organization | Yes | No (403) | No (403) | No (403) |

### 6.3 Sole Owner Protection
- An organization must retain at least one active member with the `owner` role.
- Demoting or deleting the last active owner is blocked with a validation error.
