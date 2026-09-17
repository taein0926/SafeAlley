from fastapi import APIRouter, HTTPException, Query

from app.repositories.road_repository import RoadRepositoryError
from app.services.road_service import (
    InvalidBoundingBoxError,
    get_road_feature_collection,
)


router = APIRouter(prefix="/api", tags=["roads"])


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
) -> dict[str, object]:
    try:
        return get_road_feature_collection(bbox, source=source)
    except InvalidBoundingBoxError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RoadRepositoryError as exc:
        raise HTTPException(status_code=503, detail="Road data is unavailable") from exc
