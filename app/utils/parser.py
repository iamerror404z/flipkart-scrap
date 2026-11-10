"""
HTML / JSON-LD parsing helpers.

All Flipkart-specific parsing logic is isolated here so that
structural changes only require updates to this module.
"""
from __future__ import annotations

import json
import logging
import re
from typing import Any

from bs4 import BeautifulSoup, Tag

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# JSON-LD helpers
# ---------------------------------------------------------------------------

def extract_json_ld(soup: BeautifulSoup) -> list[dict[str, Any]]:
    """Return all JSON-LD objects found in the page."""
    results: list[dict] = []
    for tag in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(tag.string or "")
            if isinstance(data, list):
                results.extend(data)
            elif isinstance(data, dict):
                results.append(data)
        except json.JSONDecodeError:
            pass
    return results


def find_product_json_ld(json_ld_items: list[dict]) -> dict | None:
    """Find the first JSON-LD object whose @type is Product."""
    for item in json_ld_items:
        t = item.get("@type", "")
        types = t if isinstance(t, list) else [t]
        if any(x.lower() == "product" for x in types):
            return item
    return None


# ---------------------------------------------------------------------------
# Embedded __INITIAL_STATE__ / window.__STATE__ helpers
# ---------------------------------------------------------------------------

_STATE_RE = re.compile(
    r"window\.__(?:INITIAL_)?(?:STATE|DATA)__\s*=\s*(\{.+?\});?\s*</script",
    re.DOTALL,
)


def extract_window_state(html: str) -> dict | None:
    """
    Try to extract an embedded JS window state object.
    Returns the parsed dict or None.
    """
    m = _STATE_RE.search(html)
    if not m:
        return None
    try:
        return json.loads(m.group(1))
    except json.JSONDecodeError:
        return None


# ---------------------------------------------------------------------------
# Product info extraction
# ---------------------------------------------------------------------------

_PRICE_RE = re.compile(r"[\d,]+")


def _clean_price(raw: str | None) -> float | None:
    if not raw:
        return None
    m = _PRICE_RE.search(raw.replace(",", ""))
    if m:
        try:
            return float(m.group())
        except ValueError:
            pass
    return None


def extract_product_name(soup: BeautifulSoup) -> str | None:
    """Try multiple CSS selectors / meta tags to find the product name."""
    candidates = [
        soup.find("span", class_=re.compile(r"B_NuCI|VU-ZEz|title", re.I)),
        soup.find("h1"),
        soup.find("meta", property="og:title"),
        soup.find("title"),
    ]
    for c in candidates:
        if c is None:
            continue
        if isinstance(c, Tag):
            text = (
                c.get("content") or c.get_text(strip=True)  # type: ignore[arg-type]
            )
            if text:
                return str(text).strip()
    return None


def extract_product_price(soup: BeautifulSoup) -> float | None:
    """Try multiple strategies to find the product price."""
    # 1. Common Flipkart price selectors
    for selector in [
        {"class": re.compile(r"_30jeq3|Nx9bqj|_1vC4OE", re.I)},
        {"itemprop": "price"},
        {"class": re.compile(r"price", re.I)},
    ]:
        tag = soup.find(True, selector)
        if tag:
            text = tag.get("content") or tag.get_text(strip=True)
            price = _clean_price(str(text))
            if price is not None:
                return price

    # 2. meta
    meta = soup.find("meta", property="product:price:amount")
    if meta:
        price = _clean_price(str(meta.get("content", "")))
        if price is not None:
            return price

    return None


def extract_product_image(soup: BeautifulSoup) -> str | None:
    """Try multiple strategies to find the main product image."""
    # 1. og:image
    og = soup.find("meta", property="og:image")
    if og and og.get("content"):
        return str(og["content"])

    # 2. Common image selectors
    for selector in [
        {"class": re.compile(r"_396cs4|DByuf4|_2r_T1I", re.I)},
        {"class": re.compile(r"product.*image", re.I)},
    ]:
        tag = soup.find("img", selector)
        if tag and tag.get("src"):
            return str(tag["src"])

    return None


