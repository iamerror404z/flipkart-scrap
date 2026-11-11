"""
FastAPI route definitions.
"""
from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, HTTPException, Request, status

from app.config import get_settings
from app.schemas.request import BatchCheckRequest, ProductCheckRequest
from app.schemas.response import (
    BatchCheckResponse,
    BatchResultItem,
    DeliveryStatus,
    ErrorDetail,
    HealthResponse,
    MetadataInfo,
    ProductCheckResponse,
    StockStatus,
)
from app.services.scraper import scrape_product

logger = logging.getLogger(__name__)
router = APIRouter()
settings = get_settings()


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------

@router.get("/health", response_model=HealthResponse, tags=["Health"])
async def health_check() -> HealthResponse:
    return HealthResponse()


# ---------------------------------------------------------------------------
# Single product check
# ---------------------------------------------------------------------------

@router.post(
    "/api/v1/products/check",
    response_model=ProductCheckResponse,
    tags=["Products"],
    summary="Check product availability and delivery for a PIN code",
)
async def check_product(body: ProductCheckRequest) -> ProductCheckResponse:
    result = await scrape_product(body.productUrl, body.pincode)

    if not result.success:
        # Map scraper error codes to HTTP status codes
        http_status = _error_to_http_status(result.error_code)
        return ProductCheckResponse(
            success=False,
            productUrl=body.productUrl,
            pincode=body.pincode,
            error=ErrorDetail(
                code=result.error_code or "SCRAPE_ERROR",
                message=result.error_message or "An unknown error occurred.",
            ),
        )

    return ProductCheckResponse(
        success=True,
        productUrl=body.productUrl,
        pincode=body.pincode,
        product=result.product,
        availability=result.availability,
        metadata=result.metadata,
    )


# ---------------------------------------------------------------------------
# Batch product check
# ---------------------------------------------------------------------------

@router.post(
    "/api/v1/products/batch-check",
    response_model=BatchCheckResponse,
    tags=["Products"],
    summary="Batch check availability for multiple products",
)
async def batch_check(body: BatchCheckRequest) -> BatchCheckResponse:
    semaphore = asyncio.Semaphore(settings.batch_concurrency)

    async def _check_one(product_url: str) -> BatchResultItem:
        async with semaphore:
            result = await scrape_product(product_url, body.pincode)
            if not result.success:
                return BatchResultItem(
                    productUrl=product_url,
                    stockStatus=StockStatus.UNKNOWN,
                    deliveryStatus=DeliveryStatus.UNKNOWN,
                    error=ErrorDetail(
                        code=result.error_code or "SCRAPE_ERROR",
                        message=result.error_message or "An unknown error occurred.",
                    ),
                )
            avail = result.availability
            return BatchResultItem(
                productUrl=product_url,
                product=result.product,
                isStock=avail.isStock,
                isDeliverable=avail.isDeliverable,
                stockStatus=avail.stockStatus,
                deliveryStatus=avail.deliveryStatus,
                deliveryMessage=avail.deliveryMessage,
                estimatedDelivery=avail.estimatedDelivery,
            )

    tasks = [_check_one(item.productUrl) for item in body.products]
    results = await asyncio.gather(*tasks)

    return BatchCheckResponse(
        success=all(item.error is None for item in results),
        pincode=body.pincode,
        totalProducts=len(results),
        results=list(results),
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _error_to_http_status(code: str | None) -> int:
    unprocessable = 422
    mapping = {
        "INVALID_URL": unprocessable,
        "INVALID_PINCODE": unprocessable,
        "PRODUCT_NOT_FOUND": status.HTTP_404_NOT_FOUND,
        "ACCESS_DENIED": status.HTTP_403_FORBIDDEN,
        "RATE_LIMITED": status.HTTP_429_TOO_MANY_REQUESTS,
        "TIMEOUT": status.HTTP_504_GATEWAY_TIMEOUT,
        "CAPTCHA": status.HTTP_503_SERVICE_UNAVAILABLE,
    }
    return mapping.get(code or "", status.HTTP_200_OK)
