import pytest
from pydantic import ValidationError

from app.schemas.agent import AgentToolCall, ParsedRouteIntent, RouteOptimizationArguments


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


def test_parsed_time_zone_is_normalized_to_local_wall_time() -> None:
    intent = ParsedRouteIntent.model_validate(
        {
            "departure_time": "22:00:00-10:00",
            "profile": "pedestrian",
            "preferences": [],
        }
    )

    assert intent.departure_time is not None
    assert str(intent.departure_time) == "22:00:00"
    assert intent.departure_time.tzinfo is None
