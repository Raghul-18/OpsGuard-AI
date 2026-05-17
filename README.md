# OpsGuard AI

Autonomous operations assistant for Indian D2C brands. Connects Shopify, Google Sheets, and Shiprocket into a unified data layer, runs a daily weight dispute agent, and surfaces every numerical claim with a traceable source citation.

**Stack:** FastAPI · Supabase · Groq · Next.js 14 (App Router, TypeScript, Tailwind CSS, shadcn/ui)

---

## Architecture

Three connector implementations share a common `BaseConnector` abstract class and return the same normalized types: `NormalizedOrder`, `NormalizedShipment`, and `NormalizedSKU`. The chat layer and agent import nothing connector-specific.

A sync runner pulls from each source and upserts into Supabase using `merchant_id`, `source`, `source_record_id`, and `ingested_at` on every row. A `sync_jobs` table tracks state per connector run.

FastAPI serves sync, chat, agent trigger, disputes, reports, analytics, and health endpoints. A Next.js 14 frontend consumes these via SWR.

The chat pipeline runs a Groq tool-use loop that returns structured facts alongside `row_ids`. A post-processing validator strips any number not followed by a `<cite:row_id>` tag before the response reaches the user.

An APScheduler daily job scans recent shipments for weight overcharges, calculates disputed INR amounts using zone-slab pricing, and writes findings, proposals, and full reasoning to `agent_runs`. No external API calls are made and no emails are sent.

---

## Connectors

| Connector | Rationale |
|---|---|
| **Shopify** | The commerce system of record for every D2C brand: orders, SKUs, inventory, COD vs prepaid split, and destination pincode. Without it there is no revenue, no margin, and no RTO analysis. |
| **Google Sheets** | How Indian D2C teams actually manage cost prices, packaging weights, and courier rates. Ignoring it means the system cannot answer any margin question. It also builds trust with non-technical founders because it requires zero migration. |
| **Shiprocket (mock for v0)** | Provides fulfilment-shaped data: actual charged weights, couriers, pincodes, and INR costs. The mock is built to Shiprocket's real response shape so it can be replaced with a live connector without changes to the agent or chat layer. |

Shopify, Sheets, and Shiprocket together answer the most valuable cross-tool question for an Indian D2C brand: "Is this SKU profitable after actual shipping cost?" That question cannot be answered without all three. Razorpay, which adds settlement reconciliation, is the right next layer and is listed in the roadmap section.

---

## Data Model

Every table is built on five invariants.

`merchant_id` appears as the first column on every table, making the schema multi-tenant from the start rather than retrofitted. Row Level Security is enforced at the Postgres level, not only in application code, so a misconfigured `merchant_id` in app code cannot leak data across tenants. The combination of `source` and `source_record_id` enables idempotent upserts on `(merchant_id, source, source_record_id)`, so syncing twice does not double-count. The `ingested_at` column provides a freshness signal: the agent warns when rate card data is over seven days old, and the sync dashboard shows staleness per connector. A `raw_metadata` JSONB column preserves the full API response for audit purposes and allows the schema to evolve without migrations for every new upstream field.

### Table Definitions

**`orders`**

| Column | Type | Description |
|---|---|---|
| `id` | uuid PK | Internal row ID, used as `row_id` in citations |
| `merchant_id` | text NOT NULL | Tenant identifier; RLS key |
| `order_ref` | text | Human-readable order number |
| `sku_id` | text | Matches `sku_master.sku_id` |
| `quantity` | integer | Units sold |
| `unit_price_inr` | numeric | Selling price per unit |
| `payment_method` | text | `prepaid` / `COD` |
| `destination_pincode` | text | Shipping destination |
| `ordered_at` | timestamptz | Original order timestamp |
| `source` | text | e.g. `shopify` |
| `source_record_id` | text | Shopify order ID |
| `ingested_at` | timestamptz | Timestamp of ingestion |
| `raw_metadata` | jsonb | Full API response |

**`shipments`**

| Column | Type | Description |
|---|---|---|
| `id` | uuid PK | |
| `merchant_id` | text NOT NULL | RLS key |
| `shipment_ref` | text | Shiprocket shipment ID |
| `order_id` | uuid FK | References `orders.id` |
| `courier_name` | text | Delhivery, BlueDart, etc. |
| `weight_declared_kg` | numeric | Weight entered by merchant |
| `weight_charged_kg` | numeric | Weight billed by courier |
| `shipping_cost_inr` | numeric | Actual charge |
| `status` | text | `Delivered` / `In Transit` / `RTO` |
| `rto` | boolean | True if returned to origin |
| `source` | text | `shiprocket` / `shiprocket_mock` |
| `source_record_id` | text | Original shipment ID |
| `ingested_at` | timestamptz | |
| `raw_metadata` | jsonb | |

