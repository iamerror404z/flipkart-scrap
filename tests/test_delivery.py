"""Exercise the PIN workflow in Chromium against local pages, without Flipkart."""
from contextlib import asynccontextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from threading import Thread

import pytest
import pytest_asyncio
from playwright.async_api import async_playwright

from app.services import delivery


@pytest_asyncio.fixture
async def browser_context(monkeypatch):
    async with async_playwright() as playwright:
        try:
            browser = await playwright.chromium.launch(headless=True)
        except Exception as exc:
            if "Executable doesn't exist" in str(exc):
                pytest.skip("Install Playwright Chromium to run browser regression tests.")
            raise
        context = await browser.new_context()

        @asynccontextmanager
        async def new_context():
            yield context

        monkeypatch.setattr(delivery.browser_manager, "new_context", new_context)
        monkeypatch.setattr(delivery.get_settings(), "playwright_timeout", 1200)
        yield context
        await context.close()
        await browser.close()


def product_page(tmp_path, contents):
    path = tmp_path / "product.html"
    path.write_text(
        "<html><body><aside>Exchange offer: Not available at this Pincode"
        "<button>Apply</button></aside><section><h2>Delivery details</h2>"
        + contents + "</section></body></html>", encoding="utf-8"
    )
    return path.as_uri()


@pytest.mark.asyncio
async def test_missing_pin_input_does_not_infer_delivery(browser_context, tmp_path):
    url = product_page(tmp_path, "<div>Delivery by 13 Nov</div>")
    result = await delivery.check_delivery(url, "638003")
    assert result["status"] == "UNKNOWN"
    assert "PIN input" in result["message"]


@pytest.mark.asyncio
@pytest.mark.parametrize("message,expected", [
    ("Delivery by 15 Nov", "DELIVERABLE"),
    ("Delivery not available for this location", "NOT_DELIVERABLE"),
    ("Not deliverable at your location", "NOT_DELIVERABLE"),
])
async def test_inline_pin_reads_only_delivery_block(browser_context, tmp_path, message, expected):
    url = product_page(tmp_path, """
        <div><input id="pincodeInputId"><button onclick="
            document.getElementById('result').textContent = window.deliveryMessage;
            this.textContent = 'Change';">Check</button></div>
        <div id="result">Delivery by 13 Nov</div>
        <script>window.deliveryMessage = MESSAGE;</script>
    """.replace("MESSAGE", json.dumps(message)))
    result = await delivery.check_delivery(url, "638003")
    assert result["status"] == expected
    assert result["message"] == message


@pytest.mark.asyncio
async def test_no_op_pin_check_cannot_use_stale_delivery(browser_context, tmp_path):
    url = product_page(tmp_path, """
        <div><input id="pincodeInputId"><button>Check</button><span>Change</span></div>
        <div>Delivery by 13 Nov</div>
    """)
    result = await delivery.check_delivery(url, "638003")
    assert result["status"] == "UNKNOWN"


@pytest.mark.asyncio
@pytest.mark.parametrize("suggested_pin,expected", [("638003", "DELIVERABLE"), ("638004", "UNKNOWN")])
async def test_address_search_selects_exact_pin(browser_context, tmp_path, suggested_pin, expected):
    url = product_page(tmp_path, """
        <div id="location">Location not set</div>
        <button id="chooseLocation" onclick="document.getElementById('dialog').hidden = false;">Select delivery location</button>
        <div>Delivery by Friday, 13 Nov</div>
        <div id="dialog" hidden>
            <h2>Select delivery address</h2>
            <input placeholder="Search by area, street name, pin code" oninput="
                document.getElementById('suggestion').hidden = this.value.length !== 6;">
            <div id="suggestion" hidden onclick="
                sessionStorage.setItem('selectedPin', 'SUGGESTED_PIN');
                document.getElementById('location').textContent = 'Erode SUGGESTED_PIN';
                document.getElementById('chooseLocation').textContent = 'Change';
                document.getElementById('dialog').hidden = true;">
                <div>Erode</div><div>Tamil Nadu SUGGESTED_PIN India</div>
            </div>
        </div>
        <script>
            const pin = sessionStorage.getItem('selectedPin');
            if (pin) {
                document.getElementById('location').textContent = 'Erode ' + pin;
                document.getElementById('chooseLocation').textContent = 'Change';
            }
        </script>
    """.replace("SUGGESTED_PIN", suggested_pin))
    result = await delivery.check_delivery(url, "638003")
    assert result["status"] == expected
    if expected == "DELIVERABLE":
        assert result["estimatedDate"] == "13 Nov"
        assert result["message"] == "Delivery by Friday, 13 Nov"


