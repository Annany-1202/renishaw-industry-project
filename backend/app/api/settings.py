from typing import Any, Dict

from fastapi import APIRouter, HTTPException
from pydantic import ValidationError

from backend.app.core import runtime_settings
from backend.app.core.runtime_settings import SettingsPatch

router = APIRouter(prefix="/api/settings", tags=["settings"])


@router.get("")
def get_effective_settings() -> Dict[str, Any]:
    return runtime_settings.effective()


@router.patch("")
def patch_settings(patch: SettingsPatch) -> Dict[str, Any]:
    try:
        return runtime_settings.update(patch)
    except (ValueError, ValidationError) as exc:
        message = exc.errors()[0]["msg"] if isinstance(exc, ValidationError) else str(exc)
        raise HTTPException(status_code=422, detail=message)


@router.post("/reset")
def reset_settings() -> Dict[str, Any]:
    return runtime_settings.reset()
