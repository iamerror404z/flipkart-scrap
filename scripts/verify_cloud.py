"""Call the real API with curl and save unmodified responses for a two-PIN matrix."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import time

URLS = [
    'https://www.flipkart.com/poco-x7-pro-5g-yellow-256-gb/p/itm0a066ed95064a?pid=MOBH7YZ9J6QGZZEQ&lid=LSTMOBH7YZ9J6QGZZEQCBSSSP',
    'https://www.flipkart.com/poco-x7-pro-5g-nebula-green-256-gb/p/itm8f21ab157cc72?pid=MOBH7YZ94697Z9D6',
]


def valid_item(item):
    product = item.get('product') or {}
    availability = item.get('availability') or item
    return (
        bool(product.get('name')) and isinstance(product.get('price'), (int, float))
        and isinstance(availability.get('isStock'), bool)
        and isinstance(availability.get('isDeliverable'), bool)
        and bool(availability.get('deliveryMessage'))
        and (not availability['isDeliverable'] or bool(availability.get('estimatedDelivery')))
        and not item.get('error')
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base-url', default='http://127.0.0.1:8081')
    parser.add_argument('--output', default='docs/cloud-verification.json')
    args = parser.parse_args()
    records = []
    requests = []
    for pin in ['638003', '110001']:
        for url in URLS:
            requests.append(('/api/v1/products/check', {'productUrl': url, 'pincode': pin}))
    for pin in ['638003', '110001']:
        requests.append(('/api/v1/products/batch-check', {
            'pincode': pin, 'products': [{'productUrl': url} for url in URLS]
        }))
    passed = True
    for endpoint, body in requests:
        start = time.monotonic()
        proc = subprocess.run([
            'curl', '-sS', '--max-time', '300', '-H', 'Content-Type: application/json',
            '-d', json.dumps(body), args.base_url.rstrip('/') + endpoint,
        ], capture_output=True, text=True)
        try:
            response = json.loads(proc.stdout)
        except json.JSONDecodeError:
            response = {'curlError': proc.stderr, 'rawResponse': proc.stdout}
        items = response.get('results', [response])
        verified = proc.returncode == 0 and response.get('success') is True and all(valid_item(item) for item in items)
        passed = passed and verified
        record = {
            'checkedAt': datetime.now(timezone.utc).isoformat(), 'endpoint': endpoint,
            'request': body, 'seconds': round(time.monotonic() - start, 2),
            'curlExitCode': proc.returncode, 'verified': verified, 'response': response,
        }
        records.append(record)
        Path(args.output).write_text(json.dumps(records, indent=2) + '\n')
        print(json.dumps(record), flush=True)
    return 0 if passed else 1


if __name__ == '__main__':
    raise SystemExit(main())
