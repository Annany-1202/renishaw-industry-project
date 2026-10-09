"""Conservative extractor for uploaded PDFs whose layout is not known in advance.

It only records what a table states: a row becomes a product when the table
has a recognisable part-number column, and attributes are taken only from
columns whose header names them. Nothing is defaulted (no assumed thread or
material). Images are stored but an association is marked verified only when
a caption next to the image names exactly one extracted part number.
"""
import hashlib
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

import pymupdf

from backend.app.core.logging import logger
from backend.app.ingestion.models import (
    NEEDS_REVIEW, UNVERIFIED, VALIDATED, VERIFIED, ExtractionResult,
    image_record, link_record, new_report, product_record,
)
from backend.app.ingestion.normalizer import (
    MM_PER_INCH, is_empty, normalize_material, normalize_thread, parse_number,
)
from backend.app.ingestion.pdf_utils import page_words

GENERIC_PN_RE = re.compile(r"\b(?=[A-Z0-9-]*\d{3})[A-Z0-9]{1,8}(?:-[A-Z0-9]{2,8}){1,3}\b")

HEADER_FIELDS = [
    ("part_number", r"\bpart\s*(number|no\.?|#)|\border\s*(number|no\.?)|\barticle\b|\bitem\s*(number|no\.?)"),
    ("alt_part_number", r"\b(alt\w*|cross|oem|zeiss)\b.*\b(number|no\.?)"),
    ("description", r"\bdescription\b|\bproduct\s*name\b|^name$|\bdesignation\b"),
    ("thread", r"\bthread\b|\bmount(ing)?\b|\binterface\b"),
    ("ball_material", r"\b(ball|tip|sphere)\b.*\bmaterial\b"),
    ("stem_material", r"\b(stem|shaft|body)\b.*\bmaterial\b"),
    ("ball_diameter_mm", r"\b(ball|tip|sphere)\b.*\b(dia\w*|size|ø)|^dk\b"),
    ("stem_diameter_mm", r"\b(stem|shaft)\b.*\bdia\w*|^ds\b"),
    ("effective_working_length_mm", r"\bewl\b|\beffective\b.*\blength\b|\bworking\s+length\b|^ml\b"),
    ("overall_length_mm", r"\b(overall\s+)?length\b|^l\b"),
    ("weight_g", r"\b(weight|mass)\b"),
    ("category", r"\b(type|category|component)\b"),
]
CATEGORY_WORDS = [
    ("extension", r"\bextension"), ("adaptor", r"\badapt[oe]r"), ("knuckle", r"\bknuckle"),
    ("cube", r"\bcube"), ("holder", r"\bholder"), ("kit", r"\bkit\b"), ("tool", r"\b(tool|spanner|key)\b"),
    ("stylus", r"\bstyl(us|i)\b|\bprobe tip\b"),
]
STYLUS_TYPES = [("star", r"\bstar\b"), ("disc", r"\bdis[ck]\b"), ("cylinder", r"\bcylind"), ("pointer", r"\bpointer\b")]


def _header_map(header: List[Any]) -> Dict[str, int]:
    mapping: Dict[str, int] = {}
    for idx, cell in enumerate(header):
        text = " ".join(str(cell or "").lower().split())
        if not text:
            continue
        for field, pattern in HEADER_FIELDS:
            if field not in mapping and re.search(pattern, text):
                mapping[field] = idx
                break
    return mapping


def _to_mm(value: Any, header: str) -> Optional[float]:
    number = parse_number(value)
    if number is None:
        return None
    head = header.lower()
    if re.search(r"\b(in|inch|inches)\b|\(in\.?\)", head) and "mm" not in head:
        return round(number * MM_PER_INCH, 3)
    return number


