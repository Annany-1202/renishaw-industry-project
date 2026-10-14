"""Versioned, validated data contracts between interpretation, matching and the API."""
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

QUERY_SCHEMA_VERSION = "2.0"

ALLOWED_CATEGORIES = ["stylus", "extension", "adaptor", "knuckle", "cube", "holder", "kit", "tool", "accessory"]
HARD_CAPABLE = [
    "thread", "secondary_thread", "category", "stylus_type", "ball_material", "stem_material", "ball_diameter_mm",
    "stem_diameter_mm", "overall_length_mm", "effective_working_length_mm",
]
NUMERIC_ATTRIBUTES = ["ball_diameter_mm", "stem_diameter_mm", "overall_length_mm", "effective_working_length_mm"]
# Attributes that describe a ball/tip and therefore do not apply to tip-less components.
TIP_ATTRIBUTES = ["ball_material", "ball_diameter_mm", "effective_working_length_mm"]
TIPLESS_CATEGORIES = ["extension", "adaptor", "knuckle", "cube", "holder", "tool"]


class RequestedAttribute(BaseModel):
    """One attribute of the request, with what the user typed and how it was normalised."""
    name: str
    value: Any
    unit: Optional[str] = None
    original_text: Optional[str] = None
    is_hard_constraint: bool = False
    source: Literal["query", "clarification", "llm", "inferred", "manual"] = "query"
    note: Optional[str] = None


