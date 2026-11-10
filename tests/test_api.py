"""
API-level tests using FastAPI TestClient.

Unit tests mock the scraper service.
Integration tests (marked with @pytest.mark.integration) call the scraper
for real and are skipped by default unless --integration flag is passed.
"""
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from fastapi.testclient import TestClient

from app.main import app
from app.schemas.response import (
    AvailabilityInfo,
    DeliveryStatus,
    MetadataInfo,
    ProductInfo,
    StockStatus,
)
from app.services.scraper import ScraperResult


# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


def _make_success_result(
    stock: str = "IN_STOCK",
    delivery: str = "DELIVERABLE",
    delivery_msg: str = "Delivery by 15 Nov",
    estimated: str = "15 Nov",
) -> ScraperResult:
    r = ScraperResult()
    r.product = ProductInfo(
        name="Test Phone",
        price=24999.0,
        image="https://cdn.example.com/img.jpg",
        productId="TESTPID123",
    )
    r.availability = AvailabilityInfo(
        isStock=True,
        isDeliverable=True,
        stockStatus=StockStatus(stock),
        deliveryStatus=DeliveryStatus(delivery),
        deliveryMessage=delivery_msg,
        estimatedDelivery=estimated,
    )
    r.metadata = MetadataInfo()
    return r


def _make_error_result(code: str, message: str) -> ScraperResult:
    r = ScraperResult()
    r.error_code = code
    r.error_message = message
    return r


VALID_URL = "https://www.flipkart.com/test-phone/p/ITM123?pid=ITM123"
VALID_PIN = "638001"


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------