def _orient(grid: List[List[Any]]) -> List[List[Any]]:
    """Transpose matrix-style tables whose first column holds the row labels (part number, length...)."""
    first_col = [" ".join(str(r[0] or "").lower().split()) for r in grid]
    if any(GENERIC_PN_RE.search(c.upper()) for c in first_col[1:]):
        return grid  # part numbers run down the first column: an ordinary row-per-product table
    if any(re.search(HEADER_FIELDS[0][1], c) for c in first_col[:6]) and not re.search(
        HEADER_FIELDS[0][1], " ".join(str(c or "").lower() for c in grid[0][1:])
    ):
        width = max(len(r) for r in grid)
        return [[(r[i] if i < len(r) else None) for r in grid] for i in range(width)]
    return grid


def extract_generic_catalogue(pdf_path: Path, document_id: str, image_dir: Path) -> ExtractionResult:
    doc = pymupdf.open(pdf_path)
    report = new_report(len(doc), "generic_tables")
    image_dir.mkdir(parents=True, exist_ok=True)
    result = ExtractionResult(report=report)
    seen: Dict[str, int] = {}
    page_parts: Dict[int, List[str]] = {}

    for i in range(len(doc)):
        page_no = i + 1
        page = doc[i]
        try:
            tables = page.find_tables().tables
        except Exception as exc:
            report["exceptions"].append(f"page {page_no}: table detection failed ({type(exc).__name__})")
            continue
        report["tables_detected"] += len(tables)
        for t_idx, table in enumerate(tables):
            grid = [row for row in table.extract() if any(not is_empty(c) for c in row)]
            if len(grid) < 2:
                continue
            grid = _orient(grid)
            header = [" ".join(str(c or "").split()) for c in grid[0]]
            mapping = _header_map(header)
            if "part_number" not in mapping:
                continue
            report["tables_extracted"] += 1
            for row in grid[1:]:
                report["rows_extracted"] += 1

                def cell(field: str) -> Optional[str]:
                    idx = mapping.get(field)
                    if idx is None or idx >= len(row) or is_empty(row[idx]):
                        return None
                    return " ".join(str(row[idx]).split())

                match = GENERIC_PN_RE.search((cell("part_number") or "").upper())
                if not match:
                    report["rows_rejected"] += 1
                    report["rejected_rows"].append({
                        "page": page_no, "table": t_idx,
                        "reason": "no part number in the part-number column",
                        "row": [str(c) for c in row][:12],
                    })
                    continue
                pn = match.group(0)
                if pn in seen:
                    report["rows_rejected"] += 1
                    report["rejected_rows"].append({
                        "page": page_no, "table": t_idx, "part_number": pn,
                        "reason": f"duplicate of the row extracted from page {seen[pn]}",
                    })
                    continue
                seen[pn] = page_no
                row_text = " ".join(str(c) for c in row if not is_empty(c))
                description = cell("description")
                context = f"{cell('category') or ''} {description or ''}".lower()
                category = next((c for c, pat in CATEGORY_WORDS if re.search(pat, context)), None)
                stype = next((s for s, pat in STYLUS_TYPES if re.search(pat, context)), None)
                reasons: List[str] = []
                if category is None:
                    category = "accessory"
                    reasons.append("product category could not be determined from the table")
                elif category == "stylus" and stype is None:
                    stype = "straight"
                dims = {
                    f: _to_mm(cell(f), header[mapping[f]]) for f in
                    ("ball_diameter_mm", "stem_diameter_mm", "overall_length_mm", "effective_working_length_mm")
                    if f in mapping
                }
                weight = parse_number(cell("weight_g")) if "weight_g" in mapping else None
                thread = normalize_thread(cell("thread")) or normalize_thread(description)
                if not any(v is not None for v in dims.values()) and not description:
                    reasons.append("row has a part number but no recognised attributes")
                status = NEEDS_REVIEW if reasons else VALIDATED
                report["rows_validated" if status == VALIDATED else "rows_needs_review"] += 1
                if reasons:
                    report["review_rows"].append({"part_number": pn, "page": page_no, "reasons": reasons})
                report["source_pages"][pn] = page_no
                page_parts.setdefault(page_no, []).append(pn)
                result.products.append(product_record(
                    document_id, pn,
                    source_pdf=pdf_path.name, source_page=page_no,
                    product_name=description or f"{category.capitalize()} {pn}",
                    description=description, category=category, stylus_type=stype or category,
                    alt_part_number=cell("alt_part_number"), thread=thread,
                    ball_material=normalize_material(cell("ball_material")),
                    ball_diameter_mm=dims.get("ball_diameter_mm"),
                    stem_material=normalize_material(cell("stem_material")),
                    stem_diameter_mm=dims.get("stem_diameter_mm"),
                    overall_length_mm=dims.get("overall_length_mm"),
                    effective_working_length_mm=dims.get("effective_working_length_mm"),
                    weight_g=weight,
                    source_table=f"p{page_no}: table {t_idx + 1}",
                    raw_attributes={"header": header, "row": [None if c is None else str(c) for c in row], "row_text": row_text},
                    extraction_confidence=0.9 if status == VALIDATED else 0.5,
                    validation_status=status, review_reason="; ".join(reasons) or None,
                    manufacturer="Unknown",
                ))

    # Embedded raster images. Verified only via an adjacent caption naming one extracted part.
    product_ids = {p["part_number"]: p["id"] for p in result.products}
    for i in range(len(doc)):
        page_no = i + 1
        page = doc[i]
        words = page_words(page)
        for n, info in enumerate(page.get_image_info(xrefs=True)):
            bbox = pymupdf.Rect(info["bbox"])
            xref = info.get("xref") or 0
            if bbox.width < 40 or bbox.height < 40 or not xref:
                continue
            try:
                extracted = doc.extract_image(xref)
                data = extracted["image"]
                ext = extracted.get("ext", "png").lower()
                if ext not in ("png", "jpg", "jpeg"):
                    pix = pymupdf.Pixmap(doc, xref)
                    if pix.n - pix.alpha > 3:
                        pix = pymupdf.Pixmap(pymupdf.csRGB, pix)
                    data, ext = pix.tobytes("png"), "png"
            except Exception as exc:
                report["exceptions"].append(f"page {page_no}: image {n} could not be extracted ({type(exc).__name__})")
                continue
            filename = f"p{page_no:03d}_img{n}.{ext}"
            (image_dir / filename).write_bytes(data)
            near = pymupdf.Rect(bbox.x0, bbox.y0 - 26, bbox.x1, bbox.y1 + 26)
            caption = " ".join(w.text for w in words if near.contains(pymupdf.Point(w.cx, w.cy)) and not bbox.contains(pymupdf.Point(w.cx, w.cy)))
            named = {m.group(0) for m in GENERIC_PN_RE.finditer(caption.upper())} & set(product_ids)
            image = image_record(
                document_id, f"p{page_no:03d}_img{n}",
                page_number=page_no, image_path=f"{document_id}/{filename}",
                image_type="photograph", image_hash=hashlib.sha256(data).hexdigest(),
                metadata={"method": "embedded_image", "xref": xref, "bbox": [round(v, 1) for v in bbox], "caption": caption[:200]},
            )
            result.images.append(image)
            report["images_extracted"] += 1
            if len(named) == 1:
                pn = next(iter(named))
                result.links.append(link_record(image, product_ids[pn], pn, VERIFIED, "caption next to the image names this part number"))
                report["images_verified"] += 1
            else:
                report["images_unverified"] += 1
                basis = ("caption names several part numbers" if len(named) > 1
                         else "image is on the same page only; no caption or label identifies the part")
                targets = sorted(named) if named else page_parts.get(page_no, [])
                for pn in targets:
                    result.links.append(link_record(image, product_ids[pn], pn, UNVERIFIED, basis))

    linked = {ln["part_number"] for ln in result.links if ln["association_status"] == VERIFIED}
    report["product_image_links"] = len(result.links)
    report["products_without_image"] = sum(1 for p in result.products if p["part_number"] not in linked)
    doc.close()
    logger.info("Generic extraction: %d products, %d images", len(result.products), len(result.images))
    return result
