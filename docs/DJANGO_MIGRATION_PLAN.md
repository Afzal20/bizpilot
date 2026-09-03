# BizPilot — Django REST API Backend Migration & SaaS Feature Plan

**Date:** September 3, 2026
**Status:** Proposed
**Prerequisite reading:** `SaaS_REPORT.md`

---

## 0. Executive Summary

BizPilot today is a **Next.js monolith on Supabase**: all business logic lives in React Server
Components / Server Actions (`app/(dashboard)/actions*.ts`, `lib/erp/queries.ts`), authorization
lives in Postgres RLS policies, and auth lives in Supabase Auth (GoTrue).

This plan moves the backend to a **Django + Django REST Framework (DRF) API server**, while the
existing Next.js 16 app is kept as the frontend and converted from Server Actions/Supabase-SDK
calls to a typed HTTP API client.

Four workstreams:

| # | Workstream | Goal |
|---|------------|------|
| A | **Backend migration** | Replace Supabase client + server actions with Django REST API |
| B | **Subscription management** | Plans, entitlements, limits, Stripe lifecycle, trials |
| C | **User access & Organization management** | Custom org-defined roles with granular permissions (RBAC v2) |
| D | **AI platform** | Provider-agnostic AI gateway + a prioritized backlog of AI features |

**Target timeline:** ~14 weeks, with the API serving the existing frontend from Week 6.

---

## 1. Current State Audit (what exists in this repo today)

### 1.1 Data model (from `supabase/migrations/`)
- `organizations` — business profile, invoice snapshot defaults, `stripe_customer_id`, `stripe_subscription_id`
- `team_members` — org membership: `user_id`, `email`, `name`, `role` (`owner|admin|editor|viewer`), `department`, `status` (`active|pending`), `invited_by` — unique on `(organization_id, lower(email))`
- `clients`, `products`, `invoices`, `invoice_items`, `expenses`, `payments` — each with `organization_id` (`invoice_items` derived via parent invoice)
- `subscriptions` — one per org: Stripe IDs, `status`, `price_id`, `cancel_at_period_end`, period bounds
- `profiles` — per-user preferences + default invoice settings

### 1.2 Authorization today (RLS)
- SQL helpers: `is_org_member()`, `can_write_org()` (editor+), `can_manage_org()` (admin+), `org_role()`
- RLS on every table; role rank `viewer(0) < editor(1) < admin(2) < owner(3)` — mirrored in TS in `lib/erp/org.ts`
- Invite claim: pending `team_members` row claimed by matching JWT email at login (`claimPendingInvites`)

### 1.3 Backend surface to be replaced (Server Actions → REST endpoints)
- CRUD: clients, products, invoices (+items, payments), expenses, team invites, org settings
- Queries: dashboard stats, reports (`getReportData`), global search, per-client stats
- Stripe: `createCheckoutSession`, `createCustomerPortalSession`, `syncCheckoutSession`, webhook
- AI: `generateInvoiceItems` (editor+), `askBizPilot` (any member)

