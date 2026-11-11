"""Cache and resume official Playwright archives, then use its own installer."""
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from threading import Thread
import time
from urllib.error import HTTPError
from urllib.request import Request, urlopen
import zipfile

import playwright


def download(path, cache, origins=(
    'https://cdn.playwright.dev/',
    'https://playwright.download.prss.microsoft.com/dbazure/download/playwright/',
)):
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        return
    pending = path.with_suffix(path.suffix + '.part')
    relative = path.relative_to(cache).as_posix()
    urls = tuple(origin + relative for origin in origins)
    total = None
    failures = 0
    while total is None or not pending.exists() or pending.stat().st_size < total:
        offset = pending.stat().st_size if pending.exists() else 0
        request = Request(urls[failures % len(urls)], headers={
            'Range': f'bytes={offset}-{offset + 2 * 1024 * 1024 - 1}',
            'Accept-Encoding': 'identity',
        })
        try:
            with urlopen(request, timeout=120) as response:
                if response.status == 206:
                    matched = re.fullmatch(r'bytes (\d+)-(\d+)/(\d+)', response.headers.get('Content-Range', ''))
                    if not matched or int(matched[1]) != offset:
                        raise RuntimeError('The download server returned an unexpected byte range.')
                    total = int(matched[3])
                    mode = 'ab'
                elif response.status == 200:
                    total = int(response.headers['Content-Length'])
                    mode = 'wb'
                else:
                    raise RuntimeError(f'Unexpected download status: {response.status}')
                with pending.open(mode) as output:
                    while chunk := response.read(65536):
                        output.write(chunk)
            completed = pending.stat().st_size
            print(f'{path.name}: {completed}/{total} bytes ({completed * 100 // total}%)', flush=True)
            if completed == offset:
                raise RuntimeError('The download made no progress.')
        except Exception as error:
            if isinstance(error, HTTPError) and error.code == 416:
                matched = re.fullmatch(r'bytes \*/(\d+)', error.headers.get('Content-Range', ''))
                if matched and pending.exists() and pending.stat().st_size == int(matched[1]):
                    total = int(matched[1])
                    break
            failures += 1
            print(f'Download interrupted; cached bytes retained. Attempt {failures}: {type(error).__name__}', flush=True)
            if failures >= 12:
                raise
            time.sleep(min(failures * 5, 30))
    if pending.stat().st_size != total:
        raise RuntimeError('The downloaded archive size does not match the server response.')
    try:
        with zipfile.ZipFile(pending) as archive:
            if archive.testzip() is not None:
                raise zipfile.BadZipFile('Browser archive failed its ZIP integrity check; retry the build.')
    except zipfile.BadZipFile:
        pending.unlink()
        raise
    pending.replace(path)


def main():
    cache = Path('/root/.cache/playwright-downloads')
    metadata = Path(playwright.__file__).parent / 'driver' / 'package' / 'browsers.json'
    browsers = {item['name']: item for item in json.loads(metadata.read_text())['browsers']}
    for name, directory, filename in (
        ('chromium-headless-shell', 'chromium', 'chromium-headless-shell-linux.zip'),
        ('ffmpeg', 'ffmpeg', 'ffmpeg-linux.zip'),
    ):
        revision = browsers[name]['revision']
        download(cache / 'builds' / directory / revision / filename, cache)

    handler = partial(SimpleHTTPRequestHandler, directory=str(cache))
    server = ThreadingHTTPServer(('127.0.0.1', 0), handler)
    Thread(target=server.serve_forever, daemon=True).start()
    environment = dict(os.environ, PLAYWRIGHT_DOWNLOAD_HOST=f'http://127.0.0.1:{server.server_port}')
    try:
        subprocess.run([sys.executable, '-m', 'playwright', 'install', '--only-shell', 'chromium'], env=environment, check=True)
    finally:
        server.shutdown()
        server.server_close()


if __name__ == '__main__':
    main()
