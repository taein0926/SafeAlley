import type {
  AgentExecutionResponse,
  ResolvedPlace,
  RouteCandidate,
  RouteType,
} from "./types";

export type DirectSearchWeights = {
  safety: number;
  stairs: number;
};

export type DirectLocationInput = {
  displayName: string;
  source: "text" | "map";
  latitude?: number;
  longitude?: number;
};

export type RouteSearchResult = {
  mode: "direct" | "ai";
  origin: ResolvedPlace | null;
  destination: ResolvedPlace | null;
  model: string | null;
  result: AgentExecutionResponse;
};

export type DisplayedRouteCandidate = {
  candidate: RouteCandidate;
  label: "추천 경로" | "최단 경로" | "안전 경로";
};

export function sliderToUnit(value: number): number {
  return Math.min(100, Math.max(0, value)) / 100;
}

export async function resolveDirectLocation(
  location: DirectLocationInput,
  textResolver: (name: string) => Promise<ResolvedPlace>,
): Promise<ResolvedPlace> {
  if (
    location.source === "map" &&
    typeof location.latitude === "number" &&
    typeof location.longitude === "number"
  ) {
    return {
      name: location.displayName,
      category: "building",
      address: location.displayName,
      source: "map",
      latitude: location.latitude,
      longitude: location.longitude,
    };
  }
  return textResolver(location.displayName);
}

export function buildDirectRouteToolCall(
  origin: ResolvedPlace,
  destination: ResolvedPlace,
  weights: DirectSearchWeights,
  userId: string,
) {
  const safety = Math.min(100, Math.max(0, weights.safety));
  const distance = 100 - safety;
  const preferences = [];

  if (distance > 0) {
    preferences.push({ factor: "distance_m", direction: "minimize", weight: distance });
  }
  if (safety > 0) {
    preferences.push({ factor: "safety_score", direction: "maximize", weight: safety });
  }

  return {
    tool: "rank_routes",
    arguments: {
      origin: { latitude: origin.latitude, longitude: origin.longitude },
      destination: { latitude: destination.latitude, longitude: destination.longitude },
      profile: "pedestrian",
      source: "osm",
      user_id: userId,
      stairs_weight: sliderToUnit(weights.stairs),
      preferences,
    },
  };
}

export function selectDisplayedCandidates(
  candidates: RouteCandidate[],
  recommendedType: RouteType | null,
): DisplayedRouteCandidate[] {
  const byType = new Map(candidates.map((candidate) => [candidate.route_type, candidate]));
  const recommended = recommendedType ? byType.get(recommendedType) : undefined;

  function identity(candidate: RouteCandidate): string {
    const segments = candidate.route.properties.road_segments;
    if (segments && segments.length > 0) {
      return `segments:${segments.map((segment) => segment.id).join(">")}`;
    }
    return `geometry:${JSON.stringify(candidate.route.geometry.coordinates)}`;
  }

  function unique(items: DisplayedRouteCandidate[]): DisplayedRouteCandidate[] {
    const identities = new Set<string>();
    return items.filter((item) => {
      const routeIdentity = identity(item.candidate);
      if (identities.has(routeIdentity)) return false;
      identities.add(routeIdentity);
      return true;
    });
  }

  if (!recommended) {
    return unique((["shortest", "safe"] as RouteType[])
      .map((type) => byType.get(type))
      .filter((candidate): candidate is RouteCandidate => candidate !== undefined)
      .map((candidate) => ({
        candidate,
        label: candidate.route_type === "shortest" ? "최단 경로" : "안전 경로",
      })));
  }

  const primary: DisplayedRouteCandidate = { candidate: recommended, label: "추천 경로" };
  const shortest = byType.get("shortest");
  if (shortest && identity(shortest) !== identity(recommended)) {
    return [primary, { candidate: shortest, label: "최단 경로" }];
  }

  const safe = byType.get("safe");
  return unique([
    primary,
    ...(safe ? [{ candidate: safe, label: "안전 경로" } as DisplayedRouteCandidate] : []),
  ]);
}
