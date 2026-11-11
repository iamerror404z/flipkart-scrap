#!/usr/bin/env bash
# Run as the account that should own the service; sudo must be available.
set -euo pipefail
APP_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
cd "$APP_DIR"
if [ "$(id -u)" -eq 0 ]; then
    ADMIN=()
    RUN_USER="${SUDO_USER:-root}"
else
    sudo -n true
    ADMIN=(sudo -n)
    RUN_USER="$(id -un)"
fi
RUN_GROUP="$(id -gn "$RUN_USER")"
"${ADMIN[@]}" apt-get update
"${ADMIN[@]}" apt-get install -y --no-install-recommends python3 python3-venv python3-pip ca-certificates curl dnsutils
# Java is needed only if the consuming Spring Boot application runs on this VM.
if [ "${INSTALL_JAVA:-false}" = true ]; then
    "${ADMIN[@]}" apt-get install -y --no-install-recommends openjdk-17-jre-headless
fi
if [ ! -d .venv ]; then
    if [ "$(id -u)" -eq 0 ]; then
        runuser -u "$RUN_USER" -- python3 -m venv .venv
    else
        python3 -m venv .venv
    fi
fi
if [ "$(id -u)" -eq 0 ]; then
    AS_USER=(runuser -u "$RUN_USER" --)
else
    AS_USER=()
fi
"${AS_USER[@]}" .venv/bin/python -m pip install -r requirements-runtime.txt
"${ADMIN[@]}" .venv/bin/python -m playwright install-deps chromium
"${AS_USER[@]}" .venv/bin/python -m playwright install --only-shell chromium
if [ ! -f .env ]; then
    "${AS_USER[@]}" cp .env.example .env
    "${AS_USER[@]}" chmod 600 .env
fi
UNIT_FILE="$(mktemp)"
trap 'rm -f "$UNIT_FILE"' EXIT
python3 - "$APP_DIR" "$RUN_USER" "$RUN_GROUP" "$UNIT_FILE" <<'PY'
from pathlib import Path
import sys
app_dir, user, group, output = sys.argv[1:]
# Escape paths as systemd quoted strings, including its % specifier syntax.
escaped = app_dir.replace('\\', '\\\\').replace('"', '\\"').replace('%', '%%')
unit = Path('systemd/flipkart-scraper.service').read_text()
unit = unit.replace('@APP_DIR@', escaped).replace('@RUN_USER@', user).replace('@RUN_GROUP@', group)
Path(output).write_text(unit)
PY
"${ADMIN[@]}" install -m 644 "$UNIT_FILE" /etc/systemd/system/flipkart-scraper.service
"${ADMIN[@]}" systemd-analyze verify /etc/systemd/system/flipkart-scraper.service
"${ADMIN[@]}" systemctl daemon-reload
"${ADMIN[@]}" systemctl enable flipkart-scraper.service
"${ADMIN[@]}" systemctl restart flipkart-scraper.service
"${ADMIN[@]}" systemctl --no-pager status flipkart-scraper.service
curl --fail --retry 10 --retry-connrefused --retry-delay 1 --max-time 5 http://127.0.0.1:8081/health
