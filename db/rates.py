"""Courier zone slab rates: `courier_rate_slabs` (Sheets Scope C) + legacy INR/kg card + mock fallbacks."""
from __future__ import annotations

import math
import re
import unicodedata
import logging
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

import httpx

from db.client import get_client

logger = logging.getLogger(__name__)

# Per-merchant cache: {"slabs": [...], "from_db": bool}
_merged_slabs_cache: dict[str, dict[str, Any]] = {}
_rates_map_cache: dict[str, dict[str, float]] = {}

STALE_RATE_DAYS = 7

# En-dash (common in Sheets) normalized for matching
_DASH_RE = re.compile(r"[\u2013\u2014\-]+")


def normalize_courier_name(name: str) -> str:
    return (name or "").strip().casefold()


def normalize_zone_key(zone: str) -> str:
    z = unicodedata.normalize("NFKC", (zone or "").strip())
    z = _DASH_RE.sub("-", z)
    return z.casefold()


# Default matrix (matches typical Indian carrier marketing slabs). Sync from Sheets overwrites per merchant.
def _embedded_slab_rows() -> list[dict[str, Any]]:
    # Zone strings use ASCII hyphen; normalize_zone_key() maps Sheet en-dashes to the same keys.
    rows: list[tuple[str, str, float, float, float]] = [
        ("Delhivery", "Local", 38, 76, 22),
        ("Delhivery", "Metro", 55, 111, 28),
        ("Delhivery", "National", 57, 113, 30),
        ("Delhivery", "Remote/NE", 87, 175, 45),
        ("BlueDart", "Local", 110, 150, 55),
        ("BlueDart", "Metro", 140, 210, 70),
        ("BlueDart", "National", 160, 250, 85),
        ("Xpressbees", "Local", 50, 75, 18),
        ("Xpressbees", "Metro", 65, 95, 22),
        ("Xpressbees", "National", 85, 110, 28),
        ("Ecom Express", "Local", 55, 82, 20),
        ("Ecom Express", "Metro", 70, 98, 24),
        ("Ecom Express", "National", 90, 118, 30),
        ("Shadowfax", "Local", 45, 72, 18),
        ("Shadowfax", "Metro", 60, 88, 22),
        ("Shadowfax", "National", 78, 105, 28),
        ("DTDC", "Local", 60, 90, 25),
        ("DTDC", "Metro", 85, 120, 32),
        ("DTDC", "National", 100, 130, 38),
        ("India Post", "Local", 28, 38, 10),
        ("India Post", "0-200km", 70, 85, 15),
        ("India Post", "501-1000km", 82, 117, 35),
        ("India Post", "1000km+", 93, 143, 50),
        ("Amazon Shipping", "Local", 60, 82, 20),
        ("Amazon Shipping", "Metro", 75, 110, 26),
        ("Amazon Shipping", "National", 90, 140, 35),
        ("Ekart", "Local", 60, 85, 20),
        ("Ekart", "Metro", 80, 110, 25),
        ("Ekart", "National", 100, 150, 35),
        ("Shiprocket Air", "Metro", 120, 160, 60),
        ("Shiprocket Air", "National", 150, 220, 80),
    ]
    out = []
    for courier, zone, a, b, c in rows:
        out.append({
            "courier_name": courier,
            "zone": zone,
            "rate_upto_500g_inr": a,
            "rate_upto_1kg_inr": b,
            "rate_additional_500g_inr": c,
        })
    return out


DEFAULT_COURIER_RATE_INR_PER_KG: dict[str, float] = {
    "Delhivery": 45.0,
    "BlueDart": 55.0,
    "Ecom Express": 40.0,
    "XpressBees": 42.0,
    "Xpressbees": 42.0,
    "DTDC": 38.0,
}


def clear_rates_cache(merchant_id: str | None = None) -> None:
    """Call after sync updates slabs or rate card so the next read is fresh."""
    if merchant_id is None:
        _merged_slabs_cache.clear()
        _rates_map_cache.clear()
    else:
        _merged_slabs_cache.pop(merchant_id, None)
        _rates_map_cache.pop(merchant_id, None)


