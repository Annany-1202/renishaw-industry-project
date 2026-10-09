# ROLE

You are a senior full-stack engineer and ML systems engineer. Build the COMPLETE project described below, end to end, in this repository: backend, ingestion pipeline, matching/ranking engine, local LLM integration, a professional Notion-style web frontend, image extraction/retrieval, document lifecycle management, tests, evaluation harness, and documentation. Do not stop at a skeleton or scaffold. Do not leave TODO stubs in core logic. Do not ask me for permission between phases; keep going until every acceptance criterion is met or an exception is explicitly documented.

The authoritative requirements document ("THE SPEC") is appended at the very bottom of this prompt, including the "Product Image Retrieval and Display" amendment. This prompt restates every requirement in condensed form and adds environment rules. If anything here conflicts with THE SPEC, THE SPEC wins. Read THE SPEC fully before writing code.

---

# 1. PROJECT IN ONE PARAGRAPH

An offline, locally running web application where a user describes an industrial measurement component (Renishaw styli/accessories) in plain English and receives evidence-backed catalogue results: exact matches, defensible ranked alternatives, or a clear "no suitable result". Data comes from two supplied PDFs ("Styli for ZEISS applications", 88 pages; "H-1000-3200 Styli and accessories technical specifications guide", 120 pages) plus any PDFs the user uploads later. Every result carries provenance (document, page, table), a grounded explanation, and, for perfect matches, ALL verified product images extracted from the source PDFs. The central success criterion is trustworthy retrieval, not chatbot fluency.

---

# 2. ENVIRONMENT AND OPERATING RULES (READ CAREFULLY)

## 2.1 My machine
- OS: Windows. Prompt is `C:\Users\Annany>`. Use PowerShell/cmd-compatible commands and `pathlib` for paths. Never assume bash, `sudo`, `apt`, `make`, or Unix-only tools. If you provide scripts, provide `.ps1` (and optionally `.bat`) versions.
- Ollama is ALREADY INSTALLED and running. Installed models:

      NAME                           ID              SIZE
      llama3.1:8b-instruct-q4_K_M    46e0c10c039e    4.9 GB

- Use `llama3.1:8b-instruct-q4_K_M` as the default local LLM (query interpretation + grounded explanations). Keep the model name in configuration, not hard-coded.
- No embedding model is installed yet. Choose a small Ollama embedding model (default recommendation: `nomic-embed-text`; alternative: `mxbai-embed-large`), make it configurable, and give me the pull command (see 2.2).

## 2.2 Heavy downloads: DO NOT run them yourself
- If any step needs a large or slow download (Ollama model pulls, `npm install` of big trees, large pip packages such as torch, OCR engines, Poppler/Tesseract installers, etc.), DO NOT execute it. Instead, print the exact command in a clearly marked block, say what it is for and roughly how big it is, then STOP and wait for me. I will run it myself and paste you the output. Continue only after I paste the result.
- Format for these requests:

      >>> RUN THIS YOURSELF (heavy download) <<<
      Purpose: ...
      Command: ...
      Approx size/time: ...
      After it finishes, paste the full terminal output here.

- Small, fast commands (creating folders, `pip install` of small pure-Python packages, running tests, running scripts) you may run directly.
- Prefer lightweight dependencies. Avoid torch/transformers unless truly necessary; if you need one, justify it and use the "RUN THIS YOURSELF" protocol.
- Batch all heavy-download requests together as early as possible (end of Phase 0) so I can run them in one go and you are not blocked repeatedly.

## 2.3 Offline-at-runtime is a hard requirement
- After install, nothing may call the internet: no CDNs, no Google Fonts, no external icon/CSS/JS URLs, no telemetry, no hosted APIs. Bundle fonts (e.g. Inter via `@fontsource`) and icons locally in the frontend build. Disable telemetry for ChromaDB and any other library that has it.
- Only Ollama at `http://localhost:11434` may be contacted, and it is local.
- Provide an automated "offline verification" test/script (see 10).

## 2.4 Working style
- Work in phases (Section 12). After each phase, run its verification gate, fix failures, and summarize in 5-10 lines (what was built, test results, known exceptions) before moving on.
- Keep a living `docs/PROGRESS.md` and a `docs/DECISIONS.md` (record every engineering decision: model names/versions, extraction strategy per table category, tolerance scales, thresholds, DB/vector config, dedup representation, Docker yes/no).
- Never claim success without running the relevant tests and showing real output. Never fabricate metrics. If something cannot be measured reliably, document the limitation.
- If the PDFs are not found at `./source_pdfs/`, ask me for their location once, then continue.
- Inspect real PDF pages (render to images and look at them) before designing extraction. Do not guess table layouts.

---

# 3. TECH STACK (initial choices; deviations must be recorded in DECISIONS.md)

| Component | Choice |
|---|---|
| Backend | Python 3.11+ and FastAPI (async where useful), Uvicorn |
| Frontend | React + TypeScript + Vite, Tailwind CSS, Radix UI primitives (shadcn/ui-style components), TanStack Query, React Router, Zustand or equivalent for light state, `lucide-react` icons, `cmdk` for the command palette |
| Database | SQLite (WAL mode, foreign keys ON, migrations via Alembic or a simple versioned migration runner) |
| Vector store | ChromaDB (persistent, local, telemetry off) or an equivalent local index; deletion behavior MUST be tested |
| LLM runtime | Ollama, structured JSON output validated with Pydantic |
| PDF text/images | PyMuPDF |
| PDF tables | pdfplumber and/or PyMuPDF `find_tables`, chosen per table category after a data audit; use page-image inspection for merged cells/misaligned columns |
| Tabular | pandas |
| Validation | Pydantic v2 + deterministic validators |
| Testing | pytest (+ httpx/TestClient), Vitest + Testing Library for frontend, Playwright for a small number of E2E smoke tests (this is for TESTING only, not the UI) |
| Packaging | Documented Windows setup; `start.ps1` that launches backend + serves built frontend; Docker optional |

Architecture principle: separate language understanding, retrieval, deterministic validation, ranking, persistence, UI. The LLM must NEVER control database deletion, decide whether hard constraints can be ignored, or invent the final product list. The LLM is not the source of truth for specifications.

Suggested repo layout (adapt if justified):

    /backend
      /app
        /api            (routers: health, search, documents, settings, images)
        /core           (config, logging, errors)
        /db             (models, migrations, repositories)
        /ingestion      (pdf_audit, table_extract, normalize, validate, image_extract, image_associate, report)
        /llm            (ollama_client, query_interpreter, explainer, embeddings, schemas)
        /retrieval      (structured_retrieval, semantic_retrieval, candidate_merge)
        /matching       (attributes, units, tolerances, hard_constraints, exact_match, scoring, ranking, relevance_gate)
        /lifecycle      (upload, ingest_jobs, deletion, reconciliation)
        /evaluation     (dataset, metrics, runner)
      /tests
    /frontend
    /source_pdfs
    /data               (sqlite db, chroma, uploads, images, caches; gitignored)
    /docs
    /scripts            (start.ps1, setup.ps1, verify_offline.ps1, run_eval.ps1)

---

# 4. FUNCTIONAL REQUIREMENTS (implement ALL)

## FR-01 Natural-language search
Accept free-form English. Convert to a structured, validated search request (not literal text matching). Extract: product category/type, mounting thread/interface, ball/contact diameter, overall length, effective working length, stem material, ball material, stem diameter, other dimensions, compatibility constraints, mandatory vs preferred attributes (when explicit), application context. Only use attributes applicable to the product category (e.g. ball diameter is not meaningful for every accessory).

## FR-02 Query normalization
Normalize: "2 mm"/"2 millimeters"; "0.08 inch" to metric (explicit conversion factors and defined rounding rules); "M5 threaded"/"M5 thread"; unambiguous abbreviations. Keep the original query AND the normalized interpretation for diagnostics. Never overwrite original catalogue values with normalized ones. Unitless numbers are not silently given units unless context makes them unambiguous.

## FR-03 Exact match
A product is an exact match ONLY if (1) all explicit hard constraints are satisfied, (2) all specified attributes applicable to the product are verified, (3) nothing requested contradicts the record, (4) required compatibility is supported by source data or an approved deterministic rule. Semantic similarity alone can NEVER establish an exact match.

## FR-04 Alternatives
If no exact match: evaluate remaining candidates, exclude any that violate hard constraints, rank eligible ones by attribute satisfaction, attribute importance, normalized numeric differences, category/application relevance, supported compatibility, and record completeness/reliability. Every alternative discloses its material differences.

## FR-05 Unsupported-query rejection
Reject unrelated products (laptop, cooking appliance, bicycle), nonsensical attribute combinations, uninterpretable characteristics, and cases where no candidate satisfies mandatory constraints. Return a clear no-results response. NEVER recommend something because its embedding similarity is high relative to other irrelevant candidates.

## FR-06 Search-first ambiguity handling
Search with what is available whenever meaningful. Ask a targeted follow-up ONLY when missing info prevents reliable matching/compatibility (e.g. "stylus for my probe" -> ask probe model or mounting interface). Retain the original query and extracted attributes so the user's answer refines the existing search. Never re-ask for attributes already given; never demand a long form.

## FR-07 Result explanations
Each result includes: product name/description, manufacturer part number, alternative part number, relevant specs, match classification, internal score (if shown), matching attributes, differing attributes, missing/unverified attributes relevant to the request, source document + page, concise grounded explanation.

## FR-08 Multi-document retrieval
Search all active (Ready) documents; the two original catalogues are included by default. Documents may stay separate sources.

## FR-09 Document upload
Settings-page upload. PDF only; max 100 MB (configurable); stored locally with a unique internal ID; duplicate detection via cryptographic content hash (SHA-256); visible processing status; useful errors on failure; partially processed documents never appear as searchable.

## FR-10 Document deletion
Delete: source file, document metadata, page/table records, product records derived exclusively from the document, text chunks, embeddings, vector-index entries, cached retrieval results, extracted images/image metadata/associations, any other document-owned searchable artifact. Must be traceable and verifiable. A product shared with another document must not lose the surviving source's record/provenance. No embedding may remain searchable solely because its document was deleted. If any stage fails: do NOT report success; report failure and support reconciliation of partial cleanup.

