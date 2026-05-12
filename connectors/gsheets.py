from datetime import datetime
from typing import Optional

from google.oauth2 import service_account
from googleapiclient.discovery import build

from connectors.base import BaseConnector, ConnectorConfigError, NormalizedOrder, NormalizedShipment, NormalizedSKU

DEFAULT_COLUMN_MAP = {
    "SKU": "sku_id",
    "Product Name": "name",
    "Cost Price": "cost_price_inr",
    "Packaging Weight (g)": "packaging_weight_g",
    "Reorder Level": "reorder_level",
    "Category": "category",
}

REQUIRED_COLUMNS = {"SKU", "Product Name", "Cost Price", "Packaging Weight (g)", "Reorder Level"}


class GsheetsConnector(BaseConnector):
    def __init__(self, merchant_id: str, credentials: dict):
        super().__init__(merchant_id, credentials)
        self.spreadsheet_id = credentials["spreadsheet_id"]
        self.sheet_range = credentials.get("sheet_range", "Sheet1")
        self.column_map = credentials.get("column_map", DEFAULT_COLUMN_MAP)

        service_account_info = credentials["service_account_info"]
        creds = service_account.Credentials.from_service_account_info(
            service_account_info,
            scopes=["https://www.googleapis.com/auth/spreadsheets.readonly"],
        )
        self.service = build("sheets", "v4", credentials=creds)

    def _read_sheet(self):
        result = (
            self.service.spreadsheets()
            .values()
            .get(spreadsheetId=self.spreadsheet_id, range=self.sheet_range)
            .execute()
        )
        return result.get("values", [])

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
