# OpsGuard AI
### Autonomous Operations Assistant for Indian D2C Brands

> **Stack:** FastAPI · Supabase · Groq · Next.js 14 (App Router, TypeScript, Tailwind CSS, shadcn/ui)

---

## 1. Architecture — 5-Line Summary

1. **Connectors** — Three implementations of a shared `BaseConnector` abstract class return the same normalized types: `NormalizedOrder`, `NormalizedShipment`, `NormalizedSKU`. The chat layer and agent import nothing connector-specific.
2. **Sync** — A sync runner pulls from each source and upserts into Supabase with `merchant_id`, `source`, `source_record_id`, and `ingested_at` on every row; `sync_jobs` tracks state per connector run.
3. **API** — FastAPI serves sync, chat, agent trigger, disputes, reports, analytics, and health; a Next.js 14 frontend calls these endpoints via SWR.
4. **Chat** — A Groq tool-use loop returns structured facts plus `row_ids`; a post-processing validator strips any number not followed by a `<cite:row_id>` tag before the response reaches the user.
5. **Agent** — An APScheduler daily job scans recent shipments for weight overcharges, calculates disputed INR using zone-slab pricing, and writes findings, proposals, and full reasoning to `agent_runs` — no external API calls, no emails sent.

---

## 2. Connectors — Which 3, Why These 3

| Connector | Why |
|---|---|
| **Shopify** | The commerce system of record for every D2C brand: orders, SKUs, inventory, COD vs prepaid split, destination pincode. Without it there is no revenue, no margin, and no RTO analysis. It is the spine of the data model. |
| **Google Sheets** | This is how Indian D2C teams actually manage cost prices, packaging weights, and courier rates — no SQL, no ERP, just a shared Sheet. Ignoring it means the system cannot answer any question that requires margin. It is also the connector that builds trust with non-technical founders because it requires zero migration. |
| **Shiprocket (mock for v0)** | Fulfilment-shaped data: actual charged weights, couriers, pincodes, and INR costs. The mock is built to Shiprocket's real response shape so it can be replaced with a real connector with zero changes to the agent or chat layer. The mock is honest about being a mock — see Eval. |

**Why not Razorpay, Amazon, or WooCommerce first?** Shopify + Sheets + Shiprocket is the exact data triangle that answers the most valuable cross-tool question for an Indian D2C brand: "Is this SKU profitable after actual shipping cost?" That question cannot be answered without all three. Razorpay adds settlement reconciliation which is the right next layer, listed in Section 9.

---

## 3. Universal Data Model — Why This Shape

Every table is built on five invariants:

- **`merchant_id` as first column on every table** — multi-tenant from row zero, not retrofitted later
- **Row Level Security in Postgres** — not just application-layer checks; if app code passes the wrong `merchant_id`, RLS prevents data leakage
- **`source` + `source_record_id`** — idempotent upserts on `(merchant_id, source, source_record_id)`; syncing twice does not double-count
- **`ingested_at`** — freshness signal; the agent warns when rate card data is over 7 days old; the sync dashboard shows staleness per connector
- **`raw_metadata` (JSONB)** — full API response preserved for audit; schema can evolve without migrations for every new upstream field

### Table Definitions

**`orders`**

| Column | Type | Description |
|---|---|---|
| `id` | uuid PK | Internal row ID — used as `row_id` in citations |
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
| `weight_declared_kg` | numeric | What merchant entered |
| `weight_charged_kg` | numeric | What courier billed |
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
| `charged_value` | numeric | What was billed |
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
| `data_window_days` | integer | How many days of data scanned |
| `shipments_scanned` | integer | Count for this run |
| `findings` | jsonb | Array of flagged items with evidence |
| `proposals` | jsonb | Array of proposed actions per courier |
| `reasoning` | text | Full chain of thought |
| `status` | text | `running` / `completed` / `failed` |
| `error` | text | Populated if status = failed |

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

**`courier_rate_slabs`** and **`courier_rate_card`** — Rate truth. Slabs hold the zone × weight matrix from Sheets; the rate card holds INR/kg fallback per courier. The agent uses slab pricing when a matching `(courier, zone)` row exists and warns when it falls back to defaults.

**RLS policy (same pattern on every table):**

```sql
ALTER TABLE orders ENABLE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON orders
  USING (merchant_id = current_setting('app.merchant_id'));
```

A flat denormalized export answers one question. This schema answers "show me weight disputes by courier", "what is the P&L on SKU-42 last 90 days", and "which pincodes have >20% RTO" without a schema change.

---

## 4. Chat — Tool Schema & How Citation Works

### Tools

