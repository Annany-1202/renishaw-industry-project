"""Retrieval settings that can be changed at runtime.

Changes are validated, applied to the in-memory settings and persisted in the
`app_settings` table so they survive a restart. Paths, model names and the
Ollama address are deliberately not changeable through the API.
"""
import json
from typing import Any, Dict, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

from backend.app.core.config import ScoringWeights, Settings, TolerancesConfig, settings
from backend.app.core.logging import logger
from backend.app.db.database import db

_KEY = "runtime_settings"


class SettingsPatch(BaseModel):
    """Fields accepted by PATCH /api/settings. Unknown fields are rejected."""
    model_config = ConfigDict(extra="forbid")

    min_alternative_score: Optional[float] = Field(default=None, ge=0, le=100)
    max_results: Optional[int] = Field(default=None, ge=1, le=20)
    llm_temperature: Optional[float] = Field(default=None, ge=0, le=1)
    llm_mode: Optional[Literal["auto", "always", "off"]] = None
    llm_explanations: Optional[bool] = None
    weights: Optional[Dict[str, float]] = None
    tolerances: Optional[Dict[str, float]] = None


def effective() -> Dict[str, Any]:
    return {
        "app_name": settings.APP_NAME,
        "version": settings.VERSION,
        "llm_model": settings.LLM_MODEL,
        "embedding_model": settings.EMBEDDING_MODEL,
        "ollama_base_url": settings.OLLAMA_BASE_URL,
        "min_alternative_score": settings.MIN_ALTERNATIVE_SCORE,
        "max_results": settings.MAX_RESULTS,
        "llm_temperature": settings.LLM_TEMPERATURE,
        "llm_mode": settings.LLM_MODE,
        "llm_explanations": settings.LLM_EXPLANATIONS,
        "embeddings_enabled": settings.EMBEDDINGS_ENABLED,
        "max_upload_size_mb": settings.MAX_UPLOAD_SIZE_MB,
        "weights": settings.WEIGHTS.model_dump(),
        "tolerances": settings.TOLERANCES.model_dump(),
    }


def _apply(values: Dict[str, Any]) -> None:
    """Apply already-validated values. Raises ValueError for unknown weight/tolerance names or bad numbers."""
    if values.get("weights") is not None:
        unknown = set(values["weights"]) - set(ScoringWeights.model_fields)
        if unknown:
            raise ValueError(f"Unknown weight: {', '.join(sorted(unknown))}")
        merged = ScoringWeights(**{**settings.WEIGHTS.model_dump(), **values["weights"]})
        if sum(merged.model_dump().values()) <= 0:
            raise ValueError("At least one weight must be greater than zero.")
        settings.WEIGHTS = merged
    if values.get("tolerances") is not None:
        unknown = set(values["tolerances"]) - set(TolerancesConfig.model_fields)
        if unknown:
            raise ValueError(f"Unknown tolerance: {', '.join(sorted(unknown))}")
        settings.TOLERANCES = TolerancesConfig(**{**settings.TOLERANCES.model_dump(), **values["tolerances"]})
    for key, attr in (("min_alternative_score", "MIN_ALTERNATIVE_SCORE"), ("max_results", "MAX_RESULTS"),
                      ("llm_temperature", "LLM_TEMPERATURE"), ("llm_mode", "LLM_MODE"),
                      ("llm_explanations", "LLM_EXPLANATIONS")):
        if values.get(key) is not None:
            setattr(settings, attr, values[key])


def _persisted() -> Dict[str, Any]:
    with db() as conn:
        row = conn.execute("SELECT value FROM app_settings WHERE key = ?", (_KEY,)).fetchone()
    try:
        data = json.loads(row["value"]) if row else {}
        return data if isinstance(data, dict) else {}
    except ValueError:
        return {}


def update(patch: SettingsPatch) -> Dict[str, Any]:
    values = patch.model_dump(exclude_none=True)
    _apply(values)  # raises before anything is stored
    stored = _persisted()
    for key, value in values.items():
        stored[key] = {**stored.get(key, {}), **value} if isinstance(value, dict) else value
    with db() as conn:
        conn.execute(
            "INSERT INTO app_settings (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = CURRENT_TIMESTAMP",
            (_KEY, json.dumps(stored)),
        )
    return effective()


def load() -> None:
    """Re-apply persisted settings at startup. Invalid stored values are ignored, never fatal."""
    stored = _persisted()
    if not stored:
        return
    try:
        _apply(SettingsPatch(**stored).model_dump(exclude_none=True))
    except Exception as exc:
        logger.warning("Stored runtime settings are invalid and were ignored: %s", type(exc).__name__)


def reset() -> Dict[str, Any]:
    """Back to configuration defaults (environment overrides included)."""
    defaults = Settings()
    for attr in ("WEIGHTS", "TOLERANCES", "MIN_ALTERNATIVE_SCORE", "MAX_RESULTS", "LLM_TEMPERATURE", "LLM_MODE",
                 "LLM_EXPLANATIONS"):
        setattr(settings, attr, getattr(defaults, attr))
    with db() as conn:
        conn.execute("DELETE FROM app_settings WHERE key = ?", (_KEY,))
    return effective()