**`sku_master`**

| Column | Type | Description |
|---|---|---|
| `id` | uuid PK | |
| `merchant_id` | text NOT NULL | |
| `sku_id` | text | Matches `orders.sku_id`; unique per merchant |
| `name` | text | Product display name |
| `cost_price_inr` | numeric | Unit cost from Sheets |
| `packaging_weight_g` | numeric | Ground truth for weight disputes |
| `reorder_level` | integer | Trigger threshold in units |
| `category` | text | Optional grouping |
| `source` | text | `gsheets` |
| `source_record_id` | text | Sheet row reference |
| `ingested_at` | timestamptz | |
| `raw_metadata` | jsonb | |

**`reconciliation_results`**

| Column | Type | Description |
|---|---|---|
| `id` | uuid PK | |
| `merchant_id` | text NOT NULL | |
| `shipment_id` | uuid FK | References `shipments.id` |
| `discrepancy_type` | text | `weight_overcharge` / `rto_high_risk` |
| `declared_value` | numeric | Merchant-declared value (kg or %) |
| `charged_value` | numeric | Billed value |
| `amount_disputed_inr` | numeric | Calculated overcharge |
| `status` | text | `open` / `actioned` / `dismissed` |
| `created_at` | timestamptz | When agent flagged it |
| `actioned_at` | timestamptz | When founder marked done |
| `action_note` | text | Free-text founder note |

**`agent_runs`**

| Column | Type | Description |
|---|---|---|
| `id` | uuid PK | |
| `merchant_id` | text NOT NULL | |
| `run_at` | timestamptz | When this run started |
| `trigger` | text | `daily_cron` / `manual` |
| `data_window_days` | integer | Days of data scanned |
| `shipments_scanned` | integer | Count for this run |
| `findings` | jsonb | Array of flagged items with evidence |
| `proposals` | jsonb | Array of proposed actions per courier |
| `reasoning` | text | Full chain of thought |
| `status` | text | `running` / `completed` / `failed` |
| `error` | text | Populated if status is `failed` |

**`sync_jobs`**

| Column | Type | Description |
|---|---|---|
| `id` | uuid PK | |
| `merchant_id` | text NOT NULL | |
| `connector` | text | `shopify` / `gsheets` / `shiprocket` |
| `status` | text | `pending` / `running` / `done` / `failed` |
| `scheduled_at` | timestamptz | When to run |
| `started_at` | timestamptz | When worker picked it up |
| `completed_at` | timestamptz | |
| `last_synced_at` | timestamptz | High-watermark for incremental pulls |
| `error` | text | If failed |

**`courier_rate_slabs`** and **`courier_rate_card`** hold the rate truth. Slabs store the zone × weight matrix from Sheets; the rate card stores INR/kg fallback values per courier. The agent uses slab pricing when a matching `(courier, zone)` row exists and warns when it falls back to defaults.

**RLS policy (applied uniformly across all tables):**

```sql
ALTER TABLE orders ENABLE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON orders
  USING (merchant_id = current_setting('app.merchant_id'));
```

---

## Chat

### Tools

| Tool | Inputs | Returns |
|---|---|---|
| `find_weight_mismatches` | `merchant_id`, `days?` | Shipments where `charged > declared × 1.1`, with `row_ids` |
| `get_rto_rate` | `merchant_id`, `sku_id?`, `pincode?` | RTO percentage with supporting order `row_ids` |
| `calculate_pnl` | `merchant_id`, `sku_id`, `period` (30d/90d) | Revenue, COGS, shipping cost, margin — all cited |
| `get_inventory_status` | `merchant_id` | SKUs below reorder level with `sku_master` row IDs |
| `get_top_skus` | `merchant_id`, `metric` (revenue/volume), `limit` | Ranked SKUs with order row citations |
| `mark_action_taken` | `reconciliation_id`, `note` | The sole write tool; updates status to `actioned` |

### Citation Contract

Every numerical claim in the model's response must be immediately followed by a `<cite:row_id>` tag referencing the source row.

```
Rs.4,840 <cite:rec_8f2a91d>
23 shipments <cite:rec_4b1c22e,rec_9d3f01a>
```

Any bare number without a following `<cite:...>` tag is replaced before the response reaches the user:

```python
import re

BARE_NUMBER = re.compile(r'(Rs\.[\d,]+|\d+%)(?!\s*<cite:)')

def enforce_citations(response: str) -> str:
    return BARE_NUMBER.sub('[uncited value removed]', response)
```

**System prompt rules:**

- Every number stated must be immediately followed by `<cite:row_id>`. If a row ID is unavailable for a number, say so rather than guessing.
- Always use numeric format (`Rs.4,700`), never word form. Never write "forty-seven hundred rupees."
- Data may only be written using the `mark_action_taken` tool. Never describe a write operation without calling the tool.
- Only answer questions about the current merchant's data.