def _fetch_db_slabs(merchant_id: str) -> list[dict[str, Any]]:
    last_err: Exception | None = None
    for attempt in range(3):
        try:
            client = get_client()
            rows = (
                client.table("courier_rate_slabs")
                .select("courier_name, zone, rate_upto_500g_inr, rate_upto_1kg_inr, rate_additional_500g_inr")
                .eq("merchant_id", merchant_id)
                .execute()
            ).data or []
            out = []
            for r in rows:
                try:
                    out.append({
                        "courier_name": str(r.get("courier_name") or ""),
                        "zone": str(r.get("zone") or ""),
                        "rate_upto_500g_inr": float(r.get("rate_upto_500g_inr") or 0),
                        "rate_upto_1kg_inr": float(r.get("rate_upto_1kg_inr") or 0),
                        "rate_additional_500g_inr": float(r.get("rate_additional_500g_inr") or 0),
                    })
                except (TypeError, ValueError):
                    continue
            return [r for r in out if r["courier_name"] and r["zone"]]
        except (httpx.RemoteProtocolError, httpx.ConnectError, httpx.ReadTimeout) as e:
            last_err = e
            logger.warning("courier_rate_slabs fetch attempt %s failed: %s", attempt + 1, e)
            time.sleep(0.4 * (attempt + 1))
    if last_err:
        logger.warning("Using embedded slabs after Supabase error: %s", last_err)
    return []


def get_db_slabs(merchant_id: str) -> list[dict[str, Any]]:
    entry = _merged_slabs_cache.get(merchant_id)
    if entry is not None:
        return entry["slabs"] if entry["from_db"] else []
    merged_slabs(merchant_id)
    entry = _merged_slabs_cache[merchant_id]
    return entry["slabs"] if entry["from_db"] else []


def merged_slabs(merchant_id: str) -> list[dict[str, Any]]:
    entry = _merged_slabs_cache.get(merchant_id)
    if entry is not None:
        return entry["slabs"]
    db = _fetch_db_slabs(merchant_id)
    from_db = bool(db)
    slabs = db if db else _embedded_slab_rows()
    _merged_slabs_cache[merchant_id] = {"slabs": slabs, "from_db": from_db}
    return slabs


def slabs_from_db(merchant_id: str) -> bool:
    merged_slabs(merchant_id)
    return bool(_merged_slabs_cache[merchant_id]["from_db"])


def _slab_index(slabs: list[dict[str, Any]]) -> dict[tuple[str, str], dict[str, Any]]:
    idx: dict[tuple[str, str], dict[str, Any]] = {}
    for r in slabs:
        k = (normalize_courier_name(r["courier_name"]), normalize_zone_key(r["zone"]))
        idx[k] = r
    return idx


def find_slab_row(courier_name: str, zone: str, slabs: list[dict[str, Any]]) -> Optional[dict[str, Any]]:
    idx = _slab_index(slabs)
    ck = normalize_courier_name(courier_name)
    zk = normalize_zone_key(zone)
    return idx.get((ck, zk))


def slab_shipping_inr(row: dict[str, Any], weight_kg: float) -> float:
    """0–500g, 501g–1kg, then each additional 500g (ceil)."""
    g500 = float(row["rate_upto_500g_inr"])
    g1k = float(row["rate_upto_1kg_inr"])
    add = float(row["rate_additional_500g_inr"])
    w = max(1e-6, float(weight_kg))
    if w <= 0.5:
        return g500
    if w <= 1.0:
        return g1k
    half_blocks = max(0, math.ceil((w - 1.0) / 0.5))
    return g1k + half_blocks * add


