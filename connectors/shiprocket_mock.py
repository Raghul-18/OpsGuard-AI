import random
from datetime import datetime, timedelta

from connectors.base import BaseConnector, NormalizedOrder, NormalizedShipment, NormalizedSKU
from db.rates import (
    ALL_DEMO_PINCODES,
    billable_weight_kg,
    merged_slabs,
    slab_price_for,
    zone_for_pincode,
)

# These pincodes have deliberately high RTO rates
BAD_PINCODES = {"700001", "380001"}


class MockShiprocketConnector(BaseConnector):
    def __init__(self, merchant_id: str, credentials: dict):
        super().__init__(merchant_id, credentials)
        self._shipments = None

    def _courier_pool(self) -> list[str]:
        slabs = merged_slabs(self.merchant_id)
        names = sorted({s["courier_name"] for s in slabs if s.get("courier_name")})
        return names if names else ["Delhivery"]

    def _generate_mock_shipments(self, count: int = 200) -> list[dict]:
        random.seed(42)
        shipments = []
        now = datetime.utcnow()
        slabs = merged_slabs(self.merchant_id)
        couriers = sorted({s["courier_name"] for s in slabs if s.get("courier_name")}) or ["Delhivery"]

        for i in range(count):
            days_ago = random.randint(0, 30)
            created_at = now - timedelta(days=days_ago)

            pincode = random.choice(ALL_DEMO_PINCODES)
            courier = random.choice(couriers)
            is_cod = random.random() < 0.45

            if pincode in BAD_PINCODES and is_cod:
                rto = random.random() < 0.20
            else:
                rto = random.random() < 0.05

            declared_weight = round(random.choice([0.3, 0.5, 0.8, 1.0, 1.2, 1.5, 2.0, 2.5]), 2)
            zone = zone_for_pincode(pincode, courier, self.merchant_id, slabs=slabs)

            # ~30% disputes: carrier bills one 0.5 kg slab above the fair (nearest) slab for declared weight
            fair_slab = billable_weight_kg(declared_weight)
            if random.random() < 0.30:
                charged_weight = fair_slab + 0.5
            else:
                charged_weight = fair_slab

            base, _src = slab_price_for(
                self.merchant_id, courier, zone, charged_weight, slabs=slabs
            )
            shipping_cost = round(base + random.uniform(5, 25), 2)

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
                "zone": zone,
            }
            shipments.append(shipment)

        return shipments

    def _get_shipments(self) -> list[dict]:
        if self._shipments is None:
            self._shipments = self._generate_mock_shipments()
        return self._shipments

    def fetch_shipments(self, since: datetime) -> list[NormalizedShipment]:
        # Regenerate on each sync so weight/slab logic changes are picked up without API restart.
        self._shipments = None
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
