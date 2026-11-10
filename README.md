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
          ├── Enter PIN and trigger check
          ├── Wait for DOM update
          └── Extract delivery information
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
| API framework  | FastAPI               | 0.115.5  |
| ASGI server    | Uvicorn               | 0.32.1   |
| Validation     | Pydantic              | 2.10.1   |
| Settings       | pydantic-settings     | 2.6.1    |
| HTTP client    | httpx                 | 0.28.0   |
| HTML parsing   | BeautifulSoup4 + lxml | 4.12.3   |
| Browser        | Playwright (Chromium) | 1.49.0   |
| Testing        | pytest + pytest-asyncio | 8.3.4  |

---

## Environment Variables

Copy `.env.example` to `.env` and adjust as needed.

| Variable                   | Default     | Description                                              |
|----------------------------|-------------|----------------------------------------------------------|
| `SERVICE_NAME`             | `flipkart-scraper` | Service name in health response                 |
| `DEBUG`                    | `false`     | Enable debug logging                                     |
| `HTTPX_TIMEOUT`            | `20.0`      | HTTP request timeout in seconds                          |
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

- Python 3.12+
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

### Build

```bash
docker build -t flipkart-scraper .
```

### Run

```bash
docker run -d \
  --name flipkart-scraper \
  -p 8000:8000 \
  flipkart-scraper
```

### With environment overrides

```bash
docker run -d \
  --name flipkart-scraper \
  -p 8000:8000 \
  -e PLAYWRIGHT_MAX_CONCURRENT=5 \
  -e BATCH_CONCURRENCY=3 \
  flipkart-scraper
```

### Verify

```bash
curl http://localhost:8000/health
```

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

---

## Error Codes

| Code                      | HTTP Status | Description                                     |
|---------------------------|-------------|-------------------------------------------------|
| `PRODUCT_NOT_FOUND`       | 200         | Product page returned HTTP 404                  |
| `ACCESS_DENIED`           | 200         | Flipkart returned HTTP 403 (bot detection)      |
| `RATE_LIMITED`            | 200         | Flipkart returned HTTP 429                      |
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

3. **CAPTCHA** — If Flipkart presents a CAPTCHA challenge, the service returns `UNKNOWN` availability without attempting to solve it. This is by design.

4. **Rate limiting** — Sending too many requests in a short period may cause Flipkart to rate-limit the scraper IP. The configurable concurrency and rate limiting settings help mitigate this.

5. **Dynamic content** — PIN code delivery checks always use Playwright (Chromium) since the delivery section is rendered dynamically. Browser startup adds latency to the first request of each server lifecycle.

6. **Geographic availability** — Flipkart may serve different page structures or restrict access based on the scraper's IP location.

7. **Single browser instance** — Only one Chromium browser is shared across all requests. Under very high load, requests will queue at the semaphore. Scale by increasing `PLAYWRIGHT_MAX_CONCURRENT` (within memory limits).

8. **No caching** — Each request triggers a fresh scrape. No result caching is implemented; add a caching layer (e.g., Redis) externally if needed.

9. **Legal and ToS compliance** — This service scrapes only publicly accessible product pages. Users are responsible for compliance with Flipkart's Terms of Service.
