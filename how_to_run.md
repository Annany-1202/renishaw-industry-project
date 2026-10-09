# How to run the project

Run every command in **PowerShell**, in the order given. Steps 1–4 are one-time setup; after that you
only need step 5 to start the app.

## 1. Go to the project folder

```powershell
cd E:\renishaw_industry_project\renishaw_ind_pro_v1
```

## 2. Install the Python packages (one time)

This uses the existing `renishaw_venv`. It also checks Ollama and the frontend build and tells you if
anything is missing.

```powershell
powershell -ExecutionPolicy Bypass -File scripts\setup.ps1
```

## 3. Start Ollama and make sure the two models are installed (optional but recommended)

Ollama normally starts with Windows. Check which models you have:

```powershell
ollama list
```

You should see `llama3.1:8b-instruct-q4_K_M` and `nomic-embed-text`. If one is missing, pull it
(large downloads, internet needed once):

```powershell
ollama pull llama3.1:8b-instruct-q4_K_M
```

```powershell
ollama pull nomic-embed-text
```

The app still works without Ollama: queries are then read by rules only, and the vector index is
skipped.

## 4. Build the frontend (only if `frontend\dist` is missing)

On the original machine a build already exists, so this step can be skipped there. If you cloned the
project from GitHub the build is not included and this step is required. Also run it after you change
frontend code, or whenever `setup.ps1` reports that the frontend has not been built.

If you cloned from GitHub, first follow "Set up from a fresh clone" in `README.md`: it explains which
PDF files to paste into `source_pdfs\` and how to create `renishaw_venv`.

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

## 5. Start the application

```powershell
powershell -ExecutionPolicy Bypass -File scripts\start.ps1
```

Leave this window open. Then open this address in your browser:

```
http://127.0.0.1:8000
```

**First start only:** if the catalogues have not been ingested yet, the app ingests the two supplied
PDFs in the background (about 2–3 minutes). Open the **Documents** page and wait until both documents
show **Ready** before searching. On later starts they are ready immediately.

To stop the app, press `Ctrl+C` in the PowerShell window.

To use another port:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\start.ps1 -Port 8010
```

## 6. Check that everything works (optional)

Open a **second** PowerShell window in the project folder for these. They use a temporary data
folder and do not change your data.

Run the automated tests (about 1–2 minutes, expected result: `180 passed`):

```powershell
powershell -ExecutionPolicy Bypass -File scripts\run_tests.ps1
```

Run the 135-query evaluation and regenerate `docs\EVALUATION.md` (several minutes):

```powershell
powershell -ExecutionPolicy Bypass -File scripts\run_eval.ps1
```