### 1.4 Pain points that motivate the migration
1. Business logic split between TS server actions and RLS — hard to unit test
2. RLS cannot express **custom, org-defined roles** (§5) — fixed 4-role ladder only
3. No plan-limit enforcement layer yet (report #10 / §4.1)
4. AI key/model logic buried in one Next module; no usage metering or quotas
5. A real REST API is prerequisite for report items #23 (public API) and #22 (mobile/PWA)

---

## 2. Target Architecture

```
┌──────────────────────────┐   HTTPS/JSON (JWT) + SSE        ┌─────────────────────────────┐
│  Next.js 16 Frontend     │ ──────────────────────────────► │  Django 5 + DRF API         │
│  (SSR marketing pages,   │ ◄────────────────────────────── │  apps:                      │
│   SPA for /dashboard)    │                                 │   accounts (auth/users)     │
└──────────────────────────┘                                 │   orgs (org + RBAC v2)      │
        │                                                    │   billing (Stripe/plans)    │
        │  Stripe Checkout (browser redirect)                │   erp (inv/cli/pro/exp/pay) │
        └───────────────────────────────────────────────────►│   reports, ai, core         │
                                                             └────────────┬────────────────┘
                ┌──────────────┐  ┌──────────────┐  ┌───────────▼─────────────────────┐
                │ Stripe API   │  │ Email (SES/  │  │ PostgreSQL (migrated from       │
                │ + webhooks   │  │ Resend)      │  │ Supabase) + Redis + Celery      │
                └──────────────┘  └──────────────┘  └─────────────────────────────────┘
```

### 2.1 Technology decisions

| Concern | Choice | Rationale |
|---|---|---|
| Framework | Django 5.2 LTS + DRF 3.15 | Mature, batteries included, native ORM over existing Postgres |
| Auth | `djangorestframework-simplejwt` (rotating refresh) + `django-allauth` for Google OAuth | JWT fits SPA + future mobile; OAuth parity with today's Google login |
| DB | PostgreSQL (reuse Supabase Postgres initially; dedicated instance later) | In-place data migration path |
| Async/jobs | Celery + Redis (Celery Beat for schedules) | Recurring invoices, email, webhook retries, AI batching |
| Validation | DRF Serializers | Single source of truth for request/response shapes |
| API docs | `drf-spectacular` (OpenAPI 3 → typed TS client via `openapi-typescript`) | Generated type-safe frontend client replaces hand-synced `lib/erp/types.ts` |
| Rate limiting | `django-ratelimit` + Redis (per-user and per-org buckets) | Report item #10 |
| Payments | Official `stripe` Python SDK, signed + idempotent webhook endpoint | Port of `actions/stripe.ts` |
| Email | `django-anymail` (Resend or SES) | Report §4.2 |
| Monitoring | Sentry (Python + JS) | Report §4.9 |

### 2.2 Repository layout

```
backend/
  manage.py
  config/               # settings/{base,dev,prod}.py, urls.py, celery.py
  apps/
    accounts/           # custom User, Profile, auth endpoints, OAuth
    orgs/               # Organization, Membership, Role, Permission, invites
    billing/            # Plan, PlanEntitlement, Subscription, StripeService, webhooks
    erp/                # clients, products, invoices, expenses, payments (package)
    reports/            # dashboard stats, reports, global search
    ai/                 # provider gateway, quotas, feature endpoints
    core/               # base models, pagination, exceptions, permissions, audit log
```

### 2.3 API conventions

- Base path `/api/v1/`; every domain endpoint is **org-scoped via URL**: `/api/v1/orgs/{org_id}/invoices/`
- Active-org context comes from the URL (not a cookie) — removes the `bp_active_org` cookie dependency and eliminates the org-scoping bug class flagged in the report (#9)
- Auth: `Authorization: Bearer <access>`; refresh at `POST /api/v1/auth/token/refresh/` with httpOnly-cookie fallback
- Errors: RFC 7807-style `{"type","title","status","detail","errors"}` via a custom DRF exception handler
- Pagination: cursor-based; filtering via `django-filter`
- Every mutating endpoint writes an `AuditLog` row (who, what, org, before/after diff)

---

## 3. Workstream A — Backend Migration Plan

### 3.1 Phased migration strategy

| Phase | Weeks | Deliverable |
|---|---|---|
| 1. Scaffold | 1 | Django project, Docker Compose (web/worker/beat/redis/postgres), CI, health check, OpenAPI schema |
| 2. Auth | 2 | JWT auth, Google OAuth, password reset, profile endpoints; **dual-run** with Supabase Auth |
| 3. Orgs & RBAC v2 | 3–4 | Org, membership, custom roles/permissions (§5); billing plan models in place (§4) |
| 4. Domain APIs | 5–7 | clients → products → invoices/payments → expenses → reports/search (each: models, serializers, viewsets, service layer, tests) |
| 5. Billing & webhooks | 6–8 | Stripe checkout/portal/webhooks, entitlement enforcement (§4) |
| 6. Frontend cutover | 6–9 | Replace server actions & Supabase SDK with generated API client, page by page |
| 7. AI platform | 8–10 | AI gateway + feature endpoints (§6) |
| 8. Data cutover & hardening | 10–12 | Full data migration, Supabase Auth → Django accounts, E2E tests, production hardening |

### 3.2 Domain endpoints (1:1 port of today's server actions)

```
POST   /api/v1/auth/signup | login | google | logout | password/reset | password/confirm
GET    /api/v1/me                                     # user + memberships + permissions
PATCH  /api/v1/me/profile

GET|POST            /api/v1/orgs/                     # list my orgs / create org (auto personal org)
GET|PATCH|DELETE    /api/v1/orgs/{org_id}/
GET                 /api/v1/orgs/{org_id}/dashboard/  # stats cards, trends, low stock
GET                 /api/v1/orgs/{org_id}/reports/    # getReportData equivalent
GET                 /api/v1/orgs/{org_id}/search/     # global search (org-scoped — fixes #9)

CRUD  /api/v1/orgs/{org_id}/clients/                  # + GET .../clients/{id}/stats/
CRUD  /api/v1/orgs/{org_id}/products/                 # + POST .../products/{id}/adjust-stock/
CRUD  /api/v1/orgs/{org_id}/invoices/                 # nested items; POST .../invoices/{id}/mark-paid/
POST  /api/v1/orgs/{org_id}/invoices/{id}/payments/   # partial payments, auto-settle (service layer)
CRUD  /api/v1/orgs/{org_id}/expenses/
POST  /api/v1/orgs/{org_id}/invoices/{id}/pdf/        # move PDF gen server-side (WeasyPrint) later; keep @react-pdf initially

GET|POST           /api/v1/orgs/{org_id}/members/     # team list, invite
PATCH|DELETE       /api/v1/orgs/{org_id}/members/{id}/
POST               /api/v1/auth/invites/claim/        # replaces claimPendingInvites()
GET|POST|PATCH     /api/v1/orgs/{org_id}/roles/       # custom role management (§5)
GET                /api/v1/orgs/{org_id}/audit-log/   # new (report #19)
```

### 3.3 Service layer rule
ViewSets stay thin (auth, permission, serialize). All business rules ported into `services.py`
modules with the existing semantics preserved:
- invoice number generation `INV-YYYY-NNN` (per-org sequence, `select_for_update`)
- auto-deduct stock on invoice send, restore on cancel
- payment auto-settle → `status=paid` when payments ≥ balance
- low-stock warnings when line item qty > `stock_quantity`
- delete cascades: org delete → all business data (mirrors current FK `on delete cascade`)

### 3.4 Data migration from Supabase
1. **Schema:** Django models via `inspectdb` as a starting point, then normalized (see §5.3 changes: `team_members` → `memberships` + `membership_roles`).
2. **Data:** `pg_dump`/copy per table into Django-managed tables; UUID PKs preserved; `auth.users` → `accounts_user` (bcrypt hashes are compatible — GoTrue uses bcrypt, Django supports it natively via `PASSWORD_HASHERS`), so **no password reset is required**.
3. **Auth cutover:** issue JWTs from Django behind the same domain; retire Supabase Auth keys after a 2-week dual-session window.
4. **RLS:** disabled once all reads/writes go through Django (service-role-style connection). Keep RLS enabled as defense-in-depth for any residual direct DB access.
5. **Verification:** row-count + checksum reconciliation script per table; parallel-run report queries and diff outputs before cutover.

---

## 4. Workstream B — Subscription Management

Extends the existing Stripe foundation (`subscriptions` table, checkout session, portal session,
webhook route) into a full plan/entitlement system.

### 4.1 Models (app: `billing`)

```python
class Plan(models.Model):                     # synced from Stripe Products (metadata "tier")
    code = SlugField(unique=True)             # "free" | "pro" | "enterprise"
    name, description, stripe_product_id
    tier = PositiveSmallIntegerField()        # ordering / upgrade rank
    trial_days = PositiveSmallIntegerField(default=14)
    is_active, sort_order

class PlanEntitlement(models.Model):          # per-plan limits & feature flags
    plan = FK(Plan, related_name="entitlements")
    key = CharField()                         # see catalog below
    value = JSONField()                       # int limit, bool, or list

class Subscription(models.Model):             # replaces/extends public.subscriptions
    organization = OneToOne(Organization)
    plan = FK(Plan)                           # resolved from stripe price → plan mapping
    stripe_subscription_id (unique), stripe_customer_id, stripe_price_id
    status = CharField()                      # trialing|active|past_due|canceled|incomplete|paused
    trial_start, trial_end, current_period_start, current_period_end
    cancel_at_period_end, canceled_at, ends_at

class PriceMapping(models.Model):             # stripe price_id → (plan, interval)
    stripe_price_id (unique), plan = FK(Plan), interval = "month"|"year"
```

### 4.2 Entitlement catalog (initial)

| Key | Type | Free | Pro | Enterprise |
|---|---|---|---|---|
| `max_invoices_per_month` | int | 10 | 500 | null (=unlimited) |
| `max_clients` | int | 5 | 200 | null |
| `max_products` | int | 10 | 1000 | null |
| `max_team_members` | int | 1 | 10 | null |
| `max_organizations` | int | 1 | 3 | null |
| `ai_credits_per_month` | int | 25 | 500 | 5000 |
| `recurring_invoices` | bool | false | true | true |
| `email_invoice_delivery` | bool | false | true | true |
| `client_portal` | bool | false | true | true |
| `data_export` | bool | false | true | true |
| `custom_roles` | bool | false | false | true (§5) |
| `audit_log` | bool | false | true | true |

### 4.3 Usage metering & enforcement

- `UsageCounter(org, key, period_start, count)` — Redis write-through + nightly Celery reconciliation to Postgres (invoices/month, AI credits, etc.)
- Enforcement as DRF permission class + service guard:

```python
# usage inside any ViewSet or service call
billing.enforce(org, "max_invoices_per_month")   # raises PlanLimitExceeded (HTTP 402/403 with upgrade hint)
billing.allow(org, "recurring_invoices")         # raises FeatureNotAvailable
```

- Response contract for blocked actions includes `{ "upgrade_required": true, "limit": "max_invoices_per_month", "plan": "free" }` so the frontend can render upgrade prompts (replaces today's hard errors).
- Downgrade: at period end, over-limit data is **never deleted** — features become read-only / write-blocked per entitlement.

### 4.4 Stripe lifecycle (port + harden of `actions/stripe.ts` + webhook route)

- `POST /api/v1/billing/checkout/` → Stripe Checkout Session (embeds `organization_id` in metadata, exactly as today) — permission: `billing.manage` (owner/admin)
- `POST /api/v1/billing/portal/` → Customer Portal session
- `GET  /api/v1/billing/subscription/` → current plan, status, usage vs limits, available plans
- Webhook `POST /api/v1/billing/webhooks/stripe/`: signature verification, event idempotency table (`stripe_event_id` unique), Celery handlers for
  `checkout.session.completed`, `customer.subscription.created|updated|deleted`, `invoice.payment_failed` (→ `past_due` + dunning email), `invoice.paid` (receipt email)
- Trials: personal orgs start on `free`; upgrading starts `trialing` (14 days) before first charge
- Upgrade/downgrade/proration: use Stripe subscriptions update API with proration; webhooks reconcile plan
- Failed payment dunning: 3 retries (day 3/7/10) via Celery Beat, then soft-lock write access, keep read access

### 4.5 Free-tier enforcement points to implement (report gap #10/#4.1)
1. Invoice create (monthly cap) — checked in `InvoiceService.create`
2. Client/product create (total cap)
3. Invite member (`max_team_members`)
4. Create additional org (`max_organizations`)
5. AI endpoints (`ai_credits_per_month`) — §6
6. Feature flags: recurring invoices, email delivery, exports, custom roles

---

## 5. Workstream C — Organization & User Access Management (RBAC v2)

**Goal (as requested):** organizations can define **their own roles** with **their own access
(permissions)**, and org control is driven entirely by the member's role — beyond the fixed
`owner > admin > editor > viewer` ladder that RLS enforces today.

### 5.1 Permission model

A fixed **permission catalog** (code lives in Django, cannot be edited by orgs — keeps
enforceability). Format: `resource.action`.

| Resource | Permissions |
|---|---|
| invoices | `view`, `create`, `edit`, `delete`, `send`, `record_payment` |
| clients | `view`, `create`, `edit`, `delete` |
| products | `view`, `create`, `edit`, `delete`, `adjust_stock` |
| expenses | `view`, `create`, `edit`, `delete` |
| reports | `view`, `export` |
| team | `view`, `invite`, `manage_roles`, `remove` |
| organization | `view`, `edit_settings`, `delete` |
| billing | `view`, `manage` |
| ai | `use_assistant`, `generate` |
| audit_log | `view` |

### 5.2 Models (app: `orgs`)

```python
class Organization(models.Model):     # 1:1 port of public.organizations (+ billing FK)
    ...same fields as today...

class Role(models.Model):
    organization = FK(Organization, null=True)      # null → system role template
    name = CharField()                              # "Accountant", "Sales", custom
    description = TextField(blank=True)
    is_system = BooleanField(default=False)         # owner/admin/editor/viewer seeded per org
    permissions = M2M("Permission")                 # the org's defined access
    unique_together (organization, name)

class Permission(models.Model):       # mirrors the catalog above
    codename = CharField(unique=True)               # "invoices.create"
    resource, action, description

class Membership(models.Model):       # replaces team_members
    organization = FK(Organization, related_name="memberships")
    user = FK(User, null=True)                      # null while invite pending
    email (lower, indexed), name, department
    roles = M2M(Role)                               # supports multiple roles per member
    status = "pending" | "active"                   # invite flow preserved
    invited_by, invited_at, joined_at
    unique_together (organization, email)
    # constraint: last active owner cannot be demoted/removed (was owner-protection in RLS)

class Invite(models.Model):           # tokenized invites (upgrade over email-matching)
    organization, email, roles M2M, invited_by
    token (unique, hashed), expires_at, accepted_at
```

### 5.3 Migration from the current 4-role system

Backfill map (data migration): `owner` → Role(`is_system`, perms = all) · `admin` → all minus
`organization.delete`, `billing.manage`→kept · `editor` → all `view/create/edit/delete` on
invoices/clients/products/expenses + `ai.*` · `viewer` → `*.view` + `ai.use_assistant`.
The old `team_members.role` column maps into seeded system Roles + `membership.roles` M2M.

### 5.4 Enforcement (replaces RLS as the primary gate)

```python
# core/permissions.py — resolves the caller's permission set for one org
def org_permissions(user, org_id) -> set[str]:
    # union of permissions across the member's roles; owner short-circuits to "*"
    # cached in Redis per (user, org) with invalidation on role/membership change

class OrgPermission(BasePermission):
    # DRF permission: checks org in URL, membership active, required permission(s)

class OrgScopedViewSet(ViewSet):
    # - queryset always filtered by org_id from URL (object-level isolation = RLS replacement)
    # - permission_map = {"GET": "invoices.view", "POST": "invoices.create", ...}
```

- Superuser checks in services (e.g., `team.manage_roles` requires admin-level system role OR
  the custom permission; removing/demoting the **last active owner** is always blocked in
  `MembershipService`).
- **Role change events invalidate** the Redis permission cache immediately (no stale access).
- Every check failure returns `403` with the missing permission codename for UI messaging.

### 5.5 API (app: `orgs`)

```
GET    /api/v1/orgs/{org_id}/roles/              # list roles + permission matrix
POST   /api/v1/orgs/{org_id}/roles/              # create custom role   [perm: custom_roles + team.manage_roles]
PATCH  /api/v1/orgs/{org_id}/roles/{id}/         # edit permissions (system roles locked except name/desc)
DELETE /api/v1/orgs/{org_id}/roles/{id}/         # only if unassigned
GET    /api/v1/orgs/{org_id}/permissions/        # catalog for the role builder UI
PATCH  /api/v1/orgs/{org_id}/members/{id}/roles/ # assign/replace member roles
GET    /api/v1/me/permissions/?org={org_id}      # my effective permission set (drives UI gating)
```

Gate: the **role builder UI** and custom-role endpoints are `custom_roles = true` entitlements
(Enterprise plan, §4.2) — a natural upsell. Free/Pro orgs keep the fixed system roles.

### 5.6 Frontend impact
- `lib/erp/org.ts` (`requireRole`, `roleAtLeast`) → replaced by `usePermissions()` hook fed by
  `/api/v1/me/permissions/`; UI gating becomes capability-based (`can("invoices.create")`) instead
  of rank-based — this is what makes custom roles first-class in the UI.
- Existing tests in `tests/e2e/roles.spec.ts` ported to the new permission matrix + extended with
  custom-role scenarios.

---

## 6. Workstream D — AI Integration (Platform + Feature Backlog)

### 6.1 AI Gateway (app: `ai`)

Port and generalize `lib/ai/openrouter.ts` into a provider-agnostic gateway:

```python
class LLMProvider(Protocol):
    def complete(self, messages, *, json_mode=False, max_tokens=1200, temperature=0.4,
                 stream=False) -> LLMResponse: ...

class OpenRouterProvider:   # first provider; keeps the existing free-model fallback chain
class OpenAIProvider:       # add for paid tiers / embeddings
class AnthropicProvider:    # optional fallback

# gateway features (all missing today):
# - model fallback chain + circuit breaker + timeout (kept from current code)
# - response caching (hash of prompt+model) in Redis
# - per-org quota: ai_credits_per_month (§4.2) enforced before every call
# - per-user rate limiting (e.g., 10 req/min)
# - usage log: org, user, feature, model, tokens in/out, latency, cost estimate
# - prompt-injection defense: org data injected as structured JSON (already the pattern in
#   askBizPilot), never raw user text concatenated into system prompts
# - SSE streaming endpoint for chat features
# - structured output validation: Pydantic schemas validated after extraction
```

### 6.2 Port of existing AI features (Weeks 8–9)

| # | AI task | Today | Django target |
|---|---|---|---|
| 1 | **AI invoice line-item generation** — plain-language description → structured items | `generateInvoiceItems` in `ai-actions.ts` | `POST /api/v1/orgs/{id}/ai/generate-items/` [perm `ai.generate`, entitlement `ai_credits_per_month`] |
| 2 | **BizPilot business assistant** — Q&A over live org report data | `askBizPilot` in `ai-actions.ts` | `POST /api/v1/orgs/{id}/ai/assistant/` + SSE streaming variant [perm `ai.use_assistant`] |

### 6.3 New AI feature backlog (prioritized)

| # | AI task | Value | Effort | Phase |
|---|---|---|---|---|
| 3 | **Expense auto-categorization** — suggest category/vendor from expense title+notes (9 existing categories) | High | S | 9–10 |
| 4 | **Payment reminder email drafting** — polite, tone-controlled reminder text per invoice | High | S | 9–10 |
| 5 | **Natural-language report answers** ("why did March profit drop?") — extends BizPilot with chart-attached answers | High | M | 10–11 |
| 6 | **Receipt/invoice OCR ingestion** — photo/PDF → expense or invoice draft (vision model) | High | L | 11–12 |
| 7 | **AI email delivery composer** — branded invoice email body + subject per client | Med | S | 11 |
| 8 | **Cash-flow forecast** — 3-month projection from revenue/expense series | Med | M | 11–12 |
| 9 | **Anomaly detection** — flag unusual expenses, duplicate invoices, price outliers | Med | M | 12 |
| 10 | **Semantic global search** — embeddings over invoices/clients/products ("the website redesign job") | Med | M | 12 |
| 11 | **Product description generator** — catalog copy from name/category | Low | S | 12 |
| 12 | **Invoice translation (i18n support, report #21)** — translate invoice into client language | Low | M | 13 |
| 13 | **Late-payer risk score** — client payment-behavior scoring for credit terms | Low | M | 13+ |
| 14 | **Voice-to-invoice** — dictate line items on mobile (PWA, report #22) | Low | L | 14+ |
| 15 | **Onboarding copilot** — guided org setup from a business description (auto-fills defaults, sample catalog) | Med | M | 13 |

### 6.4 AI governance
- Quota metering per feature (#3–#15 each consume credits; weights configurable per plan)
- `AiUsageLog` → surfaced to admins in billing page ("AI credits used this period")
- Model pinning per feature via Django settings (cheap models for classification #3/#9; stronger models for assistant #2/#5)
- Feature flags per plan (e.g., OCR is Pro+ only) using the §4.3 entitlement mechanism
- Evaluation set + regression prompts in CI to catch model-chain quality drift

---

## 7. Frontend Migration (Next.js stays)

1. Generate a typed API client from OpenAPI (`drf-spectacular` → `openapi-typescript` + `openapi-fetch`) into `lib/api/`
2. Introduce an auth provider that stores JWT access token in memory + refresh in httpOnly cookie; global 401 → refresh → retry interceptor
3. Replace per-module data calls page by page (order = domain API order, §3.1 Phase 4):
   - Supabase query calls in `lib/erp/queries.ts` → API client
   - Server Actions in `app/(dashboard)/actions.ts` → client-side mutations via API
   - `actions/stripe.ts` → `/api/v1/billing/*`; keep Stripe.js redirect flow in browser
   - `ai-actions.ts` → `/api/v1/orgs/{id}/ai/*` (add streaming UI for assistant)
4. Marketing/legal pages (`/`, `/pricing`, `/terms`, ...) stay server-rendered in Next.js — untouched
5. Delete `lib/supabase/*`, `lib/erp/org.ts` role helpers, and cookie-based org switching once the last dashboard page is cut over; the new `OrgSwitcher` writes a client-side org context that feeds `{org_id}` URLs
6. Keep existing Playwright/Selenium test suites green; only auth setup (login helper) and selectors that depend on loading states change

---

## 8. Timeline & Milestones

| Milestone | Week | Exit criteria |
|---|---|---|
| M1 Scaffold | 1 | CI green, Docker Compose up, OpenAPI served |
| M2 Auth parity | 2 | Signup/login/OAuth/reset via Django JWT; Supabase passwords importable |
| M3 Orgs + RBAC v2 | 4 | Custom roles CRUD + permission enforcement + e2e role tests pass |
| M4 Domain parity | 7 | All ERP CRUD/reports/search served by Django; frontend dual-running |
| M5 Billing live | 8 | Checkout, portal, webhooks, entitlement enforcement, trials |
| M6 Frontend cutover | 9 | 100% dashboard traffic on Django; Supabase SDK removed |
| M7 AI platform | 10 | Gateway + ported features #1–#2 + credits metering |
| M8 AI backlog wave 1 | 12 | Features #3–#6 shipped |
| M9 Production hardening | 14 | Rate limiting, audit log, backups, Sentry, load test, pen-test fixes |

**Team assumption:** 2 backend + 1 frontend + 1 part-time DevOps. Solo-founder pace: roughly 2× (≈ 6 months).

---

## 9. Risks & Mitigations

| Risk | Mitigation |
|---|---|
| Auth cutover locks users out | bcrypt hash compatibility verified first (§3.4); dual-session window; staged 5% → 100% rollout behind a feature flag |
| Business-rule regressions (invoice numbering, auto-settle, stock deduction) | Parallel-run + output diffing of report queries; port service rules with characterization tests written against current behavior first |
| Scope creep during migration | Migration PRs add **no new features**; new features (recurring invoices, client portal, emails) land only after M6 |
| Stripe webhook duplication during dual-run | Idempotency table (`stripe_event_id` unique) from day one; one system owns webhook processing at a time |
| RLS removed = accidental cross-org data leaks | Org scoping centralized in `OrgScopedViewSet` + a dedicated security test suite asserting cross-org access returns 404/403 for every endpoint |
| AI cost overrun | Hard per-org credit caps, response caching, cheap-model-first chains, usage alerts at 80% quota |
| Perf: N+1 on dashboard/reports | `select_related/prefetch_only` + materialized aggregates; Redis cache for dashboard stats (60s TTL) |

---

## 10. Immediate Next Steps

1. Approve plan + entitlement matrix (§4.2) — pricing/packaging dependency
2. Approve permission catalog (§5.1) — blocks RBAC v2 schema
3. Provision: Postgres instance, Redis, Stripe products/prices (Free/Pro/Enterprise × monthly/yearly)
4. Scaffold `backend/` (M1) and set up CI (ruff + mypy + pytest + coverage gate)
5. Write characterization tests against the current Next.js behavior for: invoice numbering, payment auto-settle, stock deduction, invite claiming — these become the migration's safety net