class TestHealthCheck:
    def test_health_ok(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "UP"
        assert data["service"] == "flipkart-scraper"


# ---------------------------------------------------------------------------
# Single product check – validation
# ---------------------------------------------------------------------------

class TestProductCheckValidation:
    def test_invalid_url_domain(self, client):
        resp = client.post(
            "/api/v1/products/check",
            json={"productUrl": "https://www.amazon.in/product", "pincode": "638001"},
        )
        assert resp.status_code == 422

    def test_invalid_pincode_letters(self, client):
        resp = client.post(
            "/api/v1/products/check",
            json={"productUrl": VALID_URL, "pincode": "ABCDEF"},
        )
        assert resp.status_code == 422

    def test_invalid_pincode_too_short(self, client):
        resp = client.post(
            "/api/v1/products/check",
            json={"productUrl": VALID_URL, "pincode": "12345"},
        )
        assert resp.status_code == 422

    def test_missing_fields(self, client):
        resp = client.post("/api/v1/products/check", json={})
        assert resp.status_code == 422

    def test_empty_url(self, client):
        resp = client.post(
            "/api/v1/products/check",
            json={"productUrl": "", "pincode": "638001"},
        )
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Single product check – mocked scraper
# ---------------------------------------------------------------------------

class TestProductCheckMocked:
    @patch("app.api.routes.scrape_product", new_callable=AsyncMock)
    def test_in_stock_deliverable(self, mock_scrape, client):
        mock_scrape.return_value = _make_success_result()
        resp = client.post(
            "/api/v1/products/check",
            json={"productUrl": VALID_URL, "pincode": VALID_PIN},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["availability"]["isStock"] is True
        assert data["availability"]["isDeliverable"] is True
        assert data["availability"]["stockStatus"] == "IN_STOCK"
        assert data["availability"]["deliveryStatus"] == "DELIVERABLE"
        assert data["product"]["name"] == "Test Phone"
        assert data["product"]["price"] == 24999.0
        assert data["metadata"]["source"] == "flipkart"

    @patch("app.api.routes.scrape_product", new_callable=AsyncMock)
    def test_out_of_stock(self, mock_scrape, client):
        r = _make_success_result(stock="OUT_OF_STOCK", delivery="UNKNOWN")
        r.availability.isStock = False
        r.availability.isDeliverable = None
        mock_scrape.return_value = r
        resp = client.post(
            "/api/v1/products/check",
            json={"productUrl": VALID_URL, "pincode": VALID_PIN},
        )
        data = resp.json()
        assert data["availability"]["isStock"] is False
        assert data["availability"]["stockStatus"] == "OUT_OF_STOCK"

    @patch("app.api.routes.scrape_product", new_callable=AsyncMock)
    def test_in_stock_not_deliverable(self, mock_scrape, client):
        r = _make_success_result(stock="IN_STOCK", delivery="NOT_DELIVERABLE")
        r.availability.isDeliverable = False
        mock_scrape.return_value = r
        resp = client.post(
            "/api/v1/products/check",
            json={"productUrl": VALID_URL, "pincode": VALID_PIN},
        )
        data = resp.json()
        assert data["availability"]["isStock"] is True
        assert data["availability"]["isDeliverable"] is False
        assert data["availability"]["deliveryStatus"] == "NOT_DELIVERABLE"

    @patch("app.api.routes.scrape_product", new_callable=AsyncMock)
    def test_unknown_availability(self, mock_scrape, client):
        r = ScraperResult()
        r.product = ProductInfo(name="Unknown Product")
        r.availability = AvailabilityInfo(
            isStock=None,
            isDeliverable=None,
            stockStatus=StockStatus.UNKNOWN,
            deliveryStatus=DeliveryStatus.UNKNOWN,
        )
        r.metadata = MetadataInfo()
        mock_scrape.return_value = r
        resp = client.post(
            "/api/v1/products/check",
            json={"productUrl": VALID_URL, "pincode": VALID_PIN},
        )
        data = resp.json()
        assert data["availability"]["isStock"] is None
        assert data["availability"]["isDeliverable"] is None
        assert data["availability"]["stockStatus"] == "UNKNOWN"
        assert data["availability"]["deliveryStatus"] == "UNKNOWN"

    @patch("app.api.routes.scrape_product", new_callable=AsyncMock)
    def test_product_not_found(self, mock_scrape, client):
        mock_scrape.return_value = _make_error_result(
            "PRODUCT_NOT_FOUND", "Product page was not found."
        )
        resp = client.post(
            "/api/v1/products/check",
            json={"productUrl": VALID_URL, "pincode": VALID_PIN},
        )
        data = resp.json()
        assert data["success"] is False
        assert data["error"]["code"] == "PRODUCT_NOT_FOUND"

    @patch("app.api.routes.scrape_product", new_callable=AsyncMock)
    def test_access_denied(self, mock_scrape, client):
        mock_scrape.return_value = _make_error_result(
            "ACCESS_DENIED", "HTTP 403."
        )
        resp = client.post(
            "/api/v1/products/check",
            json={"productUrl": VALID_URL, "pincode": VALID_PIN},
        )
        data = resp.json()
        assert data["success"] is False
        assert data["error"]["code"] == "ACCESS_DENIED"

    @patch("app.api.routes.scrape_product", new_callable=AsyncMock)
    def test_rate_limited(self, mock_scrape, client):
        mock_scrape.return_value = _make_error_result(
            "RATE_LIMITED", "HTTP 429."
        )
        resp = client.post(
            "/api/v1/products/check",
            json={"productUrl": VALID_URL, "pincode": VALID_PIN},
        )
        data = resp.json()
        assert data["success"] is False
        assert data["error"]["code"] == "RATE_LIMITED"

    @patch("app.api.routes.scrape_product", new_callable=AsyncMock)
    def test_timeout(self, mock_scrape, client):
        mock_scrape.return_value = _make_error_result("TIMEOUT", "Request timed out.")
        resp = client.post(
            "/api/v1/products/check",
            json={"productUrl": VALID_URL, "pincode": VALID_PIN},
        )
        data = resp.json()
        assert data["success"] is False
        assert data["error"]["code"] == "TIMEOUT"


# ---------------------------------------------------------------------------
# Batch check
# ---------------------------------------------------------------------------

class TestBatchCheck:
    @patch("app.api.routes.scrape_product", new_callable=AsyncMock)
    def test_batch_success(self, mock_scrape, client):
        mock_scrape.return_value = _make_success_result()
        resp = client.post(
            "/api/v1/products/batch-check",
            json={
                "pincode": VALID_PIN,
                "products": [
                    {"productUrl": VALID_URL},
                    {"productUrl": "https://www.flipkart.com/another/p/XYZ?pid=XYZ"},
                ],
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["totalProducts"] == 2
        assert len(data["results"]) == 2

    @patch("app.api.routes.scrape_product", new_callable=AsyncMock)
    def test_batch_mixed_results(self, mock_scrape, client):
        success = _make_success_result()
        failure = _make_error_result("PRODUCT_NOT_FOUND", "Not found")

        mock_scrape.side_effect = [success, failure]
        resp = client.post(
            "/api/v1/products/batch-check",
            json={
                "pincode": VALID_PIN,
                "products": [
                    {"productUrl": VALID_URL},
                    {"productUrl": "https://www.flipkart.com/another/p/XYZ?pid=XYZ"},
                ],
            },
        )
        data = resp.json()
        assert data["totalProducts"] == 2
        results = data["results"]
        assert results[0]["stockStatus"] == "IN_STOCK"
        assert results[1]["error"]["code"] == "PRODUCT_NOT_FOUND"

    def test_batch_invalid_pincode(self, client):
        resp = client.post(
            "/api/v1/products/batch-check",
            json={
                "pincode": "BADPIN",
                "products": [{"productUrl": VALID_URL}],
            },
        )
        assert resp.status_code == 422

    def test_batch_empty_products(self, client):
        resp = client.post(
            "/api/v1/products/batch-check",
            json={"pincode": VALID_PIN, "products": []},
        )
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Integration tests (skipped unless --integration CLI flag)
# ---------------------------------------------------------------------------

@pytest.fixture
def integration(request):
    if not request.config.getoption("--integration"):
        pytest.skip("Pass --integration to run integration tests.")


@pytest.mark.integration
def test_real_product_check(integration, client):
    """
    Integration test: performs a real scrape against Flipkart.
    Requires network access and a valid product URL.
    """
    resp = client.post(
        "/api/v1/products/check",
        json={
            "productUrl": "https://www.flipkart.com/apple-iphone-15/p/itmbf14ef54f645d",
            "pincode": "110001",
        },
        timeout=60,
    )
    data = resp.json()
    # We only assert structure, not specific values, as they may change.
    assert "success" in data
    if data["success"]:
        assert "availability" in data
        assert data["availability"]["stockStatus"] in ("IN_STOCK", "OUT_OF_STOCK", "UNKNOWN")
        assert data["availability"]["deliveryStatus"] in (
            "DELIVERABLE", "NOT_DELIVERABLE", "UNKNOWN"
        )
