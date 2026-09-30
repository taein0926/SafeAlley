from fastapi import APIRouter, HTTPException, Query

from app.repositories.place_repository import (
    PlaceAmbiguousError,
    PlaceNotFoundError,
    PlaceRepositoryError,
)
from app.schemas.agent import ResolvedPlace
from app.services.place_service import resolve_place, reverse_place


router = APIRouter(prefix="/api/places", tags=["places"])


@router.get("/resolve", response_model=ResolvedPlace)
def resolve_place_name(
    name: str = Query(min_length=1, max_length=255),
) -> dict[str, object]:
    """Resolve a place/GIS building name without invoking the LLM."""

    try:
        return resolve_place(name)
    except PlaceAmbiguousError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except PlaceNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PlaceRepositoryError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.get("/reverse", response_model=ResolvedPlace)
def reverse_place_coordinate(
    latitude: float = Query(ge=-90, le=90),
    longitude: float = Query(ge=-180, le=180),
) -> dict[str, object]:
    """Resolve a map-selected coordinate when building metadata has no label."""

    try:
        return reverse_place(latitude, longitude)
    except PlaceNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PlaceRepositoryError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