def extract_product_id(url: str) -> str | None:
    """
    Flipkart encodes the product ID in the URL as the value of the
    ``pid`` query param, or as the last path segment before ``/p/``.
    """
    # pid query param
    m = re.search(r"[?&]pid=([A-Za-z0-9]+)", url)
    if m:
        return m.group(1)

    # /p/<pid> path pattern
    m = re.search(r"/p/([A-Za-z0-9]+)", url)
    if m:
        return m.group(1)

    return None


# ---------------------------------------------------------------------------
# Availability extraction
# ---------------------------------------------------------------------------

_OOS_PATTERNS = [
    re.compile(r"sold\s*out", re.I),
    re.compile(r"out\s*of\s*stock", re.I),
    re.compile(r"currently\s*unavailable", re.I),
    re.compile(r"not\s*available", re.I),
    re.compile(r"notify\s*me", re.I),
]

_IN_STOCK_PATTERNS = [
    re.compile(r"add\s*to\s*cart", re.I),
    re.compile(r"buy\s*now", re.I),
    re.compile(r"in\s*stock", re.I),
]


def detect_stock_status_from_html(soup: BeautifulSoup) -> str:
    """
    Returns 'IN_STOCK', 'OUT_OF_STOCK', or 'UNKNOWN'
    based on HTML content heuristics.
    """
    page_text = soup.get_text(" ", strip=True)

    for pat in _OOS_PATTERNS:
        if pat.search(page_text):
            return "OUT_OF_STOCK"

    for pat in _IN_STOCK_PATTERNS:
        if pat.search(page_text):
            return "IN_STOCK"

    return "UNKNOWN"


def detect_stock_status_from_json_ld(product_ld: dict) -> str:
    """
    Returns 'IN_STOCK', 'OUT_OF_STOCK', or 'UNKNOWN'
    from a JSON-LD Product node.
    """
    offers = product_ld.get("offers") or product_ld.get("Offers")
    if not offers:
        return "UNKNOWN"

    if isinstance(offers, list):
        offers = offers[0]

    avail = str(offers.get("availability", "")).lower()
    if "instock" in avail:
        return "IN_STOCK"
    if "outofstock" in avail or "discontinued" in avail or "soldout" in avail:
        return "OUT_OF_STOCK"

    return "UNKNOWN"


# ---------------------------------------------------------------------------
# Delivery extraction from dynamic HTML snippets
# ---------------------------------------------------------------------------

_DELIVERY_POSITIVE = [
    re.compile(r"delivery\s+by", re.I),
    re.compile(r"delivered\s+by", re.I),
    re.compile(r"expected\s+delivery", re.I),
    re.compile(r"ships?\s+to", re.I),
]

_DELIVERY_NEGATIVE = [
    re.compile(r"not\s+serviceable", re.I),
    re.compile(r"does\s+not\s+deliver", re.I),
    re.compile(r"unavailable\s+in\s+your\s+area", re.I),
    re.compile(r"delivery\s+not\s+available", re.I),
    re.compile(r"pincode.*not.*serviceable", re.I),
    re.compile(r"not.*available.*pincode", re.I),
]

_DELIVERY_DATE_RE = re.compile(
    r"\b(\d{1,2}\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)(?:\s+\d{4})?)\b",
    re.I,
)


def extract_delivery_info(text: str) -> dict:
    """
    Given a text snippet (from dynamic DOM or Playwright page content),
    return a dict with keys:
        status       : 'DELIVERABLE' | 'NOT_DELIVERABLE' | 'UNKNOWN'
        message      : str | None
        estimatedDate: str | None
    """
    for pat in _DELIVERY_NEGATIVE:
        if pat.search(text):
            return {
                "status": "NOT_DELIVERABLE",
                "message": _first_matching_line(text, pat),
                "estimatedDate": None,
            }

    for pat in _DELIVERY_POSITIVE:
        if pat.search(text):
            date_match = _DELIVERY_DATE_RE.search(text)
            return {
                "status": "DELIVERABLE",
                "message": _first_matching_line(text, pat),
                "estimatedDate": date_match.group(1) if date_match else None,
            }

    return {"status": "UNKNOWN", "message": None, "estimatedDate": None}


def _first_matching_line(text: str, pat: re.Pattern) -> str | None:
    for line in text.splitlines():
        if pat.search(line):
            return line.strip() or None
    return None
