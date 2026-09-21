export type RouteType = "shortest" | "balanced" | "safe";

export type RouteGeometry = {
  type: "LineString";
  coordinates: number[][];
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
      total_crosswalk_count: number;
      stairs_distance_m: number;
      sidewalk_coverage_percent: number;
      max_slope_percent: number | null;
      slope_coverage_percent: number;
      review_status: "needs_field_review" | "map_data_only";
      unverified_major_road_count: number;
      unverified_major_road_source_ids: string[];
      [key: string]: unknown;
    };
  };
};

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
  resolved_origin: {
    name: string;
    category: string | null;
    address: string | null;
    source: string;
    latitude: number;
    longitude: number;
  } | null;
  resolved_destination: {
    name: string;
    category: string | null;
    address: string | null;
    source: string;
    latitude: number;
    longitude: number;
  } | null;
  result: {
    recommendation_id: string | null;
    selected_route_type: RouteType | null;
    recommendation_status: "ready" | "field_review_required" | "no_supported_preferences";
    candidates: RouteCandidate[];
    unsupported_preferences: Array<{ factor: string; reason: string }>;
  };
};
