# Renishaw Technical Catalogue Retrieval

An offline web application: describe a Renishaw stylus or accessory in plain English and get
evidence-backed catalogue results — exact matches, ranked alternatives, or a clear "no suitable
product". Every result names its source document and page and shows the verified catalogue images.

Everything runs on this computer. The only service used is a local Ollama (`http://localhost:11434`),
and search still works without it.

## Set up from a fresh clone

The repository contains the code only. Four things are **not** in it and must be supplied on your
machine: the two catalogue PDFs, the Python virtual environment, the frontend build, and the Ollama
models. Run every command in **PowerShell** from the repository root.

### 1. What you need installed

- Windows with PowerShell
- Python 3.11 or newer
- Node.js 18 or newer (to build the frontend)
- [Ollama](https://ollama.com) — optional but recommended; without it queries are read by rules only

### 2. Files you must add yourself

The Renishaw catalogues are copyrighted and are not distributed with this repository. Get the two
PDFs from Renishaw and paste them into the `source_pdfs\` folder with **exactly** these names:

```
source_pdfs\Styli_for_ZEISS_applications_H-1000-3036_EN.pdf
source_pdfs\H-1000-3200_Styli_and_accessories_technical_specifications_guide_EN.pdf
```

Nothing else needs to be copied anywhere. The `data\` folder (database, extracted images, search
index) is created automatically on first start.

If you do not have these PDFs you can still start the app and upload any PDF catalogue from the
Documents page; the automatic first-start ingestion is simply skipped.

### 3. Create the virtual environment and install the Python packages

The scripts expect the environment to be named `renishaw_venv` in the repository root.

```powershell
python -m venv renishaw_venv
```

```powershell
powershell -ExecutionPolicy Bypass -File scripts\setup.ps1
```

`setup.ps1` installs `backendequirements.txt`, checks Ollama and its models, and tells you if the
frontend still needs building.

### 4. Pull the Ollama models (optional, large downloads)

```powershell
ollama pull llama3.1:8b-instruct-q4_K_M
```

```powershell
ollama pull nomic-embed-text
```

### 5. Build the frontend

```powershell
cd frontend
```

```powershell
npm install
```

```powershell
npm run build
```

```powershell
cd ..
```

### 6. Start the application

```powershell
powershell -ExecutionPolicy Bypass -File scripts\start.ps1
```

Open http://127.0.0.1:8000 in your browser.

On the very first start the two catalogues in `source_pdfs\` are ingested in the background (about
2–3 minutes with embeddings). Open the **Documents** page and wait until both show **Ready**, then
search. Later starts are immediate.

Step-by-step commands, example search prompts with their expected results, and troubleshooting are in
[how_to_run.md](how_to_run.md).

To start without the script:

```powershell
$env:PYTHONPATH = (Get-Location)
renishaw_venv\Scripts\python.exe -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000
```

### What is not in the repository

| Not committed | Why | How you get it |
|---|---|---|
| `source_pdfs\*.pdf` | copyrighted catalogues | paste your own copies (step 2) |
| `renishaw_venv\` | machine-specific | step 3 |
| `frontend
ode_modules\`, `frontend\dist\` | build output | step 5 |
| `data\` | generated from the PDFs | created on first start |

## Test and evaluate

```powershell
scripts\run_tests.ps1          # 180 automated tests, about 1–2 minutes, no Ollama needed
scripts\run_eval.ps1           # 135-query evaluation, rewrites docs\EVALUATION.md (several minutes)
scripts\run_eval.ps1 -Llm off  # rules-only evaluation, no Ollama needed
scripts\verify_offline.ps1     # offline checks
```

Tests and the evaluation use a temporary data directory; they never modify `data\`. Both need the
two catalogue PDFs in `source_pdfs\`.

## Using it

- **Search**: type a description, e.g. `M2 stylus with 2 mm ruby ball, 20 mm long`. The panel
  "How your request was read" shows each extracted attribute. Click a value to edit it, the lock to
  switch between mandatory and flexible, or × to remove it; the same search is run again.
- **Result classes**: *Exact match* (every requested attribute is verified in the catalogue record),
  *Related alternatives* (all mandatory requirements hold, differences are listed), *Insufficient
  evidence*, *No suitable product found*, *Outside the catalogue*.
- **Clarification**: when a request cannot be searched reliably (no thread or probe, "long", two
  different threads) one question is asked; the answer refines the same search.
- **Details**: full specification, requested-vs-catalogue table, every source, and the image gallery
  (← → keys, click to enlarge).
- **Documents**: drop a PDF to add it, expand a row for its ingestion report, delete with a
  confirmation that lists what will be removed. Failed documents can be retried.
- **Settings**: system status, ranking weights and thresholds (validated and kept after restart),
  and maintenance (Reconcile, Reindex, Restore supplied catalogues).

## How it decides

1. A rule-based parser extracts dimensions, units, threads, materials, product type and probe model.
   The local LLM is asked only about wording the rules cannot read; it can never change a value the
   rules found, add a number the user did not type, relax a mandatory requirement, or bring a request
   into scope on its own.
2. Requests about products outside the catalogues are rejected before any search.
3. Every record of the `Ready` documents is compared attribute by attribute. A record that does not
   state an attribute is "not stated", never a match.
4. Thread and an explicitly named product type are mandatory by default. A record violating a
   mandatory requirement is never shown, whatever its score.
5. Exact = every requested attribute matches. Otherwise alternatives are ranked with the weighted
   score from the specification and must pass the minimum score and closeness rules. Nothing is
   padded.

Details and the reasons for each rule: `docs/DECISIONS.md`. Data findings: `docs/DATA_AUDIT.md`.
Measured results: `docs/EVALUATION.md`.

## Configuration

Defaults live in `backend/app/core/config.py`. Override with environment variables prefixed
`RENISHAW_`, for example:

| Variable | Meaning | Default |
|---|---|---|
| `RENISHAW_DATA_DIR` | where the database, images, index and uploads are kept | `data` |
| `RENISHAW_LLM_MODE` | `auto`, `always` or `off` | `auto` |
| `RENISHAW_EMBEDDINGS_ENABLED` | build and use the vector index | `true` |
| `RENISHAW_MAX_UPLOAD_SIZE_MB` | upload limit | `100` |
| `RENISHAW_AUTO_INGEST_SOURCE_PDFS` | ingest the supplied catalogues on first start | `true` |

A wrongly associated image can be corrected without code: put
`{"<image_id>|<part_number>": "rejected"}` (or `verified` / `unverified`) in
`data\image_overrides.json` and re-ingest the document. The image ids are in the document's
"Image associations (CSV)" download.

## Layout

```
backend/app/ingestion    PDF extraction (two catalogue-specific extractors, one generic), validation, pipeline
backend/app/llm          Ollama client, query interpretation, embeddings
backend/app/matching     scoring, hard constraints, relevance gate, engine, explanations
backend/app/lifecycle    background ingestion jobs, deletion state machine, reconciliation
backend/app/api          HTTP routes
backend/app/evaluation   evaluation query set and runner
backend/tests            automated tests
frontend/                React + TypeScript UI (built into frontend/dist)
scripts/                 PowerShell scripts
docs/                    audit, decisions, evaluation, progress
```

## Known limitations

See the end of `docs/EVALUATION.md` and `docs/PROGRESS.md`. In short: extraction is verified against
the PDFs by sample, not exhaustively; 49 records are flagged for review; 134 products have no
associated image; uploaded PDFs of unknown layout are read conservatively (ruled tables with a
part-number column); there are no frontend unit tests.
