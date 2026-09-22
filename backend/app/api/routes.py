from collections.abc import Callable

from fastapi import APIRouter, HTTPException

from app.repositories.road_repository import RoadRepositoryError
from app.schemas.route import RouteFeature, RouteRequest
from app.services.route_service import (
    RouteNotFoundError,
    RoutingDataNotFoundError,
    SnapDistanceExceededError,
    get_balanced_route,
    get_safe_route,
    get_shortest_route,
)


router = APIRouter(prefix="/api/routes", tags=["routes"])


def _run_route(
    request: RouteRequest,
    route_service: Callable[..., dict[str, object]],
) -> dict[str, object]:
    try:
        return route_service(
            start_longitude=request.start.longitude,
            start_latitude=request.start.latitude,
            end_longitude=request.end.longitude,
            end_latitude=request.end.latitude,
            source=request.source,
            stairs_weight=request.stairs_weight,
            intersection_weight=request.intersection_weight,
        )
    except SnapDistanceExceededError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except (RoutingDataNotFoundError, RouteNotFoundError) as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except RoadRepositoryError as exc:
        raise HTTPException(status_code=503, detail="Road data is unavailable") from exc


@router.post("/shortest", response_model=RouteFeature)
def create_shortest_route(request: RouteRequest) -> dict[str, object]:
    return _run_route(request, get_shortest_route)


@router.post("/safe", response_model=RouteFeature)
def create_safe_route(request: RouteRequest) -> dict[str, object]:
    return _run_route(request, get_safe_route)


@router.post("/balanced", response_model=RouteFeature)
def create_balanced_route(request: RouteRequest) -> dict[str, object]:
    return _run_route(request, get_balanced_route)
