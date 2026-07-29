# Changelog

All notable changes to the Vahini 20-Factor Handwriting Analyser are
documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/); until the first
tagged release, entries are grouped by date of merge to `main`.

## 2026-07-26

### Added

- The visitor's cookie-consent state is forwarded on upload (#30).
- `CLAUDE.md` with working rules, CI facts, and architecture notes for
  AI-assisted contributions (#28).

### Fixed

- Printed reports no longer squeeze pages into overlapping text (#29).

## 2026-07-20

### Added

- Plain-language layer over the 20 factors: coach view with tips for
  parents and teachers, endurance trend, and drift direction (#22).

### Fixed

- Restored the coach-tips feature that was lost from `main` by a
  stacked-PR squash-merge (#27).

## 2026-07-08

### Added

- Writing-style detection, and flagging of words whose internal spacing
  risks reading as two words (#20).

## 2026-07-06

### Added

- Commercial licensing notice in the README (#19).
- Contributor license agreement and feature-request guidance (#14).
- A fourth "Good" scoring tier, with band wording unified across the
  report (#15).

### Fixed

- Margin Discipline corrected for camera tilt (#18, issue #16).
- Margin Discipline's evidence crop, and a false deskew claim removed
  from the report (#17).

### Changed

- Repository cleanup: dead code removed, stale docs pruned, filenames
  without spaces, folder restructure (#10).

## 2026-07-05

### Added

- Hybrid OCR pipeline: PaddleOCR detects text regions; TrOCR or Surya
  re-read handwriting depending on script; the Chandra backend was
  dropped (#7).
- Handwriting-only rule enforced: printed text never enters a report (#5).

### Fixed

- Four security findings: a Dependabot-reported RCE, CodeQL DOM-XSS
  findings, and workflow permission hardening (#8).
- End-to-end test scripts fail fast instead of hanging for hours (#9).

### Changed

- Docs cleanup and a single port (8080) everywhere; recovered the
  orange-boxes commit (#4).

## 2026-07-04

### Added

- Compact 4-page report with published reference values, and the
  deterministic-CV-over-LLM rationale documented (#2).
- Orange detection boxes restored, honest recognition captions with
  confidence percentages, simple-English wording, root redirect (#3).

### Fixed

- Scans no longer fail when the OCR recognizer cannot run; every one of
  the 20 factors is guaranteed a reference image (#1).
- SBOM generation (#2).

## 2026-06-30

### Added

- Initial public release of the Vahini 20-Factor Handwriting Analyser
  under AGPL-3.0: FastAPI backend (`/ocr`, `/analyze-vl`,
  `/report-python`), browser frontend, Docker Compose deployment, and
  tiered OCR backends selected by `VAHINI_OCR_BACKEND`.
