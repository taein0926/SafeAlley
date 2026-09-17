from dataclasses import dataclass
import os


@dataclass(frozen=True)
class StreetlightAnalysisConfig:
    segment_length_m: float
    search_radius_m: float
    sample_interval_m: float
    candidate_search_radius_m: float
    distance_weight: float
    density_weight: float
    gap_weight: float

    @classmethod
    def from_environment(cls) -> "StreetlightAnalysisConfig":
        config = cls(
            segment_length_m=float(
                os.getenv("STREETLIGHT_SEGMENT_LENGTH_M", "20")
            ),
            search_radius_m=float(
                os.getenv("STREETLIGHT_SEARCH_RADIUS_M", "30")
            ),
            sample_interval_m=float(
                os.getenv("STREETLIGHT_SAMPLE_INTERVAL_M", "5")
            ),
            candidate_search_radius_m=float(
                os.getenv("STREETLIGHT_CANDIDATE_SEARCH_RADIUS_M", "500")
            ),
            distance_weight=float(
                os.getenv("STREETLIGHT_DISTANCE_WEIGHT", "0.4")
            ),
            density_weight=float(
                os.getenv("STREETLIGHT_DENSITY_WEIGHT", "0.3")
            ),
            gap_weight=float(os.getenv("STREETLIGHT_GAP_WEIGHT", "0.3")),
        )
        if min(
            config.segment_length_m,
            config.search_radius_m,
            config.sample_interval_m,
            config.candidate_search_radius_m,
        ) <= 0:
            raise ValueError("Streetlight distance parameters must be positive")
        if min(
            config.distance_weight,
            config.density_weight,
            config.gap_weight,
        ) < 0:
            raise ValueError("Streetlight safety weights cannot be negative")
        if abs(config.total_weight - 1.0) > 1e-9:
            raise ValueError("Streetlight safety weights must add up to 1.0")
        return config

    @property
    def total_weight(self) -> float:
        return self.distance_weight + self.density_weight + self.gap_weight

    @property
    def analysis_version(self) -> str:
        return (
            "sl-v1:"
            f"s{self.segment_length_m:g};"
            f"r{self.search_radius_m:g};"
            f"i{self.sample_interval_m:g};"
            f"w{self.distance_weight:g},"
            f"{self.density_weight:g},{self.gap_weight:g}"
        )
