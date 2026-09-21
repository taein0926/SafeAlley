from fastapi import APIRouter, HTTPException, Query

from app.repositories.safety_repository import SafetyRepositoryError
from app.services.road_service import InvalidBoundingBoxError
from app.services.safety_service import (
    get_cctv_feature_collection,
    get_help_point_feature_collection,
    get_safety_road_feature_collection,
    get_streetlight_feature_collection,
)


router = APIRouter(prefix="/api", tags=["streetlight safety"])


@router.get("/safety/roads")
def get_safety_roads(
    bbox: str | None = Query(default=None),
    source: str | None = Query(default="osm", min_length=1, max_length=32),
) -> dict[str, object]:
    try:
        return get_safety_road_feature_collection(bbox, source)
    except InvalidBoundingBoxError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except SafetyRepositoryError as exc:
        raise HTTPException(status_code=503, detail="Safety data is unavailable") from exc


@router.get("/streetlights")
def get_streetlights(
    bbox: str | None = Query(default=None),
    source: str | None = Query(
        default="michuhol-public-data", min_length=1, max_length=64
    ),
) -> dict[str, object]:
    try:
        return get_streetlight_feature_collection(bbox, source)
    except InvalidBoundingBoxError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except SafetyRepositoryError as exc:
        raise HTTPException(status_code=503, detail="Streetlight data is unavailable") from exc


@router.get("/cctvs")
def get_cctvs(
    bbox: str | None = Query(default=None),
    source: str | None = Query(
        default="michuhol-cctv-ai-ready", min_length=1, max_length=64
    ),
    safety_only: bool = Query(default=True),
) -> dict[str, object]:
    try:
        return get_cctv_feature_collection(
            bbox, source, safety_only=safety_only
        )
    except InvalidBoundingBoxError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except SafetyRepositoryError as exc:
        raise HTTPException(status_code=503, detail="CCTV data is unavailable") from exc


@router.get("/help-points")
def get_help_points(
    bbox: str | None = Query(default=None),
    source: str | None = Query(
        default="ai-ready-help-points", min_length=1, max_length=64
    ),
    category: str | None = Query(default=None, min_length=1, max_length=64),
) -> dict[str, object]:
    try:
        return get_help_point_feature_collection(bbox, source, category)
    except InvalidBoundingBoxError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except SafetyRepositoryError as exc:
        raise HTTPException(status_code=503, detail="Help-point data is unavailable") from exc
