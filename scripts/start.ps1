# Start the application on http://127.0.0.1:8000 (this computer only).
# On the first start the two supplied catalogues are ingested in the background (about 2-3 minutes);
# watch the Documents page until both show "Ready".
param([int]$Port = 8000)
. "$PSScriptRoot\_common.ps1"

if (-not (Test-Path (Join-Path $ProjectRoot "frontend\dist\index.html"))) {
    Write-Host "frontend\dist is missing, so only the API will be served. Build it with: cd frontend; npm run build" -ForegroundColor Yellow
}
Write-Host "Open http://127.0.0.1:$Port in your browser. Press Ctrl+C to stop."
& $Python -m uvicorn backend.app.main:app --host 127.0.0.1 --port $Port
