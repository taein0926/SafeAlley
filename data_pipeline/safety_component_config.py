from dataclasses import dataclass
import os


def _float(name: str, default: str) -> float:
    return float(os.getenv(name, default))


@dataclass(frozen=True)
class SafetyComponentConfig:
    cctv_search_radius_m: float
    cctv_sample_interval_m: float
    cctv_candidate_search_radius_m: float
    cctv_distance_weight: float
    cctv_density_weight: float
    cctv_gap_weight: float
    safety_streetlight_weight: float
    safety_cctv_weight: float
    safety_help_point_weight: float

    @classmethod
    def from_environment(cls) -> "SafetyComponentConfig":
        config = cls(
            cctv_search_radius_m=_float("CCTV_SEARCH_RADIUS_M", "30"),
            cctv_sample_interval_m=_float("CCTV_SAMPLE_INTERVAL_M", "5"),
            cctv_candidate_search_radius_m=_float(
                "CCTV_CANDIDATE_SEARCH_RADIUS_M", "500"
            ),
            cctv_distance_weight=_float("CCTV_DISTANCE_WEIGHT", "0.4"),
            cctv_density_weight=_float("CCTV_DENSITY_WEIGHT", "0.3"),
            cctv_gap_weight=_float("CCTV_GAP_WEIGHT", "0.3"),
            safety_streetlight_weight=_float(
                "SAFETY_STREETLIGHT_WEIGHT", "0.4"
            ),
            safety_cctv_weight=_float("SAFETY_CCTV_WEIGHT", "0.4"),
            safety_help_point_weight=_float(
                "SAFETY_HELP_POINT_WEIGHT", "0.2"
            ),
        )
        if min(
            config.cctv_search_radius_m,
            config.cctv_sample_interval_m,
            config.cctv_candidate_search_radius_m,
        ) <= 0:
            raise ValueError("CCTV distance parameters must be positive")
        component_weights = (
            config.cctv_distance_weight,
            config.cctv_density_weight,
            config.cctv_gap_weight,
        )
        safety_weights = (
            config.safety_streetlight_weight,
            config.safety_cctv_weight,
            config.safety_help_point_weight,
        )
        if min(*component_weights, *safety_weights) < 0:
            raise ValueError("Safety weights cannot be negative")
        if abs(sum(component_weights) - 1.0) > 1e-9:
            raise ValueError("CCTV component weights must add up to 1.0")
        if abs(sum(safety_weights) - 1.0) > 1e-9:
            raise ValueError("Composite safety weights must add up to 1.0")
        return config
