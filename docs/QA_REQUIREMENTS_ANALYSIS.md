# BizPilot — Requirements Analysis & QA Assessment

**Date:** September 3, 2026
**Author:** Senior QA Engineering
**Product:** BizPilot — Mini-ERP SaaS for small businesses (Invoicing, Clients, Inventory, Expenses, Reports, Teams)
**Codebase:** `/home/dev-dir/MiniERP/invoive_generator-next`
**Status:** Baseline for SaaS commercial launch

---

## 1. Purpose, Scope & References

### 1.1 Purpose
This document performs a formal **requirements analysis** of BizPilot ahead of selling it as a
SaaS. It (a) reconstructs the requirements baseline from the implemented system and available
documentation, (b) classifies each requirement by priority and testability, (c) identifies gaps,
ambiguities, conflicts, and compliance risks, and (d) defines the QA strategy and traceability
needed to certify a sellable release.

### 1.2 Scope
- **In scope:** all implemented features (auth, multi-org, RBAC, invoicing, payments, clients,
  products/inventory, expenses, dashboard, reports, search, settings, billing, AI), plus
  commercial-launch necessities (email, plan enforcement, compliance).
- **Out of scope:** mobile native apps, third-party integrations (QuickBooks, Zapier), white-label.

### 1.3 References
| Ref | Artifact |
|---|---|
| R1 | `SaaS_REPORT.md` — testing summary, feature inventory, gap list |
| R2 | `DJANGO_MIGRATION_PLAN.md` — backend migration & RBAC v2 plan |
| R3 | `README.md` — product description & declared roadmap gaps |
| R4 | `supabase/migrations/*` — 4 migrations defining data model + RLS |
| R5 | `lib/erp/*`, `app/(dashboard)/actions*.ts` — implemented behavior |
| R6 | `tests/e2e/*.spec.ts`, `tests/selenium/*` — current test assets |

### 1.4 Method
Requirements were **reverse-engineered from the implementation** (code + DB constraints) and
reconciled against R1/R3. Every requirement is tagged: priority (**MoSCoW**), verification method
(**T**=test, **A**=analysis, **D**=demonstration, **I**=inspection), and testability status.

---

## 2. Product Summary & Users

### 2.1 Business goal
Sell a subscription-based mini-ERP where a small business owner runs invoicing, inventory, and
expenses, and invites staff with controlled access. Revenue model: Free / Pro / Enterprise tiers.

### 2.2 Personas & stakeholder quality expectations
| ID | Persona | Expectation |
|---|---|---|
| P1 | **Solo owner** (primary buyer) | Zero-setup start; first invoice in < 5 min; trustworthy financial numbers |
| P2 | **Org owner w/ staff** | Precise control over what each role can see/do; safe invite/revoke |
| P3 | **Staff member** (editor/viewer) | Fast UI; clear errors when lacking permission |
| P4 | **Accountant** (viewer) | Accurate reports; exportable data |
| P5 | **BizPilot ops/support** | Observability, audit trail, low support load from billing confusion |
| P6 | **Prospect (anonymous)** | Working free experience; honest pricing page |

### 2.3 Critical quality drivers (top 4 for this product)
1. **Data correctness** — monetary figures, invoice numbering, stock levels (P1/P4 trust)
2. **Access isolation** — cross-org and cross-role leakage is existential for a B2B SaaS (P2)
3. **Billing integrity** — Stripe lifecycle vs. plan enforcement consistency (revenue + P5)
4. **Data durability** — no silent data loss on delete/downgrade (P1 trust, legal exposure)

---

## 3. Functional Requirements Baseline

Legend: **Pri** = MoSCoW (M/S/C/W) · **Ver** = verification (T/A/D/I) · **Status** = ✔ implemented,
◐ partial, ✘ missing. Sources cite concrete evidence (file/table/policy).

### 3.1 Authentication & User Management (FR-AUTH)

