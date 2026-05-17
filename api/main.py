import os
import json
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Any, Literal

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from groq import APIStatusError
from pydantic import BaseModel, Field

from chat.citation import extract_row_ids
from chat.groq_loop import run_chat_loop
from chat.tools import (
    calculate_pnl,
    find_weight_mismatches,
    get_inventory_status,
    get_rto_rate,
    get_top_skus,
    mark_action_taken,
)
from db.client import execute_with_retry, get_client, insert_row, update_row, upsert_rows
from db.rates import rate_card_stale_warning
from scripts.sync_runner import get_sync_status, run_sync

load_dotenv()

app = FastAPI(title="OpsGuard AI", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class SyncRequest(BaseModel):
    merchant_id: str = "merchant_demo"
    since_days: int = Field(default=30, ge=1, le=365)
    include_shopify: bool = True
    include_gsheets: bool = True
    include_shiprocket_mock: bool = False


class ChatRequest(BaseModel):
    merchant_id: str = "merchant_demo"
    message: str
    history: list[dict[str, Any]] = Field(default_factory=list)


class ToolRequest(BaseModel):
    merchant_id: str = "merchant_demo"
    tool: Literal[
        "find_weight_mismatches",
        "get_rto_rate",
        "calculate_pnl",
        "get_inventory_status",
        "get_top_skus",
    ]
    arguments: dict[str, Any] = Field(default_factory=dict)


class DisputeActionRequest(BaseModel):
    reconciliation_id: str
    note: str = "Marked via dashboard"


def _json_env(name: str) -> dict | None:
    value = os.environ.get(name)
    if not value:
        return None
    try:
        return json.loads(value)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail=f"{name} must be valid JSON") from exc


def _credentials_from_env(payload: SyncRequest) -> dict:
    credentials: dict[str, Any] = {
        "shiprocket_mock": payload.include_shiprocket_mock or os.environ.get("ENABLE_SHIPROCKET_MOCK") == "true",
    }

    if payload.include_shopify:
        shop = (os.environ.get("SHOPIFY_SHOP") or "").strip()
        token = (os.environ.get("SHOPIFY_ACCESS_TOKEN") or "").strip()
        if shop and token:
            credentials["shopify"] = {"shop": shop, "access_token": token}

    if payload.include_gsheets:
        spreadsheet_id = os.environ.get("GSHEETS_SPREADSHEET_ID") or os.environ.get("GOOGLE_SHEET_ID")
        service_account_info = _json_env("GOOGLE_SERVICE_ACCOUNT_JSON")
        if spreadsheet_id and service_account_info:
            credentials["gsheets"] = {
                "spreadsheet_id": spreadsheet_id,
                "sheet_range": os.environ.get("GSHEETS_RANGE", "Sheet1"),
                "rate_slabs_range": (os.environ.get("GSHEETS_RATE_SLABS_RANGE") or "").strip(),
                "rate_card_range": (os.environ.get("GSHEETS_RATE_CARD_RANGE") or "").strip(),
                "service_account_info": service_account_info,
            }

    return credentials


def _latest_agent_run_at(merchant_id: str) -> str | None:
    result = (
        get_client()
        .table("agent_runs")
        .select("run_at")
        .eq("merchant_id", merchant_id)
        .order("run_at", desc=True)
        .limit(1)
        .execute()
    )
    return result.data[0]["run_at"] if result.data else None


def _get_disputes(merchant_id: str) -> list[dict]:
    result = (
        get_client()
        .table("reconciliation_results")
        .select("*")
        .eq("merchant_id", merchant_id)
        .order("created_at", desc=True)
        .execute()
    )
    return result.data or []


def _citation_metadata(row_ids: list[str]) -> list[dict]:
    if not row_ids:
        return []
    citations = []
    client = get_client()
    for table in (
        "orders",
        "shipments",
        "sku_master",
        "reconciliation_results",
        "courier_rate_card",
        "courier_rate_slabs",
    ):
        rows = client.table(table).select("id, source, source_record_id, ingested_at").in_("id", row_ids).execute().data or []
        for row in rows:
            citations.append({
                "row_id": row["id"],
                "source": row.get("source") or table,
                "source_record_id": row.get("source_record_id") or row["id"],
                "ingested_at": row.get("ingested_at"),
            })
    return citations


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/api/summary")
def summary(merchant_id: str = Query(default="merchant_demo")) -> dict:
    disputes = _get_disputes(merchant_id)
    inventory = get_inventory_status(merchant_id)
    open_disputes = [item for item in disputes if item.get("status") == "open"]

    return {
        "open_disputes": len(open_disputes),
        "total_disputed_inr": round(
            sum(float(item.get("amount_disputed_inr") or 0) for item in open_disputes),
            2,
        ),
        "low_stock_skus": inventory["low_stock_count"],
        "last_agent_run": _latest_agent_run_at(merchant_id),
    }