**Rendering:** Citation tags are parsed in Next.js and rendered as shadcn/ui `Badge` components. Hovering shows the source record: connector name, `source_record_id`, and `ingested_at` timestamp.

---

## Agent

### Behaviour

The weight dispute agent runs daily at 06:00 IST via APScheduler, or on demand via `POST /api/agent/run`.

| Element | Detail |
|---|---|
| **Trigger** | Daily cron at 06:00 IST, or `POST /api/agent/run?merchant_id=X`. Trigger type logged in `agent_runs.trigger`. |
| **Data** | Last 30 days of non-RTO shipments joined with `sku_master` on `sku_id`, using `packaging_weight_g` as the declared-weight ground truth. Threshold: `declared × 1.1` (10% tolerance for legitimate slab rounding). |
| **Decision** | Flag any shipment where `weight_charged_kg > weight_declared_kg × 1.1`. Calculate overcharge as `(charged − declared) × courier_rate_per_kg` using zone-slab pricing from `courier_rate_slabs`, falling back to INR/kg from `courier_rate_card`. Group by courier and sum totals. |
| **Output** | Findings and per-courier proposals written to `agent_runs`. Flagged shipments upserted to `reconciliation_results`. No external API calls. No emails sent. |

**Agent run log format (`agent_runs.findings`):**

```json
{
  "findings": [
    {
      "shipment_id": "uuid",
      "courier": "Delhivery",
      "declared_kg": 0.5,
      "charged_kg": 1.0,
      "overcharge_inr": 42.50,
      "evidence_row_id": "uuid"
    }
  ],
  "proposals": [
    {
      "courier": "Delhivery",
      "shipment_count": 14,
      "total_disputed_inr": 595.00,
      "action": "Raise dispute with Delhivery for 14 shipments totalling Rs.595"
    }
  ],
  "reasoning": "Scanned 187 shipments. Delhivery charged 1.0kg on 14 shipments declared at 0.5kg..."
}
```

### Agent Selection Rationale

Of the four plausible first agents (weight disputes, RTO patterns, inventory alerts, P&L by SKU), the weight dispute agent produces the most concrete, immediately actionable output: a rupee figure the founder can dispute the same day. The trigger is binary, the decision is deterministic math, and it draws on data from all three connectors. RTO analysis is the right second agent; it requires pincode and SKU pattern work that depends on having sufficient order history first.

### Failure Modes

| Condition | Behaviour |
|---|---|
| Stale rate card | Agent warns if `courier_rate_slabs.ingested_at` is over 7 days old; the run continues |
| Re-flagging | Deduplicates on `(merchant_id, shipment_id)` in `reconciliation_results` before inserting |
| Mock data | Weight discrepancy figures reflect generated data; real Shiprocket billing will produce different distributions |
| Fixed tolerance | The 10% tolerance is hardcoded in v0; per-courier tolerance configuration is the appropriate fix |
| Scheduler failure | APScheduler logs exceptions and retries once after 5 minutes |

---

## Scale

### What Is Built

`merchant_id` is present on all business tables with RLS enforced at the Postgres level. Upserts are idempotent on `(merchant_id, source, source_record_id)`. The `sync_jobs` table implements a `pending → running → done/failed` state machine, ready for a queue worker to replace inline sync. `since_days` bounds are applied to all sync pulls to avoid full re-reads. Analytics and reconciliation are served from dedicated endpoints to keep chat payloads small.

### Scaling Constraints

| Bottleneck | What Breaks | Recommended Fix |
|---|---|---|
| Inline sync in the API process | At more than ~10 concurrent syncs, workers block and requests time out | Redis + RQ or Celery; workers pull `sync_jobs` rows with per-merchant rate limits |
| Shopify polling at scale | 10,000 merchants polling simultaneously will trigger a rate ban | Webhook-first via `order/create` and `order/fulfilled` events; polling only for gap-fill |
| APScheduler at scale | 10,000 simultaneous agent runs overwhelm the database and Groq concurrency limits | One job per merchant pushed to a queue; workers with Groq rate limiting |
| Supabase connection pool | ~100 connections on the free tier exhausted at scale | PgBouncer (Supabase provides it); read replicas for analytics |
| Google Sheets quota | 60 reads/min per project; exceeded in seconds at 10k merchants | Cache with `ingested_at` high-water marks; avoid re-pulling unchanged ranges |
| `raw_metadata` JSONB growth | 10k merchants × 200 shipments × 5KB grows quickly | Compress blobs; archive records older than 90 days to S3 or GCS |

---

## Known Limitations

