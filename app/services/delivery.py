"""Apply a delivery PIN and read availability from the product's delivery section."""
from __future__ import annotations

import asyncio
import logging
import re
from urllib.parse import urlparse

from playwright.async_api import ElementHandle, Locator, Page, TimeoutError as PlaywrightTimeoutError

from app.config import get_settings
from app.services.browser import browser_manager
from app.utils.parser import extract_delivery_info

logger = logging.getLogger(__name__)

_PIN_SELECTOR = ", ".join(
    selector + ":visible:not([readonly]):not([disabled])"
    for selector in (
        "input[id*='pincode' i]",
        "input[placeholder*='pin' i]",
        "input[maxlength='6']",
    )
)
_LEGACY_DELIVERY_SELECTORS = (
    "div[class*='_3XINqE']",
    "div[class*='_2Tpdn3']",
    "div[class*='aw9Thp']",
    "span[class*='_2Tpdn3']",
)


def _unknown(message: str) -> dict:
    return {"status": "UNKNOWN", "message": message, "estimatedDate": None}


async def _delivery_section(page: Page) -> Locator | None:
    """Find a small delivery block without including exchange/bank offers."""
    heading = page.get_by_text("Delivery details", exact=True).first
    if await heading.count() and await heading.is_visible():
        section = heading
        for _ in range(4):
            section = section.locator("..")
            text = await section.inner_text()
            if len(text) > 2500 or re.search(r"exchange\s+offer|bank\s+offers", text, re.I):
                break
            if re.search(
                r"delivery\s+by|delivered\s+by|delivery\s+(?:is\s+)?not|"
                r"not\s+serviceable|not\s+deliverable|cannot\s+be\s+delivered|does\s+not\s+deliver|"
                r"location\s+not\s+set|select\s+delivery\s+location",
                text, re.I,
            ):
                return section

    for selector in _LEGACY_DELIVERY_SELECTORS:
        section = page.locator(selector + ":visible").first
        if await section.count():
            text = await section.inner_text()
            if len(text) < 2500 and not re.search(r"exchange\s+offer|bank\s+offers", text, re.I):
                return section
    return None


async def _open_pin_input(page: Page, timeout: int) -> Locator | None:
    pin = page.locator(_PIN_SELECTOR).first
    # The server-rendered location link may appear before its click handler is
    # hydrated. Retry only after waiting for the actual input to become visible.
    for _ in range(3):
        if await pin.count():
            return pin
        section = await _delivery_section(page)
        if section is None:
            await page.wait_for_timeout(min(500, timeout))
            continue
        entry = section.get_by_text(
            re.compile(r"^(?:Select|Change) delivery location$|^Change$", re.I)
        ).first
        if not await entry.count():
            return None
        try:
            await entry.click(timeout=min(2000, timeout))
        except PlaywrightTimeoutError:
            # A location sheet can open between attempts and intercept the
            # second click. Its input is still the desired next state.
            pass
        try:
            await pin.wait_for(state="visible", timeout=timeout)
            return pin
        except PlaywrightTimeoutError:
            continue
    return None


