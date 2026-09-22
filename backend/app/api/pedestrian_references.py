from fastapi import APIRouter, HTTPException

from app.repositories.pedestrian_reference_repository import PedestrianReferenceError
from app.services.pedestrian_reference_service import get_pedestrian_bridge_collection

router = APIRouter(prefix="/api", tags=["pedestrian-references"])


@router.get("/pedestrian-bridges")
def get_pedestrian_bridges() -> dict:
    try:
        return get_pedestrian_bridge_collection()
    except PedestrianReferenceError as exc:
        raise HTTPException(status_code=503, detail="Pedestrian bridge data is unavailable") from exc
