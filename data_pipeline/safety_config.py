from dataclasses import dataclass
import os


@dataclass(frozen=True)
class SafetyScoreWeights:
    streetlight: float
    cctv: float
    population: float

    @classmethod
    def from_environment(cls) -> "SafetyScoreWeights":
        weights = cls(
            streetlight=float(os.environ["SAFETY_STREETLIGHT_WEIGHT"]),
            cctv=float(os.environ["SAFETY_CCTV_WEIGHT"]),
            population=float(os.environ["SAFETY_POPULATION_WEIGHT"]),
        )
        if min(weights.streetlight, weights.cctv, weights.population) < 0:
            raise ValueError("Safety score weights cannot be negative")
        if weights.total <= 0:
            raise ValueError("At least one safety score weight must be positive")
        return weights

    @property
    def total(self) -> float:
        return self.streetlight + self.cctv + self.population

    def calculate(self, streetlight: float, cctv: float, population: float) -> float:
        return (
            self.streetlight * streetlight
            + self.cctv * cctv
            + self.population * population
        ) / self.total
