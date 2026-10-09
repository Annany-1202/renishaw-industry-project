"""Extractor for 'Styli and accessories - technical specifications' (H-1000-3200).

Layout (see docs/DATA_AUDIT.md):
  * Body pages: column-oriented tables. Each column is one geometry; the part
    number cell stacks up to three part numbers (ruby / silicon nitride /
    zirconia ball) and the rows below give ball dia, length, stem dia, EWL and
    mass as 'mm (in.)'. A small illustration of each geometry sits in the
    bottom row of the table, under its column.
  * 'Product range listing by part number' at the end: one row per part
    number with thread, component type, ball size and material, length, stem
    material, EWL, mass and the section it is specified in.

The listing is the source of record for every attribute it carries. The body
tables add the stem diameter and the original 'mm (in.)' strings, and are used
to cross-check ball diameter and length; disagreements are flagged for review.
"""
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pymupdf

from backend.app.core.logging import logger
from backend.app.ingestion.models import (
    NEEDS_REVIEW, VALIDATED, VERIFIED, ExtractionResult,
    image_record, link_record, new_report, product_record,
)
from backend.app.ingestion.normalizer import (
    classify_h1000, inches_to_mm, is_empty, normalize_material, normalize_thread, parse_number,
)
from backend.app.ingestion.pdf_utils import (
    Word, column_anchors, drawing_rects, group_lines, page_headings, page_words, rect_tuple,
    save_crop, split_row, strip_part_number,
)

LISTING_COLUMNS = [
    "Part no.", "PS no", "Description", "Thread", "Component", "Ball/tip size (mm)",
    "Ball/tip Material", "Length (mm)", "Stem material", "EWL (mm)", "Mass (g)", "Section no.",
]
SECTION_LABEL_RE = re.compile(r"^\d{1,2}\.\d{1,2}$")
NUMBER_WORD_RE = re.compile(r"^Ø?\d+(?:\.\d+)?$")
FRACTIONS = {"¼": 0.25, "½": 0.5, "¾": 0.75, "⅛": 0.125}

# Body-table row labels -> field. Checked in order.
ROW_LABELS: List[Tuple[str, str]] = [
    ("ball_diameter", r"\bball\s+dia"),
    ("stem_diameter", r"\bstem\s+dia"),
    ("ewl", r"\be(s)?wl\b|\beffective\s+length"),
    ("mass", r"\bmass\b"),
    ("length", r"\b(overall\s+)?length\s+(mm|\()"),
]
EXTRA_LABEL_RE = re.compile(
    r"\b(disc dia\w*|disc depth|roller depth|cylinder dia\w*|outer dia\w*|span|centre offset|"
    r"diameter [ab]|length [ab]|end feature|angles|rollers|thread size|male/female thread|ball mm)",
    re.IGNORECASE,
)


def _parse_size(text: str) -> Tuple[Optional[float], Optional[str]]:
    """Ball/tip size in mm. Inch sizes ('¾', '1 in.', '1/8 in.') are converted and noted."""
    if is_empty(text):
        return None, None
    value = parse_number(text)
    if value is not None:
        return value, None
    s = text.strip().lower().replace("in.", "").replace("in", "").replace('"', "").strip()
    inches: Optional[float] = None
    if s in FRACTIONS:
        inches = FRACTIONS[s]
    elif re.fullmatch(r"\d+/\d+", s):
        a, b = s.split("/")
        inches = int(a) / int(b)
    elif re.fullmatch(r"\d+(\.\d+)?", s):
        inches = float(s)
    elif len(s) == 2 and s[0].isdigit() and s[1] in FRACTIONS:
        inches = int(s[0]) + FRACTIONS[s[1]]
    if inches is None:
        return None, f"ball/tip size '{text}' not understood"
    return round(inches_to_mm(inches), 3), f"ball/tip size given in inches in the catalogue ('{text}'); converted with 25.4 mm/in"


def _listing_candidate_rows(page: "pymupdf.Page") -> List[List[Word]]:
    rows = []
    for line in group_lines(page_words(page)):
        start = next((i for i, w in enumerate(line[:2]) if strip_part_number(w.text)), None)
        if start is not None:
            rows.append(line[start:])
    if len(rows) < 10 or sum(len(r) for r in rows) / len(rows) < 9:
        return []
    return rows