@pytest.mark.asyncio
@pytest.mark.parametrize("map_pin,expected", [("638003", "DELIVERABLE"), ("638004", "UNKNOWN")])
async def test_map_location_must_be_confirmed_for_requested_pin(browser_context, tmp_path, map_pin, expected):
    map_dir = tmp_path / "address-map"
    map_dir.mkdir()
    map_page = map_dir / "map.html"
    url = product_page(tmp_path, """
        <div id="location">Location not set</div>
        <button id="chooseLocation" onclick="document.getElementById('dialog').hidden = false;">Select delivery location</button>
        <div>Delivery by 15 Nov</div>
        <div id="dialog" hidden><h2>Select delivery address</h2>
            <input placeholder="Search by area, street name, pin code" oninput="
                document.getElementById('suggestion').hidden = this.value.length !== 6;">
            <div id="suggestion" hidden onclick="
                document.getElementById('dialog').hidden = true;
                setTimeout(() => { window.location.href = window.mapUri; }, 100);">
                Tamil Nadu 638003 India
            </div>
        </div>
        <script>
            window.mapUri = MAP_URI;
            if (sessionStorage.getItem('confirmedPin')) {
                document.getElementById('location').textContent = 'Erode, Tamil Nadu';
                document.getElementById('chooseLocation').textContent = 'Change';
            }
        </script>
    """.replace("MAP_URI", json.dumps(map_page.as_uri())))
    map_page.write_text("""
        <html><body><h2>Set Delivery location</h2><div>Erode MAP_PIN</div>
        <button onclick="sessionStorage.setItem('confirmedPin', 'MAP_PIN'); window.location.href = window.productUri;">Confirm</button>
        <script>window.productUri = PRODUCT_URI;</script></body></html>
    """.replace("MAP_PIN", map_pin).replace("PRODUCT_URI", json.dumps(url)), encoding="utf-8")
    result = await delivery.check_delivery(url, "638003")
    assert result["status"] == expected


@pytest.mark.asyncio
async def test_confirmed_spa_location_is_preserved_without_reload(browser_context):
    html = b"""
        <html><body><section id="product"><h2>Delivery details</h2>
        <div id="label">Location not set</div>
        <button id="chooseLocation" onclick="document.getElementById('dialog').hidden = false;">Select delivery location</button>
        <div id="date">Delivery by 13 Nov</div>
        <div id="dialog" hidden><h2>Select delivery address</h2>
            <input placeholder="Search by area, street name, pin code" oninput="
                document.getElementById('suggestion').hidden = this.value.length !== 6;">
            <div id="suggestion" hidden onclick="
                document.getElementById('product').hidden = true;
                document.getElementById('dialog').hidden = true;
                document.getElementById('map').hidden = false;
                history.pushState(null, '', '/address-map/');">Tamil Nadu 638003 India</div>
        </div></section>
        <div id="map" hidden><h2>Set Delivery location</h2><div>Erode 638003</div>
        <button onclick="
            document.getElementById('map').hidden = true;
            document.getElementById('product').hidden = false;
            document.getElementById('label').textContent = 'Erode, Tamil Nadu';
            document.getElementById('chooseLocation').textContent = 'Change';
            document.getElementById('date').textContent = 'Delivery by 15 Nov';
            history.replaceState(null, '', '/product');">Confirm</button></div>
        </body></html>
    """

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(html)

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        result = await delivery.check_delivery(f"http://127.0.0.1:{server.server_port}/product", "638003")
        assert result["status"] == "DELIVERABLE"
        assert result["estimatedDate"] == "15 Nov"
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


@pytest.mark.asyncio
async def test_address_search_recovers_when_initial_input_has_no_predictions(browser_context, tmp_path):
    url = product_page(tmp_path, """
        <div id="location">Location not set</div>
        <button onclick="document.getElementById('dialog').hidden = false;">Select delivery location</button>
        <div>Delivery by 15 Nov</div>
        <div id="dialog" hidden><h2>Select delivery address</h2>
            <input placeholder="Search by area, street name, pin code" oninput="
                if (this.value === '638003') {
                    window.searches++;
                    document.getElementById('suggestion').hidden = window.searches < 2;
                }">
            <div id="suggestion" hidden onclick="
                document.getElementById('location').textContent = 'Erode 638003';
                document.getElementById('dialog').hidden = true;">Tamil Nadu 638003 India</div>
        </div><script>window.searches = 0;</script>
    """)
    result = await delivery.check_delivery(url, "638003")
    assert result["status"] == "DELIVERABLE"
    assert await browser_context.pages[0].evaluate("window.searches") == 2


def map_search_page(tmp_path, map_contents):
    map_dir = tmp_path / "address-map"
    map_dir.mkdir()
    map_page = map_dir / "map.html"
    url = product_page(tmp_path, """
        <div id="location">Location not set</div>
        <button onclick="document.getElementById('dialog').hidden = false;">Select delivery location</button>
        <div>Delivery by 15 Nov</div>
        <div id="dialog" hidden><h2>Select delivery address</h2>
            <input placeholder="Search by area, street name, pin code" oninput="
                document.getElementById('suggestion').hidden = this.value.length !== 6;">
            <div id="suggestion" hidden onclick="
                document.getElementById('dialog').hidden = true;
                window.location.href = window.mapUri;">Tamil Nadu 638003 India</div>
        </div><script>
            window.mapUri = MAP_URI;
            if (sessionStorage.getItem('confirmedPin')) {
                document.getElementById('location').textContent = 'Erode, Tamil Nadu';
            }
        </script>
    """.replace("MAP_URI", json.dumps(map_page.as_uri())))
    map_page.write_text(
        "<html><body><h2>Set Delivery location</h2>"
        "<script>window.productUri = " + json.dumps(url) + "; window.retries = 0;</script>"
        + map_contents + "</body></html>", encoding="utf-8",
    )
    return url


