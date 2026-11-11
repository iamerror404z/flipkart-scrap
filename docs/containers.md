# Docker image and deployment

The Debian 12 slim runtime image contains Python 3.13, the FastAPI application,
and Playwright's
matching headless Chromium with its Linux libraries. It runs as UID `10001`,
starts one Uvicorn worker, and has a `/health` probe. A separate builder uses
`python:3.13-slim-bookworm`, installs a venv without pip, and strips debug
symbols before copying Python, the venv, and the browser into the runtime.
Direct runtime versions are pinned in `requirements-runtime.txt`; test tools,
local environments, logs,
issue reports, and exported images are excluded from the build context.

See [image-size.md](image-size.md) for the layer breakdown, size measurements,
browser requirement, and base-image comparison.

## Build and verify

```powershell
./scripts/build-image.ps1
```

This builds `flipkart-scraper:1.0.2` for `linux/amd64` and verifies that the
API routes exist and Chromium can launch and interact with a page as the
unprivileged container user. Docker Desktop must be running in Linux mode.

BuildKit caches package and browser downloads outside the final image. The
browser download resumes interrupted transfers from official Playwright
servers, checks the ZIP integrity, and uses Playwright's installer to unpack
the cached archives. Re-running the build preserves completed dependency
layers and downloaded bytes.

For an archive that can be transferred without a registry:

```powershell
./scripts/build-image.ps1 -Export
docker load --input dist/flipkart-scraper-1.0.2-linux-amd64.tar
```

The export includes a SHA-256 checksum. Every image also records its complete
resolved Python dependency list at
`/usr/local/share/flipkart-scraper/requirements-resolved.txt`.

## Run locally

```bash
docker compose up -d --build
docker compose ps
```

The container is available at `http://127.0.0.1:8001/docs`; the existing
Python server on port `8000` can stay running. Use `HOST_PORT` to change the
published port. Compose configures a 2 GiB memory limit, a 1 GiB shared-memory
segment, an init process, and graceful shutdown.

To run an already-built image directly:

```bash
docker run -d --name flipkart-scraper --init --restart unless-stopped \
  --memory 2g --shm-size 1g -p 127.0.0.1:8001:8000 flipkart-scraper:1.0.2
curl http://127.0.0.1:8001/health
```

Keep `PLAYWRIGHT_HEADLESS=true`: this image packages headless Chromium.
Scraping requires outbound HTTPS to Flipkart and the address lookup services
used by its frontend. Delivery checks typically take tens of seconds, so
configure the cloud proxy's request timeout to at least 180 seconds and allow
additional time for larger batches.

## Private Docker Hub repository

The release repository is `iamerror404/flipkart-scraper` and must remain
private. Verify repository privacy in Docker Hub before the first push.

```bash
docker login
docker tag flipkart-scraper:1.0.2 iamerror404/flipkart-scraper:1.0.2
docker push iamerror404/flipkart-scraper:1.0.2
```

On a cloud host authorized to pull the private repository:

```bash
docker login
docker pull iamerror404/flipkart-scraper:1.0.2
docker run -d --name flipkart-scraper --init --restart unless-stopped \
  --memory 2g --shm-size 1g -p 8000:8000 iamerror404/flipkart-scraper:1.0.2
```

Keep registry credentials in the hosting platform's registry settings or
secret store. Use the published digest from the release report for an exact
image reference.

## Cloud container settings

- Image architecture: Linux AMD64.
- Application port: `8000` by default; setting `PORT` changes both Uvicorn and
  the container health probe.
- Health path: `/health`.
- Starting resources: 1 CPU and 2 GiB RAM with at most three browser contexts.
- One application worker per container; add container replicas for capacity.
- No database, persistent disk, or background scheduler is required.

Pushing the image stores the release in Docker Hub. Running a public API also
requires a hosting service, its registry access, and network configuration.
