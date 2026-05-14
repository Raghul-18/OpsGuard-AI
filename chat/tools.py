"""
Chat tool implementations.
Each function queries Supabase and returns data with row_ids for citation.
"""

from datetime import datetime, timedelta
from typing import Optional

from db.client import get_client

# Per-kg slab rates (aligned with connectors/shiprocket_mock.RATE_PER_KG); used instead of back-solving from invoice cost.
COURIER_RATE_INR_PER_KG = {
    "Delhivery": 45,
    "BlueDart": 55,
    "Ecom Express": 40,
    "XpressBees": 42,
    "DTDC": 38,
}


def find_weight_mismatches(merchant_id: str, days: int = 30) -> dict:
    """Find shipments where charged weight > declared weight × 1.1."""
    client = get_client()
    since = (datetime.utcnow() - timedelta(days=days)).isoformat()

    result = (
        client.table("shipments")
        .select("id, shipment_ref, courier_name, weight_declared_kg, weight_charged_kg, shipping_cost_inr, destination_pincode, ingested_at")
        .eq("merchant_id", merchant_id)
        .gte("ingested_at", since)
        .execute()
    )

    mismatches = []
    for row in result.data:
        declared = row["weight_declared_kg"] or 0
        charged = row["weight_charged_kg"] or 0
        if declared > 0 and charged > declared * 1.1:
            overcharge_kg = charged - declared
            courier = row.get("courier_name") or ""
            rate = COURIER_RATE_INR_PER_KG.get(courier, 45)
            overcharge_inr = round(overcharge_kg * rate, 2)
            mismatches.append({
                "row_id": row["id"],
                "shipment_ref": row["shipment_ref"],
                "courier_name": row["courier_name"],
                "weight_declared_kg": declared,
                "weight_charged_kg": charged,
                "overcharge_inr": overcharge_inr,
                "destination_pincode": row["destination_pincode"],
            })

    total_overcharge = sum(m["overcharge_inr"] for m in mismatches)
    return {
        "mismatches": mismatches,
        "total_count": len(mismatches),
        "total_overcharge_inr": round(total_overcharge, 2),
        "row_ids": [m["row_id"] for m in mismatches],
    }


def get_rto_rate(merchant_id: str, sku_id: Optional[str] = None, pincode: Optional[str] = None) -> dict:
    """Calculate RTO rate, optionally filtered by SKU or pincode."""
    client = get_client()

    # Get shipments
    q = client.table("shipments").select("id, rto, destination_pincode, order_ref").eq("merchant_id", merchant_id)
    if pincode:
        q = q.eq("destination_pincode", pincode)
    shipments = q.execute().data

    # If filtering by SKU, cross-reference with orders
    if sku_id:
        orders_q = (
            client.table("orders")
            .select("order_ref, sku_id, destination_pincode")
            .eq("merchant_id", merchant_id)
            .eq("sku_id", sku_id)
            .execute()
        )
        order_rows = orders_q.data or []
        order_refs = {o["order_ref"] for o in order_rows}
        sku_pincodes = {o["destination_pincode"] for o in order_rows if o.get("destination_pincode")}
        by_ref = [s for s in shipments if s.get("order_ref") in order_refs]
        if by_ref:
            shipments = by_ref
        elif sku_pincodes:
            # Mock Shiprocket uses synthetic order_ref; align demo data by destination pincode
            shipments = [s for s in shipments if s.get("destination_pincode") in sku_pincodes]

    total = len(shipments)
    rto_count = sum(1 for s in shipments if s.get("rto"))
    rto_rate = round((rto_count / total * 100), 2) if total > 0 else 0

    return {
        "total_shipments": total,
        "rto_count": rto_count,
        "rto_rate_pct": rto_rate,
        "row_ids": [s["id"] for s in shipments if s.get("rto")],
        "filter_sku": sku_id,
        "filter_pincode": pincode,
    }


def calculate_pnl(merchant_id: str, sku_id: str, period: str = "30d") -> dict:
    """Calculate P&L for a SKU over a period."""
    client = get_client()
    days = 30 if period == "30d" else 90
    since = (datetime.utcnow() - timedelta(days=days)).isoformat()

    # Orders for this SKU
    orders = (
        client.table("orders")
        .select("id, quantity, unit_price_inr, ordered_at")
        .eq("merchant_id", merchant_id)
        .eq("sku_id", sku_id)
        .gte("ordered_at", since)
        .execute()
    ).data

    # SKU cost data
    sku_data = (
        client.table("sku_master")
        .select("id, cost_price_inr, name")
        .eq("merchant_id", merchant_id)
        .eq("sku_id", sku_id)
        .limit(1)
        .execute()
    ).data

    cost_price = sku_data[0]["cost_price_inr"] if sku_data else 0
    sku_name = sku_data[0]["name"] if sku_data else sku_id

    total_units = sum(o["quantity"] for o in orders)
    total_revenue = sum(o["quantity"] * o["unit_price_inr"] for o in orders)
    total_cogs = total_units * cost_price

    # Shipping cost (approximate from shipments)
    shipments_result = (
        client.table("shipments")
        .select("id, shipping_cost_inr")
        .eq("merchant_id", merchant_id)
        .gte("ingested_at", since)
        .execute()
    ).data
    # Assign shipping proportionally (simplified)
    total_shipping = sum(s["shipping_cost_inr"] or 0 for s in shipments_result)
    total_orders_all = (
        client.table("orders")
        .select("id", count="exact")
        .eq("merchant_id", merchant_id)
        .gte("ordered_at", since)
        .execute()
    ).count or 1
    shipping_per_order = total_shipping / total_orders_all
    sku_shipping = shipping_per_order * len(orders)

    gross_profit = total_revenue - total_cogs - sku_shipping
    margin_pct = round((gross_profit / total_revenue * 100), 2) if total_revenue > 0 else 0

    return {
        "sku_id": sku_id,
        "sku_name": sku_name,
        "period": period,
        "total_units_sold": total_units,
        "total_revenue_inr": round(total_revenue, 2),
        "total_cogs_inr": round(total_cogs, 2),
        "total_shipping_inr": round(sku_shipping, 2),
        "gross_profit_inr": round(gross_profit, 2),
        "margin_pct": margin_pct,
        "row_ids": [o["id"] for o in orders] + ([sku_data[0]["id"]] if sku_data else []),
    }


