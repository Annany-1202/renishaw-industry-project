from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from backend.app.matching.schemas import SearchResponse
from backend.app.retrieval.unified_search import MAX_QUERY_CHARS, InvalidOverride, search_products

router = APIRouter(prefix="/api/search", tags=["search"])


class SearchRequest(BaseModel):
    query: str = Field(default="", max_length=MAX_QUERY_CHARS)
    clarification_answer: Optional[str] = Field(default=None, max_length=MAX_QUERY_CHARS)
    # The interpreted_query of the previous response, sent back to refine the SAME search.
    previous_query: Optional[Dict[str, Any]] = None
    # Attribute edits from the UI chips, e.g. {"thread": "M3", "hard_constraints": ["thread"]}.
    manual_overrides: Optional[Dict[str, Any]] = None


@router.post("", response_model=SearchResponse)
def post_search(req: SearchRequest) -> SearchResponse:
    if not req.query.strip() and not (req.clarification_answer or "").strip():
        raise HTTPException(status_code=400, detail="Enter a description of the product you are looking for.")
    try:
        return search_products(req.query, req.clarification_answer, req.previous_query, req.manual_overrides)
    except InvalidOverride as exc:
        raise HTTPException(status_code=422, detail=str(exc))