| Issue | Condition | Severity |
|---|---|---|
| Mock Shiprocket | All weight dispute figures come from generated data. Accuracy against real courier billing is unverified. | High |
| Citation regex bypass | The model could write "forty-seven hundred rupees" instead of `Rs.4,700`; the validator would miss it. Mitigated by the system prompt but not eliminated. | Medium |
| Sheets column drift | If a founder renames "Cost Price" to "CP", the connector raises `ConnectorConfigError` only if the error is surfaced in the dashboard | Medium |
| Stale rate card | An outdated rate per kg causes the disputed amount to be incorrect | Medium |
| Pincode zone heuristic | Zone mapping is approximate; slab-based dispute amounts are only as accurate as the zone assignment | Medium |
| RLS misconfiguration | RLS holds only if the app correctly sets `app.merchant_id` at connection time | Medium |
| Agent re-flagging | A bug in deduplication logic would cause the same shipment to be flagged on every daily run | Low |
| Supabase free tier | 500MB storage and ~100 connections; reaches limits with more than ~3 test merchants running full sync history | Low |
| Shopify dev store | Synthetic orders; agent output quality depends on how carefully test data is seeded | Low |
| CORS misconfiguration | Misconfigured CORS on FastAPI blocks all frontend requests in production | Low |

---

## Roadmap

**Real Shiprocket connector** — auth, pagination, delta pulls via `updated_at`, and validation of weight dispute output against actual billing data. This is what makes the agent's rupee figures meaningful.

**Razorpay / Cashfree connector** — the fourth data source. Settlement vs order revenue is the most-requested D2C insight and requires no new schema: `orders` already has `payment_method`.

**Shopify webhooks** — replace polling with `order/create` and `order/fulfilled` events to eliminate the rate limit problem and make data near-real-time.

**Job queue** — Redis + RQ or Celery replacing APScheduler inline sync; required before adding a second real merchant.

**RTO agent** — a second autonomous agent using pincode and SKU patterns, proving the agent framework is genuinely modular.

**Eval harness** — seed known-bad data with specific shipments at known overcharge amounts, run the agent, and assert that it flags the correct rows.

**Supabase Auth** — merchant self-onboarding; currently `merchant_id` is hardcoded in the environment.

**PDF reconciliation export** — a founder-ready report from `reconciliation_results` suitable for sending directly to a courier's billing team.

**Optimistic UI updates** in Next.js for `mark_action_taken`, improving UX when actioning or dismissing disputes.

---

## Running Locally

### Prerequisites

- Python 3.11+ with a virtual environment at `.venv` or `venv` in the repo root
- Node.js and npm on PATH
- A `.env` file in the repo root (see Environment Variables below)

### Windows

```bat
start-opsguard.bat
```

The script checks for `.env`, finds the virtual environment, installs frontend dependencies if needed, skips ports already in use, opens two terminal windows (backend on `http://127.0.0.1:8000`, frontend on `http://127.0.0.1:3000`), waits five seconds, and opens the browser automatically.

**First-time setup:**

```bat
py -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
start-opsguard.bat
```

Fill in your credentials in `.env` before running.

### macOS / Linux

```bash
# Backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn api.main:app --host 127.0.0.1 --port 8000

# Frontend (separate terminal)
cd frontend && npm install && npm run dev -- -H 127.0.0.1 -p 3000
```

### Trigger a Sync and Agent Run

```bash
curl -X POST "http://127.0.0.1:8000/api/sync?merchant_id=merchant_demo"
curl -X POST "http://127.0.0.1:8000/api/agent/run?merchant_id=merchant_demo"
```

### Environment Variables

| Variable | Description |
|---|---|
| `SUPABASE_URL` | Supabase project URL |
| `SUPABASE_KEY` | Supabase service role key |
| `GROQ_API_KEY` | Groq API key |
| `SHOPIFY_SHOP` | `your-store.myshopify.com` |
| `SHOPIFY_TOKEN` | Private app access token |
| `GSHEETS_SPREADSHEET_ID` | Google Sheet ID |
| `GSHEETS_RANGE` | e.g. `SKUMaster!A:H` |
| `GOOGLE_CREDENTIALS_JSON` | Path to service account JSON |
| `MERCHANT_ID` | Default merchant for local dev (e.g. `merchant_demo`) |

---

## AI Tools Used

**Claude (Anthropic)** — architecture planning, schema design, tool schema definitions, citation enforcement logic, system prompt drafting, and README structure.

**OpenAI Codex** — boilerplate FastAPI route structure, Next.js component scaffolding, and Groq tool-use loop plumbing, with generated suggestions reviewed and accepted selectively.

Connector interfaces, mock data design, Supabase schema and RLS policies, citation contract, agent trigger/decision/action logic, scale analysis, and all final debugging were written directly.

---

*OpsGuard AI · FastAPI + Supabase + Groq + Next.js 14*
