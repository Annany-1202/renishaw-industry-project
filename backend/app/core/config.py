"""Application configuration.

Everything tunable lives here, separate from business logic. Values can be
overridden with environment variables prefixed `RENISHAW_` (for example
`RENISHAW_DATA_DIR`, `RENISHAW_LLM_MODE=off`). Retrieval settings changed
through `PATCH /api/settings` are persisted in the database and re-applied at
startup (see `backend.app.core.runtime_settings`).
"""
from pathlib import Path
from typing import List, Literal

from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent


class TolerancesConfig(BaseModel):
    """Deviation scales (tau) for the numeric attribute score s = max(0, 1 - |x - y| / tau).

    tau = max(absolute, relative * requested value). These are ranking scales
    chosen for this proof of concept; they are NOT manufacturer tolerances.
    """
    ball_diameter: float = Field(0.5, gt=0, le=20)
    overall_length: float = Field(5.0, gt=0, le=200)
    stem_diameter: float = Field(0.5, gt=0, le=20)
    effective_working_length: float = Field(5.0, gt=0, le=200)
    ball_diameter_rel: float = Field(0.25, ge=0, le=1)
    overall_length_rel: float = Field(0.20, ge=0, le=1)
    stem_diameter_rel: float = Field(0.25, ge=0, le=1)
    effective_working_length_rel: float = Field(0.20, ge=0, le=1)


class ScoringWeights(BaseModel):
    """Attribute importance weights from the specification (section 9.4)."""
    thread: float = Field(25.0, ge=0, le=100)
    category: float = Field(20.0, ge=0, le=100)
    ball_diameter: float = Field(15.0, ge=0, le=100)
    overall_length: float = Field(15.0, ge=0, le=100)
    stem_material: float = Field(10.0, ge=0, le=100)
    ball_material: float = Field(10.0, ge=0, le=100)
    other_dimensions: float = Field(5.0, ge=0, le=100)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="RENISHAW_", extra="ignore")

    APP_NAME: str = "Renishaw Technical Catalogue Retrieval"
    VERSION: str = "1.1.0"
    DEBUG: bool = False

    # Directories. Everything the application writes lives under DATA_DIR.
    BASE_DIR: Path = BASE_DIR
    DATA_DIR: Path = BASE_DIR / "data"
    SOURCE_PDFS_DIR: Path = BASE_DIR / "source_pdfs"

    # Ollama (local only)
    OLLAMA_BASE_URL: str = "http://localhost:11434"
    LLM_MODEL: str = "llama3.1:8b-instruct-q4_K_M"
    EMBEDDING_MODEL: str = "nomic-embed-text"
    LLM_TEMPERATURE: float = 0.0
    LLM_TIMEOUT_S: float = 30.0
    # auto: call the LLM only when the rule-based parser leaves words it cannot explain.
    # always: call it for every query. off: rule-based parsing only.
    LLM_MODE: Literal["auto", "always", "off"] = "auto"
    # Grounded LLM explanations are validated against the record and fall back to the template.
    LLM_EXPLANATIONS: bool = False
    EMBEDDINGS_ENABLED: bool = True
    EMBEDDING_BATCH_SIZE: int = 64

    # Upload
    MAX_UPLOAD_SIZE_MB: int = 100
    MAX_PDF_PAGES: int = 2000
    SUPPORTED_EXTENSIONS: List[str] = [".pdf"]
    AUTO_INGEST_SOURCE_PDFS: bool = True

    # Search & ranking
    WEIGHTS: ScoringWeights = ScoringWeights()
    TOLERANCES: TolerancesConfig = TolerancesConfig()
    MIN_ALTERNATIVE_SCORE: float = 60.0
    MAX_RESULTS: int = 5
    SEMANTIC_CANDIDATE_LIMIT: int = 25
    # A query value typed in inches matches a catalogue millimetre value when the two agree
    # at the precision the user typed and differ by no more than this relative amount.
    INCH_INPUT_REL_TOL: float = 0.025
    # An alternative must stay within the deviation scale on every requested dimension.
    REQUIRE_DIMENSIONS_WITHIN_SCALE: bool = True
    # Share of the non-mandatory attributes' weight an alternative must earn. Agreeing on the
    # mandatory attributes (thread, product type) alone does not make a product a related alternative.
    MIN_FLEXIBLE_AGREEMENT: float = 0.5

    @property
    def UPLOAD_DIR(self) -> Path:
        return self.DATA_DIR / "uploads"

    @property
    def IMAGE_DIR(self) -> Path:
        return self.DATA_DIR / "images"

    @property
    def REPORT_DIR(self) -> Path:
        return self.DATA_DIR / "reports"

    @property
    def SQLITE_PATH(self) -> Path:
        return self.DATA_DIR / "renishaw.db"

    @property
    def CHROMA_DIR(self) -> Path:
        return self.DATA_DIR / "chroma"

    def ensure_directories(self) -> None:
        for d in (self.DATA_DIR, self.UPLOAD_DIR, self.IMAGE_DIR, self.REPORT_DIR, self.CHROMA_DIR):
            d.mkdir(parents=True, exist_ok=True)


settings = Settings()
settings.ensure_directories()
