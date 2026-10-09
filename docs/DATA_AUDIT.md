# Data audit

Findings from inspecting the two supplied PDFs and from the current extraction run. Counts are from
the ingestion reports (`data/reports/*_ingestion_report.json`); "checked" means compared against the
PDF by the regression tests in `backend/tests/test_extraction.py`.

## Documents

| | Styli for ZEISS applications (H-1000-3036) | Styli and accessories guide (H-1000-3200) |
|---|---|---|
| Pages | 88 | 120 |
| Part-number listing | pp. 69–87, 16 columns incl. body page number | pp. 106–119, 12 columns incl. section number |
| Listing rows read | 655 | 738 |
| Rows rejected | 0 | 0 |
| Products stored | 656 | 762 |
| Flagged `needs_review` | 19 | 30 |
| Images stored | 110 | 413 |
| Product–image links (all verified by layout rule) | 655 | 629 |
| Products without an image | 1 | 133 |
| Records with no thread stated | 26 | 74 |

Distinct part numbers across both: 1,361; 57 appear in both documents.

Product types stored — ZEISS: stylus 399, extension 127, accessory 40, cube 32, adaptor 24, holder 14,
tool 12, knuckle 8. H-1000-3200: stylus 555, extension 76, accessory 70, kit 34, cube 9, knuckle 8,
tool 6, adaptor 4.

## Layout findings

**H-1000-3036 (ZEISS).** Body pages are section blocks: a heading, a two-column property box (Thread,
Base, Stem, Ball, notes), a row-per-part table, and one schematic drawing to the right. The table
cells do not carry thread or material — those are in the property box, which the earlier extractor
never read (it stored M5 / ruby / tungsten carbide for every part). Threads actually present: M5 409,
M3 156, M2 60, M8 5, none stated 26. The listing at the back repeats every part with its dimensions and
body page.

**H-1000-3200.** Body pages hold column-per-part tables (one part per column, attributes as rows, values
as "mm (in.)"), with an illustration strip under the columns. Pages 82–104 (accessories, kits, datum
balls) have tables without per-part illustrations. The listing gives thread, component, ball size and
material, length, stem material, EWL and mass per part. Quick-reference tables that repeat parts are
not ingested as products.

**Both.** Text is vector text (no OCR needed). Margin labels and rotated text had to be filtered out of
the word stream. `find_tables` cell text was unreliable on both (merged and split cells), so tables are
rebuilt from word positions.

## Records flagged for review (49)

| Reason | ZEISS | H-1000-3200 |
|---|---|---|
| Listing and body table disagree on a value | 16 | 6 |
| Part is on a body page but not in the listing | 2 | 24 |
| Part is in the listing but on no body page | 1 | 0 |

These look like inconsistencies in the catalogues themselves (for example a length printed differently
in the two places); they have not been resolved by a person. The full list with reasons is in each
document's "Rows needing review (CSV)" download.

## Cross-document differences

The two catalogues sometimes print different values for the same part number (checked example:
A-5003-3822, overall length 20.0 mm in H-1000-3200 p. 21, 21 mm in H-1000-3036 p. 61). Both records are
kept; see decision D4.

## Images

- ZEISS: 110 section schematics shared by the parts of their section. A schematic shows the generic
  dimensioned outline of the family, not the individual part.
- H-1000-3200: 413 per-column illustrations. 133 products have none: kits 34, accessories 48,
  styli 31, extensions 6, tools 6, knuckles 5, adaptors 2, cube 1 — mostly pp. 82–104 where the
  catalogue prints no per-part illustration, plus parts found only in the listing.
- Automated checks: every image file exists and is not blank (sample of 60), every link stays within
  its document and records its basis, the report's "products without image" count matches the
  database. Correctness of the picture for the part has **not** been reviewed by a person; the
  per-document "Image associations (CSV)" has an empty reviewer column for that.

## What was checked against the PDFs

12 records (6 per catalogue) covering styli, a star stylus, extensions, knuckles and an adaptor:
thread, ball diameter and material, length, stem material, EWL, mass, ZEISS order number and body page.
All agree with the printed listings. This is a spot check, not full verification.
