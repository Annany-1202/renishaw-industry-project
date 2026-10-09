"""Extractor for 'Styli for ZEISS applications' (H-1000-3036).

Layout (see docs/DATA_AUDIT.md):
  * Body pages: a section heading, a two-column property box (Thread / Base /
    Stem / Ball / notes) and a row-oriented specification table, with the
    dimensional schematic for that section to the right of the table.
  * Index pages at the end: one row per part number with every dimension and
    the page the part is specified on.

The index is the source of the dimensions (one clean row per part). The body
page supplies what the index lacks (section, thread, materials, notes) and is
used to cross-check the index numbers; rows that disagree are flagged for
review instead of being silently accepted.
"""
import re
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pymupdf

from backend.app.core.logging import logger
from backend.app.ingestion.models import (
    NEEDS_REVIEW, UNVERIFIED, VALIDATED, VERIFIED, ExtractionResult,
    image_record, link_record, new_report, product_record,
)
from backend.app.ingestion.normalizer import (
    all_threads, classify_zeiss_section, is_empty, normalize_material, normalize_thread,
    parse_number, parse_pair,
)
from backend.app.ingestion.pdf_utils import (
    Word, column_anchors, drawing_rects, group_lines, join_cell, page_headings, page_words,
    rect_tuple, save_crop, split_row, strip_part_number, union_rect,
)

INDEX_COLUMNS = [
    "Renishaw part no.", "ZEISS part no.", "DK (mm)", "ML1/ML (mm)", "DG/D (mm)", "L (mm)",
    "DS1/DS (mm)", "EAL/B (mm)", "Weight (g)", "A (mm)", "Thread/bore (mm)", "Thread (from/to)",
    "MB (mm)", "G1 (mm)", "SW (mm)", "Page no.",
]
# Dimension letters that can label a schematic, per index column.
COLUMN_LETTERS = {
    2: {"DK"}, 3: {"ML1", "ML"}, 4: {"DG", "D"}, 5: {"L"}, 6: {"DS1", "DS"}, 7: {"EAL", "B"},
    9: {"A"}, 12: {"MB"}, 13: {"G1"}, 14: {"SW"},
}
ALL_LETTERS = set().union(*COLUMN_LETTERS.values())
# Property-box keys that name the body material of a non-stylus component.
BODY_MATERIAL_KEYS = [
    "stem", "extension", "material", "meterial", "washer", "pin", "holder", "cube", "adaptor",
    "knuckle", "angle", "guage", "gauge", "spanner", "cube and plate",
]
TIP_MATERIAL_KEYS = ["ball", "disc", "cylinder"]
ZEISS_PN_RE = re.compile(r"^\d{4,6}-\d{4}(-\d{3})?$")
BODY_TOP, BODY_BOTTOM = 62.0, 545.0


def _index_candidate_rows(page: "pymupdf.Page") -> List[List[Word]]:
    lines = group_lines(page_words(page))
    rows = [ln for ln in lines if strip_part_number(ln[0].text)]
    if len(rows) < 10 or sum(len(r) for r in rows) / len(rows) < 12:
        return []
    return rows


def _parse_index(doc: "pymupdf.Document") -> Dict[int, List[List[str]]]:
    """Parse the index pages. Column starts are derived per left-margin group
    (odd and even pages are offset) from all of that group's rows together."""
    candidates = {i + 1: _index_candidate_rows(doc[i]) for i in range(len(doc))}
    candidates = {p: rows for p, rows in candidates.items() if rows}
    groups: Dict[int, List[int]] = {}
    for p, rows in candidates.items():
        groups.setdefault(int(round(rows[0][0].x0)), []).append(p)
    parsed: Dict[int, List[List[str]]] = {}
    for pages in groups.values():
        pooled = [r for p in pages for r in candidates[p]]
        anchors = column_anchors(pooled, expected=len(INDEX_COLUMNS))
        if len(anchors) != len(INDEX_COLUMNS):
            continue
        for p in pages:
            parsed[p] = [split_row(r, anchors) for r in candidates[p]]
    return parsed