@app.post("/api/sync")
def sync(
    request: SyncRequest | None = None,
    merchant_id: str | None = Query(default=None),
    since_days: int | None = Query(default=None),
) -> dict:
    payload = request or SyncRequest()
    if merchant_id:
        payload.merchant_id = merchant_id
    if since_days:
        payload.since_days = since_days

    credentials = _credentials_from_env(payload)
    results = run_sync(payload.merchant_id, credentials, since_days=payload.since_days)
    return {
        "job_id": None,
        "status": "done" if all(item["status"] == "done" for item in results.values()) else "failed",
        "merchant_id": payload.merchant_id,
        "results": results,
    }


@app.get("/api/sync/status")
def sync_status(merchant_id: str = Query(default="merchant_demo")) -> list[dict]:
    return get_sync_status(merchant_id)


@app.get("/api/agent/runs")
def agent_runs(merchant_id: str = Query(default="merchant_demo")) -> list[dict]:
    try:
        result = execute_with_retry(
            lambda: (
                get_client()
                .table("agent_runs")
                .select("*")
                .eq("merchant_id", merchant_id)
                .order("run_at", desc=True)
                .limit(20)
                .execute()
            )
        )
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Database unavailable: {e}") from e
    return result.data or []


@app.post("/api/agent/run")
def agent_run(merchant_id: str = Query(default="merchant_demo")) -> dict:
    mismatches = find_weight_mismatches(merchant_id)
    grouped: dict[str, dict] = defaultdict(
        lambda: {"courier": "", "shipment_count": 0, "total_disputed_inr": 0.0, "shipment_ids": []}
    )

    reconciliation_rows = []
    for item in mismatches["mismatches"]:
        courier = item["courier_name"]
        group = grouped[courier]
        group["courier"] = courier
        group["shipment_count"] += 1
        group["total_disputed_inr"] += item["overcharge_inr"]
        group["shipment_ids"].append(item["row_id"])

        reconciliation_rows.append({
            "merchant_id": merchant_id,
            "shipment_id": item["row_id"],
            "discrepancy_type": "weight_overcharge",
            "declared_value": item["weight_declared_kg"],
            "charged_value": item["weight_charged_kg"],
            "amount_disputed_inr": item["overcharge_inr"],
            "status": "open",
        })

    if reconciliation_rows:
        upsert_rows(
            "reconciliation_results",
            reconciliation_rows,
            ["merchant_id", "shipment_id", "discrepancy_type"],
        )

    proposals = []
    for group in grouped.values():
        group["total_disputed_inr"] = round(group["total_disputed_inr"], 2)
        group["action"] = "Create weight dispute in Shiprocket with cited shipment evidence."
        proposals.append(group)

    reasoning_parts = [
        "Flagged shipments where charged weight exceeded the fair 0.5 kg billable slab "
        "for declared weight (nearest-half-kg rounding). Overcharge INR uses zone slab "
        "rates from courier_rate_slabs when synced, else embedded defaults / legacy INR/kg."
    ]
    stale = rate_card_stale_warning(merchant_id)
    if stale:
        reasoning_parts.append(stale)
    reasoning = " ".join(reasoning_parts)

    run = insert_row("agent_runs", {
        "merchant_id": merchant_id,
        "trigger": "manual",
        "data_window_days": 30,
        "shipments_scanned": mismatches["total_count"],
        "findings": mismatches["mismatches"],
        "proposals": proposals,
        "reasoning": reasoning,
        "status": "completed",
    })

    return {"run_id": run.get("id"), "status": "completed"}


@app.get("/api/disputes")
def disputes(merchant_id: str = Query(default="merchant_demo")) -> list[dict]:
    return _get_disputes(merchant_id)


@app.post("/api/disputes/action")
def disputes_action(request: DisputeActionRequest) -> dict:
    if "dismiss" in request.note.lower():
        update_row("reconciliation_results", request.reconciliation_id, {
            "status": "dismissed",
            "actioned_at": datetime.utcnow().isoformat(),
            "action_note": request.note,
        })
    else:
        mark_action_taken(request.reconciliation_id, request.note)
    return {"success": True}


