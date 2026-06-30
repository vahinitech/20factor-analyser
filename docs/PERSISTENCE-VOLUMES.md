# Persistence Volumes (Uploads, Reports, Feedback)

This setup stores analyser artifacts on host-mounted folders so data survives container restarts.

## Host folders

- Upload images: `/home/vishnu/uploads`
- Generated reports: `/home/vishnu/reports`
- Feedback/lead records: `/home/vishnu/feedback`

## Services

A new internal service `persist` runs at `persist:8090` inside Docker.

Nginx routes:

- `POST /persist/upload-image`
- `POST /persist/generated-report`
- `POST /persist/feedback`
- `GET /persist/health`

## What gets saved

1. Uploaded image

- Binary image file + metadata JSON are written to `/home/vishnu/uploads`.

2. Generated report

- Report snapshot JSON and HTML are written to `/home/vishnu/reports`.

3. Feedback and PDF lead

- Individual JSON files + daily NDJSON stream are written to `/home/vishnu/feedback`.

## Deploy

```bash
cd /home/vishnu/web-live
mkdir -p /home/vishnu/uploads /home/vishnu/reports /home/vishnu/feedback
./deploy/release.sh stag
```

## Verify

```bash
curl -s http://127.0.0.1:3016/persist/health
```

After using the analyser once (upload + generate report + print/report lead):

```bash
ls -la /home/vishnu/uploads | tail -n 5
ls -la /home/vishnu/reports | tail -n 5
ls -la /home/vishnu/feedback | tail -n 10
```
