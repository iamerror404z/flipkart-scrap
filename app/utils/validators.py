"""
Input validation utilities.
"""
from __future__ import annotations

import re
from urllib.parse import urlparse


_PINCODE_RE = re.compile(r"^\d{6}$")
_FLIPKART_HOSTS = {"www.flipkart.com", "flipkart.com"}


def validate_flipkart_url(url: str) -> str:
    """
    Validate that *url* is a well-formed Flipkart product URL.

    Raises ValueError with a user-friendly message on failure.
    """
    url = url.strip()
    if not url:
        raise ValueError("productUrl must not be empty.")

    try:
        parsed = urlparse(url)
    except Exception:
        raise ValueError(f"Malformed URL: {url!r}")

    if parsed.scheme not in ("http", "https"):
        raise ValueError(
            f"URL scheme must be http or https, got {parsed.scheme!r}."
        )

    host = parsed.netloc.lower().split(":")[0]  # strip port if present
    if host not in _FLIPKART_HOSTS:
        raise ValueError(
            f"URL host {host!r} is not supported. Only flipkart.com URLs are accepted."
        )

    if not parsed.path or parsed.path == "/":
        raise ValueError("URL does not appear to point to a product page.")

    return url


def validate_pincode(pincode: str) -> str:
    """
    Validate that *pincode* is a valid 6-digit Indian PIN code.

    Raises ValueError with a user-friendly message on failure.
    """
    pincode = pincode.strip()
    if not _PINCODE_RE.match(pincode):
        raise ValueError(
            f"PIN code must be exactly 6 digits, got {pincode!r}."
        )
    return pincode
