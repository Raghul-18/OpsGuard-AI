import os
import json
from collections import defaultdict
from datetime import datetime
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
from db.client import get_client, insert_row, update_row, upsert_rows
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
    for table in ("orders", "shipments", "sku_master"):
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
    result = (
        get_client()
        .table("agent_runs")
        .select("*")
        .eq("merchant_id", merchant_id)
        .order("run_at", desc=True)
        .limit(20)
        .execute()
    )
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

    run = insert_row("agent_runs", {
        "merchant_id": merchant_id,
        "trigger": "manual",
        "data_window_days": 30,
        "shipments_scanned": mismatches["total_count"],
        "findings": mismatches["mismatches"],
        "proposals": proposals,
        "reasoning": (
            "Flagged shipments where charged weight exceeded declared weight by more "
            "than the 10% tolerance threshold."
        ),
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