def _chunks(lst: list[str], n: int):
    for i in range(0, len(lst), n):
        yield lst[i : i + n]


@app.get("/api/reports/reconciliation")
def reconciliation_report(
    merchant_id: str = Query(default="merchant_demo"),
    days: int = Query(default=90, ge=1, le=366),
) -> dict:
    client = get_client()
    since_dt = datetime.utcnow() - timedelta(days=days)
    since = since_dt.isoformat()
    recs = (
        client.table("reconciliation_results")
        .select("*")
        .eq("merchant_id", merchant_id)
        .gte("created_at", since)
        .order("created_at", desc=True)
        .execute()
    ).data or []

    ship_ids = [str(r["shipment_id"]) for r in recs if r.get("shipment_id")]
    ship_map: dict[str, dict] = {}
    for batch in _chunks(ship_ids, 80):
        rows = (
            client.table("shipments")
            .select("id, courier_name, shipment_ref, destination_pincode, weight_declared_kg, weight_charged_kg")
            .in_("id", batch)
            .execute()
        ).data or []
        for s in rows:
            ship_map[str(s["id"])] = s

    by_courier: dict[str, dict] = defaultdict(
        lambda: {"courier": "", "line_count": 0, "amount_inr": 0.0, "open_amount_inr": 0.0}
    )
    by_status: dict[str, int] = defaultdict(int)
    total_inr = 0.0
    open_inr = 0.0
    lines_detail: list[dict] = []

    for r in recs:
        st = r.get("status") or "open"
        by_status[st] += 1
        amt = float(r.get("amount_disputed_inr") or 0)
        total_inr += amt
        if st == "open":
            open_inr += amt
        sid = str(r["shipment_id"]) if r.get("shipment_id") else ""
        sh = ship_map.get(sid, {})
        courier = (sh.get("courier_name") or "unknown").strip() or "unknown"
        g = by_courier[courier]
        g["courier"] = courier
        g["line_count"] += 1
        g["amount_inr"] += amt
        if st == "open":
            g["open_amount_inr"] += amt
        lines_detail.append({
            "reconciliation_id": r.get("id"),
            "shipment_id": sid,
            "shipment_ref": sh.get("shipment_ref"),
            "courier_name": courier,
            "status": st,
            "amount_disputed_inr": round(amt, 2),
            "declared_value": r.get("declared_value"),
            "charged_value": r.get("charged_value"),
            "created_at": r.get("created_at"),
            "destination_pincode": sh.get("destination_pincode"),
        })

    by_courier_list = sorted(
        [
            {
                "courier": v["courier"],
                "line_count": v["line_count"],
                "amount_inr": round(v["amount_inr"], 2),
                "open_amount_inr": round(v["open_amount_inr"], 2),
            }
            for v in by_courier.values()
        ],
        key=lambda x: x["amount_inr"],
        reverse=True,
    )

    return {
        "merchant_id": merchant_id,
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "period": {"from": since, "days": days},
        "totals": {
            "lines": len(recs),
            "amount_inr": round(total_inr, 2),
            "open_amount_inr": round(open_inr, 2),
            "by_status": dict(by_status),
        },
        "by_courier": by_courier_list,
        "lines": lines_detail[:200],
        "lines_truncated": len(lines_detail) > 200,
    }


