"""Check the packaged API and launch its Chromium as the container user.

Run with: docker run --rm -i --init --entrypoint python IMAGE - < this_file
"""
import asyncio
import json
import os
import subprocess
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

from app.main import app
from app.services.browser import browser_manager


async def main():
    if os.getuid() == 0:
        raise RuntimeError("The production image must run as a non-root user.")
    for package in ("pytest", "pytest-asyncio", "pip"):
        try:
            version(package)
        except PackageNotFoundError:
            continue
        raise RuntimeError(f"Build/test dependency included in the runtime image: {package}")
    if Path("/app/.env").exists() or Path("/app/.venv").exists():
        raise RuntimeError("Local environment files were included in the image.")
    for root in (Path("/app"), Path("/opt/venv"), Path("/usr/local")):
        if next(root.rglob("*.pyc"), None) is not None:
            raise RuntimeError(f"Precompiled Python cache included under {root}.")
    installed = set(subprocess.check_output(
        ["dpkg-query", "-W", "-f=${Package}\n"], text=True,
    ).splitlines())
    for package in ("binutils", "gcc", "xvfb", "libllvm15", "libgl1-mesa-dri"):
        if package in installed:
            raise RuntimeError(f"Unnecessary system package included: {package}")
    # These imports exercise Python shared libraries copied into Debian slim.
    import ctypes
    import sqlite3
    import ssl
    import uvloop
    assert ssl.create_default_context().get_ca_certs()
    with sqlite3.connect(":memory:") as connection:
        assert connection.execute("select 638003").fetchone()[0] == 638003
    schema = app.openapi()
    for route in ("/health", "/api/v1/products/check", "/api/v1/products/batch-check"):
        if route not in schema["paths"]:
            raise RuntimeError(f"Missing API route: {route}")
    try:
        async with browser_manager.new_context() as context:
            page = await context.new_page()
            await page.set_content("<button onclick='this.textContent = 638003'>Check PIN</button>")
            await page.get_by_role("button", name="Check PIN").click()
            assert await page.get_by_role("button").inner_text() == "638003"
            assert await page.evaluate("""() => {
                const canvas = document.createElement('canvas');
                const ctx = canvas.getContext('2d');
                ctx.font = '20px sans-serif';
                ctx.fillText('PIN 638003 ₹', 0, 25);
                return ctx.getImageData(0, 0, 200, 50).data.some(value => value > 0);
            }""")
            browser_version = context.browser.version
    finally:
        await browser_manager.close()
    print(json.dumps({
        "status": "PASS",
        "uid": os.getuid(),
        "apiVersion": schema["info"]["version"],
        "chromiumVersion": browser_version,
        "playwrightVersion": version("playwright"),
    }))


asyncio.run(main())
