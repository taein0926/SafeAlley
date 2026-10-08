import json
import logging
from collections.abc import Iterator

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from app.repositories.road_repository import RoadRepositoryError
from app.core.config import get_settings
from app.schemas.agent import (
    AgentExecutionResponse,
    AgentToolCall,
    NaturalLanguageQueryRequest,
    NaturalLanguageQueryResponse,
    RouteSelectionRequest,
    RouteSelectionResponse,
    RouteOptimizationArguments,
)
from app.services.local_llm_service import (
    LocalLLMOutputError,
    LocalLLMUnavailableError,
    parse_route_intent,
)
from app.services.route_service import (
    RouteNotFoundError,
    RoutingDataNotFoundError,
    SnapDistanceExceededError,
)
from app.services.tool_router import execute_tool_call
from app.services.route_progress import iter_workflow_progress
from app.repositories.personalization_repository import PersonalizationRepositoryError
from app.repositories.place_repository import (
    PlaceAmbiguousError,
    PlaceNotFoundError,
    PlaceRepositoryError,
)
from app.services.personalization_service import learn_from_selection
from app.services.place_service import resolve_place


router = APIRouter(prefix="/api/agent", tags=["agent"])
logger = logging.getLogger(__name__)


@router.post("/execute", response_model=AgentExecutionResponse)
def execute_agent_tool(tool_call: AgentToolCall) -> AgentExecutionResponse:
    """Validate structured output and execute one allowlisted GIS workflow."""

    return _execute_agent_tool(tool_call)


def _execute_agent_tool(tool_call: AgentToolCall, *, on_progress=None) -> AgentExecutionResponse:
    try:
        return execute_tool_call(tool_call, on_progress=on_progress) if on_progress else execute_tool_call(tool_call)
    except SnapDistanceExceededError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except (RoutingDataNotFoundError, RouteNotFoundError) as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except RoadRepositoryError as exc:
        raise HTTPException(status_code=503, detail="Road data is unavailable") from exc


@router.post("/query", response_model=NaturalLanguageQueryResponse)
def query_agent(request: NaturalLanguageQueryRequest) -> NaturalLanguageQueryResponse:
    """Parse natural language locally, then execute the validated allowlisted tool."""

    for event in _query_events(request):
        if event["type"] == "result":
            return event["data"]
    raise RuntimeError("Query completed without a result")


@router.post("/query/stream")
def stream_query_agent(request: NaturalLanguageQueryRequest) -> StreamingResponse:
    """Stream observable workflow stages, not a model's private reasoning."""

    def events() -> Iterator[str]:
        try:
            for event in _query_events(request, stream_progress=True):
                yield json.dumps(event, ensure_ascii=False, default=_json_default) + "\n"
        except HTTPException as exc:
            yield json.dumps({"type": "error", "detail": exc.detail}, ensure_ascii=False) + "\n"
        except Exception:
            logger.exception("Streaming route query failed")
            yield json.dumps({"type": "error", "detail": "경로 검색에 실패했습니다."}, ensure_ascii=False) + "\n"

    return StreamingResponse(
        events(),
        media_type="application/x-ndjson",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


def _json_default(value: object) -> object:
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    raise TypeError(f"Cannot serialize {type(value).__name__}")


def _query_events(request: NaturalLanguageQueryRequest, *, stream_progress=False) -> Iterator[dict[str, object]]:
    yield {"type": "stage", "stage": "interpreting"}

    try:
        interpretation = parse_route_intent(request.query)
    except LocalLLMUnavailableError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except LocalLLMOutputError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    yield {"type": "interpreted", "data": interpretation}

    resolved_origin = None
    resolved_destination = None
    origin = request.origin
    destination = request.destination
    yield {"type": "stage", "stage": "resolving"}
    if origin is None or destination is None:
        if not interpretation.origin_name or not interpretation.destination_name:
            raise HTTPException(
                status_code=422,
                detail="질문에 출발지와 도착지를 모두 입력해 주세요.",
            )
        try:
            resolved_origin = resolve_place(interpretation.origin_name)
            resolved_destination = resolve_place(interpretation.destination_name)
        except PlaceAmbiguousError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except PlaceNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except PlaceRepositoryError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        origin = {
            "latitude": resolved_origin["latitude"],
            "longitude": resolved_origin["longitude"],
        }
        destination = {
            "latitude": resolved_destination["latitude"],
            "longitude": resolved_destination["longitude"],
        }
    yield {
        "type": "resolved",
        "origin": resolved_origin,
        "destination": resolved_destination,
    }

    tool_call = AgentToolCall(
        tool="rank_routes",
        arguments=RouteOptimizationArguments(
            origin=origin,
            destination=destination,
            departure_time=interpretation.departure_time,
            profile=interpretation.profile,
            source=request.source,
            user_id=request.user_id,
            preference_mode="explicit_only",
            preferences=interpretation.preferences,
        ),
    )
    yield {"type": "stage", "stage": "routing"}
    if stream_progress:
        for event in iter_workflow_progress(lambda callback: _execute_agent_tool(tool_call, on_progress=callback)):
            if event["type"] == "routing_result":
                result = event["data"]
            else:
                yield event
    else:
        result = execute_agent_tool(tool_call)
    response = NaturalLanguageQueryResponse(
        query=request.query,
        model=get_settings().ollama_model,
        interpretation=interpretation,
        resolved_origin=resolved_origin,
        resolved_destination=resolved_destination,
        result=result,
    )
    yield {"type": "result", "data": response}


@router.post("/route-selections", response_model=RouteSelectionResponse)
def select_recommended_route(
    request: RouteSelectionRequest,
) -> RouteSelectionResponse:
    """Record an explicit choice and update route-specific user preferences."""

    try:
        preferences = learn_from_selection(
            request.recommendation_id,
            request.user_id,
            request.selected_route_type,
        )
    except PersonalizationRepositoryError as exc:
        detail = str(exc)
        status_code = 404 if detail == "Recommendation not found" else 400
        raise HTTPException(status_code=status_code, detail=detail) from exc

    return RouteSelectionResponse(
        recommendation_id=request.recommendation_id,
        selected_route_type=request.selected_route_type,
        preferences=preferences,
    )
