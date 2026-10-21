# SPDX-License-Identifier: AGPL-3.0-only
# (c) 2026 Vahini Technologies.
"""The parts of the 20-factor model behind scoring.py.

scoring.py stays the entry point: it holds the factor catalogue and
build_analysis, and re-exports the names other modules import from it.
The parts, in the order a page passes through them:

- page.py: rows of lines and the page's camera tilt
- features.py: the measurements (fx) taken from the page
- structure.py, spatial.py, dynamics.py, style.py: the factor formulas,
  one file per report section
- availability.py: which factors this page cannot measure, and why
- advisory.py: zone, cross-bar, writing-style and finishing-letter
  checks, the baseline drift note and coach tips
- results.py, stats.py: the result dataclasses and small statistics
"""
