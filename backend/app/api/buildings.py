from fastapi import APIRouter, HTTPException, Query

from app.repositories.building_repository import BuildingRepositoryError
from app.services.building_service import (
    InvalidBuildingBoundingBoxError,
    get_building_feature_collection,
)


router = APIRouter(prefix="/api", tags=["buildings"])


@router.get("/buildings")
def get_buildings(
    bbox: str | None = Query(
        default=None,
        description="minLongitude,minLatitude,maxLongitude,maxLatitude in EPSG:4326",
    ),
    source: str | None = Query(
        default=None,
        min_length=1,
        max_length=32,
        description="Optional building data source, for example molit-gis-building",
    ),
) -> dict[str, object]:
    try:
        return get_building_feature_collection(bbox, source=source)
    except InvalidBuildingBoundingBoxError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except BuildingRepositoryError as exc:
        raise HTTPException(status_code=503, detail="Building data is unavailable") from exc
