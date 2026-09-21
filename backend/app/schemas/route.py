from typing import Literal

from pydantic import BaseModel, Field


class CoordinateInput(BaseModel):
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)


class RouteRequest(BaseModel):
    start: CoordinateInput
    end: CoordinateInput
    source: str | None = Field(default=None, min_length=1, max_length=32)


class GeoJSONLineString(BaseModel):
    type: Literal["LineString"]
    coordinates: list[list[float]]


class RouteRoadSegment(BaseModel):
    id: int
    source_id: str
    name: str | None
    from_node_id: int
    to_node_id: int
    distance_m: float
    streetlight_score: float
    cctv_score: float
    population_score: float
    safety_score: float
    streetlight_data_available: bool = True
    walkability_factor: float = 1.0
    crossing_node_ids: list[int] = Field(default_factory=list)
    is_steps: bool = False
    sidewalk_confirmed: bool = False
    incline_percent: float | None = None
    walkability_class: str | None = None
    field_status: str = "unverified"
    distance_factor: float
    risk_factor: float
    traversal_cost: float


class RouteCostWeights(BaseModel):
    distance: float
    risk: float


class RouteProperties(BaseModel):
    route_type: Literal["shortest", "balanced", "safe"]
    crs: Literal["EPSG:4326"]
    total_distance: float
    total_distance_m: float
    average_safety_score: float | None
    total_cost: float
    cost_weights: RouteCostWeights
    start_node_id: int
    end_node_id: int
    start_snap_distance_m: float
    end_snap_distance_m: float
    total_crosswalk_count: int = 0
    stairs_distance_m: float = 0
    sidewalk_coverage_percent: float = 0
    max_slope_percent: float | None = None
    slope_coverage_percent: float = 0
    review_status: Literal["needs_field_review", "map_data_only"] = "map_data_only"
    unverified_major_road_count: int = Field(default=0, ge=0)
    unverified_major_road_source_ids: list[str] = Field(default_factory=list)
    road_segments: list[RouteRoadSegment]


class RouteFeature(BaseModel):
    type: Literal["Feature"]
    geometry: GeoJSONLineString
    properties: RouteProperties
