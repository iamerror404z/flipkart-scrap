"""Upstream errors must not become fabricated product availability."""
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from app.services import scraper
from app.services.upstream import page_error


@pytest.mark.parametrize('html,status,expected', [
    ('<h1>Access Denied</h1>', 200, 'BLOCKED'),
    ('<h1>Forbidden</h1>', 403, 'BLOCKED'),
    ('Too many requests', 429, 'BLOCKED'),
    ('<h1>Verify you are human</h1>', 200, 'CAPTCHA'),
    ('<h1>CAPTCHA</h1>', 403, 'CAPTCHA'),
    ('<script src="captcha.js"></script><h1>Phone</h1>', 200, None),
])
def test_page_error(html, status, expected):
    error = page_error(html, status)
    assert (error[0] if error else None) == expected


@pytest.mark.asyncio
async def test_timeout_retries_then_recovers(monkeypatch):
    monkeypatch.setattr(scraper.settings, 'httpx_retry_backoff', 0)
    response = httpx.Response(200, text='<h1>Phone</h1>')
    get = AsyncMock(side_effect=[httpx.ReadTimeout('slow'), response])
    with patch.object(httpx.AsyncClient, 'get', get):
        result = scraper.ScraperResult()
        assert await scraper._fetch_html('https://www.flipkart.com/', result) == '<h1>Phone</h1>'
    assert result.success
    assert get.call_count == 2


@pytest.mark.asyncio
async def test_blocked_is_not_retried():
    get = AsyncMock(return_value=httpx.Response(403, text='Access Denied'))
    with patch.object(httpx.AsyncClient, 'get', get):
        result = scraper.ScraperResult()
        assert await scraper._fetch_html('https://www.flipkart.com/', result) is None
    assert result.error_code == 'BLOCKED'
    assert get.call_count == 1
