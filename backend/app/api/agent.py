from fastapi import APIRouter, HTTPException

from app.repositories.road_repository import RoadRepositoryError
from app.schemas.agent import AgentExecutionResponse, AgentToolCall
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
