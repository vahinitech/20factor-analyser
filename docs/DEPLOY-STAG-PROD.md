# Staging to Production Deployment

This project now supports a clean two-step rollout:

- Stage first on `stag.vahinitech.com` via local port `127.0.0.1:3016`
- Cut over later to `vahinitech.com` via local port `127.0.0.1:3015`
- Bundle PP-OCRv5 into Docker and expose OCR at `/ocr` through the web container

The reverse proxy (Hestia/nginx on host) should terminate TLS and proxy to these localhost ports.

## Files

- `deploy/docker-compose.stag.yml`
- `deploy/docker-compose.prod.yml`
- `deploy/release.sh`
- `deploy/stag.vahinitech.com.nginx.conf`
- `deploy/vahinitech.com.nginx.conf`

## 1) Deploy Staging

From repo root:

```bash
./deploy/release.sh stag
```

Verify on server:

```bash
curl -I http://127.0.0.1:3016/site/index.html
curl -I http://127.0.0.1:3016/analyser/Vahini%20Analyser.html
curl http://127.0.0.1:3016/ocr/health
```

Apply host nginx vhost using `deploy/stag.vahinitech.com.nginx.conf` and reload nginx.

## 2) Validate Staging Domain

Validate these before cutover:

- Home page, product pages, blog pages
- `analyser/Vahini Analyser.html`
- Asset links and cache headers
- Browser console errors

## 3) Cut Over to Production

Deploy production container:

```bash
./deploy/release.sh prod
```

Apply host nginx vhost using `deploy/vahinitech.com.nginx.conf` and reload nginx.

Verify:

```bash
curl -I http://127.0.0.1:3015/site/index.html
curl -I http://127.0.0.1:3015/analyser/Vahini%20Analyser.html
curl http://127.0.0.1:3015/ocr/health
```

## 4) Rollback

If production check fails:

1. Restore previous nginx vhost and reload nginx.
2. Keep previous web container running on prior port.
3. Check logs:

```bash
docker compose -f deploy/docker-compose.prod.yml logs --tail=120 web
```

## Notes

- Current server already has a service on `127.0.0.1:3015`, so staging uses `3016` to avoid collision.
- Keep API and OCR services isolated from this static site deployment.
- Current staging web container proxies `/ocr` to the existing OCR container `vahini-vd-ocr` on Docker network `app_default`.
- Host-persisted Paddle model cache is stored at `/home/vishnu/paddle-models/.paddlex`.