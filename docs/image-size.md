# Docker image size

All measurements are for Linux AMD64. MB means decimal megabytes.
`docker history --human=false` reports uncompressed filesystem layer sizes.
OCI manifest layer descriptors report compressed blob sizes. Docker Desktop's
DISK USAGE combines stored compressed content and unpacked layers; it is not
the unpacked size alone. Shared layers also mean two image sizes cannot simply
be added to predict Docker's total storage use.

## Original 1.0.1 layers

Measured with `docker history --no-trunc --human=false` and the private
registry's AMD64 manifest. Metadata-only instructions contribute zero bytes.

| Layer, oldest first | Uncompressed | Compressed |
|---|---:|---:|
| Debian base | 85.303 MB | 28.248 MB |
| CA certificates, netbase, tzdata | 9.679 MB | 3.342 MB |
| Python runtime | 41.615 MB | 12.612 MB |
| Python command symlinks | 0.016 MB | <0.001 MB |
| Working directory | 0.008 MB | <0.001 MB |
| Requirements file | 0.012 MB | <0.001 MB |
| Python runtime packages | 190.398 MB | 62.132 MB |
| Browser system libraries and fonts | 315.314 MB | 124.712 MB |
| Headless Chromium and FFmpeg | 343.097 MB | 114.576 MB |
| Non-root account | 0.070 MB | 0.003 MB |
| Application source | 0.106 MB | 0.014 MB |
| **Total layers** | **985.620 MB** | **345.639 MB** |

The largest uncompressed layer is the browser. The largest compressed layer
is the broad browser system dependency installation. It brought in LLVM
(about 117 MB installed), Mesa drivers, Xvfb, system ICU, and several font
packs. Chromium also contained 126 MB of symbol/string tables. Playwright's
Node binary contained 16 MB of debug/symbol data, and uvloop contained 14 MB.

## Runtime build

The builder installs wheels into `/opt/venv` with `--no-cache-dir` and
`--no-compile`, using its own pip. The copied venv has no pip or test tooling.
ELF symbols are stripped with `strip --strip-unneeded`; dynamic symbols and
runtime resources remain. Python caches, development headers, TypeScript
declarations, and source maps are removed before files enter runtime layers.

The final stage starts from `debian:bookworm-slim` and copies only the cleaned
Python installation, venv, headless browser, dependency record, and app.
System packages are an explicit shared-library list, installed with
`--no-install-recommends`. Apt indexes, documentation, manuals, and translated
OS messages are removed in the same installation layer. C.UTF-8, CA
certificates, time-zone data, DejaVu font fallback, Chromium ICU/resources,
bundled graphics libraries, and FFmpeg remain. No Mesa/LLVM, Xvfb, headed
Chromium, Firefox, or WebKit is installed.

The `.dockerignore` uses an allowlist, excluding Git metadata, environment
files, venvs, tests, logs, node_modules, caches, and release archives.

## Browser requirement

Product HTML, metadata, price, image, and stock use httpx plus BeautifulSoup.
Health and documentation do not launch the lazy browser. Both single-product
and batch delivery checks use Playwright to apply and verify the requested
PIN through Flipkart's JavaScript address/map flow. This optimization preserves
that behavior; it does not introduce an HTTP-only delivery path or skip
delivery checks when stock is unavailable.

## Base alternatives

| Base | Assessment |
|---|---|
| Debian slim | glibc environment matching the official Playwright headless shell; explicit apt libraries and a compatible Python 3.13 runtime. Selected for this release. |
| Distroless | Can reduce OS utilities, but still needs Python 3.13, Node, Chromium, fonts, certificates, and their dynamic-library closure. Official Python distroless images do not provide this exact runtime. Requires a separate build and validation; no size or compatibility claim is made here. |
| Alpine | Uses musl; the official Playwright Linux Chromium and Node artifacts target glibc. A distro Chromium or compatibility shim would change the deployment assumptions. Not built or benchmarked, and not selected without a working verified replacement. |

Changing browser versions, removing the browser/Node, changing delivery logic,
or removing Chromium graphics/ICU resources could affect functionality and is
outside this packaging optimization.
