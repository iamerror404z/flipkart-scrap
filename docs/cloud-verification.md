# Cloud VM verification — 11 November 2026 UTC

Work started on `cloud` from commit `724ec8f`. The original local `dev` branch
was left at that commit; this checkout has no local `main` branch.
The VM is Debian 12 / Python 3.11 in Azure Canada Central.

## Diagnosis before code changes

| Check | Actual observation |
|---|---|
| Browser-UA curl, homepage, 20-second limit | HTTP 200, 1.108 seconds, IPv4 23.222.17.78 |
| Browser-UA curl, supplied product, IPv4, 20-second limit | HTTP 200, 1.347 seconds |
| Original image's `_fetch_html`, homepage | Success, 1.18 seconds, 1,148,963 HTML characters |
| Original image's `_fetch_html`, supplied product | Success, 1.10 seconds, 1,618,076 HTML characters |
| Original project HTTP client on host | Homepage 0.97 seconds; product 1.21 seconds; both successful |
| DNS | A records 23.222.17.74/78 and AAAA records present |
| Forced IPv6 curl | Connection failure in 0.086 seconds; IPv6 is not usable on this VM |
| Host/container firewall | OUTPUT ACCEPT; Docker NAT/forwarding enabled; IPv4 HTTPS worked in both |
| Clock | UTC, synchronized by NTP |
| Original API on 8081, supplied product/PIN | Name POCO X7 Pro 5G (Yellow, 256 GB), price 23999, in stock, but delivery UNKNOWN after 24.03 seconds |

The reported **HTTP request timeout was not reproduced** in these initial
HTTP tests. There is no evidence here of a product-page IP block. A bare
request to the API host root returned 429, but the real browser session's
user-state/location-update endpoints returned 200. The local firewall and
successful requests rule out a general outbound HTTPS failure. Azure NSG
control-plane rules were not available to inspect directly; they were not
changed. The API was initially stopped; its existing registry image was
started temporarily to reproduce the original behavior, then stopped before
systemd took over port 8081.

The delivery failure was reproducible. Google reverse geocoding returned
`status: OK` and an address containing 638003. Flipkart's guest map also
requested `/api/1/contacts?source=entry`, which returned HTTP 401. Inspection
of the served `Maps.js` confirmed that this rejected saved-contacts request
sets the map error, while successful geocoding clears it: response order
makes the guest map work intermittently. Re-selecting the exact PIN inside
the existing map clears the error without refetching saved contacts. The
normal Confirm action then calls `/api/4/location/update` and returns to the
product. No credentials or saved-address writes were used.

Initial API verification also exposed the product heading being removed
between locating it and reading its parent during navigation. Those browser
timeouts were fixed by tolerating that DOM transition and rechecking the
current page. The initial responses, including failures, are retained in
[cloud-initial-verification.json](cloud-initial-verification.json).

## Verification of the final implementation

Full curl requests and unmodified parsed API responses, with timestamps and
elapsed times, are in [cloud-verification.json](cloud-verification.json).
They were obtained through the running systemd API, without mocks or a proxy:

```bash
.venv/bin/python scripts/verify_cloud.py
```

The script runs all four single-product combinations and both two-product
batches, saves every response, and exits nonzero if a response lacks the
required fields or has an upstream error. A null estimated date is valid
for a negative delivery result. It does not invent product or delivery data.

A direct reproduction of the supplied request:

```bash
curl -sS --max-time 300 http://127.0.0.1:8081/api/v1/products/check \
  -H 'Content-Type: application/json' \
  -d '{"productUrl":"https://www.flipkart.com/poco-x7-pro-5g-yellow-256-gb/p/itm0a066ed95064a?pid=MOBH7YZ9J6QGZZEQ&lid=LSTMOBH7YZ9J6QGZZEQCBSSSP","pincode":"638003"}'
```

All six final curl calls passed. The observed results were:

| Endpoint | Product | PIN | Price | isStock | isDeliverable | deliveryMessage | estimatedDelivery |
|---|---|---|---:|---|---|---|---|
| Single | POCO X7 Pro 5G (Yellow, 256 GB) | 638003 | 23999.0 | true | false | Not deliverable at your location | null |
| Single | POCO X7 Pro 5G (Nebula Green, 256 GB) | 638003 | 23999.0 | true | false | Not deliverable at your location | null |
| Single | POCO X7 Pro 5G (Yellow, 256 GB) | 110001 | 23999.0 | true | false | Not deliverable at your location | null |
| Single | POCO X7 Pro 5G (Nebula Green, 256 GB) | 110001 | 23999.0 | true | false | Not deliverable at your location | null |
| Batch | POCO X7 Pro 5G (Yellow, 256 GB) | 638003 | 23999.0 | true | false | Not deliverable at your location | null |
| Batch | POCO X7 Pro 5G (Nebula Green, 256 GB) | 638003 | 23999.0 | true | false | Not deliverable at your location | null |
| Batch | POCO X7 Pro 5G (Yellow, 256 GB) | 110001 | 23999.0 | true | false | Not deliverable at your location | null |
| Batch | POCO X7 Pro 5G (Nebula Green, 256 GB) | 110001 | 23999.0 | true | false | Not deliverable at your location | null |

These are real negative delivery results from the confirmed delivery section;
no positive delivery date was observed for these products/PINs. They do not
prove that all Flipkart products are unavailable at either PIN. Product prices
and serviceability can change with time, seller and session.

Validation: `pytest tests/ -q` finished with **94 passed, 1 skipped** (the
network integration test is skipped by default; the real API calls above
supply live verification). The installed unit passed `systemd-analyze verify`;
`systemctl is-enabled` returned `enabled`, `is-active` returned `active`, and
`ss` confirmed `0.0.0.0:8081`. Service restart was tested, but the VM itself
was not rebooted. `setup_vm.sh` was executed and rerun on this Debian VM;
fresh Ubuntu installation was not exercised here. Compose YAML was parsed,
but the VM has no Docker Compose CLI. The existing registry image remains
unchanged and must be rebuilt to use the cloud fixes in a container.

No proxy was supplied or needed in these tests. Actual operation through a
residential proxy has not been verified. If access becomes persistently
blocked, supply an Indian residential/ISP proxy using the documented env
variables; CAPTCHA and unsolved upstream failures remain explicit errors.