def slab_price_for(
    merchant_id: str,
    courier_name: str,
    zone: str,
    weight_kg: float,
    slabs: Optional[list[dict[str, Any]]] = None,
) -> tuple[float, str]:
    """
    Returns (inr, source) where source is 'slab_db' | 'slab_embedded' | 'inr_per_kg_fallback'.
    """
    slabs = slabs or merged_slabs(merchant_id)
    row = find_slab_row(courier_name, zone, slabs)
    if row:
        src = "slab_db" if slabs_from_db(merchant_id) else "slab_embedded"
        return round(slab_shipping_inr(row, weight_kg), 2), src
    # Legacy INR/kg on courier only (no zone)
    dbm = get_db_rates_map(merchant_id)
    rate, rsrc = resolve_rate_inr_per_kg(merchant_id, courier_name, dbm)
    return round(float(weight_kg) * rate, 2), f"inr_per_kg_{rsrc}"


# --- Pincode → zone (heuristic; must match Sheet zone labels) ---
METRO_PINCODES = {"400001", "110001", "560001", "600001", "500001", "700001", "380001", "411001"}
LOCAL_PINCODES = {"411001"}  # Pune as "local" demo
REMOTE_NE_PINCODES = {"781001", "793001", "737101"}  # NE-style demo pins
NATIONAL_PINCODES = {"442001", "452001", "281001", "641001"}

ALL_DEMO_PINCODES = sorted(METRO_PINCODES | LOCAL_PINCODES | REMOTE_NE_PINCODES | NATIONAL_PINCODES)


def zone_for_pincode(
    pincode: str,
    courier_name: str,
    merchant_id: str = "",
    slabs: Optional[list[dict[str, Any]]] = None,
) -> str:
    pin = (pincode or "").strip()
    c = normalize_courier_name(courier_name)
    slabs = slabs if slabs is not None else merged_slabs(merchant_id)
    if "india post" in c:
        bands = ["Local", "0-200km", "501-1000km", "1000km+"]
        return bands[sum(ord(ch) for ch in pin) % len(bands)]
    if "shiprocket air" in c:
        return "Metro" if pin in METRO_PINCODES else "National"
    if pin in LOCAL_PINCODES:
        return "Local"
    if pin in METRO_PINCODES:
        return "Metro"
    if pin in REMOTE_NE_PINCODES:
        return "Remote/NE" if find_slab_row(courier_name, "Remote/NE", slabs) else "National"
    if pin in NATIONAL_PINCODES or (len(pin) == 6 and pin.isdigit()):
        return "National"
    return "National"


def billable_weight_kg(actual_kg: float) -> float:
    """Billable weight on 0.5 kg slabs — round to nearest half kg (e.g. 0.8→1, 0.5→0.5, 2→2, 0.3→0.5)."""
    w = max(0.05, float(actual_kg))
    return round(w * 2) / 2


def zone_from_shipment_row(row: dict[str, Any], merchant_id: str) -> str:
    meta = row.get("raw_metadata") or {}
    if isinstance(meta, dict) and meta.get("zone"):
        return str(meta["zone"])
    return zone_for_pincode(
        str(row.get("destination_pincode") or ""),
        str(row.get("courier_name") or ""),
        merchant_id,
    )


# --- Legacy per-kg card (optional Sheets tab) ---
def get_db_rates_map(merchant_id: str) -> dict[str, float]:
    if merchant_id in _rates_map_cache:
        return _rates_map_cache[merchant_id]
    out: dict[str, float] = {}
    try:
        client = get_client()
        rows = (
            client.table("courier_rate_card")
            .select("courier_name, rate_inr_per_kg")
            .eq("merchant_id", merchant_id)
            .execute()
        ).data or []
        for r in rows:
            key = normalize_courier_name(r.get("courier_name") or "")
            if not key:
                continue
            try:
                out[key] = float(r.get("rate_inr_per_kg") or 0)
            except (TypeError, ValueError):
                continue
    except (httpx.RemoteProtocolError, httpx.ConnectError, httpx.ReadTimeout) as e:
        logger.warning("courier_rate_card fetch failed: %s", e)
    _rates_map_cache[merchant_id] = out
    return out


