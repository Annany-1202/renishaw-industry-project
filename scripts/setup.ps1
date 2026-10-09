# One-time setup: Python packages, a check of the local Ollama models, and the frontend build.
# Nothing is downloaded silently: model pulls are only printed for you to run.
. "$PSScriptRoot\_common.ps1"

Write-Host "Installing Python packages into renishaw_venv ..."
& $Python -m pip install -r (Join-Path $ProjectRoot "backend\requirements.txt")
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host "`nChecking Ollama at http://localhost:11434 ..."
try {
    $tags = Invoke-RestMethod -Uri "http://localhost:11434/api/tags" -TimeoutSec 5
    $names = @($tags.models | ForEach-Object { $_.name })
    foreach ($model in @("llama3.1:8b-instruct-q4_K_M", "nomic-embed-text")) {
        if ($names -contains $model -or $names -contains "${model}:latest") {
            Write-Host "  found   $model" -ForegroundColor Green
        } else {
            Write-Host "  missing $model" -ForegroundColor Yellow
            Write-Host "  >>> RUN THIS YOURSELF (heavy download) <<<   ollama pull $model"
        }
    }
} catch {
    Write-Host "  Ollama is not running. Search still works (rules only); start Ollama for LLM help and the vector index." -ForegroundColor Yellow
}

$dist = Join-Path $ProjectRoot "frontend\dist\index.html"
if (Test-Path $dist) {
    Write-Host "`nFrontend build found."
} else {
    Write-Host "`nThe frontend has not been built. Run these yourself (npm install downloads packages):" -ForegroundColor Yellow
    Write-Host "  cd frontend"
    Write-Host "  npm install"
    Write-Host "  npm run build"
}
Write-Host "`nSetup finished. Start the application with scripts\start.ps1"
