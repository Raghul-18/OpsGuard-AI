from datetime import datetime
from typing import Optional

from google.oauth2 import service_account
from googleapiclient.discovery import build

from connectors.base import (
    BaseConnector,
    ConnectorConfigError,
    NormalizedCourierRate,
    NormalizedCourierRateSlab,
    NormalizedOrder,
    NormalizedShipment,
    NormalizedSKU,
)

DEFAULT_COLUMN_MAP = {
    "SKU": "sku_id",
    "Product Name": "name",
    "Cost Price": "cost_price_inr",
    "Packaging Weight (g)": "packaging_weight_g",
    "Reorder Level": "reorder_level",
    "Category": "category",
}

REQUIRED_COLUMNS = {"SKU", "Product Name", "Cost Price", "Packaging Weight (g)", "Reorder Level"}

DEFAULT_RATE_COLUMN_MAP = {
    "Courier": "courier_name",
    "Rate INR per kg": "rate_inr_per_kg",
    "Effective from": "effective_from",
}
REQUIRED_RATE_COLUMNS = {"Courier", "Rate INR per kg"}

DEFAULT_SLAB_COLUMN_MAP = {
    "Courier": "courier_name",
    "Zone": "zone",
    "Up to 500g": "rate_upto_500g_inr",
    "Up to 1kg": "rate_upto_1kg_inr",
    "Additional 500g": "rate_additional_500g_inr",
}
REQUIRED_SLAB_COLUMNS = {"Courier", "Zone", "Up to 500g", "Up to 1kg", "Additional 500g"}


