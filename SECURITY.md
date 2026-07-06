# Security Policy

## Reporting a vulnerability

Please report security issues **privately**. Do not open a public issue for a
vulnerability.

- Preferred: open a private security advisory via GitHub
  ("Security" tab → "Report a vulnerability") on
  https://github.com/vahinitech/20factor-analyser
- Or email: **info@vahinitech.com** with the subject `SECURITY:`

Include a description, reproduction steps, affected version/commit, and impact.
We aim to acknowledge within 5 business days and to provide a remediation
timeline after triage. Please give us reasonable time to fix before any public
disclosure.

## Scope

- The browser engine and app (`frontend/`).
- The Python OCR / 20-factor server (`backend/`).
- Deployment config (`deployment/`, `docker-compose.yml`).

## Handling user data

This project processes handwriting images, which can be sensitive.

- Do not commit real user images. `samples/` is git-ignored; CI fixtures are
  synthetic.
- Every supported OCR backend (`paddle`, `trocr`, `surya`, `hybrid`) runs
  locally; no image data leaves the machine.
- Never put personal data or secrets in URLs, logs, issues, or commits.