## FR-11 Statuses
Uploaded, Queued, Processing, Ready, Failed, Deleting. Settings page shows name, status, upload time, error details. A document is searchable only after its ingestion transaction completes.

## FR-12 Source-grounded responses
Distinguish: facts present in the catalogue; attributes inferred from the query; engineering assumptions used by ranking; information not available in the source. Never fabricate part numbers, dimensions, materials, compatibility, or availability.

## FR-13 Product image extraction
During ingestion (both initial PDFs and uploads) extract product-related images, preserving: source document ID, PDF filename, page number, image ID, image file reference, associated product record ID, extraction/association status. Handle embedded raster images AND vector/complex-layout illustrations (render page regions when the image is not independently extractable).

## FR-14 Product-to-image association
Associate each image with a product using: position relative to table row/description, table/page layout, captions/labels/part numbers in surrounding content, page/image analysis where necessary, and manual verification for ambiguous cases during catalogue validation. NEVER associate an image with a product merely because it is on the same page. If an association cannot be made reliably, mark it `unverified` and do not display it as a confirmed product image. Distinguish complete product images from page-level images containing several products; crop regions when reliable boundaries exist, and keep the original page reference.

## FR-15 Show ALL images for perfect matches
For a perfect match, display every verified image for that product across all indexed documents (photos, technical illustrations, dimensional drawings, alternate views). Images come only from the original PDFs: no AI-generated, generic, web, or unrelated images. If the product appears in multiple documents, show all verified images with individual provenance. Deduplicate for presentation only when it hides no meaningful view or source reference. This applies on first search, after clarification answers, and after query refinement.

## FR-16 Match-dependent image policy
- Perfect match: all verified images.
- Related alternative: images only if reliably associated with that specific alternative; clearly labelled as an alternative.
- No suitable match: no unrelated product image shown as a recommendation.
- Unverified association: never presented as confirmed.
- An image is NEVER evidence that a product satisfies the requested specs.

## FR-17 Image presentation
Images shown inside the product result with source document name, PDF page number, image type/view description (when identifiable), and a larger preview/lightbox. Multiple images use a gallery/carousel/thumbnail strip so users can inspect each without mixing up products. If a perfect match has no verified image, still return it and explicitly say no associated image was available.

## FR-18 Image persistence and deletion
Images stored locally and linked to source documents. Deleting a document removes its owned image files, metadata, and associations (recoverable lifecycle, same policy as FR-10). If the same product/image survives in another active source, its valid association must remain.