class GsheetsConnector(BaseConnector):
    def __init__(self, merchant_id: str, credentials: dict):
        super().__init__(merchant_id, credentials)
        self.spreadsheet_id = credentials["spreadsheet_id"]
        self.sheet_range = credentials.get("sheet_range", "Sheet1")
        self.rate_slabs_range = (credentials.get("rate_slabs_range") or "").strip()
        self.rate_card_range = (credentials.get("rate_card_range") or "").strip()
        self.column_map = credentials.get("column_map", DEFAULT_COLUMN_MAP)
        self.rate_column_map = credentials.get("rate_column_map", DEFAULT_RATE_COLUMN_MAP)
        self.slab_column_map = credentials.get("slab_column_map", DEFAULT_SLAB_COLUMN_MAP)

        service_account_info = credentials["service_account_info"]
        creds = service_account.Credentials.from_service_account_info(
            service_account_info,
            scopes=["https://www.googleapis.com/auth/spreadsheets.readonly"],
        )
        self.service = build("sheets", "v4", credentials=creds)

    def _read_range(self, a1_range: str) -> list[list]:
        result = (
            self.service.spreadsheets()
            .values()
            .get(spreadsheetId=self.spreadsheet_id, range=a1_range)
            .execute()
        )
        return result.get("values", [])

    def _read_sheet(self):
        return self._read_range(self.sheet_range)

    def fetch_courier_rate_slabs(self) -> list[NormalizedCourierRateSlab]:
        """Optional tab: Courier × Zone × slab INR (Scope C). Skips if rate_slabs_range unset."""
        if not self.rate_slabs_range:
            return []
        rows = self._read_range(self.rate_slabs_range)
        if not rows:
            return []

        headers = rows[0]
        self._validate_slab_columns(headers)

        col_idx = {h: i for i, h in enumerate(headers)}
        inv = {v: k for k, v in self.slab_column_map.items()}
        h_courier = inv.get("courier_name", "Courier")
        h_zone = inv.get("zone", "Zone")
        h500 = inv.get("rate_upto_500g_inr", "Up to 500g")
        h1k = inv.get("rate_upto_1kg_inr", "Up to 1kg")
        hadd = inv.get("rate_additional_500g_inr", "Additional 500g")

        out: list[NormalizedCourierRateSlab] = []
        ingested_at = datetime.utcnow()

        for row_num, row in enumerate(rows[1:], start=2):
            def get(header: str) -> Optional[str]:
                idx = col_idx.get(header)
                if idx is None or idx >= len(row):
                    return None
                return row[idx] or None

            cname = get(h_courier)
            zname = get(h_zone)
            if not cname or not zname:
                continue
            try:
                a = float(get(h500) or 0)
                b = float(get(h1k) or 0)
                c = float(get(hadd) or 0)
            except ValueError:
                continue
            if a <= 0 and b <= 0:
                continue

            out.append(
                NormalizedCourierRateSlab(
                    merchant_id=self.merchant_id,
                    courier_name=cname.strip(),
                    zone=zname.strip(),
                    rate_upto_500g_inr=a,
                    rate_upto_1kg_inr=b,
                    rate_additional_500g_inr=c,
                    source=self.get_source_name(),
                    source_record_id=f"slab_row_{row_num}",
                    ingested_at=ingested_at,
                    raw_metadata={"row": row, "row_num": row_num},
                )
            )
        return out

    def fetch_courier_rates(self) -> list[NormalizedCourierRate]:
        """Legacy: Courier + INR/kg only. Used when rate_slabs_range is empty."""
        if not self.rate_card_range:
            return []
        rows = self._read_range(self.rate_card_range)
        if not rows:
            return []

        headers = rows[0]
        self._validate_rate_columns(headers)

        col_idx = {h: i for i, h in enumerate(headers)}
        inv = {v: k for k, v in self.rate_column_map.items()}
        courier_header = inv.get("courier_name", "Courier")
        rate_header = inv.get("rate_inr_per_kg", "Rate INR per kg")
        eff_header = inv.get("effective_from", "Effective from")

        out: list[NormalizedCourierRate] = []
        ingested_at = datetime.utcnow()

        for row_num, row in enumerate(rows[1:], start=2):
            def get(header: str) -> Optional[str]:
                idx = col_idx.get(header)
                if idx is None or idx >= len(row):
                    return None
                return row[idx] or None

            name = get(courier_header)
            if not name:
                continue
            try:
                rate = float(get(rate_header) or 0)
            except ValueError:
                rate = 0.0
            if rate <= 0:
                continue

            eff_raw = get(eff_header)
            effective_from: Optional[datetime] = None
            if eff_raw:
                try:
                    effective_from = datetime.fromisoformat(eff_raw.replace("Z", "+00:00"))
                except ValueError:
                    effective_from = None

            out.append(
                NormalizedCourierRate(
                    merchant_id=self.merchant_id,
                    courier_name=name.strip(),
                    rate_inr_per_kg=rate,
                    source=self.get_source_name(),
                    source_record_id=f"rate_row_{row_num}",
                    ingested_at=ingested_at,
                    raw_metadata={"row": row, "row_num": row_num},
                    effective_from=effective_from,
                )
            )
        return out

    def fetch_sku_master(self) -> list[NormalizedSKU]:
        rows = self._read_sheet()
        if not rows:
            return []

        headers = rows[0]
        self._validate_columns(headers)

        col_idx = {h: i for i, h in enumerate(headers)}
        skus = []
        ingested_at = datetime.utcnow()

        for row_num, row in enumerate(rows[1:], start=2):
            def get(col_name) -> Optional[str]:
                idx = col_idx.get(col_name)
                if idx is None or idx >= len(row):
                    return None
                return row[idx] or None

            sku_id = get("SKU")
            if not sku_id:
                continue

            try:
                cost_price = float(get("Cost Price") or 0)
            except ValueError:
                cost_price = 0.0

            try:
                packaging_weight = float(get("Packaging Weight (g)") or 0)
            except ValueError:
                packaging_weight = 0.0

            try:
                reorder_level = int(get("Reorder Level") or 0)
            except ValueError:
                reorder_level = 0

            skus.append(NormalizedSKU(
                merchant_id=self.merchant_id,
                sku_id=sku_id,
                name=get("Product Name") or "",
                cost_price_inr=cost_price,
                packaging_weight_g=packaging_weight,
                reorder_level=reorder_level,
                category=get("Category"),
                source=self.get_source_name(),
                source_record_id=f"row_{row_num}",
                ingested_at=ingested_at,
                raw_metadata={"row": row, "row_num": row_num},
            ))
        return skus

    def _validate_columns(self, headers: list[str]):
        found = set(headers)
        missing = REQUIRED_COLUMNS - found
        if missing:
            raise ConnectorConfigError(
                f"Google Sheets column drift detected. Missing required columns: {missing}. "
                f"Found columns: {found}. "
                f"Update the column_map in connector credentials or rename the sheet columns."
            )

    def _validate_rate_columns(self, headers: list[str]):
        found = set(headers)
        missing = REQUIRED_RATE_COLUMNS - found
        if missing:
            raise ConnectorConfigError(
                f"Rate card sheet: missing columns {missing}. Found: {found}. "
                f"Expected headers include: {sorted(REQUIRED_RATE_COLUMNS)}."
            )

    def _validate_slab_columns(self, headers: list[str]):
        found = set(headers)
        missing = REQUIRED_SLAB_COLUMNS - found
        if missing:
            raise ConnectorConfigError(
                f"Rate slabs sheet: missing columns {missing}. Found: {found}. "
                f"Expected: {sorted(REQUIRED_SLAB_COLUMNS)}."
            )

    def fetch_orders(self, since: datetime) -> list[NormalizedOrder]:
        return []

    def fetch_shipments(self, since: datetime) -> list[NormalizedShipment]:
        return []

    def test_connection(self) -> bool:
        try:
            self._read_sheet()
            return True
        except Exception:
            return False

    def get_source_name(self) -> str:
        return "gsheets"
