# Shared helpers for the project scripts. Dot-source this file: . "$PSScriptRoot\_common.ps1"
$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $ProjectRoot "renishaw_venv\Scripts\python.exe"
if (-not (Test-Path $Python)) {
    Write-Host "The virtual environment 'renishaw_venv' was not found in $ProjectRoot." -ForegroundColor Red
    Write-Host "Create it once with:  python -m venv renishaw_venv   then run scripts\setup.ps1"
    exit 1
}
Set-Location $ProjectRoot
$env:PYTHONPATH = $ProjectRoot
$env:ANONYMIZED_TELEMETRY = "False"