@app.get("/api/analytics/orders")
def analytics_orders(
    merchant_id: str = Query(default="merchant_demo"),
    days: int = Query(default=30, ge=1, le=366),
) -> dict:
    client = get_client()
    since = (datetime.utcnow() - timedelta(days=days)).isoformat()
    orders = (
        client.table("orders")
        .select("id, sku_id, quantity, unit_price_inr, payment_method, destination_pincode, ordered_at")
        .eq("merchant_id", merchant_id)
        .gte("ordered_at", since)
        .execute()
    ).data or []

    revenue_by_day: dict[str, float] = defaultdict(float)
    pay_cod = 0
    pay_pre = 0
    pin_revenue: dict[str, float] = defaultdict(float)
    pin_orders: dict[str, int] = defaultdict(int)
    sku_revenue: dict[str, dict] = defaultdict(lambda: {"sku_id": "", "units": 0, "revenue_inr": 0.0})

    for o in orders:
        qty = int(o.get("quantity") or 0)
        price = float(o.get("unit_price_inr") or 0)
        rev = qty * price
        ot = o.get("ordered_at") or ""
        day = ot[:10] if isinstance(ot, str) and len(ot) >= 10 else "unknown"
        revenue_by_day[day] += rev
        pm = (o.get("payment_method") or "").lower()
        if pm == "cod":
            pay_cod += 1
        else:
            pay_pre += 1
        pin = (o.get("destination_pincode") or "").strip() or "unknown"
        pin_revenue[pin] += rev
        pin_orders[pin] += 1
        sk = o.get("sku_id") or "unknown"
        sku_revenue[sk]["sku_id"] = sk
        sku_revenue[sk]["units"] += qty
        sku_revenue[sk]["revenue_inr"] += rev

    top_pincodes = sorted(
        [
            {"pincode": p, "revenue_inr": round(pin_revenue[p], 2), "order_lines": pin_orders[p]}
            for p in pin_revenue
        ],
        key=lambda x: x["revenue_inr"],
        reverse=True,
    )[:12]

    sku_list = sorted(sku_revenue.values(), key=lambda x: x["revenue_inr"], reverse=True)[:20]
    sku_ids = [s["sku_id"] for s in sku_list if s["sku_id"] != "unknown"]
    costs: dict[str, float] = {}
    if sku_ids:
        for batch in _chunks(sku_ids, 50):
            rows = (
                client.table("sku_master")
                .select("sku_id, cost_price_inr, name")
                .eq("merchant_id", merchant_id)
                .in_("sku_id", batch)
                .execute()
            ).data or []
            for row in rows:
                costs[str(row["sku_id"])] = float(row.get("cost_price_inr") or 0)

    top_skus_enriched = []
    for s in sku_list:
        sid = s["sku_id"]
        cost = costs.get(sid, 0.0)
        units = int(s["units"])
        cogs = units * cost
        rev = s["revenue_inr"]
        margin = rev - cogs
        top_skus_enriched.append({
            "sku_id": sid,
            "units": units,
            "revenue_inr": round(rev, 2),
            "cogs_inr": round(cogs, 2),
            "margin_inr": round(margin, 2),
        })

    days_sorted = sorted(k for k in revenue_by_day if k != "unknown")

    return {
        "merchant_id": merchant_id,
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "period": {"from": since, "days": days},
        "summary": {
            "order_lines": len(orders),
            "revenue_inr": round(sum(revenue_by_day.values()), 2),
            "cod_lines": pay_cod,
            "prepaid_lines": pay_pre,
        },
        "revenue_by_day": [{"date": d, "revenue_inr": round(revenue_by_day[d], 2)} for d in days_sorted],
        "top_pincodes": top_pincodes,
        "top_skus": top_skus_enriched,
    }


@app.post("/api/tools/run")
def run_tool(request: ToolRequest) -> dict:
    args = dict(request.arguments)

    if request.tool == "find_weight_mismatches":
        result = find_weight_mismatches(request.merchant_id, days=int(args.get("days", 30)))
    elif request.tool == "get_rto_rate":
        result = get_rto_rate(
            request.merchant_id,
            sku_id=args.get("sku_id"),
            pincode=args.get("pincode"),
        )
    elif request.tool == "calculate_pnl":
        sku_id = args.get("sku_id")
        if not sku_id:
            raise HTTPException(status_code=400, detail="calculate_pnl requires sku_id")
        result = calculate_pnl(request.merchant_id, sku_id=sku_id, period=args.get("period", "30d"))
    elif request.tool == "get_inventory_status":
        result = get_inventory_status(request.merchant_id)
    elif request.tool == "get_top_skus":
        result = get_top_skus(
            request.merchant_id,
            metric=args.get("metric", "revenue"),
            limit=int(args.get("limit", 10)),
        )
    else:
        raise HTTPException(status_code=400, detail=f"Unsupported tool: {request.tool}")

    return {"tool": request.tool, "result": result}


@app.post("/api/chat")
def chat(request: ChatRequest) -> dict:
    try:
        answer = run_chat_loop(request.merchant_id, request.message, request.history)
    except APIStatusError as e:
        if e.status_code in (413, 429):
            raise HTTPException(
                status_code=429,
                detail=(
                    "Groq token or rate limit exceeded. Try a shorter message, clear chat history, "
                    "or set GROQ_MODEL=llama-3.1-8b-instant for higher throughput."
                ),
            ) from e
        raise HTTPException(status_code=502, detail="Groq API error") from e
    row_ids = extract_row_ids(answer)
    return {
        "merchant_id": request.merchant_id,
        "response": answer,
        "answer": answer,
        "citations": _citation_metadata(row_ids),
        "row_ids": row_ids,
    }
