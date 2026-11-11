# POCO X7 delivery PIN selection times out

Status: fixed and verified through the running API on 10 November 2026.

## Reproduction

- Product: POCO X7 5G (Yellow, 256 GB)
- Product ID: `MOBH7YZ9NSDFC3EK`
- URL: https://www.flipkart.com/poco-x7-5g-yellow-256-gb/p/itm09a41b8f384f7?pid=MOBH7YZ9NSDFC3EK
- PIN: `638003` (Erode, Tamil Nadu)
- Endpoint: `POST /api/v1/products/check`
- Observed on: 10 November 2026, 18:00 IST

The live request returned HTTP 200 after 38.3 seconds. Stock and price were
read successfully (`IN_STOCK`, INR 19,999), but delivery was `UNKNOWN` with
`isDeliverable: null` and no estimated date.

```json
{
  "stockStatus": "IN_STOCK",
  "deliveryStatus": "UNKNOWN",
  "deliveryMessage": "Timed out while confirming delivery for PIN 638003."
}
```

## Failure evidence

The Chromium workflow opened the delivery address search but timed out after
10 seconds waiting for an exact `638003` suggestion inside the ancestor
containing the heading `Select delivery address`:

```text
Locator.wait_for: Timeout 10000ms exceeded.
waiting for locator("input[id*='pincode' i]:visible:not([readonly]):not([disabled]), input[placeholder*='pin' i]:visible:not([readonly]):not([disabled]), input[maxlength='6']:visible:not([readonly]):not([disabled])").first
  .locator("xpath=ancestor::*[.//*[normalize-space(.)='Select delivery address']][1]")
  .get_by_text(re.compile(r"\b638003\b")).first to be visible
```

Earlier server attempts also stalled while waiting for the map's `Confirm`
control. A browser capture reproduced a map that replaced this control with:

```text
Unable to pin your location now
It is taking longer than usual. Please check your internet connection and try again.
Try Again
```

The original click kept waiting for `Confirm` after it was detached, without
using the site's retry control.

Another live browser run successfully confirmed PIN `638003`, then showed
this product's delivery block:

```text
Delivery details
KAS Nagar, Marapalam Road, Ramanuja Nagar, Karungalpalayam, Erode, Tamil Nadu
Not deliverable at your location
Seller: ECOMTAMSINRetail
```

That run still returned `UNKNOWN`: both the delivery-section finder and the
message parser missed the exact phrase `Not deliverable at your location`.

## Root cause

1. The address search had one 10-second wait with no recovery if initial input
   events or a temporary prediction failure produced no suggestion. The
   search UI and its prediction provider load asynchronously.
2. The map could expose a provisional `Confirm` control, then replace or
   overlay it during reverse geocoding. A single long click prevented the
   workflow from noticing and recovering through `Try Again`.
3. The delivery-section finder omitted `not deliverable`, and the parser's
   old pattern expected `location` before `not deliverable`. Flipkart currently
   uses the opposite order. A confirmed restriction was therefore unreadable.

## Required behavior

Select the requested PIN, verify any map address still has that PIN, confirm
it, and read the product's delivery section after the location is applied.
Keep unconfirmed results `UNKNOWN`; never infer a delivery restriction from
exchange or bank offers.

## Fix

In `app/services/delivery.py`:

- Retry address search up to three attempts within the configured Playwright
  search budget, clearing and typing the exact PIN again when predictions do
  not appear. Keep suggestions scoped to the delivery address sheet.
- Add `_confirm_map_location` to wait for a resolved address instead of treating
  a visible `Confirm` skeleton as ready. Use short click attempts so replaced
  controls and map errors can be observed.
- Use the map's own `Try Again` control at most twice, within a bounded wait.
  Recheck the requested PIN before confirmation, including after a retry.
- Recognize `not deliverable` when locating the product's delivery section.

In `app/utils/parser.py`, recognize the explicit phrase `not deliverable`,
including when its words are split across DOM lines. This parser receives
the scoped delivery block after location verification. Offer restrictions
still do not establish product delivery availability.

Persistent map errors, unresolved locations, and mismatched PINs remain
`UNKNOWN`. A confirmed delivery restriction becomes `NOT_DELIVERABLE`.

## Validation

Local Chromium regression tests cover failed initial predictions, recovery
through `Try Again`, rechecking a different PIN after retry, persistent map
errors, delayed address resolution, and a replaced `Confirm` control.
Parser and browser tests also cover the current restriction phrase.

The full suite executed 81 tests: 78 passed, one live integration test was
skipped, and two local browser checks initially hit their 1.2-second fixture
timeouts. Both failed checks passed on rerun: all 80 executed checks passed.
`git diff --check` passed.

```text
python -m pytest tests/ -q -o asyncio_default_fixture_loop_scope=function
python -m pytest tests/test_delivery.py -q --lf -o asyncio_default_fixture_loop_scope=function
```

The API was restarted with the updated code on `http://127.0.0.1:8000`.
Live requests to `POST /api/v1/products/check` produced:

| Product / PIN | Stock | Delivery | Estimate | Request time |
| --- | --- | --- | --- | --- |
| POCO X7 Yellow 256 GB / 638003 | IN_STOCK, INR 19,999 | NOT_DELIVERABLE | None | 30.8 seconds |
| vivo T5x Cosmic Green 128 GB / 638003 | IN_STOCK, INR 27,999 | DELIVERABLE | Saturday, 14 Nov | 31.6 seconds |

The POCO result reflects Flipkart's explicit restriction after applying the
requested PIN. The earlier Vivo example still returns available delivery.
These are live observations; stock, seller coverage, and dates can change.

Saved responses:

- [POCO before the fix](001-poco-x7-before.json)
- [POCO after the fix](001-poco-x7-after.json)
- [Vivo regression check after the fix](001-vivo-regression-after.json)