| ID | Requirement | Pri | Ver | Status | Evidence / Notes |
|---|---|---|---|---|---|
| FR-AUTH-01 | User shall register with email + password | M | T | ✔ | Supabase Auth; `sign-up-form.tsx` |
| FR-AUTH-02 | User shall log in with Google OAuth | M | T | ✔ | `login-form.tsx`, `auth/callback/route.ts` |
| FR-AUTH-03 | User shall reset a forgotten password via email flow | M | T | ✔ | forgot/update password forms |
| FR-AUTH-04 | On signup, system shall auto-create a profile AND a personal organization | M | T | ✔ | DB trigger (R4); single point of failure for onboarding — needs explicit test |
| FR-AUTH-05 | Session shall auto-refresh; expired sessions redirect to login | M | T | ✔ | `lib/supabase/proxy.ts`, middleware |
| FR-AUTH-06 | On login, user shall auto-claim pending team invites matching their email | M | T | ✔ | `claimPendingInvites()` (org.ts) |
| FR-AUTH-07 | Two-factor authentication (TOTP) | S | T | ✘ | Report #20 — post-launch |
| FR-AUTH-08 | Session management (view/revoke active sessions) | S | T | ✘ | Report §4.7 |
| FR-AUTH-09 | Auth endpoints shall be rate-limited | M | T | ✘ | Report #10 — brute-force exposure today |

**QA note (HIGH):** FR-AUTH-06 relies on **email equality only**. Ambiguity: what if two orgs
invite the same email with different intended roles, or an email is invited before the account
exists and a *different* person later registers that address? Requires defined rules + tests.

### 3.2 Organization Management (FR-ORG)

| ID | Requirement | Pri | Ver | Status | Evidence / Notes |
|---|---|---|---|---|---|
| FR-ORG-01 | User shall belong to multiple organizations | M | T | ✔ | `team_members` multi-row per user |
| FR-ORG-02 | User shall switch active organization (persists across pages) | M | T | ✔ | `bp_active_org` cookie + switcher |
| FR-ORG-03 | User shall create a new organization and become its owner | M | T | ✔ | org create dialog |
| FR-ORG-04 | Org holds business profile (name, logo, website, email, address, phone) | M | T | ✔ | organizations table |
| FR-ORG-05 | Org holds invoice defaults (currency, tax rate, notes, terms) | M | T | ✔ | R4 migration |
| FR-ORG-06 | Deleting an org shall cascade-delete all its business data | M | T | ✔ | FK cascades — **destructive; needs confirmation dialog + audit test** |
| FR-ORG-07 | Org deletion shall be owner-only | M | T | ✔ | RLS `org_role(id) = 'owner'` |

### 3.3 Team / Access Management (FR-TEAM)

| ID | Requirement | Pri | Ver | Status | Evidence / Notes |
|---|---|---|---|---|---|
| FR-TEAM-01 | Admin shall invite a member (name, email, role, department) | M | T | ✔ | team page; unique `(org, lower(email))` |
| FR-TEAM-02 | Roles: owner > admin > editor > viewer, rank-ordered | M | T | ✔ | `ROLE_RANK` (org.ts) + RLS functions |
| FR-TEAM-03 | Viewer: read-only across org data | M | T | ✔ | RLS `can_write_org`; e2e `roles.spec.ts` |
| FR-TEAM-04 | Editor: CRUD on operational data (invoices/clients/products/expenses) | M | T | ✔ | RLS |
| FR-TEAM-05 | Admin: + team management + org settings | M | T | ✔ | RLS `can_manage_org` |
| FR-TEAM-06 | Owner: + org deletion; last active owner protected from demotion/removal | M | T | ✔ | RLS + UI guard — **needs adversarial tests (concurrent demotion of last owner)** |
| FR-TEAM-07 | Member role shall be changeable by admin | M | T | ✔ | team page |
| FR-TEAM-08 | Pending invite visible with status; claimable at login | M | T | ✔ | FR-AUTH-06 flow |
| FR-TEAM-09 | Org-defined **custom roles** with granular permissions | C | T | ✘ | Per stakeholder vision; designed in R2 §5 — Enterprise feature |
| FR-TEAM-10 | Audit log of who did what, when | S | T | ✘ | Report #19 |
| FR-TEAM-11 | Invite email shall be sent to the invitee | M | T | ✘ | README admits manual share; **blocks team-feature saleability** |