| Tool | Inputs | What it returns |
|---|---|---|
| `find_weight_mismatches` | `merchant_id`, `days?` | Shipments where `charged > declared × 1.1`, with `row_ids` |
| `get_rto_rate` | `merchant_id`, `sku_id?`, `pincode?` | RTO % with supporting order `row_ids` |
| `calculate_pnl` | `merchant_id`, `sku_id`, `period` (30d/90d) | Revenue, COGS, shipping cost, margin % — all cited |
| `get_inventory_status` | `merchant_id` | SKUs below reorder level with `sku_master` row IDs |
| `get_top_skus` | `merchant_id`, `metric` (revenue/volume), `limit` | Ranked SKUs with order row citations |
| `mark_action_taken` | `reconciliation_id`, `note` | The one write tool — updates status to actioned |

### Citation Contract

This is the most important design invariant in the system. It holds unconditionally.

> Every numerical claim in the model's response must be immediately followed by a `<cite:row_id>` tag referencing the source row.
> Format: `Rs.4,840 <cite:rec_8f2a91d>`
> Multiple rows: `23 shipments <cite:rec_4b1c22e,rec_9d3f01a>`

**Enforcement:**

```python
import re

BARE_NUMBER = re.compile(r'(Rs\.[\d,]+|\d+%)(?!\s*<cite:)')

def enforce_citations(response: str) -> str:
    return BARE_NUMBER.sub('[uncited value removed]', response)
```

Any bare number without a following `<cite:...>` tag is replaced with `[uncited value removed]` before the response reaches the user.

**System prompt (key rules):**
- Every number you state must be immediately followed by `<cite:row_id>`. Never state a number without a cite. If you do not have a row ID for a number, say so — never guess.
- Always use numeric format (`Rs.4,700`) not word form. Never write "forty-seven hundred rupees."
- You may only write data using the `mark_action_taken` tool. Never describe writing without calling the tool.
- Only answer questions about this merchant's data.

**Rendering:** Citation tags are parsed in Next.js and rendered as shadcn/ui `Badge` components. Hovering shows the source record: connector name, `source_record_id`, and `ingested_at` timestamp — full audit trail without leaving the chat.

---

## 5. Agent — What It Does, Why This One

### What it does

The weight dispute agent runs daily at 06:00 IST via APScheduler, or on demand via `POST /api/agent/run`.

| Element | Detail |
|---|---|
| **Trigger** | Daily cron at 06:00 IST, or `POST /api/agent/run?merchant_id=X`. Trigger type logged in `agent_runs.trigger`. |
| **Data** | Last 30 days of non-RTO shipments joined with `sku_master` on `sku_id` for `packaging_weight_g` as declared-weight ground truth. Threshold: `declared × 1.1` (10% tolerance for legitimate slab rounding). |
| **Decision** | Flag any shipment where `weight_charged_kg > weight_declared_kg × 1.1`. Calculate overcharge: `(charged − declared) × courier_rate_per_kg` using zone-slab pricing from `courier_rate_slabs`, falling back to INR/kg from `courier_rate_card`. Group by courier and sum totals. |
| **Action** | Write findings and per-courier proposals to `agent_runs`. Upsert flagged shipments to `reconciliation_results`. No external API calls. No emails sent. |

**Agent run log format** (`agent_runs.findings` JSONB):

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

### Why this agent

Of the four plausible first agents — weight disputes, RTO patterns, inventory alerts, P&L by SKU — this one produces the most concrete, immediately actionable output: a rupee figure the founder can dispute the same day. The trigger is binary, the decision is deterministic math, and it draws on data from all three connectors. RTO analysis is the right second agent; it requires pincode + SKU pattern work that depends on having enough order history first.

### Failure modes

- **Stale rate card** — agent warns if `courier_rate_slabs.ingested_at` > 7 days; does not block the run
- **Agent re-flagging** — deduplicates on `(merchant_id, shipment_id)` in `reconciliation_results` before inserting
- **Mock data** — weight discrepancy figures reflect generated data; real Shiprocket billing will produce different distributions
- **10% tolerance is fixed** — per-courier tolerance config is the right fix; not in v0
- **Scheduler failure** — APScheduler logs exceptions and retries once after 5 minutes

---

## 6. Scale — 1 Merchant → 10,000

### What's built

- `merchant_id` on all business tables with RLS enforced at the Postgres level
- Idempotent upserts on `(merchant_id, source, source_record_id)` — syncing twice is safe
- `sync_jobs` table with `pending → running → done/failed` state machine, ready for a queue worker to replace inline sync
- `since_days` bounds on all sync pulls — no full re-reads
- Analytics and reconciliation on dedicated endpoints to keep chat payloads small

### What breaks and how to fix it

