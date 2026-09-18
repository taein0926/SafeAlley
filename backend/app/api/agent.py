from fastapi import APIRouter, HTTPException

from app.repositories.road_repository import RoadRepositoryError
from app.core.config import get_settings
from app.schemas.agent import (
    AgentExecutionResponse,
    AgentToolCall,
    NaturalLanguageQueryRequest,
    NaturalLanguageQueryResponse,
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


router = APIRouter(prefix="/api/agent", tags=["agent"])


@router.post("/execute", response_model=AgentExecutionResponse)
def execute_agent_tool(tool_call: AgentToolCall) -> AgentExecutionResponse:
    """Validate structured output and execute one allowlisted GIS workflow."""

    try:
        return execute_tool_call(tool_call)
    except SnapDistanceExceededError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except (RoutingDataNotFoundError, RouteNotFoundError) as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except RoadRepositoryError as exc:
        raise HTTPException(status_code=503, detail="Road data is unavailable") from exc


@router.post("/query", response_model=NaturalLanguageQueryResponse)
def query_agent(request: NaturalLanguageQueryRequest) -> NaturalLanguageQueryResponse:
    """Parse natural language locally, then execute the validated allowlisted tool."""

    try:
        interpretation = parse_route_intent(request.query)
    except LocalLLMUnavailableError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except LocalLLMOutputError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    tool_call = AgentToolCall(
        tool="rank_routes",
        arguments=RouteOptimizationArguments(
            origin=request.origin,
            destination=request.destination,
            departure_time=interpretation.departure_time,
            profile=interpretation.profile,
            source=request.source,
            preferences=interpretation.preferences,
        ),
    )
    result = execute_agent_tool(tool_call)
    return NaturalLanguageQueryResponse(
        query=request.query,
        model=get_settings().ollama_model,
        interpretation=interpretation,
        result=result,
    )
