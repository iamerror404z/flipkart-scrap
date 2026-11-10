"""
High-level availability determination logic.

Combines stock and delivery signals into structured AvailabilityInfo.
"""
from __future__ import annotations

import logging

from app.schemas.response import AvailabilityInfo, DeliveryStatus, StockStatus

logger = logging.getLogger(__name__)


def build_availability(
    stock_status: str,
    delivery_status: str,
    delivery_message: str | None = None,
    estimated_delivery: str | None = None,
) -> AvailabilityInfo:
    """
    Convert raw string statuses into a validated AvailabilityInfo object.

    Rules:
    - UNKNOWN is never coerced to False.
    - isStock is True only when status is IN_STOCK.
    - isDeliverable is True only when status is DELIVERABLE.
    - If stock is OUT_OF_STOCK the delivery status is irrelevant but
      we preserve whatever we extracted.
    """
    stock_enum = StockStatus(stock_status) if stock_status in StockStatus._value2member_map_ else StockStatus.UNKNOWN
    delivery_enum = DeliveryStatus(delivery_status) if delivery_status in DeliveryStatus._value2member_map_ else DeliveryStatus.UNKNOWN

    is_stock: bool | None
    if stock_enum == StockStatus.IN_STOCK:
        is_stock = True
    elif stock_enum == StockStatus.OUT_OF_STOCK:
        is_stock = False
    else:
        is_stock = None  # UNKNOWN → do not assume

    is_deliverable: bool | None
    if delivery_enum == DeliveryStatus.DELIVERABLE:
        is_deliverable = True
    elif delivery_enum == DeliveryStatus.NOT_DELIVERABLE:
        is_deliverable = False
    else:
        is_deliverable = None  # UNKNOWN → do not assume

    return AvailabilityInfo(
        isStock=is_stock,
        isDeliverable=is_deliverable,
        stockStatus=stock_enum,
        deliveryStatus=delivery_enum,
        deliveryMessage=delivery_message,
        estimatedDelivery=estimated_delivery,
    )
