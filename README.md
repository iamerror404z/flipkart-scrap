# Flipkart Scraper API

A lightweight, containerized REST API that scrapes publicly accessible Flipkart product pages to determine stock availability and PIN-code-based delivery availability.

Designed to be consumed by an external Spring Boot application via `RestClient` or `WebClient`.

---

## Table of Contents

- [Architecture](#architecture)
- [Project Structure](#project-structure)
- [Technology Stack](#technology-stack)
- [Environment Variables](#environment-variables)
- [Installation (Local)](#installation-local)
- [Docker Setup](#docker-setup)
- [API Documentation](#api-documentation)
  - [Health Check](#health-check)
  - [Check Product Availability](#check-product-availability)
  - [Batch Product Availability](#batch-product-availability)
- [Request and Response Examples](#request-and-response-examples)
- [Error Codes](#error-codes)
- [Testing Instructions](#testing-instructions)
- [Known Limitations](#known-limitations)

---

## Architecture

```
Request
  │
  ▼
FastAPI (routes.py)
  │
  ├── Input Validation (Pydantic + validators.py)
  │
  ▼
scraper.py (ScraperService)
  │
  ├── Step 1: Fetch HTML via httpx (HTTP-first approach)
  │
  ├── Step 2: Parse HTML with BeautifulSoup
  │       ├── JSON-LD metadata
  │       ├── Embedded HTML product data
  │       └── Heuristic text patterns
  │
  ├── Step 3: Determine stock status
  │       ├── JSON-LD offers.availability
  │       └── HTML text heuristics
  │
  └── Step 4: PIN code delivery check (always via Playwright)
          ├── Open product page in Chromium
          ├── Locate PIN code input
          ├── Open delivery location search when needed
          ├── Enter PIN and select the matching address
          ├── Confirm the map location when prompted
          ├── Wait for the requested location to be applied
          └── Extract information only from the delivery section
```

The service uses a **singleton browser instance** (Playwright Chromium) shared across requests, with a configurable semaphore limiting concurrent browser contexts. This avoids spinning up a new browser for every request.

---

## Project Structure

```
flipkart-scraper/
│
├── app/
│   ├── main.py              # FastAPI app, lifespan, global exception handler
│   │
│   ├── api/
│   │   └── routes.py        # Endpoint definitions
│   │
│   ├── schemas/
│   │   ├── request.py       # Pydantic request models
│   │   └── response.py      # Pydantic response models + enums
│   │
│   ├── services/
│   │   ├── scraper.py       # Main scraping logic
│   │   ├── browser.py       # Playwright browser manager (singleton)
│   │   ├── delivery.py      # PIN selection, confirmation, and scoped delivery checks
│   │   └── availability.py  # Availability classification logic
│   │
│   ├── utils/
│   │   ├── validators.py    # URL and PIN code validation
│   │   └── parser.py        # HTML / JSON-LD parsing helpers
│   │
│   └── config.py            # Settings (pydantic-settings)
│
├── tests/
│   ├── test_api.py          # API-level tests (mocked + integration)
│   └── test_parser.py       # Unit tests for parser/validator utilities
│
├── requirements.txt
├── Dockerfile
├── .dockerignore
├── .env.example
└── README.md
```

---

## Technology Stack

| Component      | Library               | Version  |
|----------------|-----------------------|----------|
| API framework  | FastAPI               | 0.162.2  |
| ASGI server    | Uvicorn               | 0.54.0   |
| Validation     | Pydantic              | 2.14.3   |
| Settings       | pydantic-settings     | 2.16.2   |
| HTTP client    | httpx                 | 0.28.1   |
| HTML parsing   | BeautifulSoup4        | 4.13.4   |
| Browser        | Playwright (Chromium) | 1.54.0   |
| Testing        | pytest + pytest-asyncio | See requirements.txt |

---

## Environment Variables

Copy `.env.example` to `.env` and adjust as needed.

| Variable                   | Default     | Description                                              |
|----------------------------|-------------|----------------------------------------------------------|
| `SERVICE_NAME`             | `flipkart-scraper` | Service name in health response                 |
| `DEBUG`                    | `false`     | Enable debug logging                                     |
| `HTTPX_TIMEOUT`            | `30.0`      | HTTP read/write/pool timeout in seconds                          |
| `HTTPX_CONNECT_TIMEOUT` | `10.0` | HTTP connection timeout in seconds |
| `HTTPX_RETRIES` | `2` | Extra retries for timeouts, connection errors and transient 5xx |
| `HTTPX_RETRY_BACKOFF` | `1.0` | Exponential retry delay base in seconds |
| `HTTPX_FORCE_IPV4` | `true` | Bind HTTP transport to IPv4 on VMs without IPv6 connectivity |
| `FLIPKART_PROXY` / `HTTPS_PROXY` | unset | Optional HTTP(S) proxy for HTTP and Chromium; FLIPKART_PROXY takes precedence |
| `HTTPX_MAX_REDIRECTS`      | `5`         | Maximum HTTP redirects to follow                         |
| `USER_AGENT`               | Chrome UA   | User-Agent header for HTTP requests                      |
| `PLAYWRIGHT_TIMEOUT`       | `30000`     | Playwright navigation timeout in milliseconds            |
| `PLAYWRIGHT_HEADLESS`      | `true`      | Run Chromium headless                                    |
| `PLAYWRIGHT_MAX_CONCURRENT`| `3`         | Max simultaneous browser contexts                        |
| `PLAYWRIGHT_SLOW_MO`       | `0`         | Milliseconds between Playwright actions (0 = disabled)   |
| `BATCH_MAX_PRODUCTS`       | `20`        | Maximum products per batch request                       |
| `BATCH_CONCURRENCY`        | `5`         | Concurrent scrapers in batch mode                        |
| `RATE_LIMIT_REQUESTS`      | `10`        | Requests per rate-limit window                           |
| `RATE_LIMIT_WINDOW`        | `60`        | Rate-limit window in seconds                             |

---

## Installation (Local)

### Prerequisites

- Python 3.11+
- pip

### Steps

```bash
cd flipkart-scraper

# Create a virtual environment
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Install Playwright Chromium browser
playwright install chromium

# Copy and configure environment
cp .env.example .env

# Start the server
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

The API is available at: http://localhost:8000  
Swagger UI: http://localhost:8000/docs  
ReDoc: http://localhost:8000/redoc  

---

## Docker Setup

The release image is `flipkart-scraper:1.0.2` for Linux AMD64. It packages
headless Chromium, runs as a non-root user, and includes a health check.
See [container and private-registry instructions](docs/containers.md) for
image export, Docker Hub, and cloud settings.

### Build

```bash
docker build --platform linux/amd64 -t flipkart-scraper:1.0.2 .
```

On Windows, build and verify Chromium with:

```powershell
./scripts/build-image.ps1
```

### Run

```bash
docker compose up -d --build
docker compose ps
```

The container serves the API on `0.0.0.0:8081` by default. Change `HOST_PORT`
or the browser-concurrency variables through the environment or `.env`.

### Verify

```bash
curl http://localhost:8081/health
```

---

## Running on cloud VM

On a fresh Ubuntu or Debian VM, run as the account that should own the service
(with passwordless sudo available):

```bash
git checkout cloud
./setup_vm.sh
curl http://127.0.0.1:8081/health
sudo systemctl status flipkart-scraper
sudo journalctl -u flipkart-scraper -f
```

The script installs Python, system libraries and matching Playwright headless
Chromium, then enables a systemd service listening on `0.0.0.0:8081` after
reboots. Java is optional for a Spring Boot consumer on the same VM:
`INSTALL_JAVA=true ./setup_vm.sh`. Stop any existing container using 8081
before starting the systemd service. Re-running the script is supported.
The exact manual command, from the project directory, is:

```bash
.venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8081 --workers 1
```

Allow inbound TCP 8081 in the Azure NSG for the intended clients. Outbound
HTTPS and DNS must reach Flipkart, its assets/API hosts and Google Maps.
The setup script does not alter Azure NSGs or firewall policy. `/health`
checks the API process; it does not promise upstream access. Configure client
and reverse-proxy timeouts of at least 300 seconds, and longer for batches.

If Flipkart blocks your datacenter IP, supply an **Indian residential/ISP
proxy** through `.env` (keep it private; URL-encode special credential characters):

```dotenv
FLIPKART_PROXY=http://username:password@proxy-host:port
```

`HTTPS_PROXY` is an alternative when `FLIPKART_PROXY` is unset. Both the HTTP
client and each isolated Chromium context use the same configured proxy.
Restart with `sudo systemctl restart flipkart-scraper` after changing `.env`.
For containers, Compose forwards this configuration; rebuild the image with
`docker compose up -d --build`. The original registry image does not include
these cloud fixes. A proxy is optional and cannot guarantee access or remove
CAPTCHA challenges. Persistent timeouts remain `TIMEOUT`; the service does
not infer an IP block from a timeout alone.

Delivery uses Flipkart's existing guest address-search/map/location-update
flow. When a saved-contacts HTTP 401 overwrites a valid map address, it
re-selects the exact PIN inside that map and waits for confirmation. It does
not create a saved address or use login credentials. A negative delivery
result has `isDeliverable: false` and `estimatedDelivery: null` because
Flipkart provides no delivery date for that location.

Batch items retain their existing availability fields and also include
`product`, `deliveryMessage`, and `estimatedDelivery`. Batch `success` is
false if any item has an error; inspect each item's `error`. Unknown browser
failures are errors rather than successful checks with unexplained nulls.
Real VM responses and diagnostic evidence are recorded in
[cloud-verification.md](docs/cloud-verification.md).

---

## API Documentation

### Health Check

```
GET /health
```

**Response:**
```json
{
  "status": "UP",
  "service": "flipkart-scraper"
}
```

---

### Check Product Availability

```
POST /api/v1/products/check
Content-Type: application/json
```

**Request:**
```json
{
  "productUrl": "https://www.flipkart.com/apple-iphone-15/p/itmbf14ef54f645d",
  "pincode": "638001"
}
```

**Success Response (200):**
```json
{
  "success": true,
  "productUrl": "https://www.flipkart.com/apple-iphone-15/p/itmbf14ef54f645d",
  "pincode": "638001",
  "product": {
    "name": "Apple iPhone 15 (Black, 128 GB)",
    "price": 69999.0,
    "image": "https://rukminim2.flixcart.com/image/...",
    "productId": "MOBGTAGPAQNVFZZY"
  },
  "availability": {
    "isStock": true,
    "isDeliverable": true,
    "stockStatus": "IN_STOCK",
    "deliveryStatus": "DELIVERABLE",
    "deliveryMessage": "Delivery by 15 Nov, Thursday",
    "estimatedDelivery": "15 Nov"
  },
  "metadata": {
    "source": "flipkart",
    "checkedAt": "2026-11-10T09:30:00Z"
  }
}
```

**Error Response:**
```json
{
  "success": false,
  "productUrl": "https://www.flipkart.com/...",
  "pincode": "638001",
  "error": {
    "code": "PRODUCT_NOT_FOUND",
    "message": "The product page was not found (HTTP 404)."
  }
}
```

---

### Batch Product Availability

```
POST /api/v1/products/batch-check
Content-Type: application/json
```

**Request:**
```json
{
  "pincode": "638001",
  "products": [
    { "productUrl": "https://www.flipkart.com/product-1/p/ITM1" },
    { "productUrl": "https://www.flipkart.com/product-2/p/ITM2" }
  ]
}
```

**Success Response (200):**
```json
{
  "success": true,
  "pincode": "638001",
  "totalProducts": 2,
  "results": [
    {
      "productUrl": "https://www.flipkart.com/product-1/p/ITM1",
      "isStock": true,
      "isDeliverable": true,
      "stockStatus": "IN_STOCK",
      "deliveryStatus": "DELIVERABLE"
    },
    {
      "productUrl": "https://www.flipkart.com/product-2/p/ITM2",
      "isStock": false,
      "isDeliverable": null,
      "stockStatus": "OUT_OF_STOCK",
      "deliveryStatus": "UNKNOWN"
    }
  ]
}
```

---

## Availability States

### Stock Status

| Status        | `isStock` | Description                      |
|---------------|-----------|----------------------------------|
| `IN_STOCK`    | `true`    | Product is available for purchase|
| `OUT_OF_STOCK`| `false`   | Product is sold out              |
| `UNKNOWN`     | `null`    | Could not determine stock status |

### Delivery Status

| Status            | `isDeliverable` | Description                                |
|-------------------|-----------------|--------------------------------------------|
| `DELIVERABLE`     | `true`          | Delivery available to the given PIN code   |
| `NOT_DELIVERABLE` | `false`         | Delivery not available to the given PIN code|
| `UNKNOWN`         | `null`          | Could not determine delivery availability  |

> **Important:** `UNKNOWN` is never treated as `false`. Missing information is returned as `null`, not `false`.

If the requested PIN cannot be selected or confirmed, the check returns
`success: false` with `PARSE_ERROR` or `TIMEOUT`; a default delivery date is never used. Exchange and
bank-offer restrictions are not used as evidence of product stock or delivery.

---

## Error Codes

| Code                      | HTTP Status | Description                                     |
|---------------------------|-------------|-------------------------------------------------|
| `PRODUCT_NOT_FOUND`       | 200         | Product page returned HTTP 404                  |
| `BLOCKED` | 200 | Flipkart returned 403/429 or a visible blocking page |
| `PARSE_ERROR` | 200 | Product fields or confirmed PIN delivery result could not be read |
| `BROWSER_ERROR` | 200 | Chromium installation, launch or browser transport failed |
| `TIMEOUT`                 | 200         | Request or browser navigation timed out         |
| `NETWORK_ERROR`           | 200         | Network-level connectivity failure              |
| `HTTP_ERROR`              | 200         | Unexpected HTTP status code from Flipkart       |
| `SCRAPE_ERROR`            | 200         | Unexpected error during scraping                |
| `CAPTCHA`                 | 200         | CAPTCHA or bot-verification page encountered    |
| `AVAILABILITY_UNAVAILABLE`| 200         | Could not extract availability information      |

> All errors are returned with HTTP 200 from the API itself. The `success: false` flag and `error.code` indicate the nature of the failure.

---

## Testing Instructions

### Run all unit tests

```bash
pytest tests/ -v
```

### Run only parser/validator unit tests

```bash
pytest tests/test_parser.py -v
```

Browser regression tests use local HTML pages, with no requests to Flipkart:

```bash
playwright install chromium
pytest tests/test_delivery.py -v
```

### Run only API tests

```bash
pytest tests/test_api.py -v
```

### Run integration tests (requires network)

```bash
pytest tests/test_api.py -v --integration
```

> Integration tests make real HTTP and browser requests to Flipkart. They may fail due to Flipkart page structure changes, rate limiting, or geographic restrictions.

---

## Spring Boot Integration

### RestClient example (Java 17+)

```java
RestClient restClient = RestClient.create("http://localhost:8000");

ProductCheckResponse response = restClient.post()
    .uri("/api/v1/products/check")
    .contentType(MediaType.APPLICATION_JSON)
    .body(Map.of(
        "productUrl", "https://www.flipkart.com/product/p/ITM123",
        "pincode", "638001"
    ))
    .retrieve()
    .body(ProductCheckResponse.class);
```

### WebClient example

```java
WebClient webClient = WebClient.create("http://localhost:8000");

Mono<ProductCheckResponse> response = webClient.post()
    .uri("/api/v1/products/check")
    .bodyValue(Map.of(
        "productUrl", "https://www.flipkart.com/product/p/ITM123",
        "pincode", "638001"
    ))
    .retrieve()
    .bodyToMono(ProductCheckResponse.class);
```

---

## Known Limitations

1. **Flipkart page structure changes** — Flipkart frequently updates its frontend. CSS selectors and HTML patterns used for extraction may become stale. Multiple fallback strategies are used to minimise this risk.

2. **Bot detection** — Flipkart employs bot-detection mechanisms. HTTP-only requests may be blocked (HTTP 403) depending on request frequency, IP reputation, and headers. The service does not attempt to bypass these protections.

3. **CAPTCHA** — If Flipkart presents a CAPTCHA challenge, the service returns `success: false` with `CAPTCHA` without attempting to solve it. This is by design.

4. **Rate limiting** — Sending too many requests in a short period may cause Flipkart to rate-limit the scraper IP. The configurable concurrency and rate limiting settings help mitigate this.

5. **Dynamic content** — PIN code delivery checks always use Playwright (Chromium) since the delivery section is rendered dynamically. Browser startup adds latency to the first request of each server lifecycle.

6. **Geographic availability** — Flipkart may serve different page structures or restrict access based on the scraper's IP location.

7. **Single browser instance** — Only one Chromium browser is shared across all requests. Under very high load, requests will queue at the semaphore. Scale by increasing `PLAYWRIGHT_MAX_CONCURRENT` (within memory limits).

8. **No caching** — Each request triggers a fresh scrape. No result caching is implemented; add a caching layer (e.g., Redis) externally if needed.

9. **Legal and ToS compliance** — This service scrapes only publicly accessible product pages. Users are responsible for compliance with Flipkart's Terms of Service.