def _property_boxes(page: "pymupdf.Page") -> List[Tuple[float, float, float, Dict[str, str]]]:
    """Two-column key/value boxes at the left margin: (y0, y1, x1, {key: value})."""
    boxes = []
    try:
        tables = page.find_tables().tables
    except Exception:
        return boxes
    for t in tables:
        if t.col_count != 2 or t.bbox[0] > 100:
            continue
        grid = t.extract()
        pairs = {}
        for row in grid:
            key = " ".join(str(row[0] or "").split())
            val = " ".join(str(row[1] or "").split())
            if key:
                pairs[key] = val
        if not pairs or any(strip_part_number(v) or "part number" in k.lower() for k, v in pairs.items()):
            continue
        boxes.append((t.bbox[1], t.bbox[3], t.bbox[2], pairs))
    return boxes


def _resolve_tip_material(kv: Dict[str, str], dk: Optional[float]) -> Tuple[Optional[str], Optional[str]]:
    """Return (canonical, original) tip material, resolving 'Ball diameter up to N mm' rules."""
    lower = {k.lower(): v for k, v in kv.items()}
    for key in TIP_MATERIAL_KEYS:
        if key in lower:
            return normalize_material(lower[key]), lower[key]
    for key, val in lower.items():
        m = re.match(r"ball diameter (up to|more than) (\d+(?:\.\d+)?)\s*mm", key)
        if m and dk is not None:
            limit = float(m.group(2))
            if (m.group(1) == "up to" and dk <= limit) or (m.group(1) == "more than" and dk > limit):
                return normalize_material(val), f"{val} ({key})"
    return None, None


def _resolve_body_material(kv: Dict[str, str]) -> Tuple[Optional[str], Optional[str]]:
    lower = {k.lower(): v for k, v in kv.items()}
    for key in BODY_MATERIAL_KEYS:
        if key in lower and not is_empty(lower[key]):
            return normalize_material(lower[key]), lower[key]
    return None, None


def _numbers(text: str) -> List[float]:
    text = re.sub(r"(\d)\.\s+(\d)", r"\1.\2", text)
    return [float(x) for x in re.findall(r"(?<![\w-])\d+(?:\.\d+)?(?![\w-])", text)]


class _Occurrence:
    __slots__ = ("page", "word", "block", "family", "section", "kv", "line_text")

    def __init__(self, page, word, block, family, section, kv, line_text):
        self.page, self.word, self.block = page, word, block
        self.family, self.section, self.kv, self.line_text = family, section, kv, line_text


