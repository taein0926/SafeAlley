from fastapi import APIRouter, HTTPException, Query

from app.repositories.pedestrian_reference_repository import PedestrianReferenceError
from app.services.pedestrian_reference_service import get_pedestrian_bridge_collection
from app.services.road_service import InvalidBoundingBoxError

router = APIRouter(prefix="/api", tags=["pedestrian-references"])


@router.get("/pedestrian-bridges")
def get_pedestrian_bridges(bbox: str | None = Query(default=None)) -> dict:
    try:
        return get_pedestrian_bridge_collection(bbox)
    except InvalidBoundingBoxError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except PedestrianReferenceError as exc:
        raise HTTPException(status_code=503, detail="Pedestrian bridge data is unavailable") from exc
