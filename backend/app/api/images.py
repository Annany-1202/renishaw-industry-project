import re

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from backend.app.core.config import settings
from backend.app.db.database import READY, db

router = APIRouter(prefix="/api/images", tags=["images"])

IMAGE_ID_RE = re.compile(r"^[A-Za-z0-9_\-]{1,120}$")


@router.get("/{image_id}")
def get_image(image_id: str):
    """Serve an extracted image by id. The file path comes from the database, never from the request."""
    if not IMAGE_ID_RE.fullmatch(image_id):
        raise HTTPException(status_code=404, detail="Image not found.")
    with db() as conn:
        row = conn.execute(
            "SELECT i.image_path FROM images i JOIN documents d ON d.id = i.document_id "
            "WHERE i.image_id = ? AND d.status = ?", (image_id, READY),
        ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Image not found.")
    root = settings.IMAGE_DIR.resolve()
    path = (root / row["image_path"]).resolve()
    if not path.is_relative_to(root) or not path.is_file():
        raise HTTPException(status_code=404, detail="Image not found.")
    return FileResponse(str(path), media_type="image/png", headers={"Cache-Control": "private, max-age=3600"})
