from datetime import time
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.schemas.route import CoordinateInput, RouteFeature
from app.schemas.intent_preview import ConditionCard


PreferenceDirection = Literal["maximize", "minimize", "avoid"]
AgentToolName = Literal["rank_routes"]


class AgentCoordinateInput(CoordinateInput):
    model_config = ConfigDict(extra="forbid")


class RoutePreference(BaseModel):
    model_config = ConfigDict(extra="forbid")

    factor: str = Field(min_length=1, max_length=64, pattern=r"^[a-z][a-z0-9_]*$")
    direction: PreferenceDirection
    weight: float = Field(default=1.0, gt=0, le=100)


class RouteOptimizationArguments(BaseModel):
    model_config = ConfigDict(extra="forbid")

    origin: AgentCoordinateInput
    destination: AgentCoordinateInput
    departure_time: time | None = None
    profile: Literal["pedestrian"] = "pedestrian"
    source: str | None = Field(default=None, min_length=1, max_length=32)
    user_id: str | None = Field(default=None, min_length=1, max_length=128)
    stairs_weight: float = Field(default=0.0, ge=0.0, le=1.0)
    intersection_weight: float = Field(default=0.0, ge=0.0, le=1.0)  # legacy API only
    crossing_weight: float = Field(default=0.0, ge=0.0, le=1.0)
    preferences: list[RoutePreference] = Field(default_factory=list, max_length=20)

    @field_validator("preferences")
    @classmethod
    def reject_duplicate_factors(
        cls,
        preferences: list[RoutePreference],
    ) -> list[RoutePreference]:
        factors = [preference.factor for preference in preferences]
        if len(factors) != len(set(factors)):
            raise ValueError("preference factors must be unique")
        return preferences


class AgentToolCall(BaseModel):
    """Strict structured output accepted from an upstream LLM or parser."""

    model_config = ConfigDict(extra="forbid")

    tool: AgentToolName
    arguments: RouteOptimizationArguments


class UnsupportedPreference(BaseModel):
    factor: str
    reason: str


class RouteCandidate(BaseModel):
    route_type: Literal["shortest", "balanced", "safe", "custom"]
    preference_score: float | None
    metrics: dict[str, float | None]
    route: RouteFeature


class RecommendationCriterion(BaseModel):
    factor: str
    label: str
    outcome: Literal["better", "similar", "worse", "not_compared", "unavailable"]
    summary: str
    confidence: Literal["high", "medium", "low"]
    confidence_reason: str


class AgentExecutionResponse(BaseModel):
    tool_call: AgentToolCall
    recommendation_id: str | None = None
    selected_route_type: Literal["shortest", "balanced", "safe", "custom"] | None
    selected_route: RouteFeature | None
    recommendation_status: Literal["ready", "field_review_required", "no_supported_preferences"] = "ready"
    recommendation_reason: str | None = None
    recommendation_notes: list[str] = Field(default_factory=list)
    recommendation_factors: list[Literal["distance", "safety", "stairs", "crossing"]] = Field(default_factory=list)
    recommendation_conditions: list[ConditionCard] = Field(default_factory=list)
    compared_route_type: Literal["shortest", "balanced", "safe", "custom"] | None = None
    recommendation_criteria: list[RecommendationCriterion] = Field(default_factory=list)
    candidates: list[RouteCandidate]
    unsupported_preferences: list[UnsupportedPreference]


class ParsedRouteIntent(BaseModel):
    """Fields the local LLM may infer from natural language."""

    model_config = ConfigDict(extra="forbid")

    origin_name: str | None = Field(default=None, min_length=1, max_length=255)
    destination_name: str | None = Field(default=None, min_length=1, max_length=255)
    departure_time: time | None = None
    profile: Literal["pedestrian"] = "pedestrian"
    preferences: list[RoutePreference] = Field(default_factory=list, max_length=20)

    @field_validator("departure_time")
    @classmethod
    def normalize_local_departure_time(cls, value: time | None) -> time | None:
        if value is None or value.tzinfo is None:
            return value
        return value.replace(tzinfo=None)

    @field_validator("preferences")
    @classmethod
    def reject_duplicate_intent_factors(
        cls,
        preferences: list[RoutePreference],
    ) -> list[RoutePreference]:
        factors = [preference.factor for preference in preferences]
        if len(factors) != len(set(factors)):
            raise ValueError("preference factors must be unique")
        reserved = {
            "departure_time",
            "profile",
            "origin",
            "destination",
            "origin_name",
            "destination_name",
            "source",
            "user_id",
            "stairs_weight",
            "intersection_weight",
            "crossing_weight",
        }
        invalid = reserved.intersection(factors)
        if invalid:
            raise ValueError(
                f"request fields cannot be route preference factors: {sorted(invalid)}"
            )
        return preferences


class NaturalLanguageQueryRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query: str = Field(min_length=1, max_length=1000)
    origin: AgentCoordinateInput | None = None
    destination: AgentCoordinateInput | None = None
    source: str | None = Field(default=None, min_length=1, max_length=32)
    user_id: str | None = Field(default=None, min_length=1, max_length=128)

    @model_validator(mode="after")
    def require_coordinate_pair(self) -> "NaturalLanguageQueryRequest":
        if (self.origin is None) != (self.destination is None):
            raise ValueError("origin and destination coordinates must be supplied together")
        return self


class ResolvedPlace(BaseModel):
    name: str
    category: str | None = None
    address: str | None = None
    source: str
    latitude: float
    longitude: float


class NaturalLanguageQueryResponse(BaseModel):
    query: str
    model: str
    interpretation: ParsedRouteIntent
    resolved_origin: ResolvedPlace | None = None
    resolved_destination: ResolvedPlace | None = None
    result: AgentExecutionResponse


class RouteSelectionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    recommendation_id: str = Field(min_length=36, max_length=36)
    user_id: str = Field(min_length=1, max_length=128)
    selected_route_type: Literal["shortest", "balanced", "safe", "custom"]


class LearnedRoutePreference(BaseModel):
    factor: str
    weight: float
    observations: int


class RouteSelectionResponse(BaseModel):
    recommendation_id: str
    selected_route_type: Literal["shortest", "balanced", "safe", "custom"]
    preferences: list[LearnedRoutePreference]
