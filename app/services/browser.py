"""
Singleton Playwright browser manager.

Manages a single shared browser instance for the application lifetime.
Callers request a context (which is per-request), not a page directly,
so resources are always scoped and cleanable.
"""
from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from typing import AsyncIterator
from urllib.parse import unquote, urlsplit

from playwright.async_api import (
    Browser,
    BrowserContext,
    async_playwright,
    Playwright,
)

from app.config import get_settings

logger = logging.getLogger(__name__)

settings = get_settings()


class BrowserManager:
    """
    Lazy-initialises a single Chromium browser and hands out
    isolated BrowserContexts. A semaphore limits concurrency.
    """

    def __init__(self) -> None:
        self._playwright: Playwright | None = None
        self._browser: Browser | None = None
        self._lock: asyncio.Lock | None = None
        self._semaphore: asyncio.Semaphore | None = None

    def _get_lock(self) -> asyncio.Lock:
        if self._lock is None:
            self._lock = asyncio.Lock()
        return self._lock

    def _get_semaphore(self) -> asyncio.Semaphore:
        if self._semaphore is None:
            self._semaphore = asyncio.Semaphore(settings.playwright_max_concurrent)
        return self._semaphore

    async def _ensure_started(self) -> Browser:
        async with self._get_lock():
            if self._browser is None or not self._browser.is_connected():
                logger.info("Starting Playwright Chromium browser …")
                self._playwright = await async_playwright().start()
                launch_kwargs = {
                    "headless": settings.playwright_headless,
                    "slow_mo": settings.playwright_slow_mo,
                    "args": [
                        "--no-sandbox",
                        "--disable-dev-shm-usage",
                        "--disable-gpu",
                        "--disable-blink-features=AutomationControlled",
                    ],
                }
                try:
                    self._browser = await self._playwright.chromium.launch(**launch_kwargs)
                except Exception as exc:
                    logger.warning("Default Chromium launch failed (%s); trying system channels...", exc)
                    try:
                        self._browser = await self._playwright.chromium.launch(**launch_kwargs, channel="msedge")
                    except Exception:
                        self._browser = await self._playwright.chromium.launch(**launch_kwargs, channel="chrome")
                logger.info("Browser started successfully.")
        return self._browser

    @asynccontextmanager
    async def new_context(self) -> AsyncIterator[BrowserContext]:
        """
        Acquire a semaphore slot and yield a fresh BrowserContext.
        The context is always closed on exit.
        """
        async with self._get_semaphore():
            browser = await self._ensure_started()
            proxy = None
            if settings.proxy_url:
                parsed = urlsplit(settings.proxy_url)
                port = parsed.port or (443 if parsed.scheme == "https" else 80)
                proxy = {"server": f"{parsed.scheme}://{parsed.hostname}:{port}"}
                if parsed.username:
                    proxy["username"] = unquote(parsed.username)
                    proxy["password"] = unquote(parsed.password or "")
            context = await browser.new_context(
                proxy=proxy,
                user_agent=settings.user_agent,
                locale="en-IN",
                timezone_id="Asia/Kolkata",
                viewport={"width": 1280, "height": 800},
                java_script_enabled=True,
                extra_http_headers={
                    "Accept-Language": "en-IN,en;q=0.9",
                    "Accept": (
                        "text/html,application/xhtml+xml,application/xml;"
                        "q=0.9,image/avif,image/webp,*/*;q=0.8"
                    ),
                },
            )
            try:
                yield context
            finally:
                await context.close()

    async def close(self) -> None:
        if self._browser is None and self._playwright is None:
            return
        async with self._get_lock():
            if self._browser:
                try:
                    await self._browser.close()
                except Exception:
                    pass
                self._browser = None
            if self._playwright:
                try:
                    await self._playwright.stop()
                except Exception:
                    pass
                self._playwright = None
        logger.info("Browser stopped.")


# Module-level singleton
browser_manager = BrowserManager()
