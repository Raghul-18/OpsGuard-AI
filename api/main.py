import os
from typing import Any, Literal

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from chat.tools import (
    calculate_pnl,
    find_weight_mismatches,
    get_inventory_status,
    get_rto_rate,
    get_top_skus,
)
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
    merchant_id: str = "demo_merchant"
    since_days: int = Field(default=30, ge=1, le=365)
    include_shopify: bool = True
    include_shiprocket_mock: bool = True


class ChatRequest(BaseModel):
    merchant_id: str = "demo_merchant"
    message: str
    history: list[dict[str, Any]] = Field(default_factory=list)


class ToolRequest(BaseModel):
    merchant_id: str = "demo_merchant"
    tool: Literal[
        "find_weight_mismatches",
        "get_rto_rate",
        "calculate_pnl",
        "get_inventory_status",
        "get_top_skus",
    ]
    arguments: dict[str, Any] = Field(default_factory=dict)


def _credentials_from_env(include_shopify: bool) -> dict:
    credentials: dict[str, Any] = {}

    if include_shopify:
        shop = os.environ.get("SHOPIFY_SHOP")
        token = os.environ.get("SHOPIFY_ACCESS_TOKEN")
        if not shop or not token:
            raise HTTPException(
                status_code=400,
                detail="SHOPIFY_SHOP and SHOPIFY_ACCESS_TOKEN must be set for Shopify sync",
            )
        credentials["shopify"] = {"shop": shop, "access_token": token}

    return credentials


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.post("/api/sync")
def sync(request: SyncRequest) -> dict:
    credentials = _credentials_from_env(request.include_shopify)
    if request.include_shiprocket_mock:
        credentials["shiprocket"] = {}

    return {
        "merchant_id": request.merchant_id,
        "results": run_sync(request.merchant_id, credentials, since_days=request.since_days),
    }


@app.get("/api/sync/status")
def sync_status(merchant_id: str = Query(default="demo_merchant")) -> dict:
    return {"merchant_id": merchant_id, "sync_jobs": get_sync_status(merchant_id)}


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
    message = request.message.lower()

    if "weight" in message or "overcharge" in message or "dispute" in message:
        tool = "find_weight_mismatches"
        result = find_weight_mismatches(request.merchant_id)
        answer = (
            f"Found {result['total_count']} weight mismatches worth about "
            f"INR {result['total_overcharge_inr']}."
        )
    elif "rto" in message or "return" in message:
        tool = "get_rto_rate"
        result = get_rto_rate(request.merchant_id)
        answer = (
            f"RTO rate is {result['rto_rate_pct']}% across "
            f"{result['total_shipments']} shipments."
        )
    elif "top" in message and "sku" in message:
        tool = "get_top_skus"
        result = get_top_skus(request.merchant_id)
        answer = f"Found top SKUs by revenue. Top result count: {len(result['top_skus'])}."
    elif "inventory" in message or "stock" in message:
        tool = "get_inventory_status"
        result = get_inventory_status(request.merchant_id)
        answer = f"Found {result['low_stock_count']} low-stock SKUs out of {result['total_skus']}."
    else:
        tool = None
        result = {}
        answer = "I can answer questions about weight disputes, RTO rate, top SKUs, and inventory."

    return {
        "merchant_id": request.merchant_id,
        "answer": answer,
        "tool": tool,
        "result": result,
        "row_ids": result.get("row_ids", []),
    }