| Bottleneck | What breaks | Fix |
|---|---|---|
| Inline sync in the API process | At > ~10 concurrent syncs, workers block and requests time out | Redis + RQ or Celery; workers pull `sync_jobs` rows with per-merchant rate limits |
| Shopify polling at scale | 10,000 merchants × polling = rate ban | Webhook-first: `order/create` and `order/fulfilled` events; polling only for gap-fill |
| APScheduler at scale | 10,000 simultaneous agent runs overwhelm DB and Groq concurrency limits | One job per merchant pushed to queue; workers with Groq rate limiting |
| Supabase connection pool | ~100 connections on free tier exhausted at scale | PgBouncer (Supabase provides it); read replicas for analytics |
| Google Sheets quota | 60 reads/min per project; exceeded in seconds at 10k merchants | Cache with `ingested_at` high-water marks; avoid re-pulling unchanged ranges |
| `raw_metadata` JSONB growth | 10k merchants × 200 shipments × 5KB = 10GB+ quickly | Compress blobs; archive records > 90 days to S3/GCS |

---

## 7. Eval — Where It Breaks

| Failure mode | Condition | Severity |
|---|---|---|
| Mock Shiprocket | All weight dispute figures come from generated data. Accuracy against real courier billing is unverified. | **High** |
| Citation regex bypass | Model writes "forty-seven hundred rupees" instead of Rs.4,700; validator misses it. Mitigated by system prompt, not eliminated. | **Medium** |
| Sheets column drift | Founder renames "Cost Price" to "CP"; connector raises `ConnectorConfigError` only if handled upstream and surfaced in the dashboard | **Medium** |
| Stale rate card | Agent uses an outdated rate per kg; disputed amount is wrong | **Medium** |
| Pincode → zone heuristic | Zone mapping is approximate; slab-based dispute amounts are only as accurate as the zone assignment | **Medium** |
| RLS misconfiguration | RLS holds only if the app correctly sets `app.merchant_id` at connection time; this repo documents intent, not a full auth product | **Medium** |
| Agent re-flagging | Same shipment flagged on every daily run if deduplication has a bug | **Low** |
| Supabase free tier | 500MB storage, ~100 connections; hits limits at more than ~3 test merchants with full sync history | **Low** |
| Shopify dev store | Synthetic orders; agent output quality depends on how carefully test data is seeded | **Low** |
| Next.js / FastAPI CORS | Misconfigured CORS on FastAPI blocks all frontend requests in production | **Low** |

---

## 8. Hours Spent

~20 hours across 5 sessions over 4 days.

---

## 9. With Another Week

**Real Shiprocket connector** — auth, pagination, delta pulls via `updated_at`, validate weight dispute output against actual billing data. This is what makes the agent's rupee figures real.

**Razorpay / Cashfree connector** — the fourth source. Settlement vs order revenue is the most-requested D2C insight and requires no new schema: `orders` already has `payment_method`.

**Shopify webhooks** — replace polling with `order/create` and `order/fulfilled` events; eliminates the rate limit problem and makes data near-real-time.

**Proper job queue** — Redis + RQ or Celery replacing APScheduler inline sync; required before adding a second real merchant.

**RTO agent** — a second autonomous agent using pincode + SKU patterns; proves the agent framework is genuinely modular, not a one-off.

**Eval harness** — seed known-bad data with specific shipments at known overcharge amounts, run the agent, assert it flags the right rows. Agent reliability should be measured, not asserted by inspection.

**Supabase Auth** — merchant self-onboarding; currently `merchant_id` is hardcoded in env.

**PDF reconciliation export** — a founder-ready report from `reconciliation_results` they can send directly to a courier's billing team.

**Optimistic UI updates** in Next.js for `mark_action_taken` — improves founder UX when actioning or dismissing disputes.

---

## 10. AI Tools Used

**Claude (Anthropic)** — architecture planning, schema design, tool schema definitions, citation enforcement logic, system prompt drafting, and README structure.

**OpenAI Codex** — boilerplate FastAPI route structure, Next.js component scaffolding, and Groq tool-use loop plumbing, with generated suggestions reviewed and accepted selectively.

Connector interfaces, mock data design, Supabase schema and RLS policies, citation contract, agent trigger/decision/action logic, scale analysis, and all final debugging were written directly.

---

## 11. Running Locally

### Prerequisites

- Python 3.11+ with a virtual environment created at `.venv` or `venv` in the repo root
- Node.js + npm on PATH
- A `.env` file in the repo root (see Environment Variables below)

### Windows — one command

```bat
start-opsguard.bat
```

The script checks for `.env`, finds the virtual environment, installs frontend dependencies if needed, skips ports already in use, opens two terminal windows (backend on `http://127.0.0.1:8000`, frontend on `http://127.0.0.1:3000`), waits 5 seconds, and opens the frontend in your browser automatically.

**First-time setup:**

```bat
py -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env   # then fill in your credentials
start-opsguard.bat
```

### Manual (Mac / Linux)

```bash
# Backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn api.main:app --host 127.0.0.1 --port 8000

# Frontend (separate terminal)
cd frontend && npm install && npm run dev -- -H 127.0.0.1 -p 3000
```

### Trigger a sync and agent run

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

*OpsGuard AI · FastAPI + Supabase + Groq + Next.js 14*
