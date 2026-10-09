# Ingest the two supplied catalogues from source_pdfs\ if they are not in the library yet.
# (The application does this by itself on first start; this script is for running it by hand.)
. "$PSScriptRoot\_common.ps1"
& $Python -m backend.app.ingestion.pipeline
exit $LASTEXITCODE
