#!/usr/bin/env bash
# SPDX-License-Identifier: AGPL-3.0-only
# (c) 2026 Vahini Technologies.
#
# setup.sh — one-command CPU setup for the Vahini analyser OCR service (Linux/Mac).
#
# Creates .venv at the REPO ROOT, installs the core service + chosen engine
# tiers, then pre-downloads models. Examples:
#   ./analyser/server/setup.sh                  # core + paddle (default)
#   ./analyser/server/setup.sh paddle trocr     # + English handwriting
#   ./analyser/server/setup.sh all              # paddle + trocr + surya
#   NO_DOWNLOAD=1 ./analyser/server/setup.sh    # skip model warm-up
#
# Chandra on a CPU-only box: use the hosted API (no install) —
#   export VAHINI_OCR_BACKEND=chandra VAHINI_CHANDRA_METHOD=api DATALAB_API_KEY=...
set -euo pipefail

SERVER_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SERVER_DIR/../.." && pwd)"
VENV_DIR="$REPO_ROOT/.venv"
PY="$VENV_DIR/bin/python"

ENGINES=("$@")
[ ${#ENGINES[@]} -eq 0 ] && ENGINES=("paddle")
if [ "${ENGINES[0]}" = "all" ]; then ENGINES=(paddle trocr surya); fi

echo "Repo root : $REPO_ROOT"
echo "Venv      : $VENV_DIR"
echo "Engines   : ${ENGINES[*]}"

if [ ! -x "$PY" ]; then
  echo "[1/4] Creating virtual environment..."
  python3 -m venv "$VENV_DIR"
fi

echo "[2/4] Upgrading pip..."
"$PY" -m pip install --upgrade pip --disable-pip-version-check

echo "[3/4] Installing core + engine tiers..."
"$PY" -m pip install -r "$SERVER_DIR/requirements-core.txt"
for e in "${ENGINES[@]}"; do
  req="$SERVER_DIR/requirements-$e.txt"
  if [ -f "$req" ]; then
    echo "  -> $e"
    if [ "$e" = "trocr" ]; then
      "$PY" -m pip install torch --index-url https://download.pytorch.org/whl/cpu
    fi
    "$PY" -m pip install -r "$req"
  else
    echo "  !! no tier file for '$e' (skipped)"
  fi
done

if [ "${NO_DOWNLOAD:-0}" != "1" ]; then
  echo "[4/4] Downloading / warming models (first time is slow)..."
  VAHINI_WARMUP_ENGINES="$(IFS=,; echo "${ENGINES[*]}")" "$PY" "$SERVER_DIR/warmup_models.py"
else
  echo "[4/4] Skipped model download (NO_DOWNLOAD=1)."
fi

echo
echo "Done. Start the service with:"
echo "  VAHINI_OCR_BACKEND=paddle \"$PY\" \"$SERVER_DIR/ppocr-server.py\""
