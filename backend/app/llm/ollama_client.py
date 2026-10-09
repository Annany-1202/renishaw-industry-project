"""Thin client for the local Ollama server. Nothing here contacts any other host."""
import json
import time
from typing import Any, Dict, List, Optional

import httpx

from backend.app.core.config import settings
from backend.app.core.logging import logger


def _model_matches(configured: str, installed: str) -> bool:
    """'nomic-embed-text' matches 'nomic-embed-text:latest'; tagged names must match exactly."""
    if configured == installed:
        return True
    if ":" not in configured:
        return installed == f"{configured}:latest"
    return False


class OllamaClient:
    def __init__(self, base_url: Optional[str] = None):
        self._base_url = base_url
        self._down_until = 0.0

    @property
    def base_url(self) -> str:
        return (self._base_url or settings.OLLAMA_BASE_URL).rstrip("/")

    def check_health(self) -> Dict[str, Any]:
        status: Dict[str, Any] = {
            "ollama_reachable": False,
            "llm_model": settings.LLM_MODEL,
            "llm_model_available": False,
            "embedding_model": settings.EMBEDDING_MODEL,
            "embedding_model_available": False,
            "models_found": [],
            "error": None,
        }
        try:
            with httpx.Client(timeout=httpx.Timeout(3.0, connect=1.0)) as client:
                resp = client.get(f"{self.base_url}/api/tags")
            resp.raise_for_status()
            names = [m.get("name", "") for m in resp.json().get("models", [])]
            status["ollama_reachable"] = True
            status["models_found"] = names
            status["llm_model_available"] = any(_model_matches(settings.LLM_MODEL, n) for n in names)
            status["embedding_model_available"] = any(_model_matches(settings.EMBEDDING_MODEL, n) for n in names)
            self._down_until = 0.0
        except Exception as exc:
            status["error"] = "Ollama is not reachable at the configured local address."
            logger.debug("Ollama health check failed: %s", exc)
            self._down_until = time.time() + 20.0
        return status

    def _available(self) -> bool:
        # After a connection failure, skip calls for a short while instead of timing out per query.
        return time.time() >= self._down_until

    def generate_json(self, prompt: str, system: Optional[str] = None,
                      schema: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
        """Structured generation. Returns None on any failure; callers must fall back."""
        if not self._available():
            return None
        payload: Dict[str, Any] = {
            "model": settings.LLM_MODEL,
            "prompt": prompt,
            "format": schema or "json",
            "stream": False,
            "keep_alive": "30m",
            "options": {"temperature": settings.LLM_TEMPERATURE, "num_predict": 300},
        }
        if system:
            payload["system"] = system
        try:
            with httpx.Client(timeout=httpx.Timeout(settings.LLM_TIMEOUT_S, connect=1.5)) as client:
                resp = client.post(f"{self.base_url}/api/generate", json=payload)
            if resp.status_code != 200:
                logger.warning("Ollama generate returned HTTP %s", resp.status_code)
                return None
            parsed = json.loads(resp.json().get("response", ""))
            return parsed if isinstance(parsed, dict) else None
        except httpx.ConnectError:
            self._down_until = time.time() + 20.0
            logger.warning("Ollama is unreachable; continuing with rule-based interpretation.")
            return None
        except Exception as exc:
            logger.warning("Ollama generate_json failed: %s", type(exc).__name__)
            return None

    def embed(self, texts: List[str]) -> Optional[List[List[float]]]:
        """Embed a batch of texts. Returns None if the embedding model is unavailable."""
        if not texts or not self._available():
            return None if texts else []
        try:
            with httpx.Client(timeout=httpx.Timeout(120.0, connect=1.5)) as client:
                resp = client.post(
                    f"{self.base_url}/api/embed",
                    json={"model": settings.EMBEDDING_MODEL, "input": texts, "keep_alive": "30m"},
                )
            if resp.status_code != 200:
                logger.warning("Ollama embed returned HTTP %s", resp.status_code)
                return None
            vectors = resp.json().get("embeddings")
            if not isinstance(vectors, list) or len(vectors) != len(texts):
                return None
            return vectors
        except httpx.ConnectError:
            self._down_until = time.time() + 20.0
            return None
        except Exception as exc:
            logger.warning("Ollama embed failed: %s", type(exc).__name__)
            return None


ollama_client = OllamaClient()
