# BizPilot — Subscription Management Plan & Explanation

**Date:** September 4, 2026
**Status:** Approved design — ready for implementation (Workstream B, Milestone M5)
**Prerequisite reading:** `DJANGO_MIGRATION_PLAN.md` §4 (this document expands it into an
implementable, end-to-end explanation)
**App:** `backend/bizpilot/billing/`

---

## 1. Purpose & Scope

This document is the **single source of truth** for how BizPilot sells, meters, enforces, and
reconciles subscriptions. It answers three questions:

1. **What** exists in the database (data model, §3–§4)?
2. **How** does a subscription actually work, click by click, event by event (§5)?
3. **How** are plan limits enforced so the Free tier is real and paid features stay paid (§6–§7)?

**In scope:** plans, entitlements, Stripe Checkout/Portal, webhook processing, trials, usage
metering, limit enforcement, dunning, downgrade handling, upgrade prompts.
**Out of scope:** invoice generation itself, AI credits *spending* logic (migration plan §6 —
this doc only meters the credits), tax/VAT calculation (Stripe Tax, later), per-seat proration
(seats enforced as a hard cap, §9.6).

---

## 2. How It Works — The 60-Second Mental Model

Everything hangs off **one chain of four records**:

```
Organization ──(1:1)──► Subscription ──(FK)──► Plan ──(1:N)──► PlanEntitlements
                                        ▲
                                        │ resolved via
                                  PriceMapping (stripe_price_id → plan)
```

The runtime rule the whole system obeys:

> **Every write-capable action first asks the Billing Engine one question —
> "may this org do this?" — and the engine answers from a cached entitlement lookup.**

- **Stripe is the billing ledger; Postgres is the entitlement truth; Redis is the speed.**
- Stripe never decides what a user may do. Stripe *tells* us what was paid (via webhooks);
  we *record* it on `Subscription`, and the entitlement catalog *decides* enforcement.
- Limits are **per-organization**, not per-user (a user may belong to orgs on different plans).

## 3. Data Model (app: `billing`)

### 3.1 `Plan`

| Field | Type | Notes |
|---|---|---|
| `code` | SlugField, unique | `"free"` \| `"pro"` \| `"enterprise"` |
| `name` / `description` | Char/Text | Shown on pricing UI |
| `stripe_product_id` | Char, null | Null for `free` (no Stripe product) |
| `tier` | PositiveSmallInt | Upgrade rank: free=0 < pro=1 < enterprise=2. Upgrade means `new.tier > old.tier` |
| `trial_days` | PositiveSmallInt | 14 for pro/enterprise; 0 for free |
| `is_active` / `sort_order` | bool / int | Pricing page ordering |

Synced **from** Stripe Products (metadata `tier`), one-way. Admin edits only display fields.

### 3.2 `PlanEntitlement`

| Field | Type | Notes |
|---|---|---|
| `plan` | FK(Plan) | |
| `key` | Char | From the catalog (§4), e.g. `max_invoices_per_month` |
| `value` | JSONField | int limit, bool flag, or list |
| unique together | | `(plan, key)` |

### 3.3 `Subscription` (replaces/extends legacy `public.subscriptions`)

| Field | Type | Notes |
|---|---|---|
| `organization` | OneToOne(Organization) | **One active subscription per org** — the core invariant |
| `plan` | FK(Plan) | Resolved from Stripe price via `PriceMapping` |
| `stripe_subscription_id` | Char, unique | |
| `stripe_customer_id` | Char, indexed | |
| `stripe_price_id` | Char | |
| `status` | Char | `trialing` \| `active` \| `past_due` \| `canceled` \| `incomplete` \| `paused` (mirrors Stripe) |
| `trial_start` / `trial_end` | datetime, null | |
| `current_period_start` / `current_period_end` | datetime | Billing window |
| `cancel_at_period_end` | bool | User chose "cancel at renewal" |
| `canceled_at` / `ends_at` | datetime, null | `ends_at` = when access drops to free |
| `pending_plan` | FK(Plan), null | Scheduled downgrade (§5.5) |

