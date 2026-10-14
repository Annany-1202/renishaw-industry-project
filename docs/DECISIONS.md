# Engineering decisions

Each entry: the decision, why, and what it costs. Parameters named here are in
`backend/app/core/config.py` unless stated otherwise.

## D1. Stack
FastAPI, SQLite (WAL, foreign keys on, versioned migrations), ChromaDB (telemetry off), PyMuPDF,
local Ollama (`llama3.1:8b-instruct-q4_K_M`, `nomic-embed-text`), React + TypeScript + Vite + Tailwind.
All fonts and scripts are bundled; no CDN. `pdfplumber`, `pandas`, `pillow` and `aiofiles` were listed
but unused and were removed from `requirements.txt`.

## D2. The printed part-number listing is the source of record
Both catalogues end with a complete part-number listing (H-1000-3036 pp. 69–87, H-1000-3200
pp. 106–119). Extraction reads these listings from word geometry (`page.get_text("words")`), then reads
each part's body page for what the listing lacks (ZEISS: section title and the Thread/Base/Stem/Ball
property box; H-1000-3200: stem diameter, original "mm (in.)" strings) and cross-checks the two.
*Why:* the previous extractor read body tables with `find_tables`, lost merged rows, and filled gaps
with defaults (every ZEISS part M5/ruby/tungsten carbide). The listing gives one row per part and makes
coverage countable. *Cost:* the two extractors are layout-specific. They are selected only when the
publication number is on the cover pages and the PDF has at least 50 pages; everything else goes to
the generic extractor.

## D3. Nothing is defaulted; disagreements are kept and flagged
A value the catalogue does not state is stored as empty. When listing and body disagree, the listing
value is stored and the record is marked `needs_review` with the reason. Flagged records remain
searchable, rank after validated ones, and carry a visible caution.

## D4. Product records are per source document
Record id = `document_id:part_number`. The same part in two catalogues is two rows, merged into one
result (with both sources listed) at query time. *Why:* the old `INSERT OR REPLACE` on part number
silently dropped 171 rows, and deleting one document must not remove or alter another document's
record. When two sources state different values for a part (for example A-5003-3822: 20 mm in
H-1000-3200, 21 mm in H-1000-3036) the result shows the values of the source that matched and says
that the other source differs.

## D5. Images: association must have a recorded basis
ZEISS: one schematic per section block, shared by the parts of that section (continuation pages reuse
the earlier schematic). H-1000-3200: the illustration under a part's own table column. Uploaded PDFs:
verified only when a caption next to the image names exactly one extracted part; otherwise stored as
`unverified` and never shown. Every link stores its basis. Images and links are separate tables
(many-to-many) and are owned by a document. Only `verified` links are returned, for exact matches and
alternatives alike; alternatives' images carry an "Alternative" label. A link can be overridden by
hand in `data/image_overrides.json`.
*Limit:* "verified" means verified by layout rule, not by a person. The ZEISS schematic is a section
drawing, not a picture of the individual part.

## D6. Interpretation: rules first, LLM constrained
A deterministic parser handles units, threads, materials, product nouns, probe models, hard/flexible
wording and contradictions. The LLM (`LLM_MODE` auto / always / off) is consulted only for words the
rules cannot place or when scope is undecided. Its output is merged under these rules: a rule-extracted
value always wins; a number is accepted only if it appears in the user's text; it cannot change the
hard-constraint list; it cannot bring a request into scope unless the request itself contains a
material, dimension or probe model; malformed output is ignored. User text is passed inside a delimited
block and cannot close it.
*Why:* with the real model, "tell me a joke" and "write a poem about M5 threads" were classified as
in-scope stylus requests. *Cost:* an oddly worded request with no recognisable attribute is rejected
rather than guessed.

## D7. Relevance gate
A request is searched only if it names a catalogue product type, a part number or probe, or consists
of catalogue attributes with no unexplained words — and names no product from a list of out-of-scope
nouns (`matching/domain.py`). Embedding similarity never admits a request.
*Limit:* the out-of-scope list is finite. A foreign product not on it that also carries stylus-like
attributes can still reach a clarification question (one such case in the evaluation; no product was
recommended).

## D8. Matching and scoring
- Score: `S = 100 · Σ wᵢ·sᵢ / Σ wᵢ` over the attributes the request names, with the specification's
  weights (thread 25, type 20, ball diameter 15, length 15, stem material 10, ball material 10, other
  dimensions 5).
- Numeric attributes: `sᵢ = max(0, 1 − |x − y| / τ)`, `τ = max(absolute, relative · requested)`
  (`TOLERANCES`). These are ranking scales chosen for this proof of concept, **not** manufacturer
  tolerances.