class ParsedQuery(BaseModel):
    model_config = ConfigDict(extra="ignore")

    schema_version: str = QUERY_SCHEMA_VERSION
    original_query: str = ""
    category: Optional[str] = None
    stylus_type: Optional[str] = None
    thread: Optional[str] = None
    # Second thread of a thread adaptor ("M3 to M2 adaptor").
    secondary_thread: Optional[str] = None
    ball_material: Optional[str] = None
    ball_diameter_mm: Optional[float] = Field(default=None, gt=0, le=1000)
    stem_material: Optional[str] = None
    stem_diameter_mm: Optional[float] = Field(default=None, gt=0, le=1000)
    overall_length_mm: Optional[float] = Field(default=None, gt=0, le=5000)
    effective_working_length_mm: Optional[float] = Field(default=None, gt=0, le=5000)
    part_number: Optional[str] = None

    # Names of attributes that may not be relaxed / that the user said are flexible.
    hard_constraints: List[str] = Field(default_factory=list)
    flexible_preferences: List[str] = Field(default_factory=list)

    # Diagnostics (FR-02: keep the original request and the normalised interpretation).
    requested_attributes: List[RequestedAttribute] = Field(default_factory=list)
    unspecified_attributes: List[str] = Field(default_factory=list)
    application_terms: List[str] = Field(default_factory=list)
    descriptor_terms: List[str] = Field(default_factory=list)
    qualitative_terms: List[str] = Field(default_factory=list)
    probe_model: Optional[str] = None
    assumptions: List[str] = Field(default_factory=list)
    unparsed_terms: List[str] = Field(default_factory=list)
    # field -> {"inches": value typed, "decimals": digits typed}; used for precision-aware matching
    inch_inputs: Dict[str, Dict[str, float]] = Field(default_factory=dict)
    ignored_attributes: List[str] = Field(default_factory=list)

    is_irrelevant: bool = False
    irrelevance_reason: Optional[str] = None
    has_conflicting_constraints: bool = False
    conflict_description: Optional[str] = None
    clarification_needed: bool = False
    clarification_type: Optional[str] = None
    clarification_question: Optional[str] = None
    suggested_options: List[str] = Field(default_factory=list)
    # Clarification questions already asked for this request (blocking types, and "NARROW:<field>" for
    # follow-ups), so a follow-up dialogue progresses instead of repeating itself.
    clarification_history: List[str] = Field(default_factory=list)
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    llm_used: bool = False
    interpreter: str = "rules"

    @field_validator("category")
    @classmethod
    def _category(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        v = str(v).strip().lower()
        return v if v in ALLOWED_CATEGORIES else None

    @field_validator("thread", "secondary_thread")
    @classmethod
    def _thread(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        v = str(v).strip().upper()
        import re
        return v if re.fullmatch(r"M\d{1,2}", v) else None

    @field_validator("hard_constraints", "flexible_preferences")
    @classmethod
    def _known_names(cls, v: List[str]) -> List[str]:
        return [name for name in dict.fromkeys(v) if name in HARD_CAPABLE]

    def has_search_attributes(self) -> bool:
        return any(
            getattr(self, f) is not None for f in
            ("thread", "ball_material", "ball_diameter_mm", "stem_material", "stem_diameter_mm",
             "overall_length_mm", "effective_working_length_mm", "part_number")
        ) or bool(self.descriptor_terms)


class AttributeComparison(BaseModel):
    attribute_name: str
    label: str = ""
    requested_value: Any = None
    product_value: Any = None
    unit: Optional[str] = None
    status: Literal["MATCH", "DIFFERS", "UNKNOWN", "NOT_APPLICABLE"]
    is_hard: bool = False
    weight: float = 0.0
    score: float = 0.0
    difference_description: Optional[str] = None
    note: Optional[str] = None


class ImageInfo(BaseModel):
    image_id: str
    document_id: str
    source_pdf: str
    page_number: int
    image_url: str
    image_type: str
    association_status: str
    association_basis: Optional[str] = None
    description: Optional[str] = None
    label: Optional[str] = None


class SourceReference(BaseModel):
    document_id: str
    source_pdf: str
    source_page: int
    source_table: Optional[str] = None
    validation_status: str = "validated"
    record_id: str = ""


class ProductMatch(BaseModel):
    id: str
    document_id: str
    manufacturer: Optional[str] = None
    part_number: str
    alt_part_number: Optional[str] = None
    product_name: str
    description: Optional[str] = None
    category: str
    stylus_type: Optional[str] = None
    thread: Optional[str] = None
    ball_material: Optional[str] = None
    ball_diameter_mm: Optional[float] = None
    stem_material: Optional[str] = None
    stem_diameter_mm: Optional[float] = None
    overall_length_mm: Optional[float] = None
    effective_working_length_mm: Optional[float] = None
    weight_g: Optional[float] = None
    extra_attributes: Dict[str, Any] = Field(default_factory=dict)
    original_values: Dict[str, Any] = Field(default_factory=dict)

    # Provenance
    source_pdf: str
    source_page: int
    source_table: Optional[str] = None
    sources: List[SourceReference] = Field(default_factory=list)
    validation_status: str = "validated"
    review_reason: Optional[str] = None

    # Classification & scoring
    match_class: Literal["EXACT_MATCH", "ALTERNATIVE", "NO_MATCH"]
    score: float = 0.0

    attribute_comparisons: List[AttributeComparison] = Field(default_factory=list)
    matching_attributes: List[str] = Field(default_factory=list)
    differing_attributes: List[str] = Field(default_factory=list)
    missing_attributes: List[str] = Field(default_factory=list)

    explanation: str
    explanation_source: Literal["template", "llm"] = "template"

    images: List[ImageInfo] = Field(default_factory=list)
    image_note: Optional[str] = None


class SearchResponse(BaseModel):
    search_id: str = ""
    query: str
    interpreted_query: ParsedQuery
    result_class: Literal["EXACT_MATCH", "ALTERNATIVE", "NO_MATCH"]
    # exact | alternative | no_match | insufficient_evidence | irrelevant | conflict | clarification
    outcome: str = "no_match"
    message: Optional[str] = None
    total_found: int = 0
    results: List[ProductMatch] = Field(default_factory=list)
    clarification: Optional[Dict[str, Any]] = None
    # Optional question that narrows a broad result set; the results are still shown.
    follow_up: Optional[Dict[str, Any]] = None
    diagnostics: Dict[str, Any] = Field(default_factory=dict)
    score_note: str = (
        "Scores are internal ranking scores (0-100) over the requested attributes. They are not "
        "calibrated probabilities and do not certify engineering suitability."
    )
    execution_time_ms: float = 0.0