### 3.4 `PriceMapping`

| Field | Notes |
|---|---|
| `stripe_price_id` (unique) | |
| `plan` FK | |
| `interval` | `"month"` \| `"year"` |

This table is what makes "the plan" derivable from a webhook event. Unknown price in a
webhook → alert + park the event (§9.2). Never guess.

### 3.5 `UsageCounter`

| Field | Notes |
|---|---|
| `organization` FK, `key`, `period_start` date, `count` BigInt | unique `(organization, key, period_start)` |

Postgres mirror of the Redis counters; used for reconciliation, admin views, and the
"usage vs limits" readout.

### 3.6 `StripeEvent` (webhook idempotency)

| Field | Notes |
|---|---|
| `stripe_event_id` (unique) | Insert-first; `IntegrityError` = duplicate delivery → 200 OK, no-op |
| `type`, `payload` JSON, `processed_at`, `error` | Audit + debugging |

**Invariants (enforced in code, tested in CI):**
1. An org has **at most one** `Subscription` (OneToOne + DB constraint).
2. `Subscription.plan` is written **only** by the webhook handler or trial-start service — never by a plain API endpoint.
3. `UsageCounter.count` is only written by the metering service (Redis write-through), never incremented ad hoc.

## 4. Entitlement Catalog (initial)

The catalog is the **product decision table** — pricing/packaging changes mean editing these
rows (plus a migration), never new code paths.

| Key | Type | Free | Pro | Enterprise | Enforced at |
|---|---|---|---|---|---|
| `max_invoices_per_month` | int | 10 | 500 | null (=unlimited) | `InvoiceService.create` |
| `max_clients` | int | 5 | 200 | null | Client create |
| `max_products` | int | 10 | 1000 | null | Product create |
| `max_team_members` | int | 1 | 10 | null | Invite accept + invite create |
| `max_organizations` | int | 1 | 3 | null | Org create |
| `ai_credits_per_month` | int | 25 | 500 | 5000 | AI gateway (migration plan §6) |
| `recurring_invoices` | bool | false | true | true | Recurring-invoice endpoints |
| `email_invoice_delivery` | bool | false | true | true | Invoice email send |
| `client_portal` | bool | false | true | true | Portal routes |
| `data_export` | bool | false | true | true | Export endpoints (CSV/PDF bulk) |
| `custom_roles` | bool | false | false | true | RBAC v2 role CRUD (§5 of plan) |
| `audit_log` | bool | false | true | true | Audit-log read endpoint |

Rules:
- `null` always means **unlimited** (Enterprise never hits a cap).
- Every key must exist for **every** plan — a missing row is a data bug (tested: catalog
  completeness test fails CI when a plan lacks a key).
- `false` boolean features return a **403 with upgrade hint**, int caps return **402** (§7.3).

---

## 5. The Subscription Lifecycle — How It Works, Event by Event

### 5.0 State machine

```
                        checkout.session.completed
                                    │
                                    ▼
   signup ──► FREE(active) ──upgrade──► TRIALING ──trial ends / first
                ▲                          │        invoice.paid──► ACTIVE
                │                          │                             │
                │        customer.subscription.deleted                     │
                │            (or ends_at reached)                          │
                │                    │                                     │
                └──────── CANCELED ◄─┘          invoice.payment_failed    │
                                       ▲                │                 │
                                       └── 3 retries ── PAST_DUE ◄───────┘
                                           fail            │
                                                           │ payment recovered
                                                           ▼
                                                        ACTIVE
```

| Status | Meaning | Write access |
|---|---|---|
| `trialing` | On Pro/Enterprise trial after checkout | Full |
| `active` | Paying, good standing | Full |
| `past_due` | Payment failed, dunning running | Full (grace) — soft-locks after final retry |
| `canceled` | Ended; org downgraded to Free | Read-only if over Free caps (§5.6) |
| `incomplete` | Checkout abandoned at payment step | Blocked until `active` or 24h cleanup |
| `paused` | Reserved (not exposed in v1) | Blocked |

