from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional


@dataclass
class NormalizedOrder:
    merchant_id: str
    order_ref: str
    sku_id: str
    quantity: int
    unit_price_inr: float
    payment_method: str  # prepaid / COD
    destination_pincode: str
    ordered_at: datetime
    source: str
    source_record_id: str
    ingested_at: datetime = field(default_factory=datetime.utcnow)
    raw_metadata: dict = field(default_factory=dict)


@dataclass
class NormalizedShipment:
    merchant_id: str
    shipment_ref: str
    order_ref: str
    courier_name: str
    weight_declared_kg: float
    weight_charged_kg: float
    shipping_cost_inr: float
    status: str
    rto: bool
    destination_pincode: str
    source: str
    source_record_id: str
    ingested_at: datetime = field(default_factory=datetime.utcnow)
    raw_metadata: dict = field(default_factory=dict)


@dataclass
class NormalizedSKU:
    merchant_id: str
    sku_id: str
    name: str
    cost_price_inr: float
    packaging_weight_g: float
    reorder_level: int
    category: Optional[str]
    source: str
    source_record_id: str
    ingested_at: datetime = field(default_factory=datetime.utcnow)
    raw_metadata: dict = field(default_factory=dict)


class ConnectorConfigError(Exception):
    pass


class BaseConnector(ABC):
    def __init__(self, merchant_id: str, credentials: dict):
        self.merchant_id = merchant_id
        self.credentials = credentials

    @abstractmethod
    def fetch_orders(self, since: datetime) -> list[NormalizedOrder]:
        pass

    @abstractmethod
    def fetch_shipments(self, since: datetime) -> list[NormalizedShipment]:
        pass

    @abstractmethod
    def fetch_sku_master(self) -> list[NormalizedSKU]:
        pass

    @abstractmethod
    def test_connection(self) -> bool:
        pass

    @abstractmethod
    def get_source_name(self) -> str:
        pass