def extract_zeiss_catalogue(pdf_path: Path, document_id: str, image_dir: Path) -> ExtractionResult:
    doc = pymupdf.open(pdf_path)
    report = new_report(len(doc), "zeiss_h1000_3036")
    image_dir.mkdir(parents=True, exist_ok=True)

    # ---- 1. Index ---------------------------------------------------------------------------
    index_pages = _parse_index(doc)
    index: Dict[str, Dict[str, Any]] = {}
    for page_no, rows in index_pages.items():
        for cells in rows:
            pn = strip_part_number(cells[0])
            report["rows_extracted"] += 1
            entry = index.setdefault(pn, {"cells": cells, "alt": [], "index_page": page_no})
            if not is_empty(cells[1]) and cells[1] not in entry["alt"]:
                entry["alt"].append(cells[1])
            if entry["cells"][2:] != cells[2:]:
                entry.setdefault("conflict", True)
    report["tables_detected"] += len(index_pages)
    report["tables_extracted"] += len(index_pages)

    # ---- 2. Body pages: sections, property boxes, part-number occurrences --------------------
    occurrences: Dict[str, List[_Occurrence]] = {}
    blocks: Dict[Tuple[int, int], Dict[str, Any]] = {}
    family, section, kv = None, None, {}
    for i in range(len(doc)):
        page_no = i + 1
        if page_no in index_pages:
            continue
        page = doc[i]
        words = page_words(page)
        pn_words = [w for w in words if strip_part_number(w.text) and BODY_TOP < w.cy < BODY_BOTTOM]
        if not pn_words:
            continue
        lines = group_lines([w for w in words if BODY_TOP < w.cy < BODY_BOTTOM])
        elements: List[Tuple[float, str, Any]] = []
        for h in page_headings(page):
            if BODY_TOP < h.y0 < BODY_BOTTOM and h.x0 < 100:
                elements.append((h.y0, "heading", h))
        boxes = _property_boxes(page)
        report["tables_detected"] += len(boxes)
        for y0, y1, x1, pairs in boxes:
            elements.append((y0, "kv", (y0, y1, x1, pairs)))
        for w in pn_words:
            elements.append((w.cy, "pn", w))
        elements.sort(key=lambda e: e[0])

        block_no = 0
        blocks[(page_no, 0)] = {"y0": BODY_TOP, "x_right": 0.0, "parts": [], "page": page_no}
        last_kind = None
        for y, kind, obj in elements:
            if kind == "heading":
                if obj.size >= 15.5:
                    family = obj.text
                    continue
                section, kv = obj.text, {}
                block_no += 1
                blocks[(page_no, block_no)] = {"y0": obj.y0 - 2, "x_right": 0.0, "parts": [], "page": page_no}
            elif kind == "kv":
                y0, y1, x1, pairs = obj
                kv = pairs
                if last_kind != "heading":
                    block_no += 1
                    blocks[(page_no, block_no)] = {"y0": y0 - 2, "x_right": 0.0, "parts": [], "page": page_no}
            else:
                pn = strip_part_number(obj.text)
                line = next((ln for ln in lines if obj in ln), [obj])
                same_table = [w for w in line if w.x0 >= obj.x0 - 1 and w.x0 - obj.x0 < 520]
                blk = blocks[(page_no, block_no)]
                blk["x_right"] = max(blk["x_right"], max(w.x1 for w in same_table))
                blk["parts"].append(pn)
                blk.setdefault("rows", []).append(
                    (obj.x0, min(w.y0 for w in same_table), max(w.x1 for w in same_table), max(w.y1 for w in same_table))
                )
                blk.update(section=section, family=family, kv=dict(kv))
                occurrences.setdefault(pn, []).append(
                    _Occurrence(page_no, obj, (page_no, block_no), family, section, dict(kv),
                                join_cell([w for w in same_table if w is not obj]))
                )
            last_kind = kind
        # Close blocks: each ends where the next one on the page starts.
        page_blocks = sorted((k for k in blocks if k[0] == page_no), key=lambda k: blocks[k]["y0"])
        for a, b in zip(page_blocks, page_blocks[1:] + [None]):
            blocks[a]["y1"] = blocks[b]["y0"] if b else BODY_BOTTOM

    spec_tables = {occ.block for occs in occurrences.values() for occ in occs}
    report["tables_detected"] += len(spec_tables)
    report["tables_extracted"] += len(spec_tables)

    # ---- 3. Product records ----------------------------------------------------------------
    result = ExtractionResult(report=report)
    block_columns: Dict[Tuple[int, int], set] = {}
    primary_block: Dict[str, Tuple[int, int]] = {}
    for pn in sorted(set(index) | set(occurrences)):
        entry = index.get(pn)
        occs = occurrences.get(pn, [])
        reasons: List[str] = []
        raw: Dict[str, Any] = {}
        extra: Dict[str, Any] = {}
        dk = ml1 = ml = dg = length = ds1 = ds = weight = None
        stated_page = None

        if entry:
            cells = entry["cells"]
            raw["index"] = {INDEX_COLUMNS[i]: cells[i] for i in range(len(INDEX_COLUMNS)) if not is_empty(cells[i])}
            raw["index_page"] = entry["index_page"]
            dk = parse_number(cells[2])
            ml1, ml = parse_pair(cells[3])
            dg = parse_number(cells[4])
            length = parse_number(cells[5])
            ds1, ds = parse_pair(cells[6])
            weight = parse_number(cells[8])
            stated_page = int(cells[15]) if cells[15].isdigit() else None
            for col, key in ((7, "eal_b_mm"), (9, "a_mm"), (12, "mb_mm"), (13, "g1_mm"), (14, "sw_mm")):
                val = parse_number(cells[col])
                if val is not None:
                    extra[key] = val
            for col, key in ((2, "dk_text"), (6, "ds_text"), (9, "a_text")):
                if not is_empty(cells[col]) and parse_number(cells[col]) is None and "/" not in cells[col]:
                    extra[key] = cells[col]
            for col, key in ((10, "thread_bore"), (11, "thread_from_to")):
                if not is_empty(cells[col]):
                    extra[key] = cells[col]
            if ml1 is not None:
                extra["ml1_mm"] = ml1
            if ds1 is not None:
                extra["ds1_mm"] = ds1
            if dg is not None:
                extra["base_or_body_diameter_mm"] = dg
            if entry.get("conflict"):
                reasons.append("index lists this part number more than once with different values")
        else:
            reasons.append("part number appears on a body page but not in the catalogue index; dimensions not extracted")

        occ = next((o for o in occs if o.page == stated_page), None)
        if occ is None and occs:
            occ = occs[0]
            if stated_page is not None:
                reasons.append(f"index cites page {stated_page} but the part number was found on page {occ.page}")
        if occ is None:
            reasons.append("part number not found on any body page; section, thread and materials unknown")

        kv = occ.kv if occ else {}
        section_title = occ.section if occ else None
        source_page = occ.page if occ else (stated_page or entry["index_page"])
        if occ:
            raw["body_row"] = occ.line_text
            raw["property_box"] = kv
            primary_block[pn] = occ.block
            if entry:
                block_columns.setdefault(occ.block, set()).update(
                    c for c in COLUMN_LETTERS if not is_empty(entry["cells"][c])
                )
                # Cross-check: every number in the index row must be on the body row.
                want = Counter(n for c in range(2, 15) for n in _numbers(entry["cells"][c]))
                have = Counter(_numbers(" ".join(t for t in occ.line_text.split() if not ZEISS_PN_RE.match(t))))
                missing = want - have
                if missing:
                    reasons.append(
                        "index and body table disagree: index values "
                        f"{sorted(missing.elements())} not on the body row '{occ.line_text}'"
                    )
            if not section_title:
                reasons.append("no section heading found for the body row")
        if len({o.page for o in occs}) > 1:
            extra["also_on_pages"] = sorted({o.page for o in occs} - {source_page})

        threads = all_threads(kv.get("Thread")) or all_threads(extra.get("thread_from_to"))
        thread = threads[0] if threads else None
        if len(threads) > 1:
            extra["threads"] = threads
        tip_mat, tip_raw = _resolve_tip_material(kv, dk)
        body_mat, body_raw = _resolve_body_material(kv)
        has_tip = dk is not None and "Stem" in kv
        category, stype = classify_zeiss_section(section_title or "", has_tip)
        for key, label in (("Base", "base_material"), ("Additional notes", "notes"), ("S4 Ball", "s4_ball_material")):
            if not is_empty(kv.get(key)):
                extra[label] = kv[key]
        if occ and occ.family:
            extra["family"] = occ.family
        if tip_raw:
            raw["tip_material"] = tip_raw
        if body_raw:
            raw["body_material"] = body_raw
        # Extensions and other tip-less parts: the catalogue's D is the body diameter.
        stem_dia = ds if ds is not None else (dg if category in ("extension",) else None)

        bits = [b for b in (
            thread,
            f"Ø{dk:g} mm {tip_mat.lower() + ' ' if tip_mat else ''}{'ball' if stype in ('straight', 'star', 'swivel', 'thread_measurement') else 'tip'}" if dk is not None and category == "stylus" else None,
            f"L {length:g} mm" if length is not None else None,
            f"{body_mat.lower()}{' stem' if category == 'stylus' else ''}" if body_mat else None,
        ) if b]
        name = (section_title or "ZEISS application part") + (" – " + ", ".join(bits) if bits else "")

        status = NEEDS_REVIEW if reasons else VALIDATED
        report["rows_validated" if status == VALIDATED else "rows_needs_review"] += 1
        if reasons:
            report["review_rows"].append({"part_number": pn, "page": source_page, "reasons": reasons})
        report["source_pages"][pn] = source_page

        result.products.append(product_record(
            document_id, pn,
            source_pdf=pdf_path.name, source_page=source_page,
            product_name=name, description=section_title,
            category=category, stylus_type=stype,
            alt_part_number=", ".join(entry["alt"]) if entry and entry["alt"] else None,
            thread=thread,
            ball_material=tip_mat, ball_diameter_mm=dk,
            stem_material=body_mat, stem_diameter_mm=stem_dia,
            overall_length_mm=length, effective_working_length_mm=ml, weight_g=weight,
            source_table=f"p{source_page}: {section_title}" if section_title else f"p{source_page}",
            source_section=section_title,
            extra_attributes=extra, raw_attributes=raw,
            extraction_confidence=1.0 if not reasons else 0.6,
            validation_status=status, review_reason="; ".join(reasons) or None,
        ))

    # ---- 4. Section schematics --------------------------------------------------------------
    product_ids = {p["part_number"]: p["id"] for p in result.products}
    section_image: Dict[Tuple[Any, str], Tuple[Dict[str, Any], str, str]] = {}
    for key in sorted(blocks):
        blk = blocks[key]
        parts = [pn for pn in dict.fromkeys(blk["parts"]) if primary_block.get(pn) == key]
        if not parts:
            continue
        page = doc[key[0] - 1]
        section_key = (blk.get("section"), repr(sorted((blk.get("kv") or {}).items())))
        # Table areas of this block, one per page column (rows are grouped by their left edge).
        tables: List[pymupdf.Rect] = []
        for x0 in sorted({round(r[0] / 150) for r in blk.get("rows", [])}):
            rows = [r for r in blk["rows"] if round(r[0] / 150) == x0]
            tables.append(pymupdf.Rect(
                min(r[0] for r in rows) - 6, min(r[1] for r in rows) - 34,
                max(r[2] for r in rows) + 8, max(r[3] for r in rows) + 8,
            ))
        x_left = min(t.x1 for t in tables) if tables else blk["x_right"] + 6
        band = pymupdf.Rect(x_left, max(blk["y0"], BODY_TOP), page.rect.width - 20, min(blk["y1"], BODY_BOTTOM))
        area = None
        if not band.is_empty and band.width >= 40:
            inside = [
                r for r in drawing_rects(page)
                if band.contains(r) and (r.width > 1 or r.height > 1)
                and not any(r.intersects(t) for t in tables)
            ]
            area = union_rect(inside)
        saved = None
        if area is not None and area.width >= 20 and area.height >= 12:
            # Dimension labels sit just outside the line work; include them in the crop.
            raw_words = [Word(*w[:5]) for w in page.get_text("words")]  # includes rotated labels
            near = area + (-18, -18, 18, 18)
            label_words = [
                w for w in raw_words
                if band.contains(pymupdf.Rect(w.x0, w.y0, w.x1, w.y1))
                and pymupdf.Rect(w.x0, w.y0, w.x1, w.y1).intersects(near)
                and not any(pymupdf.Rect(w.x0, w.y0, w.x1, w.y1).intersects(t) for t in tables)
            ]
            area = union_rect([area] + [pymupdf.Rect(w.x0, w.y0, w.x1, w.y1) for w in label_words])
            crop = (area + (-6, -6, 6, 6)) & band
            filename = f"p{key[0]:03d}_s{key[1]}_schematic.png"
            saved = save_crop(page, crop, image_dir / filename)
        if not saved:
            # Continuation of a section that started on an earlier page: its schematic is printed there.
            previous = section_image.get(section_key)
            if previous and blk.get("section"):
                image, status, basis = previous
                for pn in parts:
                    result.links.append(link_record(
                        image, product_ids[pn], pn, status,
                        f"{basis}; section continues from page {image['page_number']}",
                    ))
            continue
        digest, ink = saved
        letters = {w.text.strip("()") for w in label_words} & ALL_LETTERS
        allowed = set().union(*(COLUMN_LETTERS[c] for c in block_columns.get(key, set())), set())
        conflicting = sorted(letters - allowed)
        has_raster = any(band.contains(pymupdf.Rect(info["bbox"])) for info in page.get_image_info())
        if conflicting:
            status, basis = UNVERIFIED, f"schematic shows dimensions {conflicting} that the section table does not list"
        elif letters:
            status, basis = VERIFIED, "section layout + dimension letters match the section table columns"
        else:
            status, basis = VERIFIED, "section layout (illustration is beside this section's table only)"
        image = image_record(
            document_id, f"p{key[0]:03d}_s{key[1]}",
            page_number=key[0], image_path=f"{document_id}/{filename}",
            image_type="photograph" if has_raster and not letters else "drawing",
            image_hash=digest,
            metadata={
                "method": "pymupdf_region_render", "dpi": 150, "bbox": rect_tuple(crop), "ink_ratio": round(ink, 4),
                "section": blk.get("section"), "dimension_letters": sorted(letters),
                "view": f"Section schematic for '{blk.get('section')}'",
            },
        )
        result.images.append(image)
        section_image[section_key] = (image, status, basis)
        report["images_extracted"] += 1
        report["images_verified" if status == VERIFIED else "images_unverified"] += 1
        for pn in parts:
            result.links.append(link_record(image, product_ids[pn], pn, status, basis))

    linked = {ln["part_number"] for ln in result.links if ln["association_status"] == VERIFIED}
    report["product_image_links"] = len(result.links)
    report["products_without_image"] = sum(1 for p in result.products if p["part_number"] not in linked)
    doc.close()
    logger.info(
        "ZEISS extraction: %d products (%d need review), %d images, %d links",
        len(result.products), report["rows_needs_review"], len(result.images), len(result.links),
    )
    return result
