"""Non-secret health checks: env presence, optional Shopify ping, Supabase reachability."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")


def nonempty(name: str) -> bool:
    v = os.environ.get(name)
    return bool(v and str(v).strip())


def shopify_shop_ok() -> bool:
    s = (os.environ.get("SHOPIFY_SHOP") or "").strip()
    if not s:
        return False
    s = s.removeprefix("https://").removesuffix("/")
    return ".myshopify.com" in s


def main() -> int:
    print("--- .env variable presence (values hidden) ---")
    rows = [
        ("SUPABASE_URL", nonempty("SUPABASE_URL"), "required"),
        ("SUPABASE_KEY", nonempty("SUPABASE_KEY"), "required"),
        ("SHOPIFY_SHOP", shopify_shop_ok(), "for Shopify sync"),
        ("SHOPIFY_ACCESS_TOKEN", nonempty("SHOPIFY_ACCESS_TOKEN"), "for Shopify sync"),
        (
            "GSHEETS_SPREADSHEET_ID | GOOGLE_SHEET_ID",
            nonempty("GSHEETS_SPREADSHEET_ID") or nonempty("GOOGLE_SHEET_ID"),
            "for Sheets sync",
        ),
        ("GOOGLE_SERVICE_ACCOUNT_JSON", nonempty("GOOGLE_SERVICE_ACCOUNT_JSON"), "for Sheets sync"),
        ("GSHEETS_RATE_SLABS_RANGE", nonempty("GSHEETS_RATE_SLABS_RANGE"), "optional Sheets courier × zone slab tab"),
        ("GSHEETS_RATE_CARD_RANGE", nonempty("GSHEETS_RATE_CARD_RANGE"), "optional Sheets courier INR/kg tab"),
        ("GROQ_API_KEY", nonempty("GROQ_API_KEY"), "for chat"),
    ]
    bad = 0
    for name, ok, note in rows:
        status = "OK" if ok else "MISSING/INVALID"
        if not ok and name.startswith("SUPABASE"):
            bad += 1
        print(f"  {status:16} {name:42} ({note})")

    # JSON validity for service account
    raw = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON")
    if raw and raw.strip():
        try:
            json.loads(raw.strip())
            print("  OK              GOOGLE_SERVICE_ACCOUNT_JSON parse       (valid JSON)")
        except json.JSONDecodeError:
            print("  INVALID         GOOGLE_SERVICE_ACCOUNT_JSON parse       (not valid JSON)")
            bad += 1

    print("\n--- Optional live checks ---")
    # Supabase: try import client (validates URL shape); actual network on first query
    url = (os.environ.get("SUPABASE_URL") or "").strip()
    key = (os.environ.get("SUPABASE_KEY") or "").strip()
    if url and key:
        try:
            from supabase import create_client

            client = create_client(url, key)
            r = client.table("sync_jobs").select("id").limit(1).execute()
            print(f"  OK              Supabase query sync_jobs            (HTTP OK, rows={len(r.data or [])})")
        except Exception as e:
            print(f"  FAIL            Supabase query                      ({type(e).__name__}: {e})")
            bad += 1
    else:
        print("  SKIP            Supabase query                      (missing URL or key)")

    shop = (os.environ.get("SHOPIFY_SHOP") or "").strip()
    token = (os.environ.get("SHOPIFY_ACCESS_TOKEN") or "").strip()
    if shop and token:
        shop = shop.removeprefix("https://").removesuffix("/")
        try:
            import requests

            h = {"X-Shopify-Access-Token": token}
            u = f"https://{shop}/admin/api/2024-01/shop.json"
            resp = requests.get(u, headers=h, timeout=15)
            if resp.status_code == 200:
                print("  OK              Shopify Admin API shop.json       (200)")
            else:
                print(f"  FAIL            Shopify Admin API shop.json       ({resp.status_code})")
                bad += 1
        except Exception as e:
            print(f"  FAIL            Shopify Admin API                   ({type(e).__name__}: {e})")
            bad += 1
    else:
        print("  SKIP            Shopify Admin API                   (missing shop or token)")

    print("\n--- Summary ---")
    if bad:
        print(f"  {bad} blocking issue(s) above.")
        return 1
    print("  All required checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