Image data model (minimum): image_id, document_id, page_number, product_record_id, local path/binary ref, image_type (photograph/drawing/diagram/unknown), association_status (verified/unverified/rejected), image_hash, extraction metadata (method + diagnostics). Support one-to-many and many-to-many (a product can have many images; a document's images can belong to many products).

---

# 5. DATA EXTRACTION AND NORMALIZATION

- Process ALL in-scope product and accessory tables in both PDFs. Do not assume uniform columns; tables vary by category.
- Pipeline: enumerate pages -> detect candidate tables and locations -> extract headers/rows -> attach category/table context -> preserve original extracted values -> normalize into the internal model -> validate part numbers/dimensions/units/missing values -> compare against source PDF -> log failures and uncertain rows for review.
- Where text extraction loses layout (merged cells, misaligned columns), inspect rendered page images and correct the extraction logic. Do a real data audit first (Phase 1) and write the findings to `docs/DATA_AUDIT.md`.
- Normalized product model supports (where applicable): internal ID, manufacturer, product name, category, type, manufacturer part number, alternative part number (e.g. Renishaw vs ZEISS numbers), thread/mount interface, ball material, ball diameter, stem material, stem diameter, overall length, effective working length, other dimensions, weight/mass, compatibility info, product-specific descriptive attributes, ORIGINAL source values, NORMALIZED values, source document ID, source page, source table ID, extraction confidence/validation status. Use a design that supports category-specific attributes (e.g. core columns + JSON attributes table, or EAV with typed values) and missing values.
- Missing = unknown. Never guess, never treat unknown as a verified match.
- Preserve original units and precision for display/audit; use canonical units internally for comparison. Rounding must never turn a materially different dimension into an exact match. Tolerances are defined per attribute/category in config and are NOT claimed as manufacturer tolerances.
- Product identity: do not merge records solely on similar descriptions/dimensions. Distinguish same product across documents, different products with similar specs, Renishaw vs ZEISS part numbers, and incomplete/conflicting records. Linked records keep each source's original values and provenance. Decide (and document) between source-specific records vs deduplicated shared product with multiple provenance links; either way deletion must preserve surviving provenance.
- Produce an ingestion/extraction completeness report per document: pages processed, candidate tables detected, tables extracted, rows extracted, rows validated, rows needing review, rows rejected/excluded with reasons, source pages per record. Do not claim complete coverage until all in-scope tables are reconciled or exceptions are documented. Expose the report in the UI (document detail view) and as a generated file.

---

# 6. LOCAL LLM AND EMBEDDINGS

- Ollama is used for: attribute extraction from natural language, synonym/terminology recognition, identifying mandatory vs flexible requirements, mapping to product categories, proposing concise clarification questions, and generating user-readable explanations FROM VALIDATED RESULTS ONLY.
- Query interpretation returns a versioned, Pydantic-validated object containing: original query, inferred product category, requested attributes, values and units, hard constraints, flexible preferences, unspecified attributes, application terms, interpretation confidence, clarification requirements.
- Use Ollama's JSON/structured output mode (`format` with a JSON schema) with low temperature. llama3.1 8B is a modest model: write few-shot prompts with real examples, add a deterministic rule-based pre/post-parser (regex for dimensions, units, threads like M2/M3/M4/M5, materials like ruby/silicon nitride/tungsten carbide/zirconia/steel/ceramic as they appear in the catalogues) that cross-checks and repairs LLM output. Invalid/malformed/incomplete output triggers a controlled fallback (rule-based parse) or a useful error. It must never bypass deterministic validation.
- Explanations: generated only from retrieved records, then post-validated (every part number, number, and material mentioned in an explanation must exist in the result record; otherwise fall back to a deterministic template explanation). Provide a deterministic template explainer as the default fallback so the system works even when the LLM explanation fails.
- Prompt-injection hardening: PDF text and user text are untrusted data, never instructions. Keep catalogue text out of system prompts except as clearly delimited data.
- Embeddings: local Ollama embedding model. Embedding similarity is a candidate-generation signal only. Store model identity/version in index metadata. Changing the embedding model triggers a controlled reindex (implement a reindex command/endpoint).
- Health endpoint must detect: Ollama unreachable, LLM model missing, embedding model missing, with friendly UI messages.

---

# 7. MATCHING, RANKING, REJECTION (deterministic engine)

Three result classes: A = Exact match; B = Related alternative (relevant, satisfies all mandatory constraints, differs only in relaxable/unspecified attributes); C = No suitable result. An alternative must NEVER be presented as exact.

Hard constraints: required thread/interface, explicitly required product type, mandatory material, required probe compatibility, any dimension the user explicitly declares non-negotiable. If the user says "must match exactly", never relax. When unspecified, default conservative policy: preserve compatibility/interface, preserve requested attributes where feasible, relax only where a defensible alternative exists, disclose every material difference, never assert compatibility without source evidence. Do not treat all attributes as interchangeable or equally flexible.

Candidate generation: structured DB retrieval on normalized attributes + semantic retrieval via embeddings. Semantic candidates must pass deterministic eligibility checks before being recommended.

Scoring: `S(p,q) = 100 * sum(w_i * s_i(p,q)) / sum(w_i)` over applicable, requested (or policy-justified) attributes. Unknown attributes are never counted as confirmed matches. Default weights (all configurable): mounting thread/interface 25; product type and application suitability 20; ball/contact diameter 15; overall length 15; stem material 10; ball material 10; other relevant dimensions 5. Numeric score: `s_i = max(0, 1 - |x_i - y_i| / tau_i)` with tau_i configured per attribute/category (not a manufacturer tolerance). Categorical attributes: exact agreement unless an approved domain rule permits substitution. Weights never override hard constraints.

Ranking pipeline order: (1) reject unsupported/irrelevant queries, (2) retrieve candidates, (3) validate required attributes, (4) eliminate hard-constraint violators, (5) identify exact matches, (6) if exact matches exist rank them by preferences, (7) else rank eligible alternatives, (8) remove duplicate result representations where appropriate, (9) return best eligible results with explanations, (10) return "no suitable match" if nothing passes. Default max 5 results (configurable). NEVER pad with irrelevant products. Minimum score threshold 60/100 (configurable) for alternatives, in addition to hard constraints and the relevance gate.

Relevance gate (MANDATORY): distinguish plausible-but-unavailable ("2 mm ruby stylus, M5, 17 mm length" -> search; maybe alternative) from unrelated ("gaming laptop with a 2 mm ruby ball and M5 thread" -> NO stylus returned) and nonsensical combinations (clarify or return nothing). Combine: local query interpretation, product-category validation, attribute-compatibility rules, semantic relevance, score and margin checks, deterministic eligibility. Require BOTH a plausible product-category interpretation AND at least one candidate meeting the minimum ranking policy. If multiple materially different interpretations remain, clarify instead of picking arbitrarily.

Conflicting constraints ("M5 stylus but must have an M3 thread"): detect the contradiction deterministically and ask which takes priority.

Confidence display: scores are internal ranking scores, not calibrated probabilities. UI must distinguish: Exact catalogue match / Ranked alternative / Insufficient evidence / No suitable product found. Never claim a product is safe or suitable for an application because of a high score.

Ranking must be reproducible for identical data, configuration, and interpreted queries (deterministic tie-breaking, e.g. by score desc then part number).

Handling cases A-F from the SPEC (sufficient query; missing compatibility info; flexible preferences like "long stylus, small ball" (ask for approximate dimensions if not interpretable); conflicting constraints; irrelevant request; no exact match with valid specs) must each have a test.

---

# 8. BACKEND API

Endpoints (consistent structured JSON responses, input validation, no unrestricted filesystem access, no arbitrary path deletion, no stack traces or internal paths in errors):

| Endpoint | Method | Purpose |
|---|---|---|
| /api/health | GET | App + dependency status (Ollama, models, DB, vector index) |
| /api/search | POST | Interpret query, retrieve, classify, rank; supports clarification continuation (session/search ID + answer) and refinement |
| /api/documents | GET | List documents + statuses |
| /api/documents | POST | Upload (multipart) |
| /api/documents/{id} | GET | Status, metadata, ingestion report |
| /api/documents/{id} | DELETE | Recoverable cascading delete |
| /api/documents/{id}/retry | POST | Retry failed ingestion if safe |
| /api/settings | GET | Effective config |
| /api/settings | PATCH | Update permitted config (weights, threshold, max results, etc.) |

Additional endpoints you should add: image serving (`/api/images/{image_id}`, restricted to the data directory, with path-traversal protection), reconciliation (`POST /api/admin/reconcile`), reindex, and ingestion report download. Search response includes: original query, interpreted attributes (normalized + original), result class, product records, per-attribute match table (requested vs product value, match/differ/unknown, hard vs flexible), ranking explanation, source references, images (per FR-15/16), and any clarification request.

Ingestion runs as background jobs (asynchronous) with status polling (or SSE). Ingestion happens in a staging area; activation is a single atomic switch to "Ready". Failed ingestion leaves no active vectors or records.

---

# 9. FRONTEND: NOTION-STYLE, PROFESSIONAL (HARD REQUIREMENT)

This must look and feel like a polished modern product, comparable in craft to Notion/Linear. NOT Streamlit, NOT Gradio, NOT a plain HTML form, NOT a bare Bootstrap page, NOT a chatbot-bubble UI. Treat design quality as a graded requirement.

Design language:
- Clean, calm, typographically driven. Inter font (bundled locally), generous whitespace, subtle borders (1px, low-contrast), soft shadows only on overlays, 6-8px radii, restrained neutral palette with one accent color. Full light AND dark themes with a toggle (persist locally; respect OS preference).
- Left collapsible sidebar (workspace-style): "Search", "Documents", "Settings", recent searches, document sources list with status dots. Top breadcrumb bar. Resizable/collapsible sidebar with smooth transitions.
- Notion-like block layout for results: each product result is a "page-like" card with a title (part number), property rows (icon + label + value, like Notion database properties), callout blocks for explanations/warnings ("Differs from your request", "Unverified"), toggles (collapsible sections), and tag/pill badges for match class (Exact = green, Alternative = amber, No suitable = neutral/red, Unverified = grey).
- Command palette (Ctrl+K) for navigation and actions (search focus, switch theme, go to settings, upload document). Keyboard shortcuts with a help overlay.
- Search page: a large Notion-style input area with placeholder prompts and example-query chips; streaming/skeleton loading states; interpreted-query "chips" showing extracted attributes (editable: user can click a chip to change/remove a constraint and re-run; mark hard vs flexible with a toggle); results grouped into sections ("Exact match", "Related alternatives", "No suitable result"); clarification prompt rendered as an inline callout with quick-reply buttons plus a free-text field that refines the SAME search.
- Result detail: side peek panel (Notion "side peek") with full specs, provenance (document, page, table), match table, and image gallery. Image gallery with thumbnail strip, keyboard navigation, lightbox/zoom, caption showing source document + page + image type, and a clear "No associated image available" empty state. Verified images only for exact matches; alternatives show images only when verified and carry an "Alternative" label.
- Product comparison: select 2-5 results to compare in a side-by-side table (requested vs product values; match/differ/unknown; hard vs flexible; only applicable attributes).
- Documents/Settings page: table-style database view of documents (name, status pill, upload time, size, pages, product count, image count, error details), drag-and-drop upload zone with progress, per-document detail page with the extraction report (tables detected/extracted, rows validated/needs review/rejected with reasons), retry button, delete with a confirmation dialog that lists exactly what will be removed, and a visible deletion progress/verification result. Retrieval settings (weights, threshold, max results) with validation and reset-to-default. Model/index status panel (Ollama connectivity, LLM model, embedding model, index size).
- Friendly, specific error states for: Ollama unavailable, model missing, invalid document, unsupported format, failed extraction, failed indexing, database error, failed deletion, invalid query interpretation. Toasts for transient events, inline callouts for persistent ones.
- Accessibility: semantic HTML, keyboard navigation, focus rings, ARIA for dialogs/tabs/gallery, sufficient contrast in both themes. Responsive down to tablet width.
- Polish: micro-interactions (hover states, smooth panel transitions, skeletons), empty states with guidance, consistent spacing scale, no layout shift, no default browser-looking controls.
- Fully offline: no CDN assets. Production build served by the FastAPI backend (single command to run), plus a Vite dev mode for development.

---

# 10. TESTING, EVALUATION, OFFLINE VERIFICATION

Automated tests (pytest + frontend tests) covering: unit normalization/conversion; query parsing fallback; exact-match logic; hard-constraint enforcement; scoring/ranking reproducibility; relevance gate (including the "gaming laptop with ruby ball" and "bicycle with 2 mm ruby ball" cases); clarification flows (cases A-F); extraction regression against reconciled records; image association (all cases listed in the amendment's Evaluation Tests: one image; multiple images; perfect match reached after clarification; illustrations across multiple pages; two products on the same page; no image; unverifiable association; product in multiple documents; deletion with shared/duplicated images; verification that displayed images originate from the indexed PDFs); document upload -> searchable -> delete -> no longer retrievable; deleting one document preserves another source's records and provenance; duplicate upload detection; failed ingestion leaves no active data; failed deletion is reported and recoverable via reconciliation; fresh index rebuild equals active inventory; security (path traversal, oversize/invalid files, prompt-injection text inside a PDF, malformed model output).

Evaluation harness: build a labelled set of AT LEAST 100 queries derived from real catalogue records (exact; missing optional attributes; unit conversions; synonyms/informal wording; conflicting requirements; alternatives needed; no eligible alternative; irrelevant; nonsensical; multi-document; newly uploaded document). Report: in-scope table coverage, exact-match precision (target >= 95%), Recall@5 (target >= 90%), hard-constraint violations in recommendations (target 0), unsupported-query false-recommendation rate (target 0), deletion verification (100%), offline tests (all pass). Report test-set sizes and definitions; be honest about limitations. Record hardware used. Include latency measurements against the targets (structured retrieval + ranking p95 < 1 s; end-to-end p95 < 5 s on this machine, noting that an 8B model on local hardware may exceed this; report real numbers, do not fudge).

Offline verification: a script/test that blocks outbound network access (e.g. socket-level guard in the test process and a check that no frontend asset references an external URL) and confirms search, ingestion, ranking, image retrieval, and deletion still work.

---

# 11. SECURITY AND RELIABILITY

Validate file type (magic bytes, not just extension) and size; never execute uploaded content; restrict file access to the configured data directory; prevent path traversal; do not expose arbitrary local files; validate all model-generated structured output; treat PDF text as untrusted. Failed model inference must not produce fabricated results; failed ingestion must not activate incomplete records; failed deletion must be detectable and recoverable (deletion state machine: mark Deleting -> exclude from search -> remove vectors -> remove chunks/records/images -> update shared provenance -> delete files/metadata -> verify -> report); DB and vector index must be reconcilable (provide a reconcile routine that detects orphaned vectors/images/files and fixes them); malformed queries must not crash the app; repeated ingestion of the same document must not silently create duplicates.

---

# 12. PHASES (execute in order, with gates)

Phase 0 - Setup: repo scaffold, env, config system, logging, dependency lists. Print all heavy-download commands (embedding model pull, frontend `npm install`, any OCR/Poppler needs) in the "RUN THIS YOURSELF" format and wait for my output.
Phase 1 - Data audit: inventory both PDFs (categories, tables, images), common vs category-specific attributes, extraction reliability, normalized model, `docs/DATA_AUDIT.md`. Gate: scope of all in-scope tables documented.
Phase 2 - Extraction + validation + image extraction: tables, normalization, validation, dedup/provenance, image extraction and association (with manual-verification workflow/file for ambiguous cases), persistence, reconciliation against source, completeness report. Gate: dataset available with documented exceptions.
Phase 3 - Deterministic engine: structured query model, exact match, hard constraints, comparison, scoring, ranking, rejection, explanations, unit tests. Gate: engine works with no LLM.
Phase 4 - LLM integration: Ollama client, query interpreter + rule-based cross-check, normalization, embeddings, clarification logic, grounded explanations with validation. Gate: plain-English queries produce validated requests evaluated by the deterministic engine.
Phase 5 - API + frontend: FastAPI, Notion-style UI, search, images/gallery, comparison, documents/settings, deletion, error states. Gate: all principal workflows complete in the browser.
Phase 6 - Lifecycle + offline: persistence, re-ingestion, duplicates, deletion of chunks/embeddings/images, shared provenance, failure recovery, offline run. Gate: consistent DB/vector/image state, offline tests pass.
Phase 7 - Evaluation + handover: labelled set, metrics, human-review sample file, regression tests, tuning of weights/thresholds, limitations, docs. Gate: acceptance criteria met or exceptions documented.

---

# 13. DELIVERABLES

1. Source code (frontend, backend, extraction pipeline, ranking engine, document management, image pipeline).
2. Initial normalized catalogue dataset (reproducible from the PDFs via a documented command).
3. Local search index (embeddings + metadata, reproducible).
4. Configuration (model settings, weights, tolerances, thresholds) separate from business logic.
5. Automated tests (unit, integration, retrieval, deletion, image, offline).
6. Evaluation report (`docs/EVALUATION.md`).
7. Installation guide (Windows, step by step, with model setup and startup commands).
8. Usage guide (searching, interpreting results, uploading, deleting).
9. Data audit report (table coverage, record counts, known exceptions, validation status, image coverage and unverified images).
10. Demonstration scenarios (script + doc): exact match with multiple images, near match, irrelevant request, ambiguous query with clarification leading to a perfect match with images, upload, deletion.

---

# 14. ACCEPTANCE CRITERIA (all must be met or explicitly documented as exceptions)

A. Both PDFs processed; all in-scope tables extracted/validated/documented; provenance preserved; original units/part numbers traceable; extraction errors visible.
B. Plain-English input -> validated structured attributes; exact matches distinguished from alternatives; deterministic hard-constraint checks; reproducible ranking; results link to sources.
C. Irrelevant/nonsensical queries produce no recommendations; missing specs never assumed as matches; no alternative violates a hard constraint; high score never overrides failed compatibility; "no suitable match" reported when no defensible candidate exists.
D. Upload, processing status, visible failures, deletion removing all artifacts including images, independent records from other sources preserved, failed deletion reported.
E. Everything (Ollama inference, embeddings, search, ranking, upload, indexing, deletion, images, frontend) works with no network.
F. Documented install/start commands, documented model versions, passing automated tests, evaluation metrics and limitations reported, demo covers all scenarios.
G. Image amendment: images extracted from both catalogues with provenance; correct association; perfect matches show ALL verified images (also after clarification/refinement); gallery works; alternatives' images correctly labelled; unverified images never shown as confirmed; products without images still returned; deletion removes owned image artifacts without harming surviving sources; offline; tests cover association, presentation, provenance, deletion. No claim of complete image coverage until reconciled or exceptions recorded.

---

# 15. FINAL INSTRUCTIONS

- Start now with Phase 0. Before writing code, reply with a concise plan (max ~25 lines): confirmed stack, repo layout, the batch of heavy-download commands for me to run, and any blocking questions (ask only what is truly blocking).
- Prefer correctness and traceability over speed. Where the SPEC says "must", it is non-negotiable.
- When finished, give me: how to start the app, how to run tests, how to run the evaluation, a summary of metrics with their test-set sizes, and a list of documented exceptions/limitations.

# APPENDIX: THE SPEC (authoritative)
# Project Specification
## Offline Natural-Language Product Retrieval and Recommendation System for Renishaw Catalogues

**Document type:** Product Requirements Document (PRD) and Technical Specification  
**Project classification:** Industry Proof of Concept (PoC)  
**Version:** 1.0  
**Status:** Baseline specification for implementation  
**Deployment:** Local, fully offline at runtime  
**Primary data sources:**
1. *Styli for ZEISS applications* — 88-page PDF catalogue.
2. *H-1000-3200: Styli and accessories — technical specifications guide* — 120-page PDF catalogue.

---

# 1. Executive Summary

## 1.1 Project overview

The project is to develop a locally running, natural-language product retrieval and recommendation system for technical product catalogues.

The system will allow users to describe the industrial measurement component they need in ordinary English, without requiring them to know the exact product name, catalogue section, or part number.

The application will search structured product information extracted from the supplied Renishaw PDF catalogues, identify exact matches where available, and recommend suitable alternatives when exact matches do not exist.

The application will also allow users to upload additional PDF documents through a settings interface. Newly uploaded documents will be processed and indexed locally, making their product information available through the same search interface. Deleting a document must also delete all associated indexed content and embeddings.

The complete system must operate offline at runtime. Natural-language understanding, embedding generation, retrieval, ranking, and response generation must use locally available components, including Ollama.

## 1.2 The problem being solved

Technical catalogues often contain hundreds or thousands of products organized into tables containing part numbers, dimensions, materials, compatibility information, and other specifications.

Finding the correct product can require the user to:

- Understand technical catalogue terminology.
- Navigate multiple PDF documents.
- Identify the relevant product category.
- Compare several dimensions and material specifications.
- Distinguish exact matches from near matches.
- Verify whether a candidate is compatible with the intended application.

A conventional keyword search is insufficient because users may describe a product differently from the way it is described in a catalogue.

For example, a user may request:

> I need a long stylus with a small ruby ball and a tungsten carbide stem for an M5 mounting.

The system must interpret the request, retrieve actual catalogue records, compare their specifications, and return evidence-backed results.

## 1.3 Product objective

Build a working PoC that demonstrates reliable natural-language retrieval, deterministic technical matching, defensible alternative recommendations, and complete document lifecycle management across the two supplied catalogues and subsequently uploaded documents.

The application is not intended to manufacture missing catalogue information, invent products, or certify engineering suitability.

---

# 2. Requirements Authority and Decision Policy

This document establishes three categories of requirements.

### 2.1 Explicit stakeholder requirements

The original email establishes that:

- Users must describe desired parts in plain English.
- The system must retrieve matching parts from the supplied documents.
- If an exact match is unavailable, the system should return the closest available alternative.
- All available tabular information must be used.
- The documents may remain separate sources if combining them creates unnecessary complexity.

### 2.2 Confirmed project decisions

The following decisions have been made for this PoC:

- Deliver a web application with a backend API.
- Include all product and accessory tables in both supplied catalogues.
- Use Ollama for local language-model inference.
- Use deterministic attribute matching combined with weighted alternative ranking.
- Search first and ask follow-up questions only when necessary.
- Run the application entirely offline at runtime.
- Allow users to upload additional documents through settings.
- Ensure document deletion removes associated chunks, embeddings, and searchable records.
- Reject unsupported or irrelevant requests instead of fabricating product recommendations.
- Preserve product provenance and explain why each result was returned.

### 2.3 Engineering decisions established by this specification

The original email does not prescribe numerical thresholds, software libraries, database technology, scoring weights, or performance targets.

Where these are necessary, this specification establishes provisional PoC defaults. They are engineering decisions to be validated during implementation, not additional requirements attributed to the stakeholder.

---

# 3. Project Scope

## 3.1 In scope

The implementation must include the following capabilities.

1. Local extraction of product information from the two supplied PDFs.
2. Extraction and validation of all in-scope tabular product records.
3. Preservation of document, page, table, and part-number provenance.
4. A normalized product data model.
5. Local natural-language query interpretation using Ollama.
6. Structured filtering and exact-match detection.
7. Hard-constraint enforcement and weighted alternative ranking.
8. Detection of unsupported, irrelevant, and insufficiently specified queries.
9. Explanations of matching attributes and differences.
10. A web-based search interface.
11. A backend API supporting search and document management.
12. Local document upload, processing, status tracking, and deletion.
13. Cascading removal of document-derived chunks and embeddings.
14. Local persistence of the catalogue and vector index.
15. Automated testing, evaluation, logging, and reproducible setup instructions.

## 3.2 Out of scope

The initial PoC will not include:

- Live internet searches or external product databases.
- Cloud-hosted inference or external LLM APIs.
- Automatic ordering, purchasing, or inventory management.
- Claims about live availability, pricing, or delivery dates.
- Unverified engineering compatibility predictions.
- Automatic CAD generation or physical part design.
- Automatic modifications to source PDFs.
- Training a new foundation model.
- Multi-user authentication, enterprise permissions, or distributed deployment.
- Automatic discovery of arbitrary document formats beyond the explicitly supported formats.
- Guaranteed production-grade engineering certification.

These exclusions may be reconsidered after the PoC has demonstrated its core retrieval capabilities.

---

# 4. Users and Their Requirements

## 4.1 Primary user

The primary user is an engineer, technician, or other person who needs to identify a component from technical product catalogues.

The user may understand the application requirements but may not know the catalogue's exact terminology or part number.

## 4.2 User needs

The user must be able to:

- Describe the desired product in natural language.
- Specify dimensions, materials, mounting interfaces, product types, and application constraints.
- Receive matching catalogue products without manually browsing the entire PDF.
- Identify exact matches separately from alternatives.
- Compare the specifications of returned products.
- Understand which requested properties match and which differ.
- Find the source document and page containing each product.
- Receive a useful explanation when no exact match exists.
- Receive no recommendation when the request is irrelevant or the evidence is insufficient.
- Upload additional supported documents.
- Inspect document-processing status.
- Delete uploaded documents and remove their indexed data.
- Search all currently active document sources through one interface.

## 4.3 User experience principles

The application must prioritize:

1. Technical correctness over conversational fluency.
2. Evidence-backed results over plausible-sounding answers.
3. Transparent differences over unexplained similarity scores.
4. Useful results over unnecessary clarification questions.
5. Safe rejection over unsupported recommendations.
6. Predictable document management over hidden index state.

---

# 5. Functional Requirements

## FR-01: Natural-language product search

The system shall accept free-form English descriptions of desired products.

Example:

"I need a stylus with a 2 mm ruby ball, a 30 mm length, a tungsten carbide stem, and an M5 thread."

The system shall interpret this as a structured search request rather than relying solely on literal text matching.

The query parser should identify:

- Product category or type.
- Mounting thread or interface.
- Ball or contact-element diameter.
- Overall length.
- Effective working length, where applicable.
- Stem or body material.
- Ball material.
- Stem diameter.
- Other relevant dimensions.
- Compatibility constraints.
- Mandatory versus preferred attributes, when explicitly expressed.
- Application context and relevant descriptive terms.

Only attributes supported by the relevant product category should be used. For example, a ball diameter is meaningful for a ball-ended stylus but not necessarily for every accessory.

## FR-02: Query normalization

The system shall normalize common representations before matching.

Examples include:

- "2 mm" and "2 millimeters".
- "0.08 inch" and its equivalent metric dimension, subject to precision rules.
- "M5 threaded" and "M5 thread".
- Commonly used abbreviations when their meanings are unambiguous in the catalogue.

The system must retain the original query and the normalized interpretation for diagnostics.

Conversions must use explicit conversion factors and defined rounding rules. Original catalogue values must not be overwritten by normalized values.

## FR-03: Exact-match retrieval

The system shall identify products satisfying all specified, applicable requirements.

A product shall be labelled an exact match only when:

1. All explicitly stated hard constraints are satisfied.
2. All specified attributes applicable to the product are verified.
3. No relevant requested specification contradicts the catalogue record.
4. Required compatibility information is supported by the source data or an approved deterministic compatibility rule.

A high semantic similarity score alone must never establish an exact match.

## FR-04: Alternative recommendations

When no exact match exists, the system shall evaluate remaining candidates against the user's requirements.

Candidates that violate hard constraints shall be excluded from the recommended results.

The system shall rank eligible alternatives according to:

- Satisfaction of specified attributes.
- Importance of the attributes.
- Normalized differences in numerical dimensions.
- Product-category and application relevance.
- Supported compatibility information.
- Completeness and reliability of the underlying catalogue record.

Every alternative shall disclose its meaningful differences from the requested specification.

## FR-05: Unsupported-query rejection

The system shall identify requests that are outside the scope of the indexed catalogue or have no defensible relationship to any supported product.

Examples include:

- Requests for unrelated products, such as a laptop or a cooking appliance.
- Random or nonsensical attribute combinations that do not describe a supported product.
- Requests for product characteristics that cannot be interpreted meaningfully in the relevant domain.
- Requests for which no candidate satisfies the mandatory constraints and no defensible alternative exists.

The system shall return a clear no-results response in these cases.

It must not recommend a product merely because its embedding similarity is numerically high relative to irrelevant candidates.

## FR-06: Search-first ambiguity handling

The system shall search with the information already available whenever it can produce meaningful results.

If a missing attribute does not prevent useful retrieval, the system shall not force the user to provide it.

If missing information prevents reliable matching or compatibility assessment, the system shall ask a targeted follow-up question.

Example:

User: "Find a stylus for my probe."

The application may ask for the probe model or mounting interface if that information is needed to establish compatibility.

## FR-07: Result explanations

Each result shall include:

- Product name or description, when available.
- Manufacturer part number.
- Alternative manufacturer part number, where available.
- Relevant technical specifications.
- Match classification.
- Match or ranking score, if displayed.
- Matching attributes.
- Differing attributes.
- Missing or unverified attributes relevant to the request.
- Source document and page number.
- A concise explanation of why the product was returned.

Generated explanations must be grounded in the retrieved records.

## FR-08: Multi-document retrieval

The application shall search the active indexed records from all successfully processed supported documents.

The original two catalogues must be included by default.

Additional documents shall become searchable after successful ingestion and validation.

Documents may remain separate sources internally. A shared search interface does not require physically merging the original PDFs or their source records.

## FR-09: Document upload

A settings page shall provide a document upload interface.

For the initial implementation:

- Supported upload format: PDF.
- Maximum upload size: 100 MB per document.
- Uploaded files shall be stored locally.
- The system shall assign each document a unique internal identifier.
- Duplicate uploads shall be detected using a cryptographic content hash.
- Processing status shall be visible to the user.
- Failed documents shall display a useful error.
- Partially processed documents shall not become visible as fully searchable sources.

The upload size limit is a provisional PoC default and shall be configurable.

## FR-10: Document deletion

Users shall be able to delete uploaded documents through settings.

Deleting a document must remove:

1. Its local source file, subject to successful filesystem deletion.
2. Its document metadata.
3. Its extracted page and table records.
4. Its product records derived exclusively from that document.
5. Its text chunks.
6. Its vector embeddings.
7. Its vector-index entries.
8. Its cached retrieval results, where applicable.
9. Any other document-owned searchable artifacts.

The operation must be traceable and verifiable.

If an identical product also exists in another document, deleting one source must not delete the independent record belonging to the remaining source.

For example, if two documents contain the same part number, the system may retain two source-specific records or deduplicate them into a shared product with multiple source references. In either case, deleting one document must preserve valid information and provenance from the other.

Deletion must also handle shared embeddings correctly. No embedding may remain searchable solely because its source document was deleted.

If deletion fails at any stage, the system must not falsely report that the operation succeeded. It must report the failure and support reconciliation of partially completed cleanup.

## FR-11: Document processing status

Each document shall have one of these statuses:

- Uploaded.
- Queued.
- Processing.
- Ready.
- Failed.
- Deleting.

The settings page shall display the document name, processing status, upload time, and available error details.

A document shall become searchable only after its ingestion transaction has completed successfully.

## FR-12: Source-grounded responses

The system shall distinguish between:

- Facts explicitly present in the catalogue.
- Attributes inferred from a user's query.
- Engineering assumptions used by the ranking algorithm.
- Information not available in the source.

The system must not fabricate part numbers, dimensions, materials, compatibility claims, or product availability.

---

# 6. Technical Architecture

## 6.1 Architectural principles

The architecture shall separate language understanding, retrieval, deterministic validation, ranking, persistence, and user-interface responsibilities.

The LLM shall not control database deletion, decide whether hard constraints may be ignored, or directly invent the final list of products.

## 6.2 Proposed architecture

The application shall contain these logical components:

1. Web frontend.
2. Backend API.
3. Local Ollama inference service.
4. Query interpretation module.
5. Catalogue ingestion pipeline.
6. Structured product database.
7. Local vector index.
8. Deterministic retrieval and ranking engine.
9. Document lifecycle manager.
10. Evaluation and diagnostic utilities.

### Request flow

1. The user submits a natural-language query.
2. The backend validates the request.
3. Ollama converts the query into a validated structured representation.
4. The system identifies applicable product categories and hard constraints.
5. Candidate products are retrieved from structured records, with semantic retrieval used where useful.
6. The deterministic matcher evaluates candidate specifications.
7. Hard constraints remove incompatible candidates.
8. The ranking engine orders eligible exact matches or alternatives.
9. The backend prepares grounded result explanations.
10. The frontend displays results, differences, and source references.

### Ingestion flow

1. A PDF is uploaded or selected for initial ingestion.
2. The system validates its format, size, and content.
3. Text, tables, and page information are extracted.
4. Product records are normalized and validated.
5. Text chunks and embeddings are generated locally.
6. Product records, chunks, embeddings, and provenance are persisted.
7. The ingestion process commits successfully.
8. The document becomes searchable.

A failed ingestion must not expose a partially indexed document as complete.

## 6.3 Recommended technology stack

The following stack is the initial engineering choice for the PoC.

| Component | Proposed technology |
|---|---|
| Backend | Python and FastAPI |
| Frontend | React with TypeScript |
| Database | SQLite for the initial local deployment |
| Vector storage | ChromaDB or an equivalent locally persistent vector index |
| Local LLM runtime | Ollama |
| Query parsing | Ollama structured output validated against a schema |
| PDF text extraction | PyMuPDF |
| PDF table extraction | pdfplumber and/or PyMuPDF, selected after a data audit |
| Tabular processing | pandas |
| Data validation | Pydantic and deterministic validation functions |
| Local embeddings | An Ollama-compatible embedding model |
| Testing | pytest and frontend/API tests |
| Packaging | Reproducible local setup; Docker may be added if useful |

The specific Ollama models shall be selected after checking local availability, output quality, and resource requirements. Model names and versions must be recorded in configuration.

SQLite and ChromaDB are implementation choices, not stakeholder-mandated technologies. Their data consistency and deletion behavior must be tested before the final implementation is accepted.

## 6.4 Offline execution requirement

The application must operate without an internet connection after its dependencies, models, and required assets have been installed.

The following must run locally:

- LLM inference.
- Embedding generation.
- Vector retrieval.
- Structured filtering.
- Ranking.
- Document extraction.
- API requests.
- Frontend assets.
- Persistent data storage.

No external LLM provider, hosted embedding service, cloud database, or remote retrieval API may be required at runtime.

Initial model and dependency installation may require obtaining packages and model files in advance. Once installed, normal operation must not require external downloads.

A verification test shall run the application with outbound network access unavailable and confirm that search, ingestion, ranking, and deletion still work.

---

# 7. Data Extraction and Normalization

## 7.1 Data coverage

The system shall process all in-scope product and accessory tables in both supplied catalogues.

The first catalogue is the ZEISS-specific Renishaw document. The second covers a broader range of styli and accessories.

Their tables vary by product category. The implementation must not assume that every table has the same columns.

## 7.2 Extraction strategy

The extraction pipeline shall:

1. Enumerate the PDF pages.
2. Identify candidate product tables and their locations.
3. Extract table headers and rows.
4. Associate each row with the appropriate product category and table context.
5. Preserve the original extracted values.
6. Normalize fields into the internal data model.
7. Validate part numbers, dimensions, units, and missing values.
8. Compare extracted records against the source PDF.
9. Record extraction failures and uncertain rows for review.

Text extraction alone is insufficient for tables whose layout, merged cells, or column alignment is not preserved. In such cases, page images shall be inspected and the extraction process corrected.

## 7.3 Normalized product data model

Each product record should support the following fields where applicable:

- Internal product record ID.
- Manufacturer.
- Product name.
- Product category.
- Product type.
- Manufacturer part number.
- Alternative part number.
- Thread or mounting interface.
- Ball material.
- Ball diameter.
- Stem material.
- Stem diameter.
- Overall length.
- Effective working length.
- Other relevant dimensions.
- Weight or mass.
- Compatibility information.
- Product-specific descriptive attributes.
- Original source values.
- Normalized values.
- Source document ID.
- Source page number.
- Source table identifier.
- Extraction confidence or validation status.

Not every field applies to every product. The database shall support category-specific attributes and missing values.

A missing field must remain unknown. It must not be replaced with a guessed value or silently treated as a verified match.

## 7.4 Units and precision

The system shall preserve the units and precision shown in the original catalogue.

Conversions shall use consistent canonical units for comparison while retaining original values for display and auditing.

For dimensional matching:

- Explicitly specified units shall be interpreted as provided.
- Unitless numerical values shall not be silently assigned units unless the context establishes them unambiguously.
- Rounding shall not turn a materially different dimension into an exact match.
- Numerical tolerances shall be defined per attribute or product category where appropriate.

## 7.5 Product identity and deduplication

Part numbers are important identifiers, but records must not be merged solely because they share similar descriptions or dimensions.

The system shall distinguish between:

- The same product appearing in multiple documents.
- Different products with similar specifications.
- Renishaw part numbers and corresponding ZEISS part numbers.
- Product records with incomplete or conflicting source information.

Where records are linked across sources, each source's original values and provenance must remain available.

## 7.6 Extraction completeness

The ingestion process shall produce a report containing:

- Total pages processed.
- Candidate product tables detected.
- Tables successfully extracted.
- Product rows extracted.
- Product rows validated.
- Rows requiring review.
- Rows rejected or excluded, with reasons.
- Source pages associated with each record.

The project shall not claim complete coverage until all identified in-scope tables have been reconciled against their sources or every exception has been explicitly documented.

---

# 8. Query Interpretation and Local Language Model

## 8.1 Role of Ollama

Ollama shall provide local natural-language understanding and, where appropriate, grounded response generation.

Its responsibilities include:

- Extracting requested attributes from natural-language descriptions.
- Recognizing common terminology and synonyms.
- Identifying explicit preferences and mandatory requirements.
- Mapping the query to relevant product categories.
- Suggesting a concise clarification question when needed.
- Generating a user-readable explanation from validated search results.

Ollama shall not be the source of truth for catalogue specifications.

## 8.2 Structured query representation

The query interpreter shall return a validated structured object containing:

- Original query.
- Inferred product category.
- Requested attributes.
- Requested values and units.
- Hard constraints.
- Flexible preferences.
- Unspecified attributes.
- Relevant application terms.
- Interpretation confidence.
- Clarification requirements.

The exact schema shall be versioned and validated before its output reaches the retrieval engine.

Invalid, malformed, or incomplete model output shall trigger a controlled fallback or a useful error response. It must never bypass deterministic validation.

## 8.3 Local embedding model

An embedding model may be used to retrieve semantically related product descriptions, application text, and document chunks.

Embedding similarity is a candidate-generation signal, not proof of technical compatibility.

The initial implementation shall use a locally available embedding model and store its identity and version in the index metadata.

Changing the embedding model shall trigger a controlled reindexing procedure.

## 8.4 Deterministic matching

The matching engine shall compare structured attributes using ordinary program logic.

Examples include:

- Exact thread equality.
- Exact material equality where material is required.
- Numerical dimension comparison.
- Product-category compatibility.
- Application-specific hard constraints.
- Explicitly configured allowable tolerances.

This division of responsibility makes the system more reproducible and easier to test than an implementation in which the LLM makes every decision.

---

# 9. Matching, Ranking, and Alternative Recommendation

## 9.1 Three result classes

Every search shall distinguish between three outcomes.

### Class A: Exact match

All specified requirements applicable to the product are verified, and no hard constraint is violated.

### Class B: Related alternative

The product is relevant to the requested application, satisfies all mandatory constraints, and differs only in attributes that may be relaxed or have not been specified as mandatory.

### Class C: No suitable result

No product satisfies the mandatory requirements, or the query is unsupported or unrelated to the available catalogue.

A related alternative must never be presented as an exact match.

## 9.2 Hard constraints

Hard constraints are requirements that a candidate must satisfy to be eligible for recommendation.

Examples include:

- A required mounting thread.
- An explicitly required product type.
- A mandatory material specification.
- A required probe compatibility condition.
- A dimension explicitly declared non-negotiable.

If the user explicitly states that an attribute must match exactly, the system must not relax it during alternative ranking.

When the user has not specified which attributes are flexible, the default policy shall be conservative:

- Preserve compatibility and interface requirements.
- Preserve explicitly requested attributes where feasible.
- Relax only attributes for which a defensible alternative exists.
- Clearly disclose every material difference.
- Do not assert compatibility when the source evidence is insufficient.

The system shall not assume that all attributes are interchangeable or equally flexible.

## 9.3 Candidate generation

Candidate generation shall use complementary retrieval mechanisms.

**Structured retrieval:** filter or query the product database using normalized attributes and explicit constraints.

**Semantic retrieval:** retrieve relevant product descriptions or application passages using local embeddings when this improves candidate discovery.

The two methods may contribute candidates to a shared ranking pipeline.

A candidate discovered semantically must still pass deterministic eligibility checks before it can be recommended.

## 9.4 Alternative scoring

For each eligible candidate, calculate a normalized score:

S(p,q) = 100 × Σ(wᵢ × sᵢ(p,q)) / Σ(wᵢ)

Where:

- p represents a candidate product.
- q represents the interpreted query.
- wᵢ is the configured importance weight for attribute i.
- sᵢ is the attribute-specific match score between 0 and 1.

The score shall only include attributes that are applicable, requested or otherwise justified by the ranking policy. Unknown attributes must not be treated as confirmed matches.

### Initial attribute weights

The following are provisional starting weights for relevant requested attributes.

| Attribute | Initial weight |
|---|---:|
| Mounting thread or interface | 25 |
| Product type and application suitability | 20 |
| Ball or contact-element diameter | 15 |
| Overall length | 15 |
| Stem material | 10 |
| Ball material | 10 |
| Other relevant dimensions | 5 |
| Total | 100 |

These weights are starting values for the PoC, not universal engineering priorities. They shall be configurable and evaluated against representative test queries.

The weights are subordinate to hard constraints: a high overall score can never compensate for violating a mandatory requirement.

### Numerical attribute scores

For a dimension where smaller differences are better, the system may use a normalized distance function.

For example:

sᵢ = max(0, 1 − |xᵢ − yᵢ| / τᵢ)

Where xᵢ and yᵢ are comparable normalized values and τᵢ is a configured scale representing a meaningful deviation.

A dimension score of 1 represents equality. A score of 0 represents a difference at or beyond the configured scale.

The scale shall be defined per attribute or product category. It shall not be interpreted as a manufacturer's engineering tolerance unless the source explicitly establishes that tolerance.

Categorical attributes shall use exact agreement by default unless an approved domain rule explicitly permits a substitution.

## 9.5 Ranking policy

The ranking pipeline shall operate in this order:

1. Reject unsupported or irrelevant queries.
2. Retrieve plausible candidates.
3. Validate required product attributes.
4. Eliminate candidates violating hard constraints.
5. Identify exact matches.
6. If exact matches exist, rank them using relevant preferences.
7. If no exact match exists, rank eligible alternatives.
8. Remove duplicate result representations where appropriate.
9. Return the best eligible results with explanations.
10. Return no suitable match if no candidate passes the eligibility policy.

The initial interface shall display at most five recommendations by default, with the number configurable.

The system must not fill empty result slots with irrelevant products merely to display five items.

## 9.6 Minimum recommendation threshold

For the initial PoC, a candidate with a weighted score below 60/100 shall not be recommended as a suitable alternative.

This is a provisional rejection threshold, not a guarantee of suitability. It shall be evaluated against the test set.

Candidates above the threshold must still satisfy hard constraints and the relevance gate.

A high score does not override a failed compatibility check or missing mandatory information.

## 9.7 Completely unrelated or random specifications

This requirement is mandatory.

The system shall distinguish a plausible but unavailable product request from a request that does not describe a relevant product.

Examples:

**Plausible but unavailable:**

"I need a 2 mm ruby-ball stylus with an M5 thread and a 17 mm length."

The system should search for relevant products. If no exact match exists, it may suggest an eligible related part if one is supported by the catalogue.

**Unrelated request:**

"I need a gaming laptop with a ruby ball diameter of 2 mm and an M5 thread."

The system should not return a stylus merely because some extracted attributes overlap. The request is outside the relevant product context.

**Nonsensical combination:**

A query may contain attributes that do not meaningfully describe a supported product category. If the system cannot establish a defensible interpretation, it shall ask for clarification or return no recommendations.

The implementation shall use a combination of:

- Local query interpretation.
- Product-category validation.
- Attribute compatibility rules.
- Semantic relevance.
- Candidate score and margin checks.
- Deterministic eligibility rules.

The initial design shall require both a plausible product-category interpretation and at least one relevant candidate satisfying the minimum ranking policy.

If multiple interpretations remain materially different, the system should clarify instead of choosing one arbitrarily.

## 9.8 Displaying recommendation confidence

The application may display match scores, but it must explain that they represent internal ranking scores rather than calibrated probabilities of engineering suitability.

The user must be able to distinguish:

- Exact catalogue match.
- Ranked alternative.
- Insufficient evidence.
- No suitable product found.

The application shall never claim that a product is safe or suitable for an application merely because its score is high.

---

# 10. Handling Incomplete and Ambiguous Queries

## 10.1 General policy

Search first when meaningful retrieval is possible. Ask a question when the missing information prevents a defensible result.

## 10.2 Cases

**Case A: Sufficient query**

User: "Find an M5 stylus with a 2 mm ruby ball."

Action: Search using the specified thread and ball attributes. Do not require the user to specify every other dimension.

**Case B: Missing compatibility information**

User: "Find a stylus for my measuring probe."

Action: Ask for the probe model or mounting interface if necessary to establish compatibility.

**Case C: Flexible preferences**

User: "I need a long stylus with a small ball."

Action: Search relevant categories and return suitable candidates if enough context exists. If "long" and "small" cannot be interpreted reliably, ask for approximate dimensions.

**Case D: Conflicting constraints**

User: "Find an M5 stylus, but it must have an M3 thread."

Action: Identify the contradiction and ask which requirement takes priority. Do not silently choose one.

**Case E: Irrelevant request**

User: "Find me a bicycle with a 2 mm ruby ball."

Action: Reject the unsupported interpretation and explain that the indexed sources cover stylus and accessory products.

**Case F: No exact match**

User: Provides a valid set of specifications that does not exist in the catalogue.

Action: Search for related products, enforce hard constraints, and return alternatives only when they meet the relevance and eligibility rules.

## 10.3 Follow-up question policy

Questions should be concise and directly tied to the missing information.

The system should avoid:

- Asking for attributes that are already present.
- Requiring every optional specification.
- Repeating questions unnecessarily.
- Making the user complete a lengthy form before every search.

If clarification is needed, the original query and its extracted attributes should be retained so the user's response can refine the existing search.

---

# 11. Web Application Requirements

## 11.1 Search page

The primary page shall contain:

- A natural-language query input.
- A search action.
- A loading state.
- A results list.
- Exact-match or alternative classification.
- Key product attributes.
- Match explanations.
- Source document and page references.
- A no-results state.
- A clarification prompt when required.

The result view should make differences between the requested and actual specifications easy to identify.

## 11.2 Product comparison

The user should be able to compare multiple returned products.

The comparison should show:

- Requested value.
- Product value.
- Whether the value matches.
- Whether the value differs.
- Whether the value is unknown.
- Whether the attribute is a hard constraint or a flexible preference.

Only applicable attributes should be displayed.

## 11.3 Settings page

The settings page shall include:

- Document upload.
- Document inventory.
- Document-processing status.
- Document deletion.
- Index or processing errors.
- Configurable retrieval settings where appropriate.
- Local model and index status.

Model management may be handled through documented local setup instructions rather than a complex in-app model downloader.

## 11.4 Error handling

The interface shall provide understandable errors for:

- Ollama unavailable.
- Required model missing.
- Invalid document.
- Unsupported file format.
- Failed extraction.
- Failed indexing.
- Database errors.
- Failed document deletion.
- Invalid query interpretation.

Errors must not expose unnecessary internal paths, stack traces, or implementation secrets.

---

# 12. Backend API Requirements

The backend shall expose endpoints for search, document management, and application health.

The initial API design shall include:

| Endpoint | Method | Purpose |
|---|---|---|
| `/api/health` | GET | Report application and dependency status |
| `/api/search` | POST | Interpret query and retrieve products |
| `/api/documents` | GET | List indexed and processing documents |
| `/api/documents` | POST | Upload a new document |
| `/api/documents/{id}` | GET | Retrieve document status and metadata |
| `/api/documents/{id}` | DELETE | Delete document and associated indexed data |
| `/api/documents/{id}/retry` | POST | Retry failed ingestion, if safe |
| `/api/settings` | GET | Read effective local configuration |
| `/api/settings` | PATCH | Update permitted configuration |

The API shall validate inputs and return consistent structured responses.

A search response should include the original query, interpreted attributes, result classification, product records, ranking explanations, source references, and any clarification request.

The API shall not expose unrestricted filesystem access or allow a client to delete arbitrary paths.

---

# 13. Document and Embedding Lifecycle

## 13.1 Document ownership

Every uploaded document shall have a unique document ID.

Every derived artifact must be associated with its source document, directly or through an explicit ownership relationship.

This includes product records, chunks, embeddings, source references, and processing artifacts.

## 13.2 Upload and indexing consistency

The system shall maintain a clear distinction between temporary ingestion data and active searchable data.

A document shall become active only when its required records and embeddings have been persisted successfully.

Failed ingestion must not leave orphaned active vectors.

## 13.3 Deletion consistency

Deleting a document shall invalidate all derived searchable artifacts.

The deletion procedure shall:

1. Mark the document as deleting.
2. Prevent new searches from treating the document as an active source.
3. Remove or invalidate document-owned vectors.
4. Remove chunks and document-derived records.
5. Update shared product provenance, where applicable.
6. Delete the local source file and remaining document metadata.
7. Verify cleanup.
8. Report success only after the required deletion has completed.

If the vector database and relational database cannot participate in one transaction, the application shall implement a recoverable deletion workflow and reconciliation checks.

## 13.4 Verification

An automated test shall upload a document, confirm that its records are searchable, delete it, and confirm that its document-derived records are no longer retrievable.

The test shall also verify that deleting one document does not remove valid records belonging to another source.

A fresh index rebuild shall produce results consistent with the active document inventory.

---

# 14. Non-Functional Requirements

## 14.1 Offline operation

The application shall support normal search, ingestion, indexing, deletion, and response generation without internet access.

All required models and software dependencies must be installed locally beforehand.

## 14.2 Performance

Initial provisional targets:

- Structured retrieval and deterministic ranking: p95 under 1 second for the initial local catalogue, excluding LLM inference and document ingestion.
- End-to-end search: p95 under 5 seconds for ordinary queries on the designated development machine, subject to local model performance.
- Search results: normally five or fewer recommendations.
- Document ingestion: asynchronous for long-running operations, with visible status.

These are initial PoC targets, not guarantees. The actual test environment and hardware must be recorded.

## 14.3 Reliability

- Failed model inference must not produce fabricated results.
- Failed ingestion must not activate incomplete records.
- Failed deletion must be detectable and recoverable.
- Database and vector-index state must be reconcilable.
- Malformed queries must not crash the application.
- Repeated ingestion of the same document must not silently create duplicate records.

## 14.4 Maintainability

The system shall separate:

- PDF extraction.
- Normalization.
- Query interpretation.
- Candidate retrieval.
- Hard-constraint checking.
- Ranking.
- Response generation.
- Document management.
- API handling.
- Frontend presentation.

Configuration, model identifiers, ranking weights, thresholds, and supported formats shall be documented and kept separate from business logic.

## 14.5 Security

Although the PoC runs locally, document uploads and generated artifacts must be handled safely.

The application shall:

- Validate file types and sizes.
- Avoid executing uploaded content.
- Restrict file access to the configured data directory.
- Prevent path traversal.
- Avoid exposing arbitrary local files through the API.
- Validate model-generated structured output.
- Apply appropriate protections against malicious document content and prompt injection.
- Treat PDF text as untrusted data rather than executable instructions.

---

# 15. Evaluation and Quality Assurance

## 15.1 Evaluation dataset

A representative test set shall be created from the actual catalogues and validated product records.

The initial target is at least 100 test queries, provided enough representative cases can be constructed from the source data.

The set should include:

- Exact-match queries.
- Queries with missing optional attributes.
- Queries containing unit conversions.
- Queries using synonyms or informal terminology.
- Queries with conflicting requirements.
- Queries requiring alternative recommendations.
- Queries with no eligible alternative.
- Irrelevant queries.
- Nonsensical attribute combinations.
- Queries involving multiple documents.
- Queries involving newly uploaded documents.

Expected results shall be derived from catalogue records and verified manually for the representative evaluation set.

## 15.2 Evaluation metrics

The following are provisional acceptance targets.

| Metric | Initial target |
|---|---:|
| In-scope table coverage | 100% reconciled or explicitly documented exceptions |
| Exact-match precision | At least 95% on the labelled exact-match test subset |
| Recall@5 | At least 90% on the labelled relevant-query subset |
| Hard-constraint violations in recommendations | 0 in the acceptance test set |
| Unsupported-query false recommendation rate | 0 in the acceptance test set |
| Document deletion verification | 100% of deletion tests pass |
| Offline operation | All mandatory offline tests pass |

These metrics must be reported with their test-set sizes and definitions. A small PoC test set does not establish production-level performance.

If a metric cannot be measured reliably, the limitation must be documented rather than represented as a successful result.

## 15.3 Human evaluation

A representative sample of exact matches and alternatives should be reviewed by a person familiar with the catalogue or its application.

The review should assess:

- Whether the product exists in the cited source.
- Whether the part number is correct.
- Whether the displayed specifications are accurate.
- Whether hard constraints are respected.
- Whether alternatives are meaningfully related.
- Whether the explanation accurately describes differences.

## 15.4 Regression testing

Every change to extraction, query parsing, ranking, or document lifecycle logic shall be tested against the relevant regression cases.

The test set shall include previously successful queries and known failure cases.

---

# 16. Acceptance Criteria

The PoC shall be considered complete when all mandatory criteria below are met.

## A. Data ingestion

- Both original PDFs are processed.
- All identified in-scope product and accessory tables are extracted, validated, or documented as exceptions.
- Product records preserve source-document and page provenance.
- Original units and part numbers remain traceable.
- Extraction errors are visible and documented.

## B. Retrieval

- Users can submit plain-English product descriptions.
- Query interpretation produces validated structured attributes.
- Exact matches are distinguished from alternatives.
- Candidate products are checked deterministically against hard constraints.
- Ranking is reproducible for identical data, configuration, and interpreted queries.
- Returned results link to their source information.

## C. Relevance and safety

- Irrelevant queries do not produce product recommendations.
- Nonsensical or unsupported queries are rejected or clarified.
- Missing specifications do not automatically become assumed matches.
- No alternative may violate a hard constraint.
- A high ranking score cannot override failed compatibility requirements.
- No suitable match is reported when no defensible candidate exists.

## D. Document management

- Additional supported PDFs can be uploaded through settings.
- Successfully processed documents become searchable.
- Processing failures are visible.
- Documents can be deleted.
- Deletion removes their associated searchable artifacts and embeddings.
- Independent records from other sources remain available.
- Failed deletion is reported rather than silently ignored.

## E. Offline execution

- Ollama performs inference locally.
- Embeddings are generated locally.
- Search and ranking work without network access.
- Document upload, indexing, and deletion work offline.
- All mandatory frontend and backend functionality is available locally.

## F. Delivery and evaluation

- The application can be installed and started using documented commands.
- Required dependencies and model versions are documented.
- Automated tests are available and pass.
- Evaluation metrics and limitations are reported.
- A demonstration can show exact matching, alternative ranking, irrelevant-query rejection, document upload, and document deletion.

---

# 17. Development Phases

## Phase 1: Repository and data audit

Tasks:

1. Establish the project repository and environment.
2. Inspect both PDFs and inventory their product categories and tables.
3. Identify common and category-specific attributes.
4. Assess extraction reliability.
5. Define the normalized data model.
6. Produce an extraction coverage report.

**Exit condition:** The data structure and extraction strategy are understood, and the scope of all in-scope tables is documented.

## Phase 2: Extraction and validation pipeline

Tasks:

1. Implement PDF extraction.
2. Extract tables and associate rows with source pages.
3. Normalize part numbers, dimensions, units, and attributes.
4. Add validation and error reporting.
5. Handle duplicate records and cross-source provenance.
6. Persist validated records locally.
7. Reconcile the extracted dataset against the source catalogues.

**Exit condition:** The searchable product dataset is available, with completeness and known extraction exceptions documented.

## Phase 3: Deterministic retrieval engine

Tasks:

1. Implement structured query representation.
2. Implement exact-match filtering.
3. Implement hard-constraint checks.
4. Implement numerical and categorical comparison.
5. Implement alternative scoring and ranking.
6. Implement unsupported-query rejection.
7. Generate structured result explanations.
8. Add unit tests for matching and ranking.

**Exit condition:** The engine can retrieve products and rank alternatives without depending on free-form LLM judgments.

## Phase 4: Local language-model integration

Tasks:

1. Configure Ollama.
2. Select and record a local model.
3. Implement structured query interpretation.
4. Validate model output.
5. Add unit normalization and synonym handling.
6. Add local semantic embeddings where useful.
7. Implement clarification logic.
8. Verify that generated explanations remain grounded in retrieved records.

**Exit condition:** Plain-English queries are converted into validated search requests and evaluated by the deterministic engine.

## Phase 5: API and web application

Tasks:

1. Implement the FastAPI backend.
2. Implement the search interface.
3. Display exact matches and alternatives separately.
4. Add product comparison and source references.
5. Implement document upload and processing status.
6. Implement settings and document deletion.
7. Add useful error and no-results states.

**Exit condition:** A user can complete the principal workflows through the local web interface.

## Phase 6: Document lifecycle and offline verification

Tasks:

1. Verify local persistence.
2. Test upload and re-ingestion.
3. Test duplicate-document handling.
4. Test deletion of chunks and embeddings.
5. Test shared-product provenance.
6. Test failed ingestion and failed deletion recovery.
7. Run the application without internet access.

**Exit condition:** The application operates offline and maintains consistent document, database, and vector-index state.

## Phase 7: Evaluation and handover

Tasks:

1. Build the labelled query evaluation set.
2. Measure exact-match precision, Recall@5, and false recommendations.
3. Review alternative quality.
4. Test query rejection and clarification.
5. Run regression tests.
6. Tune configurable weights and thresholds.
7. Document limitations and known failure modes.
8. Prepare setup instructions and a demonstration.

**Exit condition:** The acceptance criteria are satisfied or any remaining failures are explicitly documented.

---

# 18. Final Deliverables

The completed PoC shall include:

1. **Source code:** frontend, backend, extraction pipeline, ranking engine, and document management.
2. **Initial catalogue dataset:** normalized product records derived from the two supplied PDFs.
3. **Local search index:** generated embeddings and associated metadata.
4. **Configuration:** local model settings, ranking weights, tolerances, and thresholds.
5. **Automated tests:** unit, integration, retrieval, deletion, and offline tests.
6. **Evaluation report:** test-set definitions, metrics, representative results, and limitations.
7. **Installation guide:** dependencies, model setup, configuration, and startup commands.
8. **Usage guide:** searching, interpreting results, uploading documents, and deleting documents.
9. **Data audit report:** table coverage, extracted record counts, known extraction exceptions, and validation status.
10. **Demonstration scenarios:** exact match, near match, irrelevant request, ambiguous query, upload, and deletion.

Generated catalogue data and indexes shall be reproducible from the supplied source documents and the documented ingestion process.

---

# 19. Assumptions and Remaining Technical Decisions

The following are deliberate engineering assumptions for this PoC.

| Area | Established assumption |
|---|---|
| Users | Primarily local engineering or technical users |
| Interface | Local web application with a backend API |
| Input documents | PDF initially |
| Runtime | Entirely offline |
| Language model | Local Ollama model |
| Embeddings | Generated locally |
| Storage | Local relational database and persistent vector index |
| Search | Structured matching supplemented by semantic retrieval |
| Alternatives | Hard constraints followed by weighted ranking |
| Irrelevant requests | Rejected without recommendations |
| Missing information | Search first; clarify when necessary |
| Source references | Document and page provenance required |
| Initial result count | Up to five eligible recommendations |
| Alternative threshold | Initial score threshold of 60/100 |
| Evaluation size | Target of at least 100 labelled queries |
| Performance | Initial local latency targets defined in Section 14 |
| Document deletion | Cascading removal of all source-owned searchable artifacts |

The following decisions remain implementation-level choices and must be documented during development:

- The precise Ollama language and embedding model versions.
- The PDF extraction strategy for each table category.
- The final database and vector-index configuration.
- The dimensional tolerance scales.
- The final relevance-gate thresholds.
- Whether shared products are represented as separate source-specific records or deduplicated records with multiple provenance links.
- Whether Docker packaging is useful for the initial local deployment.

These decisions must not weaken the mandatory behavior defined in this specification.

---

# 20. Definition of Success

The project succeeds when a user can describe a desired Renishaw stylus or accessory in ordinary English and receive accurate, traceable catalogue results without manually searching the PDFs.

When an exact match exists, the system should identify it.

When no exact match exists, the system should recommend a related alternative only if the available evidence supports that recommendation and all mandatory constraints are satisfied.

When a query is irrelevant, nonsensical, or unsupported, the system should not fabricate a result.

When users upload additional documents, their validated information should become searchable. When users delete those documents, their derived searchable data and embeddings must be removed without destroying independent information from other sources.

The entire workflow must run locally, use Ollama for language-model inference, and remain functional without internet access.

**The central success criterion is trustworthy product retrieval—not merely a chatbot that can talk about the catalogues.**

# Specification Amendment: Product Image Retrieval and Display

## 1. Objective

When a user searches for a product and the system identifies a perfect catalogue match, the web application shall display **all images in the supplied source PDFs that correspond to that product**.

This requirement applies whether the perfect match is identified:

- On the first search attempt.
- After the user answers one or more clarification questions.
- After the user refines the original query.

The displayed images must be extracted from the original PDF documents and associated with the correct product record.

## 2. Functional Requirements

### FR-13: Product image extraction

During catalogue ingestion, the system shall identify and extract product-related images from both original PDFs and subsequently uploaded supported documents.

The extraction process shall preserve, where available:

- Source document ID.
- Source PDF filename.
- Source page number.
- Image identifier.
- Image data or local image-file reference.
- Associated product record ID.
- Extraction and association status.

The system must account for images embedded in PDF pages, including images that are part of complex page layouts or technical tables.

### FR-14: Product-to-image association

The system shall associate each extracted image with the corresponding catalogue product.

Association may use:

1. The image's position relative to a product's table row or product description.
2. Table and page layout information.
3. Captions, labels, and part numbers visible in the surrounding content.
4. Image and page analysis when necessary.
5. Manual verification for ambiguous cases during catalogue validation.

An image shall not be associated with a product solely because it appears on the same page.

If an image cannot be reliably associated with a specific product, it shall be marked as unverified rather than displayed as a confirmed product image.

### FR-15: Display all associated images for perfect matches

When the system identifies a perfect match, the result view shall display every verified product image associated with that product across the indexed source documents.

This includes all relevant views or illustrations available in the PDFs, such as:

- Product photographs.
- Technical illustrations.
- Dimensional drawings.
- Alternative views of the same product.
- Other product-specific images that help identify the component.

Images must be sourced from the original documents. The system shall not substitute AI-generated images, unrelated catalogue images, or generic web images.

If the same product appears in multiple documents, the application shall display all relevant verified images from those sources, preserving their individual provenance.

Duplicate images may be deduplicated for presentation only when doing so does not hide a meaningful view or source reference.

### FR-16: Match-dependent image display

The default image-display policy shall be:

- **Perfect match:** Display all verified images associated with the matched product.
- **Related alternative:** Display images only when they can be reliably associated with the specific alternative. Clearly label the result as an alternative, not a perfect match.
- **No suitable match:** Do not display an unrelated product image as though it were a recommendation.
- **Unverified association:** Do not present the image as a confirmed image of the product.

A product image shall never be used as evidence that the product satisfies the requested specifications. Technical attributes and compatibility must still be validated against the catalogue records.

### FR-17: Image presentation and provenance

The web interface shall display associated images within the corresponding product result.

Where available, each image shall include:

- Source document name.
- PDF page number.
- Image type or view description, when identifiable.
- A larger preview or image-viewing option.

If a product has multiple associated images, the interface should provide a gallery or equivalent layout so that users can inspect every image without confusing one product's images with another's.

If no verified image exists for a perfect match, the application shall still return the match and explicitly indicate that no associated image was available.

### FR-18: Image persistence and document deletion

Extracted images shall be stored locally and linked to their source documents.

When a document is deleted, the system shall remove its document-owned extracted image files, image metadata, and product-image associations, subject to successful cleanup.

If the same image or product information remains independently available in another active source, deleting one document must not remove the surviving source's valid association.

Image deletion and index cleanup shall follow the same recoverable lifecycle policy as document deletion.

## 3. Data Model Additions

Introduce a product-image association model containing at least:

| Field | Purpose |
|---|---|
| Image ID | Unique internal image identifier |
| Document ID | Source document |
| Page number | Original PDF page |
| Product record ID | Associated product |
| Local image path or binary reference | Stored image |
| Image type | Photograph, drawing, diagram, or unknown |
| Association status | Verified, unverified, or rejected |
| Image hash | Duplicate detection |
| Extraction metadata | Extraction method and relevant diagnostic information |

A product may have multiple associated images, and a source document may contain images associated with multiple products.

The data model must support this one-to-many and many-to-many behavior where appropriate.

## 4. Extraction and Validation Strategy

Image extraction shall be incorporated into the document-ingestion pipeline.

The pipeline shall:

1. Enumerate PDF pages.
2. Extract embedded images where possible.
3. Render or inspect page regions when the image is represented as part of a larger page layout rather than an independently extractable image.
4. Identify nearby product rows, labels, captions, and part numbers.
5. Associate images with product records.
6. Store image files and provenance locally.
7. Validate associations against the original PDF pages.
8. Make verified associations available to the web interface.

The implementation must distinguish between a complete product image and a page-level image that contains several products or unrelated material.

If a page contains multiple product illustrations, the system should crop relevant regions when reliable boundaries can be established. The original page reference must remain available.

Where automatic extraction or association is unreliable, the system shall record the uncertainty and support manual verification during the initial catalogue audit.

## 5. Acceptance Criteria

This requirement is complete when:

1. Product images can be extracted from both initial catalogues.
2. Extracted images retain document and page provenance.
3. Images are associated with the correct product records.
4. A perfect match displays all verified associated images.
5. The same behavior works after clarification questions lead to a perfect match.
6. Multiple images of one product can be viewed in the web interface.
7. Images of alternatives are correctly associated and labelled.
8. Unverified images are not presented as confirmed product images.
9. Products without available images can still be returned correctly.
10. Deleting a source document removes its owned image artifacts and associations without deleting surviving information from other sources.
11. The image retrieval workflow works entirely offline.
12. Automated tests verify image association, presentation, provenance, and deletion behavior.

## 6. Evaluation Tests

The test suite shall include:

- A perfect match with one associated image.
- A perfect match with multiple associated images.
- A perfect match reached after clarification.
- A product with illustrations appearing on multiple PDF pages.
- Two products appearing on the same page.
- A product with no available image.
- An image whose product association cannot be verified.
- A product appearing in multiple source documents.
- Document deletion when images are shared or duplicated across sources.
- Verification that the displayed images originate from the indexed PDFs.

The system shall not claim complete image coverage until all identified product-associated images in the in-scope catalogues have been reconciled or documented exceptions have been recorded.