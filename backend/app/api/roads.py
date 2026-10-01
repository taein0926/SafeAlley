from fastapi import APIRouter, HTTPException, Query

from app.repositories.road_repository import RoadRepositoryError
from app.services.road_service import (
    InvalidBoundingBoxError,
    get_road_feature_collection,
    get_crossing_feature_collection,
    get_osm_display_collection,
)


router = APIRouter(prefix="/api", tags=["roads"])


@router.get("/osm-roads")
def get_osm_roads(bbox: str | None = Query(default=None, description="WGS84 viewport bounding box")):
    try:
        return get_osm_display_collection(bbox)
    except InvalidBoundingBoxError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RoadRepositoryError as exc:
        raise HTTPException(status_code=503, detail="OSM display data is unavailable") from exc


@router.get("/crossings")
def get_crossings(bbox: str | None = Query(default=None)) -> dict[str, object]:
    try:
        return get_crossing_feature_collection(bbox)
    except InvalidBoundingBoxError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RoadRepositoryError as exc:
        raise HTTPException(status_code=503, detail="Crossing data is unavailable") from exc


@router.get("/roads")
def get_roads(
    bbox: str | None = Query(
        default=None,
        description="minLongitude,minLatitude,maxLongitude,maxLatitude in EPSG:4326",
    ),
    source: str | None = Query(
        default=None,
        min_length=1,
        max_length=32,
        description="Optional road data source, for example osm",
    ),
    steps_only: bool = Query(default=False, description="Return only mapped stair segments"),
) -> dict[str, object]:
    try:
        return get_road_feature_collection(bbox, source=source, steps_only=steps_only)
    except InvalidBoundingBoxError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RoadRepositoryError as exc:
        raise HTTPException(status_code=503, detail="Road data is unavailable") from exc