- A millimetre request must equal the catalogue value. An inch request matches a millimetre value when
  both are the same number at the precision typed and within 2.5 % (`INCH_INPUT_REL_TOL`), so
  "0.08 inch" matches the catalogue's own "2.0 (0.08)".
- "Not stated" scores 0 and never counts as a match.
- Mandatory by default: thread, and a product type the user named. Words such as "must", "exact",
  "only" make the attributes of that clause mandatory; "preferably", "ideally", "if possible" make them
  flexible; "about", "around", "~" soften numbers only.
- Exact = all requested attributes match.
- An alternative must: violate no mandatory requirement; score ≥ `MIN_ALTERNATIVE_SCORE` (60); differ on
  no requested dimension by the full scale or more; and earn at least half of the weight of the
  non-mandatory attributes (`MIN_FLEXIBLE_AGREEMENT`). The last rule was added after the evaluation
  showed a 35 mm steel disc offered for a "45 mm ruby ball" request on the strength of thread and type
  alone.
- Order: exact — validated first, straight styli first when no type was asked, then part number.
  Alternatives — score, validated first, fewer unknowns, part number. Embedding similarity is used only
  as a later tie-break and only when the request contains free wording.

## D9. Probe model implies a thread only where the catalogue says so
`PROBE_THREADS` quotes H-1000-3200 pp. 19, 35, 43, 61. A probe listed under one thread sets that thread
(shown as an assumption with its page). A probe listed under two (REVO, TP1) triggers a question.

## D10. Search-first clarification
A question is asked only when a search would be unreliable: no thread, dimension, material or
descriptor at all; qualitative words without numbers; one unlabelled dimension; ball attributes on a
ball-less product type; contradictory values. The same question is never asked twice.

Vague but catalogue-related requests ("something for my CMM") are clarified one question at a time:
product type → probe/thread → (if still nothing to match) a request for any detail. The questions
already asked travel with the interpretation (`clarification_history`), so answers accumulate on the
original request and no question repeats; after at most four rounds the search runs with what is
known, and a request with nothing comparable says so instead of listing products.

When more products are eligible than are shown, the results are still returned with a non-blocking
`follow_up` question about the most decisive open attribute (type, thread, ball diameter, length,
materials). Its options are values the eligible products actually have, with counts, and are offered
only if the parser reads them back as that exact value. Answering uses the clarification path, so
hard constraints and provenance are unchanged.

Requests outside the catalogues get one message: "This request is not related to the uploaded
catalogues", the reason, and the names and product types of the indexed documents.

## D11. Ingestion is staged and runs in the background
Upload stores the file under a generated name and returns at once; one worker thread ingests. Records,
images and vectors are written while the document is `Processing`; the switch to `Ready` commits in
the same transaction as the records. Any failure removes the staged artifacts and leaves `Failed` with
a user-safe message. A PDF with no extractable product table is `Failed`, not an empty `Ready`
document. Embeddings are best-effort: if the embedding model is unavailable the document still becomes
searchable and the gap is reported (repair: Reindex).

## D12. Deletion is a resumable state machine
Mark `Deleting` (excluded from search immediately) → remove vectors → image files → rows → stored PDF
and reports → verify nothing remains → remove the document row. A failing step leaves the document in
`Deleting` with the step recorded and returns an error; deleting again or running Reconcile resumes.
Success is reported only after verification.

## D13. Supplied catalogues are bootstrapped once
First start registers and ingests the two supplied PDFs. A supplied catalogue the user deletes is not
re-added on restart; "Restore supplied catalogues" does that on request.

## D14. Security posture (local single-user tool)
Server binds to 127.0.0.1. No authentication (out of scope for a local proof of concept — anyone with
access to this computer's localhost can use the API). Upload: PDF extension and magic bytes, size
limit, client file name never used in a path. Image and report downloads resolve paths from the
database and must stay inside their directory. The static-file fallback serves only files inside
`frontend/dist`. CORS allows only the Vite dev origin. Errors return generic messages; details go to
the log. Runtime settings accept only a fixed set of validated fields.

## D15. Tests and evaluation never touch real data
Both set `RENISHAW_DATA_DIR` to a temporary directory before the application is imported and ingest
the catalogues there. The evaluation's expected answers come from an independent oracle in
`evaluation/dataset.py`; `docs/EVALUATION.md` is generated from the run.

## D16. Browsing a document's images and parts
`GET /api/documents/{id}/images` lists every image extracted from the PDF (page, type, description,
linked part numbers with association status and basis). `GET /api/documents/{id}/parts` lists the
document's own product records with specifications, source page/table, validation status and linked
images; it filters by text (`q`, wildcards are literal) and `category` and pages with
`offset`/`limit`. Both answer only for `Ready` documents (409 otherwise), consistent with
`/api/images/{id}` serving only Ready images. Rejected associations are not shown.
