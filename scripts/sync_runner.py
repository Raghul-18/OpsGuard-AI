import logging
from datetime import datetime, timedelta

from connectors.base import NormalizedOrder, NormalizedShipment, NormalizedSKU
from connectors.gsheets import GsheetsConnector
from connectors.shiprocket_mock import MockShiprocketConnector
from connectors.shopify import ShopifyConnector
from db.client import dataclass_to_row, get_client, insert_row, update_row, upsert_rows

logger = logging.getLogger(__name__)


def _build_connectors(merchant_id: str, credentials: dict):
    """Order matters: Shopify first (SKU + inventory), then Sheets (cost/reorder overwrites), then Shiprocket."""
    connectors = []

    if "shopify" in credentials:
        connectors.append(ShopifyConnector(merchant_id, credentials["shopify"]))
    if "gsheets" in credentials:
        connectors.append(GsheetsConnector(merchant_id, credentials["gsheets"]))
    if credentials.get("shiprocket_mock", True):
        connectors.append(MockShiprocketConnector(merchant_id, credentials.get("shiprocket", {})))

    return connectors


def run_sync(merchant_id: str, credentials: dict, since_days: int = 30) -> dict:
    since = datetime.utcnow() - timedelta(days=since_days)
    results = {}

    for connector in _build_connectors(merchant_id, credentials):
        source = connector.get_source_name()
        job = insert_row("sync_jobs", {
            "merchant_id": merchant_id,
            "connector": "shiprocket" if source == "shiprocket_mock" else source,
            "status": "running",
            "started_at": datetime.utcnow().isoformat(),
        })
        job_id = job.get("id")
        row_count = 0

        try:
            # Fetch and upsert orders
            orders: list[NormalizedOrder] = connector.fetch_orders(since)
            if orders:
                rows = [dataclass_to_row(o) for o in orders]
                upsert_rows("orders", rows, ["merchant_id", "source", "source_record_id", "sku_id"])
                row_count += len(orders)
                logger.info(f"[{source}] Upserted {len(orders)} orders")

            # Fetch and upsert shipments
            shipments: list[NormalizedShipment] = connector.fetch_shipments(since)
            if shipments:
                rows = [dataclass_to_row(s) for s in shipments]
                # Keep source order_ref and leave the FK empty until a resolver links orders.
                for r in rows:
                    r.pop("order_id", None)
                upsert_rows("shipments", rows, ["merchant_id", "source", "source_record_id"])
                row_count += len(shipments)
                logger.info(f"[{source}] Upserted {len(shipments)} shipments")

            # Fetch and upsert SKU master
            skus: list[NormalizedSKU] = connector.fetch_sku_master()
            if skus:
                rows = [dataclass_to_row(sk) for sk in skus]
                if connector.get_source_name() == "gsheets":
                    client = get_client()
                    existing = (
                        client.table("sku_master")
                        .select("sku_id, inventory_quantity")
                        .eq("merchant_id", merchant_id)
                        .execute()
                    ).data or []
                    inv_map = {r["sku_id"]: r.get("inventory_quantity") for r in existing}
                    for r in rows:
                        sid = r.get("sku_id")
                        if sid in inv_map and inv_map[sid] is not None:
                            r["inventory_quantity"] = inv_map[sid]
                        else:
                            r.pop("inventory_quantity", None)
                upsert_rows("sku_master", rows, ["merchant_id", "sku_id"])
                row_count += len(skus)
                logger.info(f"[{source}] Upserted {len(skus)} SKUs")

            if job_id:
                update_row("sync_jobs", job_id, {
                    "status": "done",
                    "completed_at": datetime.utcnow().isoformat(),
                    "last_synced_at": datetime.utcnow().isoformat(),
                    "row_count": row_count,
                })

            results[source] = {"status": "done", "row_count": row_count}

        except Exception as e:
            logger.error(f"[{source}] Sync failed: {e}", exc_info=True)
            if job_id:
                update_row("sync_jobs", job_id, {
                    "status": "failed",
                    "completed_at": datetime.utcnow().isoformat(),
                    "error": str(e),
                })
            results[source] = {"status": "failed", "error": str(e)}

    return results


def get_sync_status(merchant_id: str) -> list[dict]:
    """Get latest sync status for each connector."""
    from db.client import get_client
    client = get_client()
    result = (
        client.table("sync_jobs")
        .select("*")
        .eq("merchant_id", merchant_id)
        .order("scheduled_at", desc=True)
        .limit(50)
        .execute()
    )
    # Return only the most recent per connector
    seen = {}
    for row in result.data:
        connector = row["connector"]
        if connector not in seen:
            seen[connector] = row
    return list(seen.values())