Run the offline checks:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\verify_offline.ps1
```

---

## Example prompts to try

Type these into the search box on the **Search** page. The "What you should see" column is what the
app returned when these were run against the two supplied catalogues.

### Exact matches

| Prompt | What you should see |
|---|---|
| `M2 stylus with 2 mm ruby ball, 20 mm long` | 3 exact matches, first is `A-5000-3603` |
| `M2 stylus with 2 mm ruby ball, tungsten carbide stem, 20 mm long` | 1 exact match: `A-5003-3822`, with 2 images (one from each catalogue) |
| `M4 stylus 6 mm ruby ball 50 mm long` | 4 exact matches, all M4 / ruby / 6 mm / 50 mm |
| `M3 stylus 3mm ruby ball 21 mm long stainless steel stem` | 1 exact match: `A-5000-3553` |
| `M5 silicon nitride ball 5 mm stylus` | exact matches from the ZEISS catalogue |
| `M3 extension 50 mm long` | 3 exact matches, from both catalogues |
| `carbon fibre extension M5 100 mm` | 5 exact matches |
| `M5 knuckle` | 6 exact matches (first 5 shown) |
| `M3 to M2 adaptor` | 3 exact matches |
| `datum ball` | exact matches with the note "No associated image" |

### Units, synonyms and informal wording

| Prompt | What you should see |
|---|---|
| `M5 stylus with 0.08 inch ruby ball` | exact matches with a 2 mm ball; the details explain the inch conversion |
| `M2 stylus 2 cm long with 2 mm ruby ball` | same as 20 mm long |
| `M2 probe tip, 2mm ruby, 20mm long, TC stem` | `A-5003-3822` ("probe tip" = stylus, "TC" = tungsten carbide) |
| `M2 2mm ruby 20mm long tc` | `A-5003-3822` |
| `need a touch probe tip, 2mm red gem end, M2, 20 mm long` | exact matches; this one uses the local LLM, so it takes a few seconds |

### Part numbers

| Prompt | What you should see |
|---|---|
| `A-5000-3603` | that product |
| `602030-8005-000` | `A-5003-3822` (found by its ZEISS order number) |
| `A-9999-9999` | "Part number … is not in the indexed catalogues" |

### Probe model instead of a thread

| Prompt | What you should see |
|---|---|
| `Stylus for TP20 with 3 mm ruby ball` | M2 styli; the thread is inferred from the probe and shown as an assumption |
| `stylus for REVO 2 mm ball` | a question: M2 or M3? Click one to continue |

### Alternatives (no exact match exists)

| Prompt | What you should see |
|---|---|
| `M2 stylus 2.2 mm ruby ball 20 mm long` | "Related alternatives", each listing how it differs, all M2 styli |
| `M2 stylus with 2 mm ruby ball, 21.5 mm long` | alternatives close in length |

### Clarification and conflicts

| Prompt | What you should see |
|---|---|
| `Stylus for my probe` | asks which probe or thread; click `M2` to refine the same search |
| `long stylus` | asks for an approximate length and thread |
| `M2 stylus 4mm` | asks whether 4 mm is the ball diameter or the length |
| `M5 extension with 5mm ruby ball` | explains that an extension has no ball and offers two choices |
| `M2 and M3 stylus with 2 mm ball` | conflict: asks which thread applies |

### No suitable product

| Prompt | What you should see |
|---|---|
| `M7 stylus 2 mm ruby ball` | no product; says no indexed product has an M7 thread |
| `M2 stylus 2 mm ruby ball 500 mm long` | no suitable product found |
| `M4 stylus 6mm ruby ball ceramic stem 51 mm long, length must be exact` | no suitable product (length was made mandatory) |

### Irrelevant requests (should be rejected, no products)

| Prompt | What you should see |
|---|---|
| `gaming laptop with 2 mm ruby ball and M5 thread` | "Outside the catalogue" |
| `bicycle with M5 thread` | "Outside the catalogue" |
| `what is the weather today` | "Outside the catalogue" |
| `asdf qwer zxcv` | "Outside the catalogue" |
| `tell me a joke` | "Outside the catalogue" |

### Things to try in the interface

- After any search, in the panel **"How your request was read"**: click a value to edit it, click the
  lock to switch between *must* and *flexible*, or click × to remove an attribute. The search reruns.
- Click **Details** on a result to see the requested-vs-catalogue table, the sources, and the image
  gallery. Use the ← → keys to move between images and click an image to enlarge it.
- Tick **Compare** on two or more results, then press **Compare**.
- **Documents** page: drop a PDF catalogue to add it, expand a row to see its ingestion report, and use
  the bin icon to delete a document (a confirmation lists what will be removed).
- **Settings** page: check the Ollama, database and vector-index status; change ranking weights; run
  *Reconcile*, *Reindex* or *Restore supplied catalogues*.

---

## If something goes wrong

| Problem | What to do |
|---|---|
| "running scripts is disabled on this system" | Use the commands exactly as written above (they include `-ExecutionPolicy Bypass`). |
| The page does not open | Check that the PowerShell window from step 5 is still running and shows no error. |
| Port 8000 is already in use | Start with another port: `scripts\start.ps1 -Port 8010`, then open `http://127.0.0.1:8010`. |
| Search says no catalogue is ready | Open **Documents** and wait for **Ready**. If both documents are gone, use **Settings → Restore supplied catalogues**. |
| A document shows **Failed** | Read the message on its row, then click the retry icon. |
| Header shows **Degraded** | Ollama is not running or a model is missing (step 3). Search still works by rules. |
| Vector index "out of sync" in Settings | Start Ollama, then click **Reindex** in Settings. |
| Something looks left over after an interrupted upload or delete | Click **Reconcile** in Settings. |

To start again from a completely clean state, stop the app, delete the `data` folder, and run step 5
again; the two supplied catalogues are re-ingested automatically.
