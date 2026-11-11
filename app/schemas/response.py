"""
Pydantic models for API responses.
"""
from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------

class StockStatus(str, Enum):
    IN_STOCK = "IN_STOCK"
    OUT_OF_STOCK = "OUT_OF_STOCK"
    UNKNOWN = "UNKNOWN"


class DeliveryStatus(str, Enum):
    DELIVERABLE = "DELIVERABLE"
    NOT_DELIVERABLE = "NOT_DELIVERABLE"
    UNKNOWN = "UNKNOWN"


# ---------------------------------------------------------------------------
# Sub-models
# ---------------------------------------------------------------------------

class ProductInfo(BaseModel):
    name: str | None = None
    price: float | None = None
    image: str | None = None
    productId: str | None = None


class AvailabilityInfo(BaseModel):
    isStock: bool | None = None
    isDeliverable: bool | None = None
    stockStatus: StockStatus = StockStatus.UNKNOWN
    deliveryStatus: DeliveryStatus = DeliveryStatus.UNKNOWN
    deliveryMessage: str | None = None
    estimatedDelivery: str | None = None


class MetadataInfo(BaseModel):
    source: str = "flipkart"
    checkedAt: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    )


class ErrorDetail(BaseModel):
    code: str
    message: str


# ---------------------------------------------------------------------------
# Top-level responses
# ---------------------------------------------------------------------------

class ProductCheckResponse(BaseModel):
    success: bool
    productUrl: str
    pincode: str
    product: ProductInfo | None = None
    availability: AvailabilityInfo | None = None
    metadata: MetadataInfo | None = None
    error: ErrorDetail | None = None


class BatchResultItem(BaseModel):
    productUrl: str
    product: ProductInfo | None = None
    isStock: bool | None = None
    isDeliverable: bool | None = None
    stockStatus: StockStatus = StockStatus.UNKNOWN
    deliveryStatus: DeliveryStatus = DeliveryStatus.UNKNOWN
    deliveryMessage: str | None = None
    estimatedDelivery: str | None = None
    error: ErrorDetail | None = None


class BatchCheckResponse(BaseModel):
    success: bool
    pincode: str
    totalProducts: int
    results: list[BatchResultItem]


class HealthResponse(BaseModel):
    status: str = "UP"
    service: str = "flipkart-scraper"
