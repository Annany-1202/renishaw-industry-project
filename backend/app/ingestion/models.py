"""Plain data containers passed from extractors to the ingestion pipeline."""
import json
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

VALIDATED = "validated"
NEEDS_REVIEW = "needs_review"
REJECTED = "rejected"

VERIFIED = "verified"
UNVERIFIED = "unverified"


def new_report(pages: int, extractor: str) -> Dict[str, Any]:
    return {
        "extractor": extractor,
        "pages_processed": pages,
        "tables_detected": 0,
        "tables_extracted": 0,
        "rows_extracted": 0,
        "rows_validated": 0,
        "rows_needs_review": 0,
        "rows_rejected": 0,
        "rejected_rows": [],
        "review_rows": [],
        "images_extracted": 0,
        "images_verified": 0,
        "images_unverified": 0,
        "product_image_links": 0,
        "products_without_image": 0,
        "source_pages": {},
        "exceptions": [],
    }


def product_record(
    document_id: str,
    part_number: str,
    *,
    source_pdf: str,
    source_page: int,
    product_name: str,
    category: str,
    stylus_type: Optional[str] = None,
    description: Optional[str] = None,
    alt_part_number: Optional[str] = None,
    thread: Optional[str] = None,
    ball_material: Optional[str] = None,
    ball_diameter_mm: Optional[float] = None,
    stem_material: Optional[str] = None,
    stem_diameter_mm: Optional[float] = None,
    overall_length_mm: Optional[float] = None,
    effective_working_length_mm: Optional[float] = None,
    weight_g: Optional[float] = None,
    source_table: Optional[str] = None,
    source_section: Optional[str] = None,
    extra_attributes: Optional[Dict[str, Any]] = None,
    raw_attributes: Optional[Dict[str, Any]] = None,
    extraction_confidence: float = 1.0,
    validation_status: str = VALIDATED,
    review_reason: Optional[str] = None,
    manufacturer: str = "Renishaw",
) -> Dict[str, Any]:
    return {
        "id": f"{document_id}:{part_number}",
        "document_id": document_id,
        "manufacturer": manufacturer,
        "part_number": part_number,
        "alt_part_number": alt_part_number,
        "product_name": product_name,
        "description": description,
        "category": category,
        "stylus_type": stylus_type,
        "thread": thread,
        "ball_material": ball_material,
        "ball_diameter_mm": ball_diameter_mm,
        "stem_material": stem_material,
        "stem_diameter_mm": stem_diameter_mm,
        "overall_length_mm": overall_length_mm,
        "effective_working_length_mm": effective_working_length_mm,
        "weight_g": weight_g,
        "extra_attributes": json.dumps(extra_attributes or {}, ensure_ascii=False),
        "raw_attributes": json.dumps(raw_attributes or {}, ensure_ascii=False),
        "source_pdf": source_pdf,
        "source_page": source_page,
        "source_table": source_table,
        "source_section": source_section,
        "extraction_confidence": extraction_confidence,
        "validation_status": validation_status,
        "review_reason": review_reason,
    }


@dataclass
class ExtractionResult:
    products: List[Dict[str, Any]] = field(default_factory=list)
    # One row per stored image file.
    images: List[Dict[str, Any]] = field(default_factory=list)
    # Many-to-many product <-> image associations.
    links: List[Dict[str, Any]] = field(default_factory=list)
    report: Dict[str, Any] = field(default_factory=dict)


def image_record(
    document_id: str,
    key: str,
    *,
    page_number: int,
    image_path: str,
    image_type: str,
    image_hash: str,
    metadata: Dict[str, Any],
) -> Dict[str, Any]:
    return {
        "image_id": f"img_{document_id}_{key}",
        "document_id": document_id,
        "page_number": page_number,
        "image_path": image_path,
        "image_type": image_type,
        "image_hash": image_hash,
        "extraction_metadata": json.dumps(metadata, ensure_ascii=False),
    }


def link_record(image: Dict[str, Any], product_id: str, part_number: str, status: str, basis: str) -> Dict[str, Any]:
    return {
        "image_id": image["image_id"],
        "document_id": image["document_id"],
        "product_id": product_id,
        "part_number": part_number,
        "association_status": status,
        "association_basis": basis,
    }
