"""Classify upstream failures consistently for HTTP and browser requests."""
import re

from bs4 import BeautifulSoup


def page_error(html: str, status: int = 200) -> tuple[str, str] | None:
    # Inspect visible content; CAPTCHA script names on valid pages are not challenges.
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style"]):
        tag.decompose()
    text = soup.get_text(" ", strip=True)
    if re.search(r"captcha|verify (?:that )?you are human|are you a robot", text, re.I):
        return "CAPTCHA", "Flipkart presented a CAPTCHA or human-verification page."
    if status in (403, 429) or re.search(
        r"access denied|request (?:has been |was )?blocked|too many requests", text, re.I
    ):
        return "BLOCKED", (
            f"Flipkart blocked the request (HTTP {status}). If this persists, configure "
            "FLIPKART_PROXY with an Indian residential/ISP proxy."
        )
    if status == 404:
        return "PRODUCT_NOT_FOUND", "The product page was not found (HTTP 404)."
    if status >= 400:
        return "HTTP_ERROR", f"HTTP {status} from Flipkart."
    return None
