import type {
  AgentExecutionResponse,
  ResolvedPlace,
  RouteCandidate,
  RouteType,
} from "./types";

export type DirectSearchWeights = {
  safety: number;
  stairs: number;
  intersection?: number;
};

export type DirectLocationInput = {
  displayName: string;
  source: "text" | "map";
  latitude?: number;
  longitude?: number;
  category?: string;
  address?: string | null;
};

export function helpPointRouteLocation(
  properties: Record<string, unknown>,
  coordinates: readonly number[],
): DirectLocationInput | null {
  const [longitude, latitude] = coordinates;
  if (!Number.isFinite(latitude) || !Number.isFinite(longitude) ||
      Math.abs(latitude) > 90 || Math.abs(longitude) > 180) return null;
  const name = typeof properties.name === "string" ? properties.name.trim() : "";
  const address = typeof properties.address === "string" ? properties.address.trim() : "";
  return {
    displayName: name || address || "안전지원시설",
    source: "map",
    latitude,
    longitude,
    category: typeof properties.category === "string" ? properties.category : "help_point",
    address: address || null,
  };
}

export type BuildingMapSelection = {
  displayName: string | null;
  address: string | null;
  latitude: number;
  longitude: number;
};

export async function resolveBuildingLocation(
  selection: BuildingMapSelection,
  reverseResolver: (latitude: number, longitude: number) => Promise<ResolvedPlace>,
): Promise<DirectLocationInput> {
  const { latitude, longitude } = selection;
  if (!Number.isFinite(latitude) || !Number.isFinite(longitude) ||
      Math.abs(latitude) > 90 || Math.abs(longitude) > 180) {
    throw new Error("건물 위치를 확인하지 못했습니다. 다시 선택해주세요.");
  }
  let displayName = selection.displayName?.trim() || selection.address?.trim();
  if (!displayName) {
    const reversed = await reverseResolver(latitude, longitude);
    displayName = reversed.address?.trim() || reversed.name;
  }
  // Reverse lookup supplies only a label; route requests retain the clicked location.
  return { displayName, latitude, longitude, source: "map" };
}

export type RouteSearchResult = {
  mode: "direct" | "ai";
  origin: ResolvedPlace | null;
  destination: ResolvedPlace | null;
  model: string | null;
  departureTime: string | null;
  result: AgentExecutionResponse;
};

export type DisplayedRouteCandidate = {
  candidate: RouteCandidate;
  label: "추천 경로" | "최단 경로" | "안전 경로";
};

export function sliderToUnit(value: number): number {
  return Math.min(100, Math.max(0, value)) / 100;
}

export function currentLocalTime(now = new Date()): string {
  return `${String(now.getHours()).padStart(2, "0")}:${String(now.getMinutes()).padStart(2, "0")}`;
}

export const WALKING_SPEED_MPS = 1.2;

// Display-only estimate, excluding traffic signals and individual walking pace.
export function estimatedWalkingMinutes(distanceM: number): number | null {
  if (!Number.isFinite(distanceM) || distanceM < 0) return null;
  return Math.ceil(distanceM / (WALKING_SPEED_MPS * 60));
}

export function isValidDepartureTime(value: string): boolean {
  return /^([01]\d|2[0-3]):[0-5]\d$/.test(value);
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
      category: location.category ?? "building",
      address: location.address ?? location.displayName,
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
  departureTime: string | null = null,
) {
  if (departureTime !== null && !isValidDepartureTime(departureTime)) {
    throw new Error("출발 시간을 올바르게 설정해주세요.");
  }
  const safety = Math.min(100, Math.max(0, weights.safety));
  const distance = 100 - safety;
  const preferences = [];

  if (distance > 0) {
    preferences.push({ factor: "distance_m", direction: "minimize", weight: distance });
  }
  if (safety > 0) {
    preferences.push({ factor: "safety_score", direction: "maximize", weight: safety });
  }
  const intersection = sliderToUnit(weights.intersection ?? 0);
  if (intersection > 0) {
    preferences.push({ factor: "intersection_distance_m", direction: "minimize", weight: intersection * 100 });
  }

  return {
    tool: "rank_routes",
    arguments: {
      origin: { latitude: origin.latitude, longitude: origin.longitude },
      destination: { latitude: destination.latitude, longitude: destination.longitude },
      profile: "pedestrian",
      source: "osm",
      user_id: userId,
      departure_time: departureTime,
      stairs_weight: sliderToUnit(weights.stairs),
      intersection_weight: intersection,
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
