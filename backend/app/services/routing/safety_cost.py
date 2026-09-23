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
    streetlight_included: bool = True
    cctv_weight: float = 0.40
    help_point_weight: float = 0.20

    def __post_init__(self) -> None:
        if self.distance_weight <= 0:
            raise ValueError("Distance weight must be greater than zero")
        if self.risk_weight < 0:
            raise ValueError("Risk weight cannot be negative")
        if not 0.0 <= self.stairs_weight <= 1.0:
            raise ValueError("Stairs weight must be between zero and one")
        if not 0.0 <= self.intersection_weight <= 1.0:
            raise ValueError("Intersection weight must be between zero and one")
        if not 0 <= self.cctv_weight <= 1 or not 0 <= self.help_point_weight <= 1:
            raise ValueError("Facility weights must be between zero and one")

    def effective_safety_score(self, edge: GraphEdge) -> float:
        if self.streetlight_included:
            return edge.safety_score
        # Preserve CCTV/help-facility proportions, normalized back to 0–100.
        # Do not edit the stored night score or mutate the shared route graph.
        total = self.cctv_weight + self.help_point_weight
        if total == 0:
            return 0.0
        return min(100.0, max(0.0, (
            edge.cctv_score * self.cctv_weight + edge.help_point_score * self.help_point_weight
        ) / total))

    def breakdown(self, edge: GraphEdge) -> SafetyCostBreakdown:
        normalized_risk = (100.0 - self.effective_safety_score(edge)) / 100.0
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
