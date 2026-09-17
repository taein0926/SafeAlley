from dataclasses import dataclass

from app.services.routing.graph import GraphEdge


@dataclass(frozen=True)
class SafetyCostBreakdown:
    distance_factor: float
    risk_factor: float

    @property
    def total(self) -> float:
        return self.distance_factor + self.risk_factor


@dataclass(frozen=True)
class SafetyCostPolicy:
    distance_weight: float
    risk_weight: float

    def __post_init__(self) -> None:
        if self.distance_weight <= 0:
            raise ValueError("Distance weight must be greater than zero")
        if self.risk_weight < 0:
            raise ValueError("Risk weight cannot be negative")

    def breakdown(self, edge: GraphEdge) -> SafetyCostBreakdown:
        normalized_risk = (100.0 - edge.safety_score) / 100.0
        return SafetyCostBreakdown(
            distance_factor=edge.distance_m * self.distance_weight,
            risk_factor=edge.distance_m * normalized_risk * self.risk_weight,
        )

    def edge_cost(self, edge: GraphEdge) -> float:
        return self.breakdown(edge).total
