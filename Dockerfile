# syntax=docker/dockerfile:1
FROM python:3.13-slim-bookworm AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright

# Build tools never enter the runtime image.
RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    apt-get update \
    && apt-get install -y --no-install-recommends binutils \
    && rm -rf /var/lib/apt/lists/*

COPY requirements-runtime.txt /tmp/requirements-runtime.txt
RUN python -m venv --without-pip /opt/venv \
    && python -m pip --python /opt/venv install --no-cache-dir --no-compile \
        --only-binary=:all: --timeout 120 -r /tmp/requirements-runtime.txt \
    && mkdir -p /out \
    && python -m pip --python /opt/venv freeze > /out/requirements-resolved.txt

# Prune and strip in the builder: deleting after COPY would retain the bytes
# in an earlier runtime layer. Keep runtime modules and package metadata.
RUN --mount=type=bind,source=scripts/prune-runtime.py,target=/tmp/prune-runtime.py \
    python /tmp/prune-runtime.py python

FROM builder AS browser
RUN --mount=type=cache,target=/root/.cache/playwright-downloads \
    --mount=type=bind,source=scripts/install-browser.py,target=/tmp/install-browser.py \
    --mount=type=bind,source=scripts/prune-runtime.py,target=/tmp/prune-runtime.py \
    PLAYWRIGHT_SKIP_VALIDATE_HOST_REQUIREMENTS=1 /opt/venv/bin/python /tmp/install-browser.py \
    && /opt/venv/bin/python /tmp/prune-runtime.py browser \
    && chmod -R a+rX /ms-playwright

FROM debian:bookworm-slim AS runtime

ARG APP_VERSION=1.0.2
LABEL org.opencontainers.image.title="Flipkart Scraper API" \
      org.opencontainers.image.description="Product stock and verified PIN-code delivery checks" \
      org.opencontainers.image.version="${APP_VERSION}"

ENV PATH=/opt/venv/bin:/usr/local/bin:/usr/local/sbin:/usr/sbin:/usr/bin:/sbin:/bin \
    LANG=C.UTF-8 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright \
    PLAYWRIGHT_HEADLESS=true \
    PORT=8000

# Shared libraries for the packaged headless shell, Node, and Python modules.
# libgbm1 works with bundled SwiftShader; Mesa/LLVM and Xvfb are unnecessary.
# DejaVu supplies font fallback; keep ICU/browser data and CA certificates.
RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    apt-get update \
    && apt-get install -y --no-install-recommends \
        ca-certificates fonts-dejavu-core \
        libasound2 libatk-bridge2.0-0 libatk1.0-0 libatspi2.0-0 \
        libbz2-1.0 libdbus-1-3 libexpat1 libffi8 libfontconfig1 libgbm1 \
        libgdbm-compat4 libgdbm6 libglib2.0-0 liblzma5 libncursesw6 \
        libnspr4 libnss3 libreadline8 libsqlite3-0 libssl3 libstdc++6 \
        libudev1 libuuid1 libx11-6 libxcb1 libxcomposite1 libxdamage1 \
        libxext6 libxfixes3 libxkbcommon0 libxrandr2 netbase tzdata zlib1g \
    && rm -rf /var/lib/apt/lists/* /usr/share/doc /usr/share/man \
        /usr/share/info /usr/share/locale \
    && groupadd --gid 10001 appgroup \
    && useradd --uid 10001 --gid appgroup --create-home --shell /usr/sbin/nologin appuser

COPY --from=builder /usr/local/ /usr/local/
COPY --from=builder /opt/venv/ /opt/venv/
COPY --from=builder /out/requirements-resolved.txt /usr/local/share/flipkart-scraper/requirements-resolved.txt
COPY --from=browser /ms-playwright/ /ms-playwright/

WORKDIR /app
COPY --chown=appuser:appgroup app/ ./app/
USER 10001:10001

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import os, urllib.request; urllib.request.urlopen('http://127.0.0.1:' + os.environ.get('PORT', '8000') + '/health', timeout=3)" || exit 1

# One worker owns one shared browser. exec forwards shutdown signals to Uvicorn.
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port \"${PORT:-8000}\" --workers 1"]
