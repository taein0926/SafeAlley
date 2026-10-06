from collections.abc import Callable

from app.schemas.agent import AgentExecutionResponse, AgentToolCall, AgentToolName
from app.services.route_ranking_service import rank_route_candidates


AgentTool = Callable[..., dict[str, object]]


def _registered_tools() -> dict[AgentToolName, AgentTool]:
    """Explicit allowlist. The router never imports a function from model output."""

    return {"rank_routes": rank_route_candidates}


def execute_tool_call(tool_call: AgentToolCall, *, on_progress=None) -> AgentExecutionResponse:
    tool = _registered_tools()[tool_call.tool]
    result = tool(tool_call.arguments, on_progress=on_progress) if on_progress else tool(tool_call.arguments)
    return AgentExecutionResponse(tool_call=tool_call, **result)
