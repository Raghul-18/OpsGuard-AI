import os
from dataclasses import asdict, is_dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from dotenv import load_dotenv
from supabase import Client, create_client

load_dotenv()

_client: Client | None = None


def _json_safe(value: Any) -> Any:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    if isinstance(value, dict):
        return {key: _json_safe(item) for key, item in value.items()}
    return value


def get_client() -> Client:
    global _client

    if _client is not None:
        return _client

    supabase_url = os.environ.get("SUPABASE_URL")
    supabase_key = os.environ.get("SUPABASE_KEY")
    if not supabase_url or not supabase_key:
        raise RuntimeError("SUPABASE_URL and SUPABASE_KEY must be set")

    _client = create_client(supabase_url, supabase_key)
    return _client


def dataclass_to_row(instance: Any) -> dict:
    if not is_dataclass(instance):
        raise TypeError("dataclass_to_row expects a dataclass instance")
    return _json_safe(asdict(instance))


def insert_row(table: str, row: dict) -> dict:
    result = get_client().table(table).insert(_json_safe(row)).execute()
    return result.data[0] if result.data else {}


def update_row(table: str, row_id: str, values: dict) -> dict:
    result = (
        get_client()
        .table(table)
        .update(_json_safe(values))
        .eq("id", row_id)
        .execute()
    )
    return result.data[0] if result.data else {}


def upsert_rows(table: str, rows: list[dict], conflict_columns: list[str]) -> list[dict]:
    if not rows:
        return []

    result = (
        get_client()
        .table(table)
        .upsert(_json_safe(rows), on_conflict=",".join(conflict_columns))
        .execute()
    )
    return result.data or []


def query_rows(table: str, merchant_id: str, limit: int = 100) -> list[dict]:
    result = (
        get_client()
        .table(table)
        .select("*")
        .eq("merchant_id", merchant_id)
        .limit(limit)
        .execute()
    )
    return result.data or []
