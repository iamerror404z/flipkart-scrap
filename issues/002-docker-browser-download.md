# Docker browser download interrupted

Date: 2026-11-10
Status: Resolved; Linux AMD64 image built and browser/container checks verified on 2026-11-11.

The first Linux AMD64 build installed the Python dependencies and Chromium's
Linux libraries, then lost the browser CDN connection at roughly 30% of the
104.8 MiB Chromium archive. Playwright's fallback requests immediately failed
with `getaddrinfo ENOTFOUND`. The combined installation command failed, so
Docker could not retain its successfully installed dependencies as a layer.

The Dockerfile now separates Python dependencies, browser archives, and Linux
libraries. BuildKit caches Python packages, Debian downloads, and partial
browser archives outside the final image. Browser and library stages can run
in parallel after the Python dependencies are available.

`scripts/install-browser.py` downloads archives from official Playwright
servers using byte ranges. It resumes interrupted transfers, restarts safely
when a server ignores ranges, checks archive size and ZIP integrity, and lets
Playwright's installer unpack the cached files through a temporary local HTTP
server. The final container smoke check launches Chromium with the installed
Linux libraries as the unprivileged application user.

Validation: three download recovery tests passed, including real HTTP
connections truncated before their advertised response lengths and rejection
of a corrupt archive. The cached archives survived a computer restart, and
the image built successfully. Its browser smoke check launched Chromium
139.0.7258.5 with Playwright 1.54.0 as UID 10001 and passed a page interaction.
The container health probe and API documentation return HTTP 200.

The live POCO X7 check at PIN 638003 returned IN_STOCK and NOT_DELIVERABLE,
matching Flipkart's explicit location restriction. The Vivo listing changed
to OUT_OF_STOCK: an independent page fetch confirmed schema.org/OutOfStock,
visible "Out of Stock", and "Notify Me". Its delivery status remains UNKNOWN;
the release report records this limitation without treating it as unavailable
delivery. This external stock change is independent of browser installation.
