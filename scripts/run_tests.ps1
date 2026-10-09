# Run the automated test suite. The tests use a temporary data directory and never touch data\.
# Ollama is not needed. Extra arguments are passed to pytest, e.g.  scripts\run_tests.ps1 -k images
. "$PSScriptRoot\_common.ps1"
& $Python -m pytest @args
exit $LASTEXITCODE