**QA note (HIGH):** role hierarchy is enforced twice (UI + RLS) with no single test of parity.
Any new endpoint/action must be proven blocked for lower roles at the **DB level**, not only hidden
in UI (the e2e currently only asserts UI hiding + page-level error).

### 3.4 Invoicing & Payments (FR-INV / FR-PAY)

| ID | Requirement | Pri | Ver | Status | Evidence / Notes |
|---|---|---|---|---|---|
| FR-INV-01 | Create invoice: client, line items, currency, tax, discount | M | T | ✔ | `create-invoice` page + actions |
| FR-INV-02 | Auto invoice number `INV-YYYY-NNN`, unique per org, sequential | M | T | ✔ | Ambiguity: **reset behavior at year rollover & concurrency under simultaneous creates — untested** |
| FR-INV-03 | Invoice statuses: draft / pending / paid / overdue / cancelled | M | T | ✔ | `types.ts`; **overdue transition mechanism undefined — no scheduler found (open issue §6)** |
| FR-INV-04 | Save as draft or mark as sent | M | T | ✔ | actions |
| FR-INV-05 | Stock warning when line qty exceeds product stock | S | T | ✔ | warning only, not blocking — intended? (question §6) |
| FR-INV-06 | Invoice detail page with status history | M | T | ✔ | `invoices/[id]` |
| FR-INV-07 | Record payment (amount, date, 5 methods, reference) | M | T | ✔ | payments table |
| FR-INV-08 | Partial payments with running balance | M | T | ✔ | **rounding/overpayment rules undefined (§6)** |
| FR-INV-09 | Auto-mark invoice paid when payments ≥ balance | M | T | ✔ | service rule |
| FR-INV-10 | PDF export of invoice | M | T | ✔ | `@react-pdf/renderer`; **fidelity vs preview, currency symbols, page breaks — needs visual regression** |
| FR-INV-11 | Invoice list: search, status tabs, summary stats | M | T | ✔ | invoices page |
| FR-INV-12 | Edit invoice after creation | M | T | ✘ | Report #7 — **high commercial impact** |
| FR-INV-13 | Delete confirmation dialog for invoices | M | T | ✘ | Report #8 |
| FR-INV-14 | Send invoice to client by email (PDF attached) | M | T | ✘ | README declares unwired |
| FR-INV-15 | Recurring invoices (weekly…yearly) | S | T | ✘ | Report #12 |
| FR-INV-16 | Public shareable invoice link (no login) | S | T | ◐ | README: anonymous create-invoice exists; public *view* link missing |
| FR-INV-17 | AI line-item generation from plain-language description | S | T | ✔ | `ai-actions.ts` — editor+ role |
| FR-INV-18 | Stock auto-deduction on send; restore on cancel | S | T | ✘ | Not found in code — **conflicts with R1 §2 claim; clarify (§6)** |
| FR-PAY-01 | Payment methods: Cash/Card/Bank Transfer/Mobile Money/Other | M | T | ✔ | check constraint |
| FR-PAY-02 | Payment history per invoice | M | T | ✔ | detail page |

### 3.5 Clients, Products/Inventory, Expenses (FR-CLI / FR-PRD / FR-EXP)

| ID | Requirement | Pri | Ver | Status | Evidence / Notes |
|---|---|---|---|---|---|
| FR-CLI-01 | Create client (name, email, phone, address, company) | M | T | ✔ | |
| FR-CLI-02 | Client list: search, active/inactive tabs | M | T | ✔ | |
| FR-CLI-03 | Per-client stats: invoice count, lifetime value, outstanding | M | T | ✔ | aggregation correctness needs value tests |
| FR-CLI-04 | Quick invoice from client context | S | T | ✔ | |
| FR-CLI-05 | Edit client | M | T | ✘ | Report #4 |
| FR-CLI-06 | Delete client — behavior with existing invoices | M | T | ◐ | FK behavior undefined to user; needs spec + destructive test |
| FR-PRD-01 | Create product (name, price, currency, category, unit, SKU) | M | T | ✔ | |
| FR-PRD-02 | Inventory: stock_quantity, low_stock_threshold, track_stock | M | T | ✔ | |
| FR-PRD-03 | Inline stock adjustment (+/−) | M | T | ✔ | **negative-stock boundary untested** |
| FR-PRD-04 | Activate/deactivate product | S | T | ✔ | |
| FR-PRD-05 | Low-stock alerts on dashboard | M | T | ✔ | |
| FR-PRD-06 | Edit product | M | T | ✘ | Report #5 |
| FR-EXP-01 | Create expense (9 categories, vendor, method, date) | M | T | ✔ | category list in `types.ts` |
| FR-EXP-02 | Expense list: search + category filter + summary stats | M | T | ✔ | |
| FR-EXP-03 | Edit expense | M | T | ✘ | Report #6 |
| FR-EXP-04 | Receipt upload/attachment | S | T | ✘ | Report #17 |

