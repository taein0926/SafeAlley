export type RouteType = "shortest" | "balanced" | "safe";

export type RouteGeometry = {
  type: "LineString";
  coordinates: number[][];
};

export type RouteRoadSegment = {
  id: number;
  source_id: string;
  name: string | null;
  distance_m: number;
  streetlight_score: number;
  cctv_score: number;
  population_score: number;
  safety_score: number;
  coordinates: number[][];
  highway: string | null;
  is_steps: boolean;
  nearby_light_count?: number;
  nearby_cctv_count?: number;
  nearby_help_point_count?: number;
  [key: string]: unknown;
};

export type RouteCandidate = {
  route_type: RouteType;
  preference_score: number | null;
  metrics: Record<string, number | null>;
  route: {
    type: "Feature";
    geometry: RouteGeometry;
    properties: {
      route_type: RouteType;
      total_distance_m: number;
      average_safety_score: number | null;
      total_cost: number;
      stairs_segment_count: number;
      total_crosswalk_count: number;
      stairs_distance_m: number;
      intersection_distance_m?: number;
      pedestrian_bridge_count?: number;
      intersection_data_available?: boolean;
      intersection_detour_limited?: boolean;
      intersection_baseline_distance_m?: number | null;
      intersection_distance_limit_m?: number | null;
      sidewalk_coverage_percent: number;
      max_slope_percent: number | null;
      slope_coverage_percent: number;
      review_status: "needs_field_review" | "map_data_only";
      unverified_major_road_count: number;
      unverified_major_road_source_ids: string[];
      road_segments?: RouteRoadSegment[];
      [key: string]: unknown;
    };
  };
};

export type ResolvedPlace = {
  name: string;
  category: string | null;
  address: string | null;
  source: string;
  latitude: number;
  longitude: number;
};

export type AgentExecutionResponse = RouteQueryResponse["result"];

export type RouteQueryResponse = {
  query: string;
  model: string;
  interpretation: {
    origin_name: string | null;
    destination_name: string | null;
    departure_time: string | null;
    profile: "pedestrian";
    preferences: Array<{
      factor: string;
      direction: "maximize" | "minimize" | "avoid";
      weight: number;
    }>;
  };
  resolved_origin: ResolvedPlace | null;
  resolved_destination: ResolvedPlace | null;
  result: {
    recommendation_id: string | null;
    selected_route_type: RouteType | null;
    recommendation_status: "ready" | "field_review_required" | "no_supported_preferences";
    candidates: RouteCandidate[];
    unsupported_preferences: Array<{ factor: string; reason: string }>;
  };
};