def _parse_listing(doc: "pymupdf.Document") -> Dict[int, List[List[str]]]:
    candidates = {i + 1: _listing_candidate_rows(doc[i]) for i in range(len(doc))}
    # The listing is the block of consecutive candidate pages at the end of the document.
    pages = sorted(p for p, rows in candidates.items() if rows)
    listing: List[int] = []
    for p in reversed(pages):
        if not listing or listing[-1] - p == 1:
            listing.append(p)
        elif listing[-1] - p > 2:
            break
    groups: Dict[int, List[int]] = {}
    for p in listing:
        groups.setdefault(int(round(candidates[p][0][0].x0)), []).append(p)
    parsed: Dict[int, List[List[str]]] = {}
    for group_pages in groups.values():
        pooled = [r for p in group_pages for r in candidates[p]]
        anchors = column_anchors(pooled, expected=len(LISTING_COLUMNS))
        if len(anchors) != len(LISTING_COLUMNS):
            continue
        for p in group_pages:
            parsed[p] = [split_row(r, anchors) for r in candidates[p]]
    return parsed


def _section_pages(doc: "pymupdf.Document") -> Dict[str, int]:
    """Margin section labels such as '3.2' -> 1-based page number."""
    labels: Dict[str, int] = {}
    for i in range(len(doc)):
        page = doc[i]
        for w in page_words(page):
            if SECTION_LABEL_RE.match(w.text) and (w.x0 < 60 or w.x1 > page.rect.width - 60) and w.y0 < 320:
                labels.setdefault(w.text, i + 1)
    return labels


class _PageInfo:
    def __init__(self, page: "pymupdf.Page", page_no: int):
        self.page_no = page_no
        width = page.rect.width
        # Margin section labels ('3.2') share a baseline with table rows; they are not table content.
        self.words = [
            w for w in page_words(page)
            if not (SECTION_LABEL_RE.match(w.text) and (w.x0 < 60 or w.x1 > width - 60))
        ]
        self.lines = group_lines(self.words)
        self.headings = [h for h in page_headings(page) if h.y0 > 60]
        self.quick_reference = "quick reference guide" in page.get_text().lower()
        self.pn_words: List[Tuple[str, Word]] = [
            (strip_part_number(w.text), w) for w in self.words if strip_part_number(w.text)
        ]
        self.label_rows: List[Tuple[str, str, List[Word]]] = []  # (field, label text, line words)
        for line in self.lines:
            first_number = next((i for i, w in enumerate(line) if NUMBER_WORD_RE.match(w.text) or w.text == "N/A"), None)
            if not first_number:
                continue
            label = " ".join(w.text for w in line[:first_number])
            field = None
            for name, pattern in ROW_LABELS:
                m = re.search(pattern, label, re.IGNORECASE)
                if m:
                    field, label = name, label[m.start():].strip()
                    break
            if field is None:
                m = EXTRA_LABEL_RE.search(label)
                if m:
                    label = label[m.start():].strip()
                    field = "extra:" + re.sub(r"\s*(mm)?\s*\(.*$", "", label).strip()
            if field:
                self.label_rows.append((field, label, line[first_number:]))
        # Part-number bands: consecutive part-number lines belong to one table header.
        self.bands: List[Tuple[float, float]] = []
        for _, w in sorted(self.pn_words, key=lambda t: t[1].y0):
            if self.bands and w.y0 - self.bands[-1][1] < 16:
                self.bands[-1] = (self.bands[-1][0], max(self.bands[-1][1], w.y1))
            else:
                self.bands.append((w.y0, w.y1))
        self._tables: Optional[List[pymupdf.Rect]] = None
        self._page = page

    @property
    def tables(self) -> List["pymupdf.Rect"]:
        if self._tables is None:
            try:
                self._tables = [pymupdf.Rect(t.bbox) for t in self._page.find_tables().tables]
            except Exception:
                self._tables = []
        return self._tables

    def section_title(self, y: float) -> Optional[str]:
        main = None
        sub = None
        for h in self.headings:
            if h.y0 > y:
                break
            if h.size >= 11.9:
                main, sub = h.text, None
            else:
                sub = h.text
        if main and sub:
            return f"{main} – {sub}"
        return main or sub


