import time
from datetime import datetime
from decimal import Decimal

import requests

from connectors.base import BaseConnector, NormalizedOrder, NormalizedSKU, NormalizedShipment


class ShopifyConnector(BaseConnector):
    def __init__(self, merchant_id: str, credentials: dict):
        super().__init__(merchant_id, credentials)
        self.shop = credentials["shop"]  # e.g. "mystore.myshopify.com"
        self.access_token = credentials["access_token"]
        self.base_url = f"https://{self.shop}/admin/api/2024-01"
        self.headers = {"X-Shopify-Access-Token": self.access_token}

    def _get(self, endpoint: str, params: dict = None):
        url = f"{self.base_url}{endpoint}"
        results = []
        while url:
            response = requests.get(url, headers=self.headers, params=params)
            response.raise_for_status()
            data = response.json()
            results.append(data)
            # Cursor-based pagination via Link header
            link_header = response.headers.get("Link", "")
            url = None
            params = None
            if 'rel="next"' in link_header:
                for part in link_header.split(","):
                    if 'rel="next"' in part:
                        url = part.split(";")[0].strip().strip("<>")
            time.sleep(0.5)  # Respect Shopify rate limit
        return results

    def fetch_orders(self, since: datetime) -> list[NormalizedOrder]:
        pages = self._get("/orders.json", params={
            "created_at_min": since.isoformat(),
            "status": "any",
            "limit": 250,
        })
        orders = []
        ingested_at = datetime.utcnow()
        for page in pages:
            for order in page.get("orders", []):
                shipping_address = order.get("shipping_address") or {}
                gateway_names = order.get("payment_gateway_names") or []
                payment_method = (
                    "COD"
                    if "cash_on_delivery" in gateway_names or order.get("payment_gateway") == "cash_on_delivery"
                    else "prepaid"
                )
                for item in order.get("line_items", []):
                    orders.append(NormalizedOrder(
                        merchant_id=self.merchant_id,
                        order_ref=str(order["id"]),
                        sku_id=item.get("sku") or str(item["variant_id"]),
                        quantity=item["quantity"],
                        unit_price_inr=float(Decimal(item["price"])),
                        payment_method=payment_method,
                        destination_pincode=shipping_address.get("zip", ""),
                        ordered_at=datetime.fromisoformat(order["created_at"].replace("Z", "+00:00")),
                        source=self.get_source_name(),
                        source_record_id=str(order["id"]),
                        ingested_at=ingested_at,
                        raw_metadata=order,
                    ))
        return orders

    def fetch_sku_master(self) -> list[NormalizedSKU]:
        pages = self._get("/products.json", params={"limit": 250})
        skus = []
        ingested_at = datetime.utcnow()
        for page in pages:
            for product in page.get("products", []):
                for variant in product.get("variants", []):
                    inv = variant.get("inventory_quantity")
                    try:
                        inventory_quantity = int(inv) if inv is not None else 0
                    except (TypeError, ValueError):
                        inventory_quantity = 0
                    skus.append(NormalizedSKU(
                        merchant_id=self.merchant_id,
                        sku_id=variant.get("sku") or str(variant["id"]),
                        name=f"{product['title']} - {variant['title']}",
                        cost_price_inr=0.0,  # Shopify doesn't store cost; comes from Sheets
                        packaging_weight_g=float(variant.get("weight", 0)) * 1000
                        if variant.get("weight_unit") == "kg"
                        else float(variant.get("weight", 0)),
                        reorder_level=0,
                        category=product.get("product_type"),
                        source=self.get_source_name(),
                        source_record_id=str(variant["id"]),
                        ingested_at=ingested_at,
                        raw_metadata=variant,
                        inventory_quantity=inventory_quantity,
                    ))
        return skus

    def fetch_shipments(self, since: datetime) -> list[NormalizedShipment]:
        # Shopify doesn't natively handle shipments — fulfilled via Shiprocket
        return []

    def test_connection(self) -> bool:
        try:
            response = requests.get(f"{self.base_url}/shop.json", headers=self.headers)
            return response.status_code == 200
        except Exception:
            return False

    def get_source_name(self) -> str:
        return "shopify"