### 5.1 Signup → Free (automatic, no Stripe)

```
POST /api/v1/auth/signup
  └─► create user + personal org (existing flow)
        └─► billing.services.ensure_subscription(org)
              ├─ Subscription exists? return it          (idempotent)
              └─ else create Subscription(plan=free, status="active",
                     current_period_start=now)           (no Stripe objects)
```

Free orgs never touch Stripe — zero cost, zero latency, no webhook dependency. The
`Subscription` row exists purely so the enforcement engine has one code path for every org.

### 5.2 Upgrade flow (the heart of the system)

```
Browser                Django                    Stripe
   │  POST /api/v1/billing/checkout/  │             │
   │  {price_id, org_id}              │             │
   ├─────────────────────────────────►│             │
   │                                  │ permission: billing.manage
   │                                  │ create Checkout Session ──► (mode=subscription,
   │                                  │   metadata: {organization_id})   (exact port of
   │◄─ {checkout_url} ────────────────┤              today's createCheckoutSession)
   │  redirect to Stripe              │             │
   ├──────────────────────────────────────────────────────────────►│
   │            user pays (or starts 14-day trial)                 │
   │                                  │   webhook: checkout.session.completed
   │                                  │◄─────────────────────────────┤
   │                                  │ 1. verify signature          │
   │                                  │ 2. INSERT StripeEvent (idempotency guard)
   │                                  │ 3. enqueue Celery handle_checkout_completed
   │                                  │ 4. subscription = PriceMapping[price] → Plan
   │                                  │ 5. Subscription.update(status, period, ids,
   │                                  │            trial fields, plan=tier-correct plan)
   │                                  │ 6. invalidate EntitlementCache(org_id)
   │◄─ 200 ───────────────────────────┤
   │  (frontend also polls GET /api/v1/billing/subscription/
   │   after redirect back — webhooks are async, UI must not assume instant)
```

**Why the webhook is authoritative and not the redirect:** the browser can close before
payment finalizes; webhooks retry for days. The frontend polls the subscription endpoint;
the webhook is the only writer of billing state.

**Trial semantics:** upgrading from Free starts a `trialing` subscription (`trial_end =
now + plan.trial_days`). `invoice.paid` at trial end flips it to `active`. A trial is granted
**once per Stripe customer** (`subscription.trial_settings` / customer metadata guards
re-trial abuse — §9.7).

### 5.3 Renewal (nothing to do — by design)

At period end Stripe charges the card and sends `invoice.paid`. The handler updates
`current_period_*`, resets **window-based** usage counters (§6.2), keeps status `active`.
No Celery Beat job creates invoices — Stripe is the clock.

### 5.4 Mid-cycle upgrade / downgrade (proration)

- **Upgrade (tier↑):** Stripe Subscription Update API with `proration_behavior="create_prorations"`;
  takes effect **immediately** on `customer.subscription.updated` → new plan + entitlements live at once.