def get_inventory_status(merchant_id: str) -> dict:
    """Get SKUs below their reorder level."""
    client = get_client()

    skus = (
        client.table("sku_master")
        .select("id, sku_id, name, reorder_level, inventory_quantity, category")
        .eq("merchant_id", merchant_id)
        .execute()
    ).data or []

    low_stock = [
        s
        for s in skus
        if s.get("reorder_level") is not None
        and s.get("inventory_quantity") is not None
        and int(s["reorder_level"]) > 0
        and int(s["inventory_quantity"]) <= int(s["reorder_level"])
    ]

    return {
        "low_stock_skus": low_stock,
        "total_skus": len(skus),
        "low_stock_count": len(low_stock),
        "row_ids": [s["id"] for s in low_stock],
    }


def get_top_skus(merchant_id: str, metric: str = "revenue", limit: int = 10) -> dict:
    """Get top SKUs by revenue or volume."""
    client = get_client()

    orders = (
        client.table("orders")
        .select("id, sku_id, quantity, unit_price_inr")
        .eq("merchant_id", merchant_id)
        .execute()
    ).data

    aggregated: dict[str, dict] = {}
    order_ids_by_sku: dict[str, list] = {}

    for o in orders:
        sid = o["sku_id"]
        if sid not in aggregated:
            aggregated[sid] = {"sku_id": sid, "total_units": 0, "total_revenue": 0.0}
            order_ids_by_sku[sid] = []
        aggregated[sid]["total_units"] += o["quantity"]
        aggregated[sid]["total_revenue"] += o["quantity"] * (o["unit_price_inr"] or 0)
        order_ids_by_sku[sid].append(o["id"])

    sort_key = "total_revenue" if metric == "revenue" else "total_units"
    ranked = sorted(aggregated.values(), key=lambda x: x[sort_key], reverse=True)[:limit]

    for item in ranked:
        item["row_ids"] = order_ids_by_sku.get(item["sku_id"], [])

    return {
        "metric": metric,
        "top_skus": ranked,
        "row_ids": [rid for item in ranked for rid in item["row_ids"]],
    }


def mark_action_taken(reconciliation_id: str, note: str) -> dict:
    """Mark a reconciliation result as actioned."""
    from db.client import update_row
    update_row("reconciliation_results", reconciliation_id, {
        "status": "actioned",
        "actioned_at": datetime.utcnow().isoformat(),
        "action_note": note,
    })
    return {"reconciliation_id": reconciliation_id, "status": "actioned", "note": note}


# Tool definitions for Groq function calling
TOOL_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "find_weight_mismatches",
            "description": "Find shipments where the courier charged more weight than declared. Returns list of overcharged shipments with INR amounts.",
            "parameters": {
                "type": "object",
                "properties": {
                    "merchant_id": {"type": "string"},
                    "days": {"type": "integer", "description": "Look back this many days", "default": 30},
                },
                "required": ["merchant_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_rto_rate",
            "description": "Get the Return to Origin (RTO) rate, optionally filtered by SKU or destination pincode.",
            "parameters": {
                "type": "object",
                "properties": {
                    "merchant_id": {"type": "string"},
                    "sku_id": {"type": "string", "description": "Filter by SKU"},
                    "pincode": {"type": "string", "description": "Filter by destination pincode"},
                },
                "required": ["merchant_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "calculate_pnl",
            "description": "Calculate revenue, COGS, shipping cost, and gross margin for a SKU.",
            "parameters": {
                "type": "object",
                "properties": {
                    "merchant_id": {"type": "string"},
                    "sku_id": {"type": "string"},
                    "period": {"type": "string", "enum": ["30d", "90d"], "default": "30d"},
                },
                "required": ["merchant_id", "sku_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_inventory_status",
            "description": "Get SKUs that are below their reorder level.",
            "parameters": {
                "type": "object",
                "properties": {
                    "merchant_id": {"type": "string"},
                },
                "required": ["merchant_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_top_skus",
            "description": "Get the top-performing SKUs by revenue or sales volume.",
            "parameters": {
                "type": "object",
                "properties": {
                    "merchant_id": {"type": "string"},
                    "metric": {"type": "string", "enum": ["revenue", "volume"], "default": "revenue"},
                    "limit": {"type": "integer", "default": 10},
                },
                "required": ["merchant_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "mark_action_taken",
            "description": "Mark a dispute or reconciliation item as actioned after the founder has resolved it.",
            "parameters": {
                "type": "object",
                "properties": {
                    "reconciliation_id": {"type": "string"},
                    "note": {"type": "string"},
                },
                "required": ["reconciliation_id", "note"],
            },
        },
    },
]
