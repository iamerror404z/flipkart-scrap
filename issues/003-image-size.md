# Docker runtime includes unnecessary browser dependencies and debug symbols

Date: 2026-11-11
Status: Optimization implemented; final image measurements and verification pending.

The 1.0.1 image stores 346 MB of compressed content and about 986 MB of
uncompressed filesystem layers. Docker Desktop reports about 1.33 GB for both
forms together. The biggest layers are the browser (343 MB), system browser
dependencies (315 MB), and Python runtime packages (190 MB).

Playwright's broad Chromium dependency installer includes packages unnecessary
for this packaged headless shell, including LLVM/Mesa and Xvfb. The official
browser and Node binaries, plus Python extensions, carry large symbol/debug
sections. Runtime files inherited the full dependency installation stage.

The revised Dockerfile uses a separate builder, installs only runtime wheels
into a pip-free venv, strips ELF symbols, and prunes caches/build files before
copying to a Debian slim runtime. That runtime installs an explicit library
list with no recommended packages and removes apt indexes/docs/localized OS
messages in the same layer. Only Chromium's headless shell and its FFmpeg
dependency are installed. The HTTP/product parsing and browser/PIN behavior
are unchanged. See `docs/image-size.md` for full measurements and comparisons.
