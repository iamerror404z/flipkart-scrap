"""
Flipkart scraper service.

Strategy:
  1. Attempt HTTP-only fetch with httpx + BeautifulSoup.
  2. Parse product details and stock from JSON-LD or HTML purchase signals.
  3. PIN code delivery check is always done via Playwright because it
     requires DOM interaction (filling the PIN input and reading dynamic result).
"""
from __future__ import annotations

import asyncio
import logging

import httpx
from bs4 import BeautifulSoup

from app.config import get_settings
from app.schemas.response import (
    AvailabilityInfo,
    MetadataInfo,
    ProductInfo,
)
from app.services.availability import build_availability
from app.services.delivery import check_delivery as _check_delivery_playwright
from app.utils.parser import (
    detect_stock_status_from_html,
    detect_stock_status_from_json_ld,
    extract_json_ld,
    extract_product_id,
    extract_product_image,
    extract_product_name,
    extract_product_price,
    find_product_json_ld,
)

logger = logging.getLogger(__name__)
settings = get_settings()

# ---------------------------------------------------------------------------
# Common HTTP headers to reduce bot-detection false positives
# ---------------------------------------------------------------------------
_HEADERS = {
    "User-Agent": settings.user_agent,
    "Accept-Language": "en-IN,en;q=0.9",
    "Accept": (
        "text/html,application/xhtml+xml,application/xml;"
        "q=0.9,image/avif,image/webp,*/*;q=0.8"
    ),
    "Referer": "https://www.flipkart.com/",
    "DNT": "1",
}


# ---------------------------------------------------------------------------
# Result container
# ---------------------------------------------------------------------------

class ScraperResult:
    def __init__(self) -> None:
        self.product: ProductInfo = ProductInfo()
        self.availability: AvailabilityInfo = AvailabilityInfo()
        self.metadata: MetadataInfo = MetadataInfo()
        self.error_code: str | None = None
        self.error_message: str | None = None

    @property
    def success(self) -> bool:
        return self.error_code is None


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

async def scrape_product(product_url: str, pincode: str) -> ScraperResult:
    """
    Main entry point.  Returns a ScraperResult regardless of outcome.
    Never raises; errors are encoded in ScraperResult.
    """
    result = ScraperResult()

    try:
        html = await _fetch_html(product_url, result)
        if html is None:
            return result  # error already set

        soup = BeautifulSoup(html, "html.parser")
        _extract_product_info(soup, html, product_url, result)

        stock_status = _determine_stock_status(soup, html, result)

        # Always use Playwright for PIN-code delivery check
        delivery = await _check_delivery_playwright(product_url, pincode)

        result.availability = build_availability(
            stock_status=stock_status,
            delivery_status=delivery["status"],
            delivery_message=delivery.get("message"),
            estimated_delivery=delivery.get("estimatedDate"),
        )

    except asyncio.TimeoutError:
        result.error_code = "TIMEOUT"
        result.error_message = "Request timed out while fetching the product page."
    except Exception as exc:
        logger.exception("Unexpected error scraping %s", product_url)
        result.error_code = "SCRAPE_ERROR"
        result.error_message = f"An unexpected error occurred: {exc}"

    return result


# ---------------------------------------------------------------------------
# HTTP fetch
# ---------------------------------------------------------------------------

async def _fetch_html(url: str, result: ScraperResult) -> str | None:
    """
    Attempt to fetch the product page using httpx.
    Sets result error fields and returns None on failure.
    """
    try:
        async with httpx.AsyncClient(
            headers=_HEADERS,
            follow_redirects=True,
            max_redirects=settings.httpx_max_redirects,
            timeout=settings.httpx_timeout,
        ) as client:
            response = await client.get(url)

            if response.status_code == 403:
                result.error_code = "ACCESS_DENIED"
                result.error_message = (
                    "Flipkart returned HTTP 403 (Forbidden). "
                    "The request may have been blocked."
                )
                return None

            if response.status_code == 429:
                result.error_code = "RATE_LIMITED"
                result.error_message = (
                    "Flipkart returned HTTP 429 (Too Many Requests). "
                    "Please retry after a short delay."
                )
                return None

            if response.status_code == 404:
                result.error_code = "PRODUCT_NOT_FOUND"
                result.error_message = "The product page was not found (HTTP 404)."
                return None

            response.raise_for_status()
            return response.text

    except httpx.TimeoutException:
        result.error_code = "TIMEOUT"
        result.error_message = "HTTP request timed out."
        return None
    except httpx.HTTPStatusError as exc:
        result.error_code = "HTTP_ERROR"
        result.error_message = f"HTTP {exc.response.status_code} from Flipkart."
        return None
    except httpx.RequestError as exc:
        result.error_code = "NETWORK_ERROR"
        result.error_message = f"Network error: {exc}"
        return None


# ---------------------------------------------------------------------------
# Product information extraction
# ---------------------------------------------------------------------------

def _extract_product_info(
    soup: BeautifulSoup,
    html: str,
    url: str,
    result: ScraperResult,
) -> None:
    """Populate result.product with available information."""
    json_ld_items = extract_json_ld(soup)
    product_ld = find_product_json_ld(json_ld_items)

    name: str | None = None
    price: float | None = None
    image: str | None = None

    if product_ld:
        name = product_ld.get("name")
        raw_image = product_ld.get("image")
        if isinstance(raw_image, list) and raw_image:
            image = str(raw_image[0])
        elif isinstance(raw_image, str):
            image = raw_image
        offers = product_ld.get("offers") or {}
        if isinstance(offers, list):
            offers = offers[0]
        price_raw = offers.get("price") or offers.get("lowPrice")
        if price_raw is not None:
            try:
                price = float(str(price_raw).replace(",", ""))
            except ValueError:
                pass

    # Fallback to HTML extraction
    if not name:
        name = extract_product_name(soup)
    if price is None:
        price = extract_product_price(soup)
    if not image:
        image = extract_product_image(soup)

    result.product = ProductInfo(
        name=name,
        price=price,
        image=image,
        productId=extract_product_id(url),
    )


# ---------------------------------------------------------------------------
# Stock status determination
# ---------------------------------------------------------------------------

def _determine_stock_status(
    soup: BeautifulSoup,
    html: str,
    result: ScraperResult,
) -> str:
    """
    Returns 'IN_STOCK', 'OUT_OF_STOCK', or 'UNKNOWN'.
    Checks JSON-LD first, then HTML heuristics.
    """
    json_ld_items = extract_json_ld(soup)
    product_ld = find_product_json_ld(json_ld_items)

    if product_ld:
        status = detect_stock_status_from_json_ld(product_ld)
        if status != "UNKNOWN":
            logger.debug("Stock status from JSON-LD: %s", status)
            return status

    status = detect_stock_status_from_html(soup)
    logger.debug("Stock status from HTML heuristics: %s", status)
    return status
