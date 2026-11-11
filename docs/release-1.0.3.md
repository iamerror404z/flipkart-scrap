# Version 1.0.3 — 11 November 2026

Published image: `iamerror404/flipkart-scraper:1.0.3` (Linux AMD64).

Registry digest:
`sha256:6a4315b5233e462af912a21eb306f3073ed0c82527bf6ba856d9d6b03d4e4d76`.

Local image ID:
`sha256:8ed150d4ef0b341f11c12a1a1c6072f25f4bb44521f4386fd577d5a421365762`.
Uncompressed image size: 478,497,433 bytes.

Includes the cloud HTTP, guest PIN selection, delivery and batch response
fixes, plus sequential processing across all product checks in one worker.
API/OpenAPI and image label versions are both 1.0.3. Build helper, Compose
defaults and deployment instructions use the same release version.

The image was built on the VM and passed the non-root API/Chromium smoke
check with Playwright 1.54.0 and Chromium 139.0.7258.5. The sequential code
had passed 97 tests (1 skipped) and two simultaneous real API calls before
this version-only update; the live responses are retained in
[cloud-serial-verification.json](cloud-serial-verification.json).

`docker push` completed successfully, then `docker pull` verified that the
registry tag resolves to the digest above. Docker Hub metadata reported the
existing repository as public. Publication was explicitly requested to that
repository; its visibility was not changed. The `latest` tag was not pushed.

```bash
docker pull iamerror404/flipkart-scraper:1.0.3
docker run -d --name flipkart-v103 --init --restart unless-stopped \
  --memory 2g --shm-size 1g -p 8082:8000 iamerror404/flipkart-scraper:1.0.3
```

Port 8082 allows this container to run alongside the systemd API on 8081.
Recreate existing containers to deploy the new version.
