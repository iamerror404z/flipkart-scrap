"""
Unit tests for parser and validator utilities.
All tests use mocked HTML — no network access required.
"""
from __future__ import annotations

import pytest
from bs4 import BeautifulSoup

from app.utils.validators import validate_flipkart_url, validate_pincode
from app.utils.parser import (
    detect_stock_status_from_html,
    detect_stock_status_from_json_ld,
    extract_delivery_info,
    extract_json_ld,
    extract_product_id,
    extract_product_image,
    extract_product_name,
    extract_product_price,
    find_product_json_ld,
)


# ---------------------------------------------------------------------------
# Validator tests
# ---------------------------------------------------------------------------

class TestValidateFlipkartUrl:
    def test_valid_url(self):
        url = "https://www.flipkart.com/some-product/p/ABCD1234?pid=ABCD1234"
        assert validate_flipkart_url(url) == url

    def test_invalid_scheme(self):
        with pytest.raises(ValueError, match="scheme"):
            validate_flipkart_url("ftp://www.flipkart.com/product")

    def test_wrong_domain(self):
        with pytest.raises(ValueError, match="not supported"):
            validate_flipkart_url("https://www.amazon.in/product")

    def test_empty_path(self):
        with pytest.raises(ValueError, match="product page"):
            validate_flipkart_url("https://www.flipkart.com/")

    def test_empty_string(self):
        with pytest.raises(ValueError, match="empty"):
            validate_flipkart_url("")

    def test_http_allowed(self):
        url = "http://www.flipkart.com/some/product"
        assert validate_flipkart_url(url) == url

    def test_bare_flipkart_domain(self):
        url = "https://flipkart.com/some/product"
        assert validate_flipkart_url(url) == url


class TestValidatePincode:
    def test_valid_pincode(self):
        assert validate_pincode("638001") == "638001"

    def test_too_short(self):
        with pytest.raises(ValueError):
            validate_pincode("12345")

    def test_too_long(self):
        with pytest.raises(ValueError):
            validate_pincode("1234567")

    def test_non_numeric(self):
        with pytest.raises(ValueError):
            validate_pincode("ABCDEF")

    def test_whitespace_stripped(self):
        assert validate_pincode("  638001  ") == "638001"


# ---------------------------------------------------------------------------
# JSON-LD extraction tests
# ---------------------------------------------------------------------------

_JSON_LD_HTML = """
<html><head>
<script type="application/ld+json">
{
  "@context": "https://schema.org/",
  "@type": "Product",
  "name": "Test Phone",
  "image": "https://example.com/img.jpg",
  "offers": {
    "@type": "Offer",
    "price": "24999",
    "availability": "https://schema.org/InStock"
  }
}
</script>
</head><body></body></html>
"""


class TestJsonLd:
    def setup_method(self):
        self.soup = BeautifulSoup(_JSON_LD_HTML, "html.parser")

    def test_extract_json_ld(self):
        items = extract_json_ld(self.soup)
        assert len(items) == 1
        assert items[0]["@type"] == "Product"

    def test_find_product_json_ld(self):
        items = extract_json_ld(self.soup)
        product = find_product_json_ld(items)
        assert product is not None
        assert product["name"] == "Test Phone"

    def test_no_json_ld(self):
        soup = BeautifulSoup("<html><body></body></html>", "html.parser")
        assert extract_json_ld(soup) == []
        assert find_product_json_ld([]) is None


# ---------------------------------------------------------------------------
# Product info extraction tests
# ---------------------------------------------------------------------------

_PRODUCT_HTML = """
<html>
<head>
  <meta property="og:title" content="Sample Laptop" />
  <meta property="og:image" content="https://cdn.flipkart.com/laptop.jpg" />
</head>
<body>
  <div class="_30jeq3 _16Jk6d">₹49,999</div>
</body>
</html>
"""


class TestProductExtraction:
    def setup_method(self):
        self.soup = BeautifulSoup(_PRODUCT_HTML, "html.parser")

    def test_extract_name(self):
        name = extract_product_name(self.soup)
        assert name == "Sample Laptop"

    def test_extract_image(self):
        img = extract_product_image(self.soup)
        assert img == "https://cdn.flipkart.com/laptop.jpg"

    def test_extract_price(self):
        price = extract_product_price(self.soup)
        assert price == 49999.0

    def test_extract_product_id_from_url(self):
        url = "https://www.flipkart.com/phone/p/ITMABC123?pid=ITMABC123"
        assert extract_product_id(url) == "ITMABC123"

    def test_extract_product_id_no_pid(self):
        url = "https://www.flipkart.com/phone/p/ITMABC123"
        assert extract_product_id(url) == "ITMABC123"

    def test_no_price_returns_none(self):
        soup = BeautifulSoup("<html><body><p>No price here</p></body></html>", "html.parser")
        assert extract_product_price(soup) is None


# ---------------------------------------------------------------------------
# Stock status tests
# ---------------------------------------------------------------------------

class TestStockStatus:
    def test_in_stock_from_html(self):
        soup = BeautifulSoup(
            "<html><body><button>Add to Cart</button></body></html>", "html.parser"
        )
        assert detect_stock_status_from_html(soup) == "IN_STOCK"

    def test_out_of_stock_from_html(self):
        soup = BeautifulSoup(
            "<html><body><div>Sold Out</div></body></html>", "html.parser"
        )
        assert detect_stock_status_from_html(soup) == "OUT_OF_STOCK"

    def test_currently_unavailable(self):
        soup = BeautifulSoup(
            "<html><body><div>Currently Unavailable</div></body></html>", "html.parser"
        )
        assert detect_stock_status_from_html(soup) == "OUT_OF_STOCK"

    def test_unknown_stock(self):
        soup = BeautifulSoup(
            "<html><body><p>Some random text</p></body></html>", "html.parser"
        )
        assert detect_stock_status_from_html(soup) == "UNKNOWN"

    def test_in_stock_from_json_ld(self):
        ld = {"offers": {"availability": "https://schema.org/InStock"}}
        assert detect_stock_status_from_json_ld(ld) == "IN_STOCK"

    def test_out_of_stock_from_json_ld(self):
        ld = {"offers": {"availability": "https://schema.org/OutOfStock"}}
        assert detect_stock_status_from_json_ld(ld) == "OUT_OF_STOCK"

    def test_no_offers_in_json_ld(self):
        assert detect_stock_status_from_json_ld({}) == "UNKNOWN"


# ---------------------------------------------------------------------------
# Delivery info extraction tests
# ---------------------------------------------------------------------------

class TestDeliveryInfo:
    def test_deliverable(self):
        text = "Delivery by 15 Nov, Thursday"
        result = extract_delivery_info(text)
        assert result["status"] == "DELIVERABLE"
        assert result["estimatedDate"] == "15 Nov"

    def test_not_deliverable(self):
        text = "Not Serviceable. This pincode is not serviceable."
        result = extract_delivery_info(text)
        assert result["status"] == "NOT_DELIVERABLE"

    def test_not_deliverable_phrase(self):
        text = "Delivery not available for this location."
        result = extract_delivery_info(text)
        assert result["status"] == "NOT_DELIVERABLE"

    def test_unknown_delivery(self):
        text = "Some unrelated product description text."
        result = extract_delivery_info(text)
        assert result["status"] == "UNKNOWN"

    def test_delivered_by(self):
        text = "Delivered by 20 Nov"
        result = extract_delivery_info(text)
        assert result["status"] == "DELIVERABLE"
        assert result["estimatedDate"] == "20 Nov"
