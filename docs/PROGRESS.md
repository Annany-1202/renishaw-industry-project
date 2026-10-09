# Progress log

## Current state (2026-10-09)

The codebase was audited end to end and largely rewritten. The earlier log claimed every phase was
complete; the audit found that the stored data and several of those claims were wrong, so this file
replaces it.

### What the audit found (prioritised)

**P0 — wrong answers**
1. ZEISS extraction never read the per-section property box: every ZEISS part was stored as M5 / ruby /
   tungsten carbide.
2. `INSERT OR REPLACE` keyed on part number: 171 H-1000-3200 rows were silently overwritten.
3. Merged table rows were dropped; ruby was forced as ball material; quick-reference tables were
   ingested as products.
4. Candidate retrieval used an unordered `LIMIT 150`, so correct products could be missed.
5. Inch requests could never match (strict equality on converted values).
6. The parser assumed ruby when no material was given.
7. Irrelevant-query rejection was a short keyword blacklist; unknown records could count as matches.
8. Every image on a page was linked to every part on it and marked "verified"; image captions used the
   product's document rather than the image's.
9. The evaluation runner hard-coded PASS and reported numbers it had not measured.

**P1 — integrity and security**
10. Static-file fallback allowed path traversal out of `frontend/dist`.
11. CORS `*` with credentials; error responses leaked exception text and paths.
12. Upload: client file name used in the stored path, synchronous ingestion in the request, failed
    ingestion left rows and files behind, three orphan copies of one PDF in `data/uploads`.
13. Deletion swallowed vector-store errors and reported success.
14. Settings PATCH was unvalidated and lost on restart.
15. Tests ran against, and modified, the live database.
16. Semantic search was implemented but never called; vector index never reconciled.

**P2 — usability**
17. Frontend: `alert()` for errors, no status polling, irrelevant requests shown as "clarification
    needed", gallery index not reset between products, drop zone without a drop handler, no retry or
    report UI, no keyboard navigation.
18. No README, no scripts, stale docs.

### What was done

- New extraction from the printed part-number listings with body-page cross-checks (items 1–3); new
  schema with per-document records and a separate image/link model (2, 8); staged background ingestion
  (12); resumable verified deletion and reconciliation (13, 16).
- New rule-based interpreter with a constrained LLM merge (5, 6, 7); new scoring and engine that
  evaluates every record (4, 7); grounded template explanations.
- API rewritten: validated settings persisted in the database (14), safe file serving (10), restricted
  CORS and generic error responses (11), upload hardening (12).
- Test suite rewritten on an isolated data directory with an offline socket guard (15): 180 tests.
- Evaluation rewritten with an independent oracle and a generated report (9).
- Frontend data layer and the Search, Details, Documents and Settings views rewritten (17).
- README, scripts and docs (18).

Bugs found by the new tests and evaluation and fixed along the way: a PDF that merely mentioned
"H-1000-3200" was routed to the catalogue-specific extractor; a corrupt PDF stayed locked on Windows
and could not be deleted; row-per-product tables were transposed by the generic extractor; the real
LLM classified "tell me a joke" as a stylus request; "about" relaxed the thread; a dimension was bound
to a keyword across a comma; a bare number was treated as a request; a 35 mm disc was offered for a
45 mm ball.

### Verified

| Check | Result |
|---|---|
| Automated tests (`scripts\run_tests.ps1`) | 180 passed |
| Evaluation, rules only, 135 queries | see `docs/EVALUATION.md` |
| Evaluation, with local LLM, 135 queries | see `docs/EVALUATION.md` |
| Upload → search → delete cycles in the evaluation | 3 of 3 verified clean, 0 leaks |
| Frontend type-check and production build | pass |
| Browser run-through (search, clarification, details and gallery, documents, settings) | pass, no console errors |

### Acceptance checklist

- [x] B. Plain-English input → validated attributes; exact vs alternative; deterministic hard
      constraints; reproducible ranking; results link to sources.
- [x] Irrelevant-query rejection, clarification and conflict flows.
- [x] Document upload, status, retry, verified deletion, reconciliation.
- [x] F. Documented setup, passing automated tests, ≥ 100-query evaluation report.
- [~] G. Images extracted from both catalogues with provenance; all verified images shown for exact
      matches; alternatives labelled; deletion cleans image artifacts. **Open:** association is verified
      by layout rule only — no human review yet; 134 products have no image (recorded as exceptions).

### Not done / limitations

1. **No human review.** Extracted values were checked against the PDFs for 12 records, not all 1,418.
   Image-to-part correctness and the usefulness of alternatives have not been reviewed by a person;
   `data/reports/human_review_sample.csv` and the per-document association CSVs are prepared for it.
2. **49 records flagged for review** where the catalogue's listing and body page disagree or a part is
   in only one of them. They are searchable with a caution; none has been resolved.
3. **134 products without an image**, mostly accessories and kits on pages with no per-part
   illustration. ZEISS images are section schematics, not pictures of the individual part.
4. **Uploaded PDFs of unknown layout** are read only from ruled tables with a recognisable part-number
   column and header names; other layouts fail with a clear message. Scanned PDFs are not supported
   (no OCR).
5. **Frontend has no automated tests** (no test runner is installed and adding one needs an
   `npm install`). It was type-checked, built and exercised by hand in a browser. Deleting a document
   through the confirmation dialog was clicked through; choosing or dropping a file in the upload area
   was not (the upload was sent to the same API endpoint from the command line and is covered by
   backend tests).
6. **LLM path depends on the local model.** With the LLM on, one irrelevant evaluation query received
   a clarification question instead of a rejection (no product recommended). LLM queries take about
   3–5 s on this machine; the first call after start is slower while the model loads.
7. **Relevance gate uses a finite out-of-scope word list** (decision D7).
8. **No authentication**; the server binds to 127.0.0.1 only (decision D14).
9. **Offline operation** is verified by a socket guard on the test suite, a scan for external URLs in
   the backend and the built frontend, and search with Ollama unreachable. It was not verified with the
   network physically disconnected.
10. Deviation scales and the two alternative thresholds are proof-of-concept choices, not validated
    engineering tolerances.
