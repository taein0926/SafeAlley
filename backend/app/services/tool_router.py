from collections.abc import Callable

from app.schemas.agent import AgentExecutionResponse, AgentToolCall, AgentToolName
from app.services.route_ranking_service import rank_route_candidates


AgentTool = Callable[[object], dict[str, object]]


def _registered_tools() -> dict[AgentToolName, AgentTool]:
    """Explicit allowlist. The router never imports a function from model output."""

    return {"rank_routes": rank_route_candidates}


def execute_tool_call(tool_call: AgentToolCall) -> AgentExecutionResponse:
    result = _registered_tools()[tool_call.tool](tool_call.arguments)
    return AgentExecutionResponse(tool_call=tool_call, **result)
