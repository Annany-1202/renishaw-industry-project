# Offline verification: runs the tests that prove nothing reaches the internet
# (socket guard on the whole suite, no external URLs in the backend or the built frontend,
# search with Ollama unreachable), then lists what the running application is listening on.
. "$PSScriptRoot\_common.ps1"
& $Python -m pytest backend/tests/test_security_offline.py -k "offline or external or local or ollama_unreachable or internet"
$code = $LASTEXITCODE
Write-Host "`nListening sockets on port 8000 (should be 127.0.0.1 only, if the application is running):"
Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue | Select-Object LocalAddress, LocalPort, OwningProcess | Format-Table
Write-Host "For a full check, disconnect the network and run scripts\run_tests.ps1 and a few searches in the browser."
exit $code
