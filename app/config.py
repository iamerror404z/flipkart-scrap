"""
Application configuration loaded from environment variables.
"""
from __future__ import annotations

import os
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Service
    service_name: str = "flipkart-scraper"
    debug: bool = False

    # HTTP scraping
    httpx_timeout: float = 20.0
    httpx_max_redirects: int = 5
    user_agent: str = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    )

    # Playwright
    playwright_timeout: int = 30_000          # milliseconds
    playwright_headless: bool = True
    playwright_max_concurrent: int = 3        # max simultaneous browser contexts
    playwright_slow_mo: int = 0               # ms between actions (0 = disabled)

    # Batch
    batch_max_products: int = 20
    batch_concurrency: int = 5                # asyncio semaphore for batch

    # Rate limiting (simple in-process token bucket)
    rate_limit_requests: int = 10             # requests per window
    rate_limit_window: int = 60              # seconds


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