async def _select_search_location(page: Page, pin: Locator, pincode: str, timeout: int) -> bool:
    dialog = pin.locator(
        "xpath=ancestor::*[.//*[normalize-space(.)='Select delivery address']][1]"
    )
    if not await dialog.count():
        return False
    suggestion = dialog.get_by_text(re.compile(rf"\b{re.escape(pincode)}\b")).first
    navigation_timeout = get_settings().playwright_timeout
    deadline = asyncio.get_running_loop().time() + navigation_timeout / 1000
    # Search is loaded lazily. The first input events may precede its handlers,
    # or predictions may fail temporarily. Re-enter the PIN within one bounded
    # search budget instead of abandoning the request after the first wait.
    for attempt in range(3):
        remaining = int((deadline - asyncio.get_running_loop().time()) * 1000)
        if remaining <= 0:
            return False
        try:
            await suggestion.wait_for(
                state="visible", timeout=min(timeout, max(1, remaining // (3 - attempt)))
            )
            break
        except PlaywrightTimeoutError:
            if attempt == 2 or not await pin.count() or not await pin.is_visible():
                return False
            logger.info("Retrying the address search for PIN %s", pincode)
            await pin.fill("")
            await pin.type(pincode, delay=50)
    logger.info("Selecting the address search result for PIN %s", pincode)
    await suggestion.click(timeout=timeout)
    await pin.wait_for(state="hidden", timeout=timeout)

    deadline = asyncio.get_running_loop().time() + navigation_timeout / 1000
    # Closing the address sheet does not mean its asynchronous navigation has
    # finished. Wait for either the map or an acknowledged PIN on the product.
    while asyncio.get_running_loop().time() < deadline:
        if "address-map" in urlparse(page.url).path:
            await page.wait_for_load_state("domcontentloaded", timeout=navigation_timeout)
            return await _confirm_map_location(page, pincode, navigation_timeout)
        section = await _delivery_section(page)
        if section is not None and re.search(
            rf"\b{re.escape(pincode)}\b", await section.inner_text()
        ):
            return True
        await page.wait_for_timeout(min(250, timeout))
    return False


async def _confirm_map_location(page: Page, pincode: str, timeout: int) -> bool:
    """Wait for a usable map address, recovering through its own retry control."""
    deadline = asyncio.get_running_loop().time() + timeout / 1000
    pin_pattern = re.compile(rf"\b{re.escape(pincode)}\b")
    retries = 0
    while asyncio.get_running_loop().time() < deadline:
        remaining = max(1, int((deadline - asyncio.get_running_loop().time()) * 1000))
        map_text = await page.inner_text("body")
        retry = page.get_by_text("Try Again", exact=True).first
        if re.search(r"unable\s+to\s+pin\s+your\s+location", map_text, re.I):
            if retries >= 2:
                return False
            if await retry.count() and await retry.is_visible():
                logger.info("Retrying the map location for PIN %s", pincode)
                try:
                    await retry.click(timeout=min(1000, remaining))
                    retries += 1
                    try:
                        await retry.wait_for(state="hidden", timeout=min(1000, max(1, remaining // 3)))
                    except PlaywrightTimeoutError:
                        pass
                except PlaywrightTimeoutError:
                    pass
        else:
            confirm = page.get_by_text("Confirm", exact=True).last
            if await confirm.count() and await confirm.is_visible():
                # A result can resolve to a different PIN. Verify the current
                # map address on every attempt, including after a retry.
                if not pin_pattern.search(map_text):
                    # A Confirm skeleton can precede the resolved address.
                    # Reject an explicitly different PIN; otherwise keep waiting.
                    if re.search(r"\b[1-9]\d{5}\b", map_text):
                        return False
                else:
                    try:
                        # The map can replace this control or overlay it while
                        # reverse geocoding finishes. A short click attempt lets
                        # the loop observe the next state and any retry control.
                        await confirm.click(timeout=min(1000, remaining))
                    except PlaywrightTimeoutError:
                        pass
                    else:
                        logger.info("Confirming the map location for PIN %s", pincode)
                        await page.wait_for_url(
                            lambda url: "address-map" not in urlparse(url).path,
                            timeout=max(1, int((deadline - asyncio.get_running_loop().time()) * 1000)),
                        )
                        return True
        await page.wait_for_timeout(min(250, remaining))
    return False


async def _submit_inline_pin(pin: Locator, timeout: int) -> ElementHandle | None:
    # Look beside the PIN input, avoiding unrelated "Apply" bank-offer buttons.
    region = pin.locator("..")
    for _ in range(3):
        button = region.get_by_text(re.compile(r"^(Check|Apply)$", re.I)).first
        if await button.count():
            acknowledgement = await button.element_handle()
            await button.click(timeout=timeout)
            return acknowledgement
        region = region.locator("..")
    await pin.press("Enter")
    return None


async def _wait_delivery_result(
    page: Page, pincode: str, timeout: int, inline_pin: Locator | None = None,
    acknowledgement: ElementHandle | None = None, location_confirmed: bool = False,
) -> dict:
    deadline = asyncio.get_running_loop().time() + timeout / 1000
    pin_pattern = re.compile(rf"\b{re.escape(pincode)}\b")
    confirmed = False
    while asyncio.get_running_loop().time() < deadline:
        section = await _delivery_section(page)
        if section is not None:
            text = await section.inner_text()
            # Current pages show the street address without its PIN after map
            # confirmation. Preserve that prior verification in this context.
            confirmed = (location_confirmed or bool(pin_pattern.search(text))) and not re.search(
                r"location\s+not\s+set", text, re.I
            )
            if (
                not confirmed and inline_pin is not None and acknowledgement is not None
                and await inline_pin.count() and await acknowledgement.is_visible()
            ):
                # Legacy pages keep the PIN in an input and acknowledge a
                # successful check by replacing "Check" with "Change".
                confirmed = (
                    (await acknowledgement.inner_text()).strip().lower() == "change"
                    and await inline_pin.input_value() == pincode
                )
            if confirmed:
                result = extract_delivery_info(text)
                if result["status"] != "UNKNOWN":
                    return result
        await page.wait_for_timeout(min(250, timeout))
    if confirmed:
        return _unknown("The PIN was applied, but no delivery result could be read.")
    return _unknown(f"Could not confirm delivery for PIN {pincode}.")


async def check_delivery(url: str, pincode: str) -> dict:
    settings = get_settings()
    timeout = min(settings.playwright_timeout, 10000)
    logger.info("Checking delivery for PIN %s", pincode)
    try:
        async with browser_manager.new_context() as context:
            page = await context.new_page()
            page.set_default_timeout(timeout)
            await page.route(
                "**/*",
                lambda route: route.abort()
                if route.request.resource_type in ("image", "font", "media")
                else route.continue_(),
            )
            await page.goto(url, wait_until="domcontentloaded", timeout=settings.playwright_timeout)
            body = (await page.inner_text("body")).lower()
            if any(word in body for word in ("captcha", "verify you are human", "access denied")):
                return _unknown("CAPTCHA or bot-verification page encountered.")

            pin = await _open_pin_input(page, timeout)
            if pin is None:
                return _unknown(f"Could not locate the delivery PIN input for {pincode}.")
            is_search = bool(re.search(r"area|street", await pin.get_attribute("placeholder") or "", re.I))
            await pin.click(timeout=timeout)
            await pin.fill("")
            await pin.type(pincode, delay=50)

            if is_search:
                if not await _select_search_location(page, pin, pincode, timeout):
                    return _unknown(f"Could not select the delivery location for PIN {pincode}.")
                # Keep the confirmed location in the current SPA when the map
                # returns to this product. Navigate only if it returned elsewhere.
                if urlparse(page.url).path != urlparse(url).path:
                    await page.goto(url, wait_until="domcontentloaded", timeout=settings.playwright_timeout)
                return await _wait_delivery_result(
                    page, pincode, settings.playwright_timeout, location_confirmed=True
                )

            acknowledgement = await _submit_inline_pin(pin, timeout)
            return await _wait_delivery_result(
                page, pincode, timeout, inline_pin=pin, acknowledgement=acknowledgement
            )
    except (PlaywrightTimeoutError, asyncio.TimeoutError) as exc:
        logger.warning("Delivery check timed out for PIN %s: %s", pincode, exc)
        return _unknown(f"Timed out while confirming delivery for PIN {pincode}.")
    except Exception:
        logger.exception("Delivery check failed for PIN %s", pincode)
        return _unknown("Browser error while checking delivery.")