### 3.6 Dashboard, Reports, Search, Settings, Marketing (FR-DASH / FR-RPT / FR-SRCH / FR-SET / FR-MKT)

| ID | Requirement | Pri | Ver | Status | Evidence / Notes |
|---|---|---|---|---|---|
| FR-DASH-01 | Stats: revenue, outstanding, expenses, clients, invoice/product counts | M | T | ✔ | **mixed-currency summation risk (§6-Q4)** |
| FR-DASH-02 | Monthly trend series (6 months) + revenue-vs-expense chart | M | T | ✔ | timezone/month-boundary tests needed |
| FR-DASH-03 | Low-stock alerts & recent activity | M | T | ✔ | |
| FR-RPT-01 | Revenue vs expense report + totals (profit, outstanding) | M | T | ✔ | `getReportData` |
| FR-RPT-02 | Expense by category + top clients | M | T | ✔ | |
| FR-RPT-03 | 12-month series | M | T | ✔ | |
| FR-RPT-04 | BizPilot AI assistant answers business questions from live data | S | T | ✔ | viewer+; **must never leak other orgs' data into prompt context (security test)** |
| FR-SRCH-01 | Global search across invoices, clients, products, team | M | T | ✔ | **known bug: scoped by user_id not organization_id (Report #9) — must be fixed + regression-locked** |
| FR-SET-01 | Edit profile (name, company details) | M | T | ✔ | |
| FR-SET-02 | Edit invoice defaults | M | T | ✔ | defaults propagate to new invoices only |
| FR-MKT-01 | Public pages: landing, pricing, contact, get-started, terms, privacy, help | M | T | ✔ | R1: all PASS |
| FR-MKT-02 | Pricing page must match actual enforced plans | M | I | ◐ | 3 tiers displayed; **no enforcement backend yet (§3.7)** — legal/misrepresentation risk |

### 3.7 Subscription / Billing (FR-BILL)

| ID | Requirement | Pri | Ver | Status | Evidence / Notes |
|---|---|---|---|---|---|
| FR-BILL-01 | Stripe Checkout for Pro/Enterprise subscription | M | T | ◐ | `actions/stripe.ts` exists + billing settings page |
| FR-BILL-02 | Webhook sync of subscription state (created/updated/cancelled/payment_failed) | M | T | ◐ | `app/api/webhooks/stripe/route.ts`; **idempotency & out-of-order events untested** |
| FR-BILL-03 | Subscription status visible in billing settings | M | T | ◐ | `subscriptions` table (1 row/org) |
| FR-BILL-04 | Stripe Customer Portal (manage/cancel) | M | T | ◐ | `createCustomerPortalSession` |
| FR-BILL-05 | Plan limit enforcement (invoices, clients, team size, features per tier) | M | T | ✘ | **core SaaS gap — a free user currently has unlimited use** |
| FR-BILL-06 | 14-day trial management | M | T | ✘ | |
| FR-BILL-07 | Upgrade/downgrade with proration | M | T | ✘ | |
| FR-BILL-08 | Graceful downgrade (read-only, never data deletion) | M | T | ✘ | must be spec'd before launch |
| FR-BILL-09 | Receipt/subscription emails | S | T | ✘ | |

### 3.8 AI Features (FR-AI)

| ID | Requirement | Pri | Ver | Status | Evidence / Notes |
|---|---|---|---|---|---|
| FR-AI-01 | Line-item generation gated to editor+ | M | T | ✔ | `requireRole("editor")` |
| FR-AI-02 | Assistant available to all org members (viewer+) | M | T | ✔ | `requireOrg()` |
| FR-AI-03 | AI failures degrade gracefully with user-friendly error | M | T | ✔ | `AiUnavailableError` chain — **needs fault-injection tests** |
| FR-AI-04 | Prompt context strictly limited to caller's org data | M | T | ✔ code, ✘ test | **critical security test missing** |
| FR-AI-05 | AI usage metering/quota per plan | C | T | ✘ | R2 §6 backlog |

---

## 4. Non-Functional Requirements (NFR)

| ID | Category | Requirement | Pri | Ver | Status / Evidence |
|---|---|---|---|---|---|
| NFR-SEC-01 | Isolation | A user shall never read/write data of an organization they are not an active member of (enforced server-side) | M | T | RLS present; **no automated cross-tenant test suite — top risk** |
| NFR-SEC-02 | Authorization depth | Privilege checks enforced at DB layer even when UI is bypassed (direct action/URL/API call) | M | T | RLS ✔; e2e only checks UI today |
| NFR-SEC-03 | Secrets | No secret in client bundle; AI/Stripe keys server-side only | M | I | ✔ (`server-only`, `NEXT_PUBLIC_` audit needed) |
| NFR-SEC-04 | Headers & hardening | CSP, HSTS, X-Frame-Options; CSRF audit; Zod on all inputs | M | T | ✘ (Report §4.7) |
| NFR-SEC-05 | Rate limiting | Auth + mutations + AI endpoints rate-limited | M | T | ✘ (Report #10) |
| NFR-PERF-01 | Responsiveness | Dashboard lists p95 < 2 s with 10k invoices/org | M | T | ✘ no perf baseline |
| NFR-PERF-02 | Scale | System usable at 1,000 orgs / 10k invoices per org | M | T | ✘ indexes exist (user_id, dates); org_id indexes partial |
| NFR-REL-01 | Availability | ≥ 99.5% monthly (managed hosting) | M | A | ✘ no monitoring/SLO defined |
| NFR-REL-02 | Backup/DR | Daily DB backups; RPO ≤ 24 h, RTO ≤ 8 h | M | A | ✘ (Report §5) |
| NFR-REL-03 | Observability | Error tracking, uptime, structured logs | M | T | ✘ Sentry planned (Report §4.9) |
| NFR-DATA-01 | Integrity | Monetary arithmetic exact (numeric(12,2)); no float rounding drift | M | T | schema ✔; **no property-based/rounding tests** |
| NFR-DATA-02 | Durability | Deletes are explicit user actions; no silent data loss | M | T | cascade rules exist; UX confirmations missing |
| NFR-USE-01 | Usability | Core flow (signup → first invoice sent) ≤ 5 min, unaided | M | D | ✔ suspected; needs moderated usability test |
| NFR-USE-02 | Accessibility | WCAG 2.1 AA on dashboard flows | S | T | ✘ untested (Radix helps but unverified) |
| NFR-USE-03 | Compatibility | Chrome/Edge/Firefox/Safari latest 2; responsive ≥ 360 px | M | T | Firefox manual only (R1); Playwright Chromium-only |
| NFR-LOC-01 | i18n | English-only acceptable at launch; no hard-coded-date/locale bugs | S | T | ◐ date-fns present; locale audit needed |
| NFR-CUR-01 | Currency | Multi-currency stored per record; **aggregation semantics must be defined & disclosed** | M | A+T | ✘ README admits naive summation — **fix or restrict UI to single-currency mode** |
| NFR-COMP-01 | Privacy | GDPR: export + delete my data; DPA-ready; cookie consent | M | T | ✘ |
| NFR-COMP-02 | Email compliance | Unsubscribe footer, sender domain (SPF/DKIM/DMARC) | M | T | ✘ no email system |
| NFR-COMP-03 | Invoicing legality | Invoice content meets jurisdictional requirements (tax IDs, sequential numbers, VAT rules) | C | A | ✘ undefined — **legal analysis needed before selling in EU/UK** |
| NFR-MAINT-01 | Testability | CI runs lint+typecheck+unit+e2e on every PR; coverage gate | M | T | ✘ no CI found in repo |
| NFR-MAINT-02 | Documentation | README accurate vs behavior | M | I | ✘ drift found (§5) |

---

## 5. Requirement Defects Found During Analysis

Issues discovered by reconciling docs ↔ code (these are QA findings, not features):

| # | Type | Finding | Impact | Recommendation |
|---|---|---|---|---|
| D-01 | Doc drift | README says "Next.js 15"; `package.json` = **16.1.1** | Minor | Update README |
| D-02 | Doc drift | README Roadmap says "no payment processor integrated yet"; code contains full Stripe checkout/portal/webhook + `subscriptions` table | **High** (misleading to contributors/buyers) | Update README or extract feature flag reality |
| D-03 | Doc/code conflict | R1 §2 claims "Inventory tracking with stock **auto-deduction**"; no deduction logic found in invoice send path | **High** (financial-data claim) | Implement or correct claim; write spec |
| D-04 | Unimplemented UI affordance | "Send invoice by email" shown but non-functional (README admits) | High (trust) | Hide button until FR-INV-14 ships |
| D-05 | Known unfixed bug | Global search scoped to `user_id`, not `organization_id` (R1 #9) | High (privacy/correctness) | Fix + regression test before launch |
| D-06 | Spec absence | No documented rule for: invoice numbering rollover, `overdue` transitions, overpayment, client deletion with invoices | High (test oracle missing) | Write behavior spec, then tests |
| D-07 | Test env coupling | e2e depends on seeded demo users (`viewer@acmesolutions.co` / `demo1234`) in `supabase/seed.sql` | Medium | Dedicated test fixtures + teardown; never seed demo creds in prod |

---

## 6. Ambiguities & Open Questions for Stakeholders

These must be answered before test oracles can be finalized. (QA cannot "pass/fail" undefined behavior.)

| # | Question | Blocks |
|---|---|---|
| Q1 | When exactly does an invoice become `overdue` — on read (due_date < today) or by a scheduled job? What cancels it? | FR-INV-03 tests |
| Q2 | Invoice numbering: strict gapless sequence (legal requirement in some countries) or best-effort? Reset each January? | FR-INV-02 |
| Q3 | May a payment exceed the invoice balance (credit)? Refund flow? | FR-INV-08/09 |
| Q4 | Mixed-currency orgs: are dashboard/report totals summed naively, converted, or filtered to org default currency? | FR-DASH-01, NFR-CUR-01 |
| Q5 | Over-stock on invoice lines: warn only, or block sending? Deduct stock at send or at payment? | FR-INV-05/18 |
| Q6 | What happens when a client with invoices is deleted — block, anonymize, or cascade (losing financial history)? | FR-CLI-06 |
| Q7 | Invite claim: if email A is invited as Editor in Org1 and Admin in Org2, both claimed? What if the invitee never signs up? Expiry? | FR-AUTH-06, FR-TEAM-08 |
| Q8 | Can two `owner`-role members exist? Transfer of ownership flow? | FR-TEAM-06 |
| Q9 | Downgrade behavior when usage exceeds new plan limits (read-only? blocked writes?) — must be defined before Stripe launch | FR-BILL-08 |
| Q10 | Is the anonymous "create invoice without login" (README feature) still intended for the SaaS, and where does that data live? | Onboarding scope |
| Q11 | Target markets for launch (defines NFR-COMP-03 tax/invoice legality + data residency)? | Compliance scope |
| Q12 | Trial: 14 days of Pro, or freemium-with-limits? Both appear in docs | FR-BILL-06, pricing page copy |

---

## 7. Acceptance Criteria (sample — critical flows)

Format: Given/When/Then. Full AC sheets to be produced per feature during test design.

### AC-INV-01 (FR-INV-01/02/04) — Create & number invoice
- **Given** org default currency = EUR and default tax = 10%, **when** Owner creates an invoice with 2 lines (100.00 × 1, 50.00 × 2) and saves as draft, **then** subtotal = 200.00, tax = 20.00, total = 220.00, status = `draft`, number matches `INV-<currentYear>-NNN` with NNN = previous max + 1.
- **When** two invoices are created concurrently (API-level parallel), **then** numbers are unique and gapless for that org (per Q2 ruling).

### AC-PAY-01 (FR-INV-07/08/09) — Partial payments & auto-settle
- **Given** invoice total 220.00 status `pending`, **when** payments of 100.00 and 120.00 are recorded, **then** after the second payment status = `paid`, balance = 0.00, and payments list shows both entries with methods preserved.

### AC-SEC-01 (NFR-SEC-01) — Cross-tenant isolation
- **Given** User B (member of Org2 only), **when** B requests any record of Org1 by direct ID via any mutating action or URL guess, **then** response is 404/403, no field of the record is reflected, and an audit entry is written (once FR-TEAM-10 exists).

### AC-TEAM-01 (FR-TEAM-03/06) — Role boundaries & owner protection
- **Given** Viewer V in Org1, **when** V invokes any create/update/delete action for Org1 (UI, direct URL, or replayed request), **then** every mutation is rejected with a permission error and no data changes.
- **Given** Org1 has exactly one active Owner, **when** that owner is demoted or removed via any path, **then** the operation is rejected with an explanatory message and ownership is preserved.

### AC-BILL-01 (FR-BILL-05/08) — Plan enforcement
- **Given** Free plan limit = 10 invoices/month, **when** the 11th invoice is attempted, **then** creation is blocked with an upgrade-prompt payload; existing invoices remain fully readable; **when** the subscription lapses (`past_due`), writes block but reads continue.

### AC-AI-01 (FR-AI-04) — Assistant data confinement
- **Given** Viewer V of Org1 asks the assistant "what is my biggest client?", **when** the prompt context is built, **then** it contains only Org1 aggregates; a question about Org2 data yields "no data"; no other org's identifiers appear in the answer or logs.

---

## 8. Test Strategy & Current Coverage Assessment

### 8.1 Current test assets (as-is)
| Asset | Scope | Assessment |
|---|---|---|
| `tests/e2e/*.spec.ts` (Playwright) | roles permission check, PDF download | Only 2 specs seen; Chromium only (`playwright.config.ts`); depends on seeded demo credentials; no CI wiring found |
| `tests/selenium/*.py` | dashboard, invoices, create-invoice, reports | Parallel/duplicate framework to Playwright — consolidate |
| Manual testing (R1) | 10 pages, Firefox | Good breadth, not repeatable; no written test cases/oracles |

### 8.2 Coverage gaps vs. requirements (to-close plan)
| Gap | Requirement refs | Priority to close |
|---|---|---|
| **No unit tests** for money math, numbering, balances, permissions | FR-INV-02/08/09, FR-CLI-03, FR-DASH-01 | P0 — cheapest defect prevention |
| **No cross-tenant security suite** (org isolation via every action) | NFR-SEC-01/02 | P0 — existential for SaaS |
| **No RBAC matrix test** (4 roles × every action, DB-level) | FR-TEAM-02..06 | P0 |
| **No billing tests** (webhook idempotency, retries, plan gates) | FR-BILL-01..09 | P0 before selling |
| No API/contract tests | all FR | P1 |
| No visual/PDF regression | FR-INV-10 | P1 |
| Single-browser e2e; no responsive | NFR-USE-03 | P1 |
| No a11y, perf, i18n checks | NFR-USE-02, NFR-PERF-01, NFR-LOC-01 | P2 |
| No CI pipeline running any of it | NFR-MAINT-01 | P0 — everything else depends on it |

### 8.3 Test levels & tooling (to-be)
1. **Unit** (Vitest): pricing/totals/balance/numbering/permission-matrix pure logic — target ≥ 85% on `lib/erp/*`
2. **Integration/API** (against local Supabase via testcontainers/CLI): every server action per role; DB-level RLS assertions via a second, non-member user context
3. **E2E** (Playwright, multi-project: Chromium/Firefox/WebKit + mobile viewport): critical journeys — signup→personal org→first invoice→payment→paid; invite→claim→role gating; billing checkout (Stripe test clocks/mocks)
4. **Security**: OWASP-lite checklist, cross-tenant fuzzing of IDs, auth bypass attempts, secret-scan in bundle, dependency scanning (Dependabot/audit)
5. **Non-functional**: k6 smoke (NFR-PERF), axe-core in Playwright (NFR-USE-02), axe + manual SR pass on core flows
6. **Billing**: Stripe CLI webhook replay, out-of-order events, duplicate delivery, test-clock trials
7. **Data migration** (when R2 executes): row-count/checksum reconciliation + parallel-run diff of reports

### 8.4 Entry & exit criteria
**Test entry:** build deploys to staging; migrations applied; seed data versioned; Q1–Q12 answered for the features in scope.
**Release exit (SaaS "sellable" gate):**
- 100% of **M**ust requirements ✔ and their ACs pass
- 0 open Critical/High defects; NFR-SEC-01/02, NFR-DATA-01, NFR-MAINT-01 verified
- FR-BILL-05 (plan enforcement) + FR-TEAM-11 (invite email) + FR-INV-13 (delete confirms) shipped
- D-01…D-07 documentation/spec defects resolved
- E2E green on 3 browsers in CI for 5 consecutive days on staging

### 8.5 Risk-based test prioritization (risk = likelihood × impact)
| Rank | Area | Why |
|---|---|---|
| 1 | Tenant isolation & RBAC | One leak = SaaS over |
| 2 | Invoice/payment money flows | Customer financial trust; legal exposure |
| 3 | Stripe subscription lifecycle | Direct revenue impact; webhook edge cases |
| 4 | Auth & invite claim flows | Lockout/incorrect access paths |
| 5 | Reports/dashboard aggregates | Silent wrong numbers destroy credibility |
| 6 | AI features | Data confinement; graceful degradation |
| 7 | Marketing pages | Low risk, high visibility |

---

## 9. Launch Readiness Verdict (QA opinion)

**Not sellable today.** The product is feature-rich and stable for demo/manual use (R1 shows zero
critical console errors), but a paying customer expects — and the current baseline lacks:

1. **Plan enforcement & billing integrity** (FR-BILL-05/06/08) — the pricing page currently promises tiers that nothing enforces (also a misrepresentation risk, FR-MKT-02).
2. **Transactional email** (FR-TEAM-11, FR-INV-14) — team invites and invoice delivery are manual, which breaks the sold workflows.
3. **Edit capability + delete confirmations** (FR-CLI-05, FR-PRD-06, FR-EXP-03, FR-INV-12/13) — day-2 operations every customer hits in week one.
4. **Compliance minimums** (NFR-COMP-01/02/03, GDPR, invoice legality) — required to charge money in most jurisdictions.
5. **An automated security & money-math test suite in CI** — the current 2-spec e2e cannot protect a commercial release.

**Recommended path:** fix D-01…D-07, answer Q1…Q12, deliver items 1–5 above with the test strategy
in §8.3, then re-run this analysis as a release audit. Estimated QA effort to launch gate: ~4–5
engineer-weeks (can overlap with the Django migration in R2, which should adopt this requirements
baseline and traceability matrix as its acceptance scope).

---

## 10. Traceability (summary matrix)

| Requirement group | # Reqs | Implemented | Partial | Missing | Automated test exists |
|---|---|---|---|---|---|
| FR-AUTH | 9 | 6 | 0 | 3 | partial (login happy path only) |
| FR-ORG | 7 | 7 | 0 | 0 | none |
| FR-TEAM | 11 | 8 | 0 | 3 | 1 spec (viewer UI only) |
| FR-INV/FR-PAY | 20 | 13 | 2 | 5 | 1 spec (PDF) |
| FR-CLI/PRD/EXP | 14 | 10 | 1 | 3 | none |
| FR-DASH/RPT/SRCH/SET/MKT | 12 | 10 | 2 | 0 | none |
| FR-BILL | 9 | 0 | 4 | 5 | none |
| FR-AI | 5 | 4 | 0 | 1 | none |
| NFR | 22 | 3 | 3 | 16 | none |
| **Total** | **109** | **61 (56%)** | **12 (11%)** | **36 (33%)** | **~4 specs total** |

*Note: counts are from reverse-engineering the implementation; they will be refined as AC sheets
are authored per feature. The matrix is the anchor for the test plan and for the Django migration's
acceptance scope (R2).*

— End of document —