def _cell_value(line: List[Word], cx: float, tolerance: float = 17.0) -> Tuple[Optional[float], Optional[str]]:
    """Value of a label row in the column centred on `cx`: (mm value, original text)."""
    best: Optional[Tuple[float, Optional[float], str]] = None
    for i, w in enumerate(line):
        if w.text == "N/A":
            centre, value, text = w.cx, None, "N/A"
        elif NUMBER_WORD_RE.match(w.text):
            nxt = line[i + 1] if i + 1 < len(line) else None
            if nxt is not None and nxt.text.startswith("(") and nxt.x0 - w.x1 < 8:
                centre, text = (w.x0 + nxt.x1) / 2, f"{w.text} {nxt.text}"
            else:
                centre, text = w.cx, w.text
            value = float(w.text.lstrip("Ø"))
        else:
            continue
        dist = abs(centre - cx)
        if dist <= tolerance and (best is None or dist < best[0]):
            best = (dist, value, text)
    return (best[1], best[2]) if best else (None, None)


def extract_h1000_catalogue(pdf_path: Path, document_id: str, image_dir: Path) -> ExtractionResult:
    doc = pymupdf.open(pdf_path)
    report = new_report(len(doc), "h1000_3200")
    image_dir.mkdir(parents=True, exist_ok=True)
    result = ExtractionResult(report=report)

    listing_pages = _parse_listing(doc)
    section_page = _section_pages(doc)
    report["tables_detected"] += len(listing_pages)
    report["tables_extracted"] += len(listing_pages)

    pages: Dict[int, _PageInfo] = {}
    occurrences: Dict[str, List[Tuple[int, Word]]] = {}
    for i in range(len(doc)):
        if (i + 1) in listing_pages:
            continue
        info = _PageInfo(doc[i], i + 1)
        if not info.pn_words:
            continue
        pages[i + 1] = info
        for pn, w in info.pn_words:
            occurrences.setdefault(pn, []).append((i + 1, w))

    listing: Dict[str, Tuple[int, List[str]]] = {}
    for page_no in sorted(listing_pages):
        for cells in listing_pages[page_no]:
            report["rows_extracted"] += 1
            pn = strip_part_number(cells[0])
            if pn in listing:
                report["rows_rejected"] += 1
                report["rejected_rows"].append({"part_number": pn, "page": page_no, "reason": "duplicate listing row"})
                continue
            listing[pn] = (page_no, cells)

    # Which image crop each (page, table, column) produced, so stacked part numbers share it.
    column_images: Dict[Tuple[int, int, int], Optional[Dict[str, Any]]] = {}
    body_tables = set()

    def body_data(pn: str, page_no: int, word: Word) -> Dict[str, Any]:
        """Values of the body-table column that contains this part number occurrence."""
        info = pages[page_no]
        band = next(b for b in info.bands if b[0] - 0.5 <= word.y0 <= b[1])
        next_band = min((b[0] for b in info.bands if b[0] > band[1]), default=1e9)
        found: Dict[str, Any] = {"rows": {}, "last_y": None, "band": band, "next_band": next_band}
        for field, label, line in info.label_rows:
            y = line[0].cy
            if not (band[1] - 2 < y < next_band and y - band[1] < 320):
                continue
            if field in found["rows"]:
                continue
            value, text = _cell_value(line, word.cx)
            if text is None:
                continue
            found["rows"][field] = (value, text, label)
            found["last_y"] = max(found["last_y"] or 0, max(w.y1 for w in line))
        return found

    def column_image(page_no: int, word: Word, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Illustration printed under this part's column, below the table's value rows."""
        info = pages[page_no]
        last_y, band, next_band = data["last_y"], data["band"], data["next_band"]
        if last_y is None:
            return None
        page = doc[page_no - 1]
        centres: List[float] = []
        for _, w in info.pn_words:
            if band[0] - 0.5 <= w.y0 <= band[1] and not any(abs(c - w.cx) < 10 for c in centres):
                centres.append(w.cx)
        centres.sort()
        col = min(range(len(centres)), key=lambda i: abs(centres[i] - word.cx))
        key = (page_no, int(band[0]), col)
        if key in column_images:
            return column_images[key]
        left_gap = centres[col] - centres[col - 1] if col > 0 else None
        right_gap = centres[col + 1] - centres[col] if col + 1 < len(centres) else None
        half = min(min(g for g in (left_gap, right_gap, 90.0) if g is not None) / 2, 45.0)
        x0, x1 = centres[col] - half, centres[col] + half
        y_top = last_y + 3
        # Skip table rows that directly continue below the last recognised row ('For use on', ...).
        span = (centres[0] - 45.0, centres[-1] + 45.0)
        for line in info.lines:
            in_span = [w for w in line if span[0] <= w.cx <= span[1] and w.y0 > last_y - 1]
            if not in_span:
                continue
            if min(w.y0 for w in in_span) - y_top <= 12:
                y_top = max(y_top, max(w.y1 for w in in_span) + 3)
            else:
                break
        y_limit = min(next_band - 30, page.rect.height - 36, y_top + 330)
        for h in info.headings:
            if h.y0 > y_top:
                y_limit = min(y_limit, h.y0 - 4)
                break
        # Stop at the first text line under the column (notes, captions of the next table).
        for w in info.words:
            if w.y0 > y_top + 2 and x0 <= w.cx <= x1:
                y_limit = min(y_limit, w.y0 - 2)
        image = None
        strip = pymupdf.Rect(x0, y_top, x1, y_limit)
        if strip.height >= 18:
            shapes = [
                r for r in drawing_rects(page)
                if x0 <= (r.x0 + r.x1) / 2 <= x1 and r.y0 >= y_top - 1 and r.y1 <= y_limit + 1
                and r.height > 1.5 and r.width < 2 * (x1 - x0)
            ]
            if shapes:
                bottom = max(r.y1 for r in shapes)
                crop = pymupdf.Rect(
                    max(x0, min(r.x0 for r in shapes) - 3), y_top,
                    min(x1, max(r.x1 for r in shapes) + 3), min(y_limit, bottom + 3),
                )
                filename = f"p{page_no:03d}_y{int(band[0])}_c{col}.png"
                saved = save_crop(page, crop, image_dir / filename, min_ink=0.012)
                if saved:
                    digest, ink = saved
                    image = image_record(
                        document_id, f"p{page_no:03d}_y{int(band[0])}_c{col}",
                        page_number=page_no, image_path=f"{document_id}/{filename}",
                        image_type="drawing", image_hash=digest,
                        metadata={
                            "method": "pymupdf_region_render", "dpi": 150, "bbox": rect_tuple(crop),
                            "ink_ratio": round(ink, 4), "column_index": col,
                            "view": "Product illustration printed under this part's column of the specification table",
                        },
                    )
                    result.images.append(image)
                    report["images_extracted"] += 1
                    report["images_verified"] += 1
        column_images[key] = image
        return image

    for pn in sorted(set(listing) | set(occurrences)):
        reasons: List[str] = []
        raw: Dict[str, Any] = {}
        extra: Dict[str, Any] = {}
        occs = occurrences.get(pn, [])
        body_occs = [(p, w) for p, w in occs if not pages[p].quick_reference]

        if pn in listing:
            listing_page, cells = listing[pn]
            raw["listing"] = {LISTING_COLUMNS[i]: cells[i] for i in range(len(LISTING_COLUMNS)) if not is_empty(cells[i])}
            raw["listing_page"] = listing_page
            description = cells[2]
            component = cells[4]
            category, stype = classify_h1000(component, description)
            thread = normalize_thread(cells[3]) or (None if is_empty(cells[3]) else cells[3])
            ball_dia, size_note = _parse_size(cells[5])
            if size_note:
                (extra if "converted" in size_note else raw)["ball_size_note"] = size_note
                if "not understood" in size_note:
                    reasons.append(size_note)
            ball_mat = normalize_material(cells[6])
            length = parse_number(cells[7])
            stem_mat = normalize_material(cells[8])
            ewl = parse_number(cells[9])
            mass = parse_number(cells[10])
            m_section = re.match(r"\d{1,2}\.\d{1,2}", cells[11])
            section_no = m_section.group(0) if m_section else None
            if not is_empty(cells[1]):
                extra["ps_number"] = cells[1]
            extra["component"] = component
            m_pack = re.search(r"×\s*(\d+)$", component)
            if m_pack:
                extra["pack_quantity"] = int(m_pack.group(1))
            if section_no:
                extra["section_no"] = section_no
        else:
            description, component, section_no = None, None, None
            category, stype, thread = "accessory", "accessory", None
            ball_dia = ball_mat = length = stem_mat = ewl = mass = None
            reasons.append("part number appears on a body page but not in the product listing; attributes not extracted")

        # Primary source page: the section the listing cites, if the part number is printed there.
        cited_page = section_page.get(section_no) if section_no else None
        primary = next(((p, w) for p, w in body_occs if p == cited_page), None)
        if primary is None and body_occs:
            primary = body_occs[0]
            if cited_page is not None:
                reasons.append(f"listing cites section {section_no} (page {cited_page}) but the part number was found on page {primary[0]}")
        stem_dia = None
        section_title = None
        image = None
        if primary:
            page_no, word = primary
            body_tables.add((page_no, round(word.y0 / 40)))
            section_title = pages[page_no].section_title(word.y0)
            data = body_data(pn, page_no, word)
            rows = data["rows"]
            raw["body"] = {label: text for _, (value, text, label) in rows.items()}
            checks = {"ball_diameter": ball_dia, "length": length}
            agree = True
            for field, expected in checks.items():
                if field in rows and rows[field][0] is not None and expected is not None:
                    if abs(rows[field][0] - expected) > 0.051:
                        agree = False
                        reasons.append(
                            f"listing and body table disagree on {field.replace('_', ' ')}: "
                            f"listing {expected:g} mm, body '{rows[field][1]}'"
                        )
            if agree and "stem_diameter" in rows:
                stem_dia = rows["stem_diameter"][0]
            for field, (value, text, label) in rows.items():
                if field.startswith("extra:"):
                    extra[re.sub(r"[^a-z0-9]+", "_", field[6:].lower()).strip("_")] = text
            if agree:
                image = column_image(page_no, word, data)
            source_page = page_no
        else:
            source_page = cited_page or (listing[pn][0] if pn in listing else occs[0][0])
            reasons.append("part number not found on a body page; stem diameter and illustration unavailable")
        other_pages = sorted({p for p, _ in occs} - {source_page})
        if other_pages:
            extra["also_on_pages"] = other_pages

        is_ball = category == "stylus" and stype in ("straight", "star", "cranked")
        bits = [b for b in (
            thread,
            f"Ø{ball_dia:g} mm {(ball_mat or '').lower()} {'ball' if is_ball else 'tip'}".replace("  ", " ") if ball_dia is not None else None,
            f"L {length:g} mm" if length is not None else None,
            f"{stem_mat.lower()} stem" if stem_mat else None,
        ) if b]
        name = (component or section_title or "Part") + (" – " + ", ".join(bits) if bits else "")
        if description:
            name = f"{name} ({description})"

        status = NEEDS_REVIEW if reasons else VALIDATED
        report["rows_validated" if status == VALIDATED else "rows_needs_review"] += 1
        if reasons:
            report["review_rows"].append({"part_number": pn, "page": source_page, "reasons": reasons})
        report["source_pages"][pn] = source_page

        product = product_record(
            document_id, pn,
            source_pdf=pdf_path.name, source_page=source_page,
            product_name=name, description=description,
            category=category, stylus_type=stype, thread=thread,
            ball_material=ball_mat, ball_diameter_mm=ball_dia,
            stem_material=stem_mat, stem_diameter_mm=stem_dia,
            overall_length_mm=length, effective_working_length_mm=ewl, weight_g=mass,
            source_table=f"p{source_page}: {section_title}" if section_title else f"p{source_page}",
            source_section=section_title,
            extra_attributes=extra, raw_attributes=raw,
            extraction_confidence=1.0 if not reasons else 0.6,
            validation_status=status, review_reason="; ".join(reasons) or None,
        )
        result.products.append(product)
        if image:
            result.links.append(link_record(
                image, product["id"], pn, VERIFIED,
                "table layout (illustration is in this part's column of the specification table)",
            ))

    report["tables_detected"] += len(body_tables)
    report["tables_extracted"] += len(body_tables)
    linked = {ln["part_number"] for ln in result.links}
    report["product_image_links"] = len(result.links)
    report["products_without_image"] = sum(1 for p in result.products if p["part_number"] not in linked)
    doc.close()
    logger.info(
        "H-1000-3200 extraction: %d products (%d need review), %d images, %d links",
        len(result.products), report["rows_needs_review"], len(result.images), len(result.links),
    )
    return result
