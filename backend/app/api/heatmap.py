import base64

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, JSONResponse, Response

from app.services.heatmap_service import heatmap_manifest, heatmap_tile

router = APIRouter(prefix="/api/streetlight-heatmap", tags=["map-assets"])
# Empty areas are a successful transparent tile, not hundreds of failed requests.
TRANSPARENT_PNG = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAAC0lEQVR42mNgAAIAAAUAAarVyFEAAAAASUVORK5CYII=")
CACHE_HEADERS = {"Cache-Control": "public, max-age=31536000, immutable"}


@router.get("/manifest")
def manifest():
    try:
        return JSONResponse(heatmap_manifest(), headers={"Cache-Control": "no-store"})
    except (OSError, ValueError):
        raise HTTPException(503, "Streetlight heatmap has not been generated") from None


@router.get("/{version}/{z}/{x}/{y}.png")
def tile(version: str, z: int, x: int, y: int):
    try:
        path = heatmap_tile(version, z, x, y)
    except (OSError, ValueError):
        raise HTTPException(404, "Heatmap tile version or coordinates unavailable") from None
    if path is None:
        return Response(TRANSPARENT_PNG, media_type="image/png", headers=CACHE_HEADERS)
    return FileResponse(path, media_type="image/png", headers=CACHE_HEADERS)
