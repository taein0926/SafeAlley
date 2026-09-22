from dataclasses import dataclass

from app.services.routing.graph import GraphEdge


MAX_STAIRS_PENALTY_MULTIPLIER = 2.0
MAX_INTERSECTION_PENALTY_MULTIPLIER = 4.0


@dataclass(frozen=True)
class SafetyCostBreakdown:
    distance_factor: float
    risk_factor: float
    stairs_penalty: float
    intersection_penalty: float = 0.0

    @property
    def total(self) -> float:
        return self.distance_factor + self.risk_factor + self.stairs_penalty + self.intersection_penalty


@dataclass(frozen=True)
class SafetyCostPolicy:
    distance_weight: float
    risk_weight: float
    stairs_weight: float = 0.0
    intersection_weight: float = 0.0

    def __post_init__(self) -> None:
        if self.distance_weight <= 0:
            raise ValueError("Distance weight must be greater than zero")
        if self.risk_weight < 0:
            raise ValueError("Risk weight cannot be negative")
        if not 0.0 <= self.stairs_weight <= 1.0:
            raise ValueError("Stairs weight must be between zero and one")
        if not 0.0 <= self.intersection_weight <= 1.0:
            raise ValueError("Intersection weight must be between zero and one")

    def breakdown(self, edge: GraphEdge) -> SafetyCostBreakdown:
        normalized_risk = (100.0 - edge.safety_score) / 100.0
        return SafetyCostBreakdown(
            distance_factor=edge.distance_m * self.distance_weight,
            risk_factor=edge.distance_m * normalized_risk * self.risk_weight,
            stairs_penalty=(
                edge.distance_m
                * self.stairs_weight
                * MAX_STAIRS_PENALTY_MULTIPLIER
                if edge.is_steps
                else 0.0
            ),
            intersection_penalty=(
                min(edge.distance_m, max(0.0, edge.intersection_exposure_m))
                * self.intersection_weight * MAX_INTERSECTION_PENALTY_MULTIPLIER
                if not edge.grade_separated else 0.0
            ),
        )

    def edge_cost(self, edge: GraphEdge) -> float:
        return self.breakdown(edge).total