def rate_slabs_stale_warning(merchant_id: str) -> Optional[str]:
    client = get_client()
    rows = (
        client.table("courier_rate_slabs")
        .select("ingested_at")
        .eq("merchant_id", merchant_id)
        .order("ingested_at", desc=True)
        .limit(1)
        .execute()
    ).data or []
    if not rows:
        return None
    ing = rows[0].get("ingested_at")
    if not ing:
        return None
    try:
        ts = datetime.fromisoformat(ing.replace("Z", "+00:00")) if isinstance(ing, str) else ing
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        return None
    age = datetime.now(timezone.utc) - ts
    if age > timedelta(days=STALE_RATE_DAYS):
        return (
            f"Courier slab table last synced {ing} (> {STALE_RATE_DAYS} days). "
            "Refresh your Sheet and run sync."
        )
    return None


# Back-compat name used by chat/tools
def rate_card_stale_warning(merchant_id: str) -> Optional[str]:
    if get_db_slabs(merchant_id):
        return rate_slabs_stale_warning(merchant_id)
    return _legacy_rate_card_stale_warning(merchant_id)


def _legacy_rate_card_stale_warning(merchant_id: str) -> Optional[str]:
    client = get_client()
    rows = (
        client.table("courier_rate_card")
        .select("ingested_at")
        .eq("merchant_id", merchant_id)
        .order("ingested_at", desc=True)
        .limit(1)
        .execute()
    ).data or []
    if not rows:
        return None
    ing = rows[0].get("ingested_at")
    if not ing:
        return None
    try:
        ts = datetime.fromisoformat(ing.replace("Z", "+00:00")) if isinstance(ing, str) else ing
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        return None
    age = datetime.now(timezone.utc) - ts
    if age > timedelta(days=STALE_RATE_DAYS):
        return (
            f"Legacy courier_rate_card last synced {ing} (> {STALE_RATE_DAYS} days). "
            "Prefer GSHEETS_RATE_SLABS_RANGE for zone slabs."
        )
    return None


def resolve_rate_inr_per_kg(
    merchant_id: str,
    courier_name: str,
    db_rates: dict[str, float],
) -> tuple[float, str]:
    key = normalize_courier_name(courier_name)
    if key in db_rates and db_rates[key] > 0:
        return db_rates[key], "sheet"
    for canon, rate in DEFAULT_COURIER_RATE_INR_PER_KG.items():
        if normalize_courier_name(canon) == key and rate > 0:
            return rate, "default"
    return 45.0, "default"


def weight_mismatch_overcharge_inr(
    merchant_id: str,
    courier_name: str,
    pincode: str,
    declared_kg: float,
    charged_kg: float,
    shipping_cost_inr: float,
    raw_metadata: Optional[dict],
) -> tuple[float, str, Optional[str]]:
    """
    When charged > declared * 1.1, estimate overcharge INR.
    Slab mode: max(0, billed - expected_at_declared_weight).
    """
    slabs = merged_slabs(merchant_id)
    meta = raw_metadata if isinstance(raw_metadata, dict) else {}
    zone = (
        str(meta.get("zone"))
        if meta.get("zone")
        else zone_for_pincode(pincode, courier_name, merchant_id, slabs=slabs)
    )
    expected, src = slab_price_for(merchant_id, courier_name, zone, declared_kg, slabs=slabs)
    billed = float(shipping_cost_inr or 0)
    if find_slab_row(courier_name, zone, slabs):
        over = max(0.0, billed - expected)
        return round(over, 2), src, zone
    # No slab row: INR/kg on weight delta
    dbm = get_db_rates_map(merchant_id)
    rate, rsrc = resolve_rate_inr_per_kg(merchant_id, courier_name, dbm)
    over = max(0.0, (charged_kg - declared_kg) * rate)
    return round(over, 2), f"inr_per_kg_{rsrc}", zone
