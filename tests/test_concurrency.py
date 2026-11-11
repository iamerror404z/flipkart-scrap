"""Single requests and separate batches must share one complete scraping slot."""
import asyncio

import httpx
import pytest
from pydantic import ValidationError

from app.config import Settings
from app.main import app
from app.services import scraper


@pytest.mark.asyncio
async def test_single_and_batches_never_overlap_scraping(monkeypatch):
    active = 0
    peak = 0
    completed = 0
    html = '<script type="application/ld+json">{"@type":"Product","name":"Phone","offers":{"price":"100","availability":"InStock"}}</script>'

    async def fetch(url, result):
        nonlocal active, peak
        active += 1
        peak = max(peak, active)
        await asyncio.sleep(0)
        return html

    async def delivery(url, pin):
        nonlocal active, completed
        await asyncio.sleep(0)
        active -= 1
        completed += 1
        return {'status': 'NOT_DELIVERABLE', 'message': 'Not deliverable at your location'}

    monkeypatch.setattr(scraper, '_scrape_lock', asyncio.Lock())
    monkeypatch.setattr(scraper, '_fetch_html', fetch)
    monkeypatch.setattr(scraper, '_check_delivery_playwright', delivery)
    url = 'https://www.flipkart.com/phone/p/itm123'
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test') as client:
        responses = await asyncio.gather(
            client.post('/api/v1/products/check', json={'productUrl': url, 'pincode': '638003'}),
            client.post('/api/v1/products/batch-check', json={'products': [{'productUrl': url}] * 2, 'pincode': '638003'}),
            client.post('/api/v1/products/batch-check', json={'products': [{'productUrl': url}] * 2, 'pincode': '110001'}),
        )
    assert all(response.json()['success'] for response in responses)
    assert completed == 5
    assert peak == 1
    assert active == 0


@pytest.mark.parametrize('field', ['playwright_max_concurrent', 'batch_concurrency'])
def test_concurrency_cannot_exceed_one(field):
    with pytest.raises(ValidationError):
        Settings(_env_file=None, **{field: 2})
