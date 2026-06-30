# SPDX-License-Identifier: AGPL-3.0-only
# (c) 2026 Vahini Technologies.
#
# setup.ps1 — one-command CPU setup for the Vahini analyser OCR service (Windows).
#
# Creates .venv at the REPO ROOT, installs the core service + the engine tiers
# you choose, then pre-downloads the models so the first request is fast.
#
# Examples (run from anywhere):
#   .\analyser\server\setup.ps1                       # core + paddle (default)
#   .\analyser\server\setup.ps1 -Engines paddle,trocr # + English handwriting
#   .\analyser\server\setup.ps1 -Engines all          # paddle + trocr + surya
#   .\analyser\server\setup.ps1 -NoDownload           # skip model warm-up
#
# Chandra on a CPU-only box: use the hosted API (no install) —
#   $env:VAHINI_OCR_BACKEND="chandra"; $env:VAHINI_CHANDRA_METHOD="api"; $env:DATALAB_API_KEY="..."
param(
    [string[]] $Engines = @("paddle"),
    [switch]   $NoDownload
)
$ErrorActionPreference = "Stop"

$ServerDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot  = Resolve-Path (Join-Path $ServerDir "..\..")
$VenvDir   = Join-Path $RepoRoot ".venv"
$Py        = Join-Path $VenvDir "Scripts\python.exe"

Write-Host "Repo root : $RepoRoot"
Write-Host "Venv      : $VenvDir"
Write-Host "Engines   : $($Engines -join ', ')"

if (-not (Test-Path $Py)) {
    Write-Host "`n[1/4] Creating virtual environment..."
    python -m venv $VenvDir
}

Write-Host "`n[2/4] Upgrading pip..."
& $Py -m pip install --upgrade pip --disable-pip-version-check

if ($Engines -contains "all") { $Engines = @("paddle", "trocr", "surya") }

Write-Host "`n[3/4] Installing core + engine tiers..."
& $Py -m pip install -r (Join-Path $ServerDir "requirements-core.txt")
foreach ($e in $Engines) {
    $req = Join-Path $ServerDir "requirements-$e.txt"
    if (Test-Path $req) {
        Write-Host "  -> $e"
        if ($e -eq "trocr") {
            # CPU torch wheels keep the download small and avoid CUDA.
            & $Py -m pip install torch --index-url https://download.pytorch.org/whl/cpu
        }
        & $Py -m pip install -r $req
    } else {
        Write-Host "  !! no tier file for '$e' (skipped)"
    }
}

if (-not $NoDownload) {
    Write-Host "`n[4/4] Downloading / warming models (first time is slow)..."
    $env:VAHINI_WARMUP_ENGINES = ($Engines -join ",")
    & $Py (Join-Path $ServerDir "warmup_models.py")
} else {
    Write-Host "`n[4/4] Skipped model download (-NoDownload)."
}

Write-Host "`nDone. Start the service with:"
Write-Host "  `$env:VAHINI_OCR_BACKEND=`"paddle`"   # or trocr|surya|chandra|auto"
Write-Host "  & `"$Py`" `"$ServerDir\ppocr-server.py`""
