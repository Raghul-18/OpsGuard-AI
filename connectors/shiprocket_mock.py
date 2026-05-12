import random
import uuid
from datetime import datetime, timedelta

from connectors.base import BaseConnector, NormalizedOrder, NormalizedShipment, NormalizedSKU

COURIERS = ["Delhivery", "BlueDart", "Ecom Express", "XpressBees", "DTDC"]

PINCODES = {
    "400001": "Mumbai",
    "110001": "Delhi",
    "560001": "Bangalore",
    "600001": "Chennai",
    "500001": "Hyderabad",
    "700001": "Kolkata",
    "380001": "Ahmedabad",
    "411001": "Pune",
}

# These pincodes have deliberately high RTO rates
BAD_PINCODES = {"700001", "380001"}

WEIGHT_SLABS = [0.5, 1.0, 1.5, 2.0, 3.0, 5.0]

RATE_PER_KG = {
    "Delhivery": 45,
    "BlueDart": 55,
    "Ecom Express": 40,
    "XpressBees": 42,
    "DTDC": 38,
}


def next_slab(weight_kg: float) -> float:
    for slab in WEIGHT_SLABS:
        if weight_kg <= slab:
            return slab
    return weight_kg * 1.5


class MockShiprocketConnector(BaseConnector):
    def __init__(self, merchant_id: str, credentials: dict):
        super().__init__(merchant_id, credentials)
        self._shipments = None

    def _generate_mock_shipments(self, count: int = 200) -> list[dict]:
        random.seed(42)  # Deterministic for tests
        shipments = []
        now = datetime.utcnow()

        for i in range(count):
            days_ago = random.randint(0, 30)
            created_at = now - timedelta(days=days_ago)

            pincode = random.choice(list(PINCODES.keys()))
            courier = random.choice(COURIERS)
            is_cod = random.random() < 0.45

            # High RTO in bad pincodes for COD
            if pincode in BAD_PINCODES and is_cod:
                rto = random.random() < 0.20
            else:
                rto = random.random() < 0.05

            declared_weight = round(random.choice([0.3, 0.5, 0.8, 1.0, 1.2, 1.5, 2.0, 2.5]), 2)

            # 30% of shipments have weight overcharge
            if random.random() < 0.30:
                charged_weight = next_slab(declared_weight * 1.1 + 0.05)
            else:
                charged_weight = next_slab(declared_weight)

            rate = RATE_PER_KG[courier]
            shipping_cost = round(charged_weight * rate + random.uniform(10, 30), 2)

            status = "Delivered" if not rto else "RTO"
            if days_ago < 3:
                status = "In Transit"

            shipment = {
                "shipment_id": f"SH{100000 + i}",
                "order_id": f"ORD-{90000 + i}",
                "courier_name": courier,
                "weight_declared_kg": declared_weight,
                "weight_charged_kg": charged_weight,
                "shipping_cost_inr": shipping_cost,
                "status": status,
                "rto": rto,
                "destination_pincode": pincode,
                "payment_method": "COD" if is_cod else "prepaid",
                "created_at": created_at.isoformat(),
            }
            shipments.append(shipment)

        return shipments

    def _get_shipments(self) -> list[dict]:
        if self._shipments is None:
            self._shipments = self._generate_mock_shipments()
        return self._shipments

    def fetch_shipments(self, since: datetime) -> list[NormalizedShipment]:
        raw = self._get_shipments()
        result = []
        ingested_at = datetime.utcnow()

        for s in raw:
            created = datetime.fromisoformat(s["created_at"])
            if created < since:
                continue
            result.append(NormalizedShipment(
                merchant_id=self.merchant_id,
                shipment_ref=s["shipment_id"],
                order_ref=s["order_id"],
                courier_name=s["courier_name"],
                weight_declared_kg=s["weight_declared_kg"],
                weight_charged_kg=s["weight_charged_kg"],
                shipping_cost_inr=s["shipping_cost_inr"],
                status=s["status"],
                rto=s["rto"],
                destination_pincode=s["destination_pincode"],
                source=self.get_source_name(),
                source_record_id=s["shipment_id"],
                ingested_at=ingested_at,
                raw_metadata=s,
            ))
        return result

    def fetch_orders(self, since: datetime) -> list[NormalizedOrder]:
        return []

    def fetch_sku_master(self) -> list[NormalizedSKU]:
        return []

    def test_connection(self) -> bool:
        return True

    def get_source_name(self) -> str:
        return "shiprocket_mock"
