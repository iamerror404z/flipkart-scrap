# =============================================================================
# Flipkart Scraper API — Docker image
# =============================================================================
# Base: slim Python 3.12 image
FROM python:3.12-slim

# --- Environment settings -------------------------------------------------
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright

# --- System dependencies required by Playwright / Chromium ----------------
RUN apt-get update && apt-get install -y --no-install-recommends \
        libglib2.0-0 \
        libnss3 \
        libatk1.0-0 \
        libatk-bridge2.0-0 \
        libcups2 \
        libxkbcommon0 \
        libxcomposite1 \
        libxdamage1 \
        libxfixes3 \
        libxrandr2 \
        libgbm1 \
        libpango-1.0-0 \
        libcairo2 \
        libasound2 \
        libxshmfence1 \
        fonts-liberation \
        fonts-noto \
    && rm -rf /var/lib/apt/lists/*

# --- Non-root user --------------------------------------------------------
RUN groupadd --system appgroup && useradd --system --gid appgroup --shell /bin/false appuser

# --- Working directory -----------------------------------------------------
WORKDIR /app

# --- Python dependencies ---------------------------------------------------
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# --- Install ONLY Chromium (no Firefox, no WebKit) ------------------------
RUN playwright install chromium --with-deps && chmod -R 755 /ms-playwright

# --- Application source code ----------------------------------------------
COPY app/ ./app/

# --- Ownership ------------------------------------------------------------
RUN chown -R appuser:appgroup /app

# --- Switch to non-root user ----------------------------------------------
USER appuser

# --- Expose port ----------------------------------------------------------
EXPOSE 8000

# --- Health check ---------------------------------------------------------
HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" || exit 1

# --- Start application -----------------------------------------------------
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
