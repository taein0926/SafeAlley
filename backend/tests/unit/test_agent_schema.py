import pytest
from pydantic import ValidationError

from app.schemas.agent import AgentToolCall, RouteOptimizationArguments


def test_structured_output_rejects_unregistered_tool() -> None:
    with pytest.raises(ValidationError):
        AgentToolCall.model_validate(
            {
                "tool": "execute_sql",
                "arguments": {
                    "origin": {"latitude": 37.46, "longitude": 126.67},
                    "destination": {"latitude": 37.47, "longitude": 126.68},
                },
            }
        )


def test_structured_output_rejects_extra_fields() -> None:
    with pytest.raises(ValidationError):
        AgentToolCall.model_validate(
            {
                "tool": "rank_routes",
                "arguments": {
                    "origin": {
                        "latitude": 37.46,
                        "longitude": 126.67,
                        "sql": "SELECT 1",
                    },
                    "destination": {"latitude": 37.47, "longitude": 126.68},
                },
            }
        )


def test_preferences_must_have_unique_factors() -> None:
    with pytest.raises(ValidationError):
        RouteOptimizationArguments.model_validate(
            {
                "origin": {"latitude": 37.46, "longitude": 126.67},
                "destination": {"latitude": 37.47, "longitude": 126.68},
                "preferences": [
                    {"factor": "distance_m", "direction": "minimize"},
                    {"factor": "distance_m", "direction": "minimize"},
                ],
            }
        )
