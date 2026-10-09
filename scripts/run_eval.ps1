# Run the evaluation on a freshly ingested temporary copy of the catalogues and rewrite docs\EVALUATION.md.
#   -Llm off    rules only (no Ollama needed)
#   -Llm auto   with the local LLM
#   -Llm both   both runs (default; takes several minutes)
param([ValidateSet("off", "auto", "both")][string]$Llm = "both", [switch]$NoEmbeddings)
. "$PSScriptRoot\_common.ps1"
$extra = @()
if ($NoEmbeddings) { $extra += "--no-embeddings" }
& $Python -m backend.app.evaluation.runner --llm $Llm @extra
exit $LASTEXITCODE
