"""Verify recovery from actual HTTP connection truncation during image builds."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import importlib.util
from io import BytesIO
import os
from pathlib import Path
from threading import Thread
import zipfile

import pytest

spec = importlib.util.spec_from_file_location(
    'browser_installer', Path(__file__).parents[1] / 'scripts' / 'install-browser.py',
)
installer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(installer)


@pytest.mark.parametrize('ignore_range', [False, True])
def test_resumes_interrupted_http_download(tmp_path, ignore_range):
    payload = BytesIO()
    with zipfile.ZipFile(payload, 'w') as archive:
        archive.writestr('browser', os.urandom(150000))
    data = payload.getvalue()
    offsets = []

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            start = int(self.headers['Range'].split('=')[1].split('-')[0])
            offsets.append(start)
            if ignore_range:
                start = 0
                self.send_response(200)
            else:
                self.send_response(206)
                self.send_header('Content-Range', f'bytes {start}-{len(data) - 1}/{len(data)}')
            self.send_header('Content-Length', str(len(data) - start))
            self.end_headers()
            # Close the first connection before the advertised response ends.
            self.wfile.write(data[start:70000] if len(offsets) == 1 else data[start:])
            self.wfile.flush()
            self.close_connection = True

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    Thread(target=server.serve_forever, daemon=True).start()
    target = tmp_path / 'builds' / 'browser.zip'
    try:
        installer.download(target, tmp_path, (f'http://127.0.0.1:{server.server_port}/',))
    finally:
        server.shutdown()
        server.server_close()
    assert offsets == [0, 70000]
    assert target.read_bytes() == data
    assert not target.with_suffix('.zip.part').exists()


def test_rejects_corrupt_archive_and_clears_partial_cache(tmp_path, monkeypatch):
    response = BytesIO(b'invalid zip')
    response.status = 200
    response.headers = {'Content-Length': str(len(response.getvalue()))}
    monkeypatch.setattr(installer, 'urlopen', lambda *args, **kwargs: response)
    target = tmp_path / 'browser.zip'
    with pytest.raises(zipfile.BadZipFile):
        installer.download(target, tmp_path)
    assert not target.exists()
    assert not target.with_suffix('.zip.part').exists()
