# BizPilot AI Assistant — Example Prompts

Reference for the Ask BizPilot feature and the BizPilot agent.

Each example is tagged:

| Tag | Meaning |
|---|---|
| `[now]` | Works today |
| `[data]` | Partially supported; only the most recent records are in context |
| `[action]` | Write operation via the agent endpoint (propose, then confirm) |

## Invoices

- How many invoices have I sent? `[now]`
- How many invoices are pending, overdue, paid, draft, or cancelled? `[now]`
- What share of invoices are paid vs overdue? `[now]`
- What is the total invoiced amount this quarter? `[now]`
- What is the average invoice value? `[now]`
- What is my largest invoice, and for which client? `[now]`
- How much am I owed in total? `[now]`
- Total tax collected and total discount given? `[now]`
- Revenue invoiced over the last 6 months? `[now]`
- Is invoicing growing or shrinking month over month? `[now]`
- Which was my best month? `[now]`

## Payments

- Who has already paid? `[now]`
- Which clients have not paid? `[now]`
- How much did I receive this month? `[now]`
- How much is still outstanding? `[now]`
- What is my collection rate? `[now]`
- Which invoice should I chase first? `[now]`
- Which invoices are partially paid? `[now]`
- Payment split by method (card, transfer, cash)? `[now]`

## Clients

- List all clients with details (email, phone, address). `[now]`
- How many clients do I have? `[now]`
- Who are my top 5 clients by revenue? `[now]`
- Which client owes me the most? `[now]`
- Contact details for a specific client. `[now]`
- Average revenue per client? `[now]`
- Which clients have not been invoiced in 3 months? `[now]`

## Products and Inventory

- List all products, or products in a category. `[now]`
- Which products are below their low-stock threshold? `[now]`
- Total inventory value (stock x unit price)? `[now]`
- Which product sells the most? `[data]`
- How many products do I have? `[now]`
- Which products are inactive or missing a SKU? `[now]`

## Expenses

- Total expenses this month or over 6 months? `[now]`
- Breakdown by category? `[now]`
- Biggest expense category? `[now]`
- Are expenses growing month over month? `[now]`
- Share of spending per category? `[now]`
- Which vendor did I pay the most? `[data]`
- Did I spend more than I earned this month? `[now]`

## Profitability and Reports

- Profit this month (revenue minus expenses)? `[now]`
- Profit margin over the last 6 months? `[now]`
- Overall financial summary. `[now]`
- This month vs last month. `[now]`
- How is cash flow looking? `[now]`

## Advice

- How can I reduce my largest expense category?
- Where should I focus to grow revenue?
- What is a realistic revenue target for next month?
- What financial risks do you see in my data?
- Give three ways to improve cash flow.

## Combined Questions

- How many invoices did I send, and how many are unpaid? `[now]`
- Top clients, and how much do they still owe? `[now]`
- Revenue vs expenses over 6 months, and the trend. `[now]`
- Summarize business health in five points. `[now]`

## Agent Actions

Write operations run through the agent endpoint. Call once without
`confirm` to preview the proposed actions, then again with `confirm: true`
to execute them. Each action runs inside a transaction with plan-limit
enforcement; failures are reported per action, not fatal.

Endpoint: `POST /api/orgs/<org_id>/ai/agent/`

Request:

```json
{"instruction": "Add client Rahim Traders, email rahim@example.com"}
```

Response:

```json
{
  "reply": "I will add the client.",
  "planned_actions": [
    {
      "tool": "add_client",
      "args": {"name": "Rahim Traders", "email": "rahim@example.com"}
    }
  ],
  "executed": false
}
```

Send the same request with `"confirm": true` to execute. Available tools:

- Add a client: "Add client Rahim Traders, email rahim@example.com." `[action]`
- Add products: "Add these 5 products, then list them." `[action]`
- Create an invoice: "Invoice Acme Ltd for 10 hours of consulting at $50/hr." `[action]`
- Record a payment: "Record $500 against INV-2024-012." `[action]`
- Add an expense: "Add $60 office supplies at OfficeMart yesterday." `[action]`

Draft and communicate:

- Payment reminder: available today via the dedicated reminder feature.
- Overdue notice for all invoices 30+ days late. `[action]`
- Reply to a client email about an invoice. `[action]`

Bulk operations:

- Import clients from a pasted email signature list. `[action]`
- Deactivate products with no sales in 6 months. `[action]`

## Bangla

Bangla questions are supported; answers match the request language.

- আমি কতগুলো ইনভয়েস পাঠিয়েছি? `[now]`
- এই মাসে আমার মোট আয় কত? `[now]`
- কোন ক্লায়েন্ট আমাকে সবচেয়ে বেশি পেমেন্ট করেছে? `[now]`
- আমার সবচেয়ে বড় খরচের খাত কোনটি? `[now]`
- সব ক্লায়েন্টের তালিকা বিস্তারিত সহ দাও। `[now]`

## Limits

- Multi-turn conversation: pass prior turns in the `history` field
  (the last 8 messages are used).
- Mention the period for clarity; the assistant receives today's date and
  resolves "this month" or "last quarter" on its own.
- Questions and instructions are limited to 2000 characters.
- The assistant never invents figures; it states when data cannot answer.
- Each call consumes one AI credit (`ai_credits_per_month`); identical
  calls within 5 minutes are served from cache.
- Context record caps: 50 clients, 50 products, 30 invoices, 30 payments,
  20 expenses. Beyond the caps, questions are answered from totals and the
  most recent records.

## Assistant Context

Data sent with every call (see `bizpilot/ai/context.py`):

| Key | Contents |
|---|---|
| `organization` | Organization name |
| `currency` | Default currency |
| `today` | Current date for period resolution |
| `totals` | Aggregate totals: invoices, payments, expenses, revenue |
| `monthly_series` | Monthly revenue, expenses, profit (12 months) |
| `expense_by_category` | Top 8 expense categories |
| `top_clients` | Top clients by revenue |
| `clients` | Name, email, phone, company, address, status (up to 50) |
| `products` | Name, category, price, stock, SKU, active (up to 50) |
| `invoices` | Number, client, status, total, balance due, dates (up to 30) |
| `payments` | Invoice, client, amount, method, date (up to 30) |
| `expenses` | Title, vendor, category, amount, date, method (up to 20) |