@pytest.mark.asyncio
@pytest.mark.parametrize("map_pin,expected", [("638003", "DELIVERABLE"), ("638004", "UNKNOWN")])
async def test_map_retry_rechecks_requested_pin(browser_context, tmp_path, map_pin, expected):
    url = map_search_page(tmp_path, """
        <div id="error">Unable to pin your location now
            <button onclick="
                window.retries++;
                document.getElementById('error').hidden = true;
                document.getElementById('ready').hidden = false;">Try Again</button>
        </div>
        <div id="ready" hidden><div>Erode MAP_PIN</div>
            <button onclick="
                sessionStorage.setItem('confirmedPin', 'MAP_PIN');
                window.location.href = window.productUri;">Confirm</button>
        </div>
    """.replace("MAP_PIN", map_pin))
    result = await delivery.check_delivery(url, "638003")
    assert result["status"] == expected
    if expected == "UNKNOWN":
        assert await browser_context.pages[0].evaluate("window.retries") == 1
        assert await browser_context.pages[0].evaluate("sessionStorage.getItem('confirmedPin')") is None


@pytest.mark.asyncio
async def test_persistent_map_error_stops_after_bounded_retries(browser_context, tmp_path):
    url = map_search_page(tmp_path, """
        <div>Unable to pin your location now</div>
        <button onclick="window.retries++;">Try Again</button>
    """)
    result = await delivery.check_delivery(url, "638003")
    assert result["status"] == "UNKNOWN"
    assert await browser_context.pages[0].evaluate("window.retries") == 2


@pytest.mark.asyncio
async def test_map_waits_for_resolved_address_before_confirming(browser_context, tmp_path):
    url = map_search_page(tmp_path, """
        <div id="address">Resolving your location</div>
        <button onclick="
            sessionStorage.setItem('confirmedPin', '638003');
            window.location.href = window.productUri;">Confirm</button>
        <script>
            setTimeout(() => { document.getElementById('address').textContent = 'Erode 638003'; }, 300);
        </script>
    """)
    result = await delivery.check_delivery(url, "638003")
    assert result["status"] == "DELIVERABLE"


@pytest.mark.asyncio
async def test_map_recovers_when_confirm_is_replaced_by_error(browser_context, tmp_path, monkeypatch):
    monkeypatch.setattr(delivery.get_settings(), "playwright_timeout", 3000)
    url = map_search_page(tmp_path, """
        <div id="ready"><div>Erode 638003</div>
            <button onclick="
                sessionStorage.setItem('confirmedPin', '638003');
                window.location.href = window.productUri;">Confirm</button>
        </div>
        <div id="overlay" style="position: fixed; inset: 0; background: white;"></div>
        <div id="error" hidden>Unable to pin your location now
            <button onclick="
                window.retries++;
                document.getElementById('error').hidden = true;
                document.getElementById('ready').hidden = false;">Try Again</button>
        </div>
        <script>
            setTimeout(() => {
                document.getElementById('ready').hidden = true;
                document.getElementById('error').hidden = false;
                document.getElementById('overlay').remove();
            }, 100);
        </script>
    """)
    result = await delivery.check_delivery(url, "638003")
    assert result["status"] == "DELIVERABLE"


@pytest.mark.asyncio
@pytest.mark.parametrize('suggested_pin,expected', [('638003', 'DELIVERABLE'), ('638004', 'UNKNOWN')])
async def test_guest_map_error_recovers_by_reselecting_exact_pin(browser_context, tmp_path, suggested_pin, expected):
    url = map_search_page(tmp_path, """
        <input placeholder="Search by area, name, street." oninput="
            document.getElementById('result').hidden = this.value.length !== 6;">
        <div id="result" hidden onclick="
            document.getElementById('error').hidden = true;
            this.hidden = true;
            document.getElementById('ready').hidden = false;">Tamil Nadu PIN India</div>
        <div id="error">Unable to pin your location now
            <button onclick="window.retries++">Try Again</button></div>
        <div id="ready" hidden><div>Erode PIN</div>
            <button onclick="sessionStorage.setItem('confirmedPin', 'PIN');
                window.location.href = window.productUri;">Confirm</button></div>
    """.replace('PIN', suggested_pin))
    result = await delivery.check_delivery(url, '638003')
    assert result['status'] == expected
    if expected == 'UNKNOWN':
        assert await browser_context.pages[0].evaluate("sessionStorage.getItem('confirmedPin')") is None
