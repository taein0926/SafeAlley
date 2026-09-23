from app.schemas.agent import RoutePreference, UnsupportedPreference
from app.services.route_ranking_service import _recommendation_factors
from types import SimpleNamespace


def test_factors_only_include_evaluated_supported_conditions():
    selected = {"metrics": {"distance_m": 300, "safety_score": 75, "cctv_score": 80, "stairs_distance_m": 0},
                "route": {"properties": {"intersection_data_available": True}}}
    preferences = [RoutePreference(factor=factor, direction=direction) for factor, direction in
                   [("distance_m", "minimize"), ("safety_score", "maximize"), ("cctv_score", "maximize"),
                    ("stairs_distance_m", "avoid"), ("max_slope_percent", "minimize")]]
    arguments = SimpleNamespace(stairs_weight=1, intersection_weight=1)
    assert _recommendation_factors(selected, preferences, [], arguments) == ["distance", "safety", "stairs", "intersection"]
    assert _recommendation_factors(None, preferences, [], arguments) == []


def test_unsupported_and_opposite_direction_are_not_badged_as_avoidance():
    selected = {"metrics": {"stairs_distance_m": 5, "safety_score": 70}, "route": {"properties": {}}}
    preferences = [RoutePreference(factor="stairs_distance_m", direction="maximize"),
                   RoutePreference(factor="safety_score", direction="maximize")]
    unsupported = [UnsupportedPreference(factor="safety_score", reason="unavailable")]
    assert _recommendation_factors(selected, preferences, unsupported, SimpleNamespace(stairs_weight=0, intersection_weight=1)) == []