- **Downgrade (tier↓):** also Stripe update, but we set `pending_plan` and schedule it for
  period end (Stripe's native pending-update behavior, `proration_behavior="none"`) so the
  user keeps what they paid for. `customer.subscription.updated` (with pending change) → store
  `pending_plan`; the actual flip happens on the renewal `invoice.paid`.

### 5.5 Cancellation

```
POST /api/v1/billing/portal/  →  Stripe Customer Portal (cancel toggle lives there)
  └─ webhook customer.subscription.updated {cancel_at_period_end: true}
       └─ record flag; user keeps paid access until current_period_end
webhook customer.subscription.deleted
  └─ status=canceled, ends_at=now → downgrade_to_free(org)
       ├─ plan=free, stripe fields cleared (kept in payload archive)
       └─ DO NOT DELETE ANY DATA (§5.6)
```

Users can also re-subscribe from the portal; `checkout.session.completed` with the same
customer simply re-activates — `ensure_subscription` keeps the row, handler updates it.

### 5.6 Downgrade / over-limit = read-only, never data loss

At `ends_at`, the org moves to Free entitlements. If existing data exceeds Free caps
(e.g. 140 clients on Pro → Free allows 5):

- All **existing** records stay visible and exportable.
- **Writes that grow usage past the cap are blocked** (create client #6 → 402 upgrade prompt).
- Editing/deleting existing records still works (except where the feature itself is plan-gated,
  e.g. `email_invoice_delivery` off).
- The subscription endpoint reports `"over_limit": ["max_clients", ...]` so the UI can show
  exactly *why* it's read-only. **No batch jobs ever delete user data.** This is the trust rule.

### 5.7 Failed payments & dunning

| When | What happens |
|---|---|
| `invoice.payment_failed` | status=`past_due`, email #1 ("update your card") |
| Retry day 3 (Stripe smart retries + our Beat fallback) | email #2 |
| Retry day 7 | email #3 |
| Retry day 10 / final failure | **soft-lock**: status stays `past_due`, writes blocked, reads open (write gate = §7.2 "active-payment gate") |
| `invoice.paid` at any point | status=`active`, lock lifted, receipt email |

All dunning emails are transactional (anymail/SES), idempotent per `invoice.id`, and logged
in `AuditLog`.

## 6. Usage Metering — How Counters Work

### 6.1 Write-through metering (the hot path)

```
InvoiceService.create(org, ...)
  ├─ billing.enforce(org, "max_invoices_per_month")   # may raise PlanLimitExceeded
  ├─ ... create the invoice ...
  └─ billing.meter(org, "max_invoices_per_month")     # usage += 1
```

`billing.meter` does **one Redis call**: `INCR usage:{org_id}:{key}:{period_key}`.
Postgres is **not** written on the hot path — only by nightly reconciliation (§6.3).
Redis failure is *fail-open for metering* (never block paying users because a counter
is down) but **fail-closed for enforcement reads** already served from cache TTL — see §9.4.

### 6.2 Window keys

| Key type | Redis key | Reset |
|---|---|---|
| Monthly window (invoices, AI credits) | `usage:{org}:{key}:{YYYY-MM}` | New key on first write of the new month; old keys expire after 40 days |
| Total stock (clients, products) | computed by `COUNT` at enforce time (no counter — counts are already indexed and org-scoped) | n/a |
| Boolean flags | not metered | n/a |

Rule of thumb: **counters only for "per period" limits; totals are queried live.** This
avoids an entire class of drift bugs for the common `max_clients`-style caps.

### 6.3 Nightly reconciliation (Celery Beat, 03:00)

```
For each (org, key, period):
    redis_count = GET usage:{org}:{key}:{period}
    pg_count    = UsageCounter row (upsert)
    if drift: log + Sentry warn, prefer... → pg_count is authoritative for reporting,
              redis is authoritative for enforcement reads within TTL
```

Reconciliation exists to keep admin dashboards honest and to self-heal after Redis
restarts (counters repopulated lazily from `UsageCounter` on first miss, §6.4).

### 6.4 Cold-start rule

`UsageCounter.get_or_init(org, key, period)`: if the Redis key is missing but the Postgres
row exists → reseed Redis from Postgres. If neither exists → seed from the live `COUNT`
query (e.g. invoices created this month). Seeding happens **inside the enforcement check**,
so a Redis flush can never make limits forget usage.

---

## 7. Enforcement Layer — How Limits Are Actually Applied

### 7.1 The engine (one module, every call site)

```python
# bizpilot/billing/engine.py
def get_entitlement(org, key) -> EntitlementValue          # Redis-cached, 60s TTL
def allow(org, key) -> None                                # bool features
    raise FeatureNotAvailable if not value
def enforce(org, key) -> None                              # int caps
    raise PlanLimitExceeded(limit=key, used=..., cap=...) if at cap
def meter(org, key, amount=1) -> None                      # after a successful action
def usage_summary(org) -> dict                             # for UI: {key: {used, cap}}
```

Both exceptions are subclasses of a `BillingError` handled by the custom DRF exception
handler (migration plan §2.3) — ViewSets/services never see billing logic beyond the call.

### 7.2 Where enforcement plugs in

1. **Service layer (primary):** every growth-path service calls `enforce()`/`allow()`
   *before* the write and `meter()` *after* commit (`transaction.on_commit`).
2. **Write gate for non-good-standing orgs:** a small DRF permission class
   `HasActiveBilling` on mutating routes → `incomplete`/`paused`/soft-locked `past_due`
   get 402 before any business code runs. Reads are always open.
3. **Not** implemented as queryset filtering — over-limit orgs keep full read access (§5.6).

### 7.3 Response contract (what the frontend builds upgrade prompts from)

```json
HTTP 402 Payment Required
{
  "type": "https://bizpilot.com/errors/plan-limit-exceeded",
  "title": "Plan limit reached",
  "status": 402,
  "detail": "You reached your Free plan limit of 10 invoices this month.",
  "errors": [],
  "upgrade_required": true,
  "limit": "max_invoices_per_month",
  "plan": "free",
  "used": 10,
  "cap": 10
}
```

Boolean feature denial (403) returns the same shape with `"feature": "recurring_invoices"`.
The generated typed API client maps `upgrade_required` → the pricing modal. This replaces
today's hard errors (QA report FR-BILL-05 gap).

### 7.4 Free-tier enforcement points (checklist from migration plan §4.5)

| # | Point | Mechanism |
|---|---|---|
| 1 | Invoice create (monthly cap) | `enforce` + `meter` in `InvoiceService.create` |
| 2 | Client / product create (total cap) | `enforce` vs live `COUNT` |
| 3 | Invite member (`max_team_members`) | `enforce` on invite create + accept |
| 4 | Create additional org (`max_organizations`) | `enforce` across user's owned orgs |
| 5 | AI endpoints (`ai_credits_per_month`) | `enforce` + `meter` in AI gateway (§6 of plan) |

## 8. API Surface — `/api/v1/billing/*`

| Method & path | Permission | Purpose |
|---|---|---|
| `POST /api/v1/billing/checkout/` | `billing.manage` (owner/admin) | Body `{org_id, price_id}` → `{checkout_url}`. Session metadata carries `organization_id` (port of `createCheckoutSession`) |
| `POST /api/v1/billing/portal/` | `billing.manage` | `{org_id}` → `{portal_url}` (cancel/update card/invoices) |
| `GET /api/v1/orgs/{org_id}/subscription/` | org member | Current plan, status, `usage_summary`, `over_limit`, `pending_plan`, available plans |
| `POST /api/v1/billing/webhooks/stripe/` | **public** (signature-verified) | The only webhook endpoint; disallows auth-bearing requests |
| `GET /api/v1/billing/plans/` | public | Pricing page data (plans + entitlements, no Stripe internals) |

Non-negotiables for the webhook endpoint:
1. Read raw body → `stripe.Webhook.construct_event` with `STRIPE_WEBHOOK_SECRET`; reject otherwise (400).
2. **Insert `StripeEvent` first** — unique constraint is the idempotency lock (§3.6).
3. Handle → enqueue Celery task per event type; **return 200 fast**, do real work async (Stripe times out at ~10s).
4. Unknown event *types* → 200 + log (forward compatibility). Unknown *prices* → 200 + Sentry alert + event parked unprocessed (§9.2).

---

## 9. Edge Cases & Invariants

1. **Duplicate webhook delivery** → `StripeEvent` unique insert; second delivery is a 200 no-op.
2. **Unknown/renamed Stripe price** → park + alert; enforcement continues on the previous plan (stale but safe).
3. **Out-of-order events** (renewal `invoice.paid` arrives before a delayed `customer.subscription.updated`): handlers are **idempotent state projections** — each applies Stripe's payload fields with `update_or_create`; final state converges because the last-applied event reflects Stripe's view at that time. For money-critical flips we compare `event.created` timestamps and ignore strictly older snapshots for the same subscription.
4. **Redis down** → enforcement falls back to a 5s-timeout Postgres read of `UsageCounter`/`COUNT`; metering failures are logged, never raised to users. Billing must not take the product down.
5. **Webhook arrives for deleted org** → handler no-ops + Sentry (manual review; Stripe dashboard remains source of truth for refunds).
6. **Seats vs roles:** `max_team_members` counts *active* memberships. Pending invites count toward the cap; revoked members free a seat instantly.
7. **Trial abuse:** trial eligibility = customer has never had a paid subscription for this Stripe customer id AND (personal org only). Enforcement is server-side on `customer.subscription` metadata, not UI.
8. **Multiple orgs, one user:** each org has its own Subscription/customer. A user's org-creation cap (`max_organizations`) is evaluated against the *plan of the org they're acting in*… resolved as: creating an org under a Pro user's *new* personal context is governed by the cap of the **plan that will own the new org** = Free → the cap is the Free cap unless they check out first. (Documented decision; revisit with packaging.)
9. **Refund/chargeback** (`charge.refunded`, `customer.subscription.deleted`) → same path as §5.5; support playbook in `runbooks/` (out of code scope).
10. **Timezones:** billing windows come from Stripe (UTC). Monthly usage windows use **UTC calendar months** for v1 — simple, explainable, matches `INV-YYYY-NNN` sequences.

---

## 10. Testing Strategy

| Layer | Tests |
|---|---|
| Unit | `engine.allow/enforce/meter` against every entitlement key × plan; catalog completeness; `PriceMapping` resolution; unknown-price parking |
| Webhook (the money suite) | `checkout.session.completed`, `customer.subscription.created|updated|deleted`, `invoice.paid`, `invoice.payment_failed` — happy path, **duplicate delivery**, **out-of-order**, **bad signature (400)**, **unknown price**, payload fuzzing |
| Lifecycle | trial → active, upgrade proration flags, downgrade at period end, cancel → read-only over-cap matrix (each entitlement key) |
| Metering | concurrent `meter()` correctness (threaded test), window rollover at month boundary, cold-start reseeding after simulated Redis flush |
| Integration | Stripe CLI (`stripe listen --forward-to`) replay in CI; Stripe **test clocks** for renewal/dunning timelines |
| Security | cross-org subscription reads → 404; webhook without signature → 400; `billing.manage` denied for editor/viewer |
| E2E | checkout redirect → poll subscription → UI shows Pro; limit modal appears at cap |

CI gate: the webhook + enforcement suites run on every PR with **100% required coverage on
`bizpilot/billing/`** (stricter than the repo-wide gate).

## 11. Implementation Plan

### 11.1 File layout (follows migration plan §2.2)

```
backend/bizpilot/billing/
├── models.py              # Plan, PlanEntitlement, Subscription, PriceMapping,
│                          # UsageCounter, StripeEvent  (§3)
├── engine.py              # allow / enforce / meter / usage_summary  (§6–§7)
├── entitlements.py        # ENTITLEMENT_CATALOG constants + validators (§4)
├── services.py            # ensure_subscription, downgrade_to_free,
│                          # apply_stripe_subscription(snapshot)  (§5)
├── stripe_client.py       # thin wrapper: checkout/portal session builders (§8)
├── webhooks/
│   ├── router.py          # event type → Celery task registry
│   └── views.py           # signature verify + idempotency insert + enqueue
├── tasks.py               # Celery handlers, nightly reconciliation, dunning emails
├── permissions.py         # HasActiveBilling, BillingManagePermission
├── api/
│   ├── serializers.py
│   └── views.py           # checkout, portal, subscription, plans
├── migrations/
└── tests/                 # §10 suites (coverage gate 100%)
```

### 11.2 Ordered task checklist

| # | Task | Depends on | Est. |
|---|---|---|---|
| 1 | Models + migrations + admin (Unfold) registration | M3 orgs | 1d |
| 2 | Entitlement catalog + `ensure_subscription` on signup/org-create | 1 | 0.5d |
| 3 | Engine (`allow/enforce/meter/usage_summary`) + Redis cache + cold-start | 2 | 1d |
| 4 | Webhook endpoint: verify → `StripeEvent` insert → Celery dispatch; handlers for the 6 event types | 1 | 1.5d |
| 5 | Checkout/Portal endpoints + Stripe Products/Prices provisioning script + `PriceMapping` sync | 4 | 1d |
| 6 | `usage_summary` endpoint + 402/403 contract in exception handler | 3 | 0.5d |
| 7 | Wire enforcement points 1–4 (invoice/client/product/invite/org) | 3 | 1d |
| 8 | Dunning emails + Beat schedule (reconciliation 03:00, dunning fallback) | 4 | 0.5d |
| 9 | Test suites (webhook money suite, lifecycle matrix, metering) | all | 2.5d |
| 10 | AI credits metering hook (when AI gateway lands, plan §6) | 3 | 0.5d |
| 11 | Frontend contract: generated client types + upgrade-modal trigger | 6 | with FE |

**Total backend ≈ 10 engineer-days** (fits Milestone M5, weeks 6–8).

### 11.3 Rollout sequence (safety)

1. Ship models + engine **dark** (enforcement points call a no-op flag `BILLING_ENFORCEMENT=False`).
2. Enable enforcement for **new** orgs only (feature flag by org created_at).
3. Enable globally after 1 week of parallel-run metrics (no false 402s in logs).
4. Stripe webhook endpoint registered with Stripe CLI signature in staging first; rotate secret in prod via env.

---

## 12. Observability & Operations

| Signal | Where | Alert |
|---|---|---|
| Webhook failures / parked events | `StripeEvent.error`, Sentry | Any parked event > 15 min |
| Metering drift | reconciliation job | Drift > 1% of counters |
| 402 spike | access logs metric | >3× daily baseline (misconfig smell) |
| Trial→paid conversion | `Subscription` transitions | Weekly report (not an alert) |
| Dunning funnel | email events | Retry exhaustion spike |

Every billing-state change writes `AuditLog` (migration plan §2.3) — who/what/old→new,
which makes support ("why was I locked?") answerable from data.

## 13. Security Notes

- Webhook signature verification is **mandatory**; endpoint ignores session/JWT auth entirely.
- `price_id` in checkout is validated against active `PriceMapping` rows (no client-chosen amounts).
- Stripe customer/subscription ids are never exposed to non-`billing.manage` members (subscription endpoint returns plan metadata, not Stripe objects).
- No card data ever touches our servers (Stripe Checkout/Portal host the PCI surface).
- Secrets (`STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET`) via env only; rotation documented in runbooks.

---

## 14. TL;DR — The Whole System in Five Sentences

1. Every org always has exactly one `Subscription` (Free by default at signup — no Stripe involved).
2. Upgrades happen through Stripe Checkout; **only webhooks write billing state**, guarded by signature verification and an idempotency table.
3. The webhook maps Stripe's price → our `Plan` via `PriceMapping` and updates the org's subscription; a 60-second Redis cache serves entitlements to the enforcement engine.
4. Services call `billing.enforce()/allow()` before growth-writes and `billing.meter()` after — Free caps return a structured `402 {upgrade_required: true}` the frontend turns into upgrade prompts.
5. Failures degrade gracefully: dunning soft-locks writes but never deletes data, downgraded orgs become read-only over their caps, and Redis/Stripe outages never block reads.

*— End of document —*






